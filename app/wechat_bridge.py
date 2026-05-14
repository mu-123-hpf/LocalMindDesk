"""
LocalMindDesk — 微信频道（业务逻辑层）

基于 ilink_client.py 的平台无关 API 层构建。
本文件仅包含 LocalMindDesk 特有的业务逻辑：
  - 角色上下文注入
  - 访问控制（配对码 + 白名单）
  - Agent 路由 & 行动确认
  - Web 前端消息同步

参考: cc-weixin 分层架构 (github.com/qufei1993/cc-weixin)
"""
import asyncio
import os
import time
import logging
import urllib.parse
from collections import deque
from datetime import datetime
from typing import Optional

from app.ilink_client import (
    # 常量
    ITEM_TEXT, ITEM_IMAGE, ITEM_VIDEO, ITEM_VOICE, ITEM_FILE,
    MEDIA_IMAGE, MEDIA_VIDEO, MEDIA_FILE, MEDIA_VOICE,
    MSG_TYPE_USER, MSG_STATE_FINISH, MAX_MSG_LEN,
    EP_GET_UPDATES, EP_SEND_MESSAGE, EP_SEND_TYPING, EP_GET_UPLOAD_URL,
    LONG_POLL_TIMEOUT, API_TIMEOUT, DATA_DIR,
    # 数据类
    Credentials, QRState,
    # 工具函数
    ilink_post, extract_text, split_message,
    aes_128_ecb_encrypt, get_mime_type, get_media_item_type,
    build_text_payload, build_media_payload,
    _base_info,
    # 持久化
    load_credentials, save_credentials, delete_credentials,
    load_whitelist, save_whitelist,
    load_sync_buf, save_sync_buf,
    load_context_tokens, save_context_tokens,
    # QR 登录
    qr_login,
)
import httpx
import secrets
import hashlib
import base64
import json

logger = logging.getLogger("LocalMindDesk.wechat")

MAX_FAILURES = 3

# 微信简洁对话的降级提示（仅当 soul.md 不存在时使用）
_WECHAT_FALLBACK_PROMPT = (
    "你正在通过微信和用户聊天。\n"
    "请遵守以下规则：\n"
    "1. 回答要简洁，像朋友对话一样，不要写长篇大论\n"
    "2. 不要使用 markdown 格式（微信不支持渲染）\n"
    "3. 不要用标题、列表、代码块等格式\n"
    "4. 如果内容较多，分要点用数字编号，每点一句话\n"
    "5. 语气自然亲切，可以用 emoji\n"
    "6. 单次回复控制在 200 字以内"
)


def _load_wechat_context() -> str:
    """
    动态加载微信角色上下文（参考 NAVI 的 ContextBuilder）。
    按优先级加载：soul.md → user.md → skills/*.md
    如果 soul.md 不存在，降级使用 _WECHAT_FALLBACK_PROMPT。
    """
    parts = []

    # 1. 角色灵魂定义（soul.md）
    soul_path = os.path.join(DATA_DIR, "soul.md")
    if os.path.isfile(soul_path):
        try:
            with open(soul_path, "r", encoding="utf-8") as f:
                soul = f.read().strip()
            if soul:
                parts.append(f"[角色设定]:\n{soul}")
                logger.info(f"[WeChat] 已加载角色设定: {soul_path} ({len(soul)}字)")
        except Exception as e:
            logger.warning(f"[WeChat] soul.md 加载失败: {e}")
    else:
        # 没有自定义角色时，使用降级提示
        parts.append(f"[微信对话规则]:\n{_WECHAT_FALLBACK_PROMPT}")

    # 2. 用户画像（user.md）
    user_path = os.path.join(DATA_DIR, "user.md")
    if os.path.isfile(user_path):
        try:
            with open(user_path, "r", encoding="utf-8") as f:
                user_info = f.read().strip()
            if user_info:
                parts.append(f"[用户画像]:\n{user_info}")
                logger.info(f"[WeChat] 已加载用户画像: {user_path}")
        except Exception as e:
            logger.warning(f"[WeChat] user.md 加载失败: {e}")

    # 3. 微信专属技能（skills/*.md，每个文件一个技能）
    skills_dir = os.path.join(DATA_DIR, "skills")
    if os.path.isdir(skills_dir):
        skill_parts = []
        try:
            for fname in sorted(os.listdir(skills_dir)):
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(skills_dir, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    skill_name = fname.replace(".md", "")
                    skill_parts.append(f"### {skill_name}\n{content}")
            if skill_parts:
                parts.append(f"[微信专属技能]:\n" + "\n\n".join(skill_parts))
                logger.info(f"[WeChat] 已加载 {len(skill_parts)} 个微信技能")
        except Exception as e:
            logger.warning(f"[WeChat] skills 加载失败: {e}")

    return "\n\n".join(parts)


# ── 微信频道（业务逻辑层） ──────────────────────────────────────

class WeChatBridge:
    """
    微信 iLink Bot 桥接器
    长轮询收消息 → agent_router 处理 → iLink API 发回复
    """

    def __init__(self):
        self._token = ""
        self._account_id = ""
        self._base_url = "https://ilinkai.weixin.qq.com"
        self._owner_user_id = ""  # bot 主人的 user_id
        self._context_tokens: dict[str, str] = {}
        self._sync_buf = ""
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._session_map: dict[str, str] = {}  # wechat_user_id → LocalMindDesk session_id
        self._stats = {"received": 0, "replied": 0, "errors": 0}
        self._recent_messages: deque[dict] = deque(maxlen=50)  # 最近消息日志
        self._pending_confirm: dict[str, list] = {}  # user_id → 挂起的待确认操作
        # 访问控制
        self._whitelist: set = load_whitelist()
        self._pending_pair: dict[str, str] = {}  # user_id → 6位配对码


    @property
    def is_online(self) -> bool:
        return self._running and bool(self._token)

    @property
    def has_credentials(self) -> bool:
        return bool(load_credentials())

    # ── 启动/停止 ──────────────────────────────────────────────

    async def start(self) -> dict:
        """启动桥接（加载凭证 → 开始长轮询）"""
        creds = load_credentials()
        if not creds:
            return {"success": False, "error": "no credentials, need QR login first"}

        self._token = creds.token
        self._account_id = creds.account_id
        self._base_url = creds.base_url
        self._owner_user_id = creds.user_id
        self._context_tokens = load_context_tokens()
        # 自动把 bot 主人加入白名单
        if creds.user_id and creds.user_id not in self._whitelist:
            self._whitelist.add(creds.user_id)
            save_whitelist(self._whitelist)
        self._sync_buf = load_sync_buf()

        self._client = httpx.AsyncClient()
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())

        logger.info(f"[WeChat] started, account={self._account_id[:8]}***")
        return {"success": True, "message": "WeChat bridge started (iLink long-polling)"}

    async def start_with_credentials(self, creds: Credentials) -> dict:
        """QR 登录成功后用新凭证启动"""
        save_credentials(creds)
        self._token = creds.token
        self._account_id = creds.account_id
        self._base_url = creds.base_url
        self._owner_user_id = creds.user_id
        self._context_tokens = load_context_tokens()
        self._sync_buf = load_sync_buf()

        if not self._client:
            self._client = httpx.AsyncClient()
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())

        logger.info("[WeChat] started after QR login")
        return {"success": True, "message": "WeChat bridge started"}

    async def stop(self) -> dict:
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
            self._client = None
        save_context_tokens(self._context_tokens)
        save_sync_buf(self._sync_buf)
        logger.info("[WeChat] stopped")
        return {"success": True, "message": "WeChat bridge stopped"}

    async def logout(self) -> dict:
        await self.stop()
        delete_credentials()
        self._token = ""
        self._account_id = ""
        self._owner_user_id = ""
        return {"success": True, "message": "logged out, credentials cleared"}

    # ── 发送消息 ───────────────────────────────────────────────

    async def send_text(self, user_id: str, text: str):
        """发送文本到微信用户（自动分片）"""
        if not self._client or not self._token:
            raise RuntimeError("WeChat not connected")

        chunks = split_message(text)
        for i, chunk in enumerate(chunks):
            ctx_token = self._context_tokens.get(user_id, "")
            payload = {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": user_id,
                    "client_id": f"lmd-{int(time.time()*1000)}-{secrets.token_hex(4)}",
                    "message_type": 2,
                    "message_state": MSG_STATE_FINISH,
                    "context_token": ctx_token,
                    "item_list": [
                        {"type": ITEM_TEXT, "text_item": {"text": chunk}},
                    ],
                },
                "base_info": _base_info(),
            }
            resp = await ilink_post(
                self._client, self._base_url, EP_SEND_MESSAGE, payload, self._token,
            )
            ret = resp.get("ret", 0)
            if ret != 0:
                errmsg = resp.get("errmsg") or resp.get("err_msg") or str(resp)[:200]
                raise RuntimeError(f"sendmessage failed ret={ret}: {errmsg}")
            if len(chunks) > 1 and i < len(chunks) - 1:
                await asyncio.sleep(0.35)

    def send_text_sync(self, user_id: str, text: str):
        """同步版发送文本（供 scheduler 子线程调用，不依赖 event loop）"""
        if not self._token:
            raise RuntimeError("WeChat not connected")

        chunks = split_message(text)
        with httpx.Client(timeout=API_TIMEOUT) as client:
            for i, chunk in enumerate(chunks):
                ctx_token = self._context_tokens.get(user_id, "")
                payload = {
                    "msg": {
                        "from_user_id": "",
                        "to_user_id": user_id,
                        "client_id": f"lmd-{int(time.time()*1000)}-{secrets.token_hex(4)}",
                        "message_type": 2,
                        "message_state": MSG_STATE_FINISH,
                        "context_token": ctx_token,
                        "item_list": [
                            {"type": ITEM_TEXT, "text_item": {"text": chunk}},
                        ],
                    },
                    "base_info": _base_info(),
                }
                url = f"{self._base_url.rstrip('/')}/{EP_SEND_MESSAGE.lstrip('/')}"
                body = json.dumps(payload).encode("utf-8")
                resp = client.post(
                    url, content=body,
                    headers=_build_headers(self._token, body),
                    timeout=API_TIMEOUT,
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                data = resp.json()
                ret = data.get("ret", 0)
                if ret != 0:
                    errmsg = data.get("errmsg") or data.get("err_msg") or str(data)[:200]
                    raise RuntimeError(f"sendmessage failed ret={ret}: {errmsg}")
                if len(chunks) > 1 and i < len(chunks) - 1:
                    time.sleep(0.35)

    async def send_media(self, user_id: str, file_path: str, caption: str = ""):
        """
        上传并发送媒体文件（图片/视频/文件）到微信用户。
        参考 NAVI 项目的 iLink 上传流程：
          1. 客户端生成随机 AES-128 key 和 filekey
          2. AES-128-ECB 加密文件
          3. 调用 getuploadurl 获取 CDN 地址
          4. POST 加密数据到 CDN
          5. 从 CDN 响应头 x-encrypted-param 获取 encrypt_query_param
          6. sendmessage 携带 encrypt_query_param + aes_key + encrypt_type=1
        """
        if not self._client or not self._token:
            raise RuntimeError("WeChat not connected")

        mime = get_mime_type(file_path)
        media_type, item_type = get_media_item_type(mime)

        with open(file_path, "rb") as f:
            file_data = f.read()
        raw_size = len(file_data)
        raw_md5 = hashlib.md5(file_data).hexdigest()
        file_name = os.path.basename(file_path)

        # Step 1: 生成随机密钥
        aes_key = secrets.token_bytes(16)      # 16字节 AES key
        file_key = secrets.token_hex(16)       # 32字符 hex filekey

        # Step 2: AES-128-ECB 加密
        encrypted = aes_128_ecb_encrypt(file_data, aes_key)
        enc_size = len(encrypted)
        logger.info(f"[WeChat] 文件加密: {file_name} raw={raw_size}B enc={enc_size}B")

        # Step 3: 获取上传 URL
        up_resp = await ilink_post(
            self._client, self._base_url, EP_GET_UPLOAD_URL,
            {
                "to_user_id": user_id,
                "media_type": media_type,
                "filekey": file_key,
                "rawsize": raw_size,
                "rawfilemd5": raw_md5,
                "filesize": enc_size,
                "aeskey": aes_key.hex(),
                "base_info": _base_info(),
            },
            self._token,
        )
        upload_param = up_resp.get("upload_param", "") or up_resp.get("upload_full_url", "")
        if not upload_param:
            raise RuntimeError(f"[WeChat] getuploadurl failed: {up_resp}")

        # Step 4: POST 加密数据到 CDN
        if upload_param.startswith("http"):
            cdn_url = upload_param
        else:
            enc_param = urllib.parse.quote(upload_param)
            enc_fkey = urllib.parse.quote(file_key)
            cdn_url = (
                f"https://novac2c.cdn.weixin.qq.com/c2c/upload"
                f"?encrypted_query_param={enc_param}&filekey={enc_fkey}"
            )
        logger.info(f"[WeChat] 上传到 CDN: {cdn_url[:80]}...")
        cdn_resp = await self._client.post(
            cdn_url,
            content=encrypted,
            headers={"Content-Type": "application/octet-stream"},
            timeout=120,
        )
        cdn_resp.raise_for_status()

        # Step 5: 从响应头拿 encrypt_query_param
        encrypt_query_param = cdn_resp.headers.get("x-encrypted-param", "")
        if not encrypt_query_param:
            raise RuntimeError(
                f"[WeChat] CDN missing x-encrypted-param: {cdn_resp.text[:200]}"
            )
        aes_key_b64 = base64.b64encode(aes_key.hex().encode()).decode()

        # Step 6: 构造 item_list 发送消息
        media_block = {
            "encrypt_query_param": encrypt_query_param,
            "aes_key": aes_key_b64,
            "encrypt_type": 1,
        }
        if item_type == ITEM_IMAGE:
            item = {"type": ITEM_IMAGE, "image_item": {"media": media_block, "mid_size": enc_size}}
        elif item_type == ITEM_VIDEO:
            item = {"type": ITEM_VIDEO, "video_item": {"media": media_block, "video_size": enc_size}}
        elif item_type == ITEM_VOICE:
            item = {"type": ITEM_VOICE, "voice_item": {"media": media_block, "voice_size": enc_size}}
        else:
            item = {"type": ITEM_FILE, "file_item": {
                "media": media_block, "file_size": enc_size, "file_name": file_name,
            }}

        item_list = [item]
        if caption:
            item_list.append({"type": ITEM_TEXT, "text_item": {"text": caption}})

        ctx_token = self._context_tokens.get(user_id, "")
        payload = {
            "msg": {
                "from_user_id": "",
                "to_user_id": user_id,
                "client_id": f"lmd-{int(time.time()*1000)}-{secrets.token_hex(4)}",
                "message_type": 2,
                "message_state": MSG_STATE_FINISH,
                "context_token": ctx_token,
                "item_list": item_list,
            },
            "base_info": _base_info(),
        }
        await ilink_post(self._client, self._base_url, EP_SEND_MESSAGE, payload, self._token)
        logger.info(f"[WeChat] 媒体已发送: {file_name} → {user_id[:8]}***")

    async def send_typing(self, user_id: str, typing: bool):
        if not self._client or not self._token:
            return
        try:
            await ilink_post(
                self._client, self._base_url, EP_SEND_TYPING,
                {"to_user_id": user_id, "typing": 1 if typing else 2, "base_info": _base_info()},
                self._token, 5,
            )
        except Exception:
            pass

    # ── 长轮询主循环 ───────────────────────────────────────────

    async def _poll_loop(self):
        failures = 0
        while self._running:
            try:
                resp = await ilink_post(
                    self._client, self._base_url, EP_GET_UPDATES,
                    {"get_updates_buf": self._sync_buf, "base_info": _base_info()},
                    self._token, LONG_POLL_TIMEOUT + 5,
                )

                ret = resp.get("ret", 0)
                if ret == 0 or "msgs" in resp:
                    failures = 0
                    self._sync_buf = resp.get("get_updates_buf", self._sync_buf)
                    save_sync_buf(self._sync_buf)

                    msgs = resp.get("msgs", [])
                    if msgs:
                        logger.info(f"[WeChat] received {len(msgs)} messages")
                        for msg in msgs:
                            try:
                                await self._handle_message(msg)
                            except Exception as e:
                                logger.error(f"[WeChat] handle error: {e}")
                                self._stats["errors"] += 1
                else:
                    logger.warning(f"[WeChat] getupdates error ret={ret}")
                    failures += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[WeChat] poll error: {e}")
                failures += 1

            if failures >= MAX_FAILURES:
                logger.error("[WeChat] too many failures, pause 30s")
                await asyncio.sleep(30)
                failures = 0
            elif failures > 0:
                await asyncio.sleep(2)

    # ── 消息处理 ───────────────────────────────────────────────

    async def _handle_message(self, msg: dict):
        """收到微信消息 → 路由到 Agent → 回复"""
        # ── 防回环过滤 ──────────────────────────────────────
        # 1. 只处理用户发来的消息（type=1），跳过 bot 自己发的（type=2）
        if msg.get("message_type") != MSG_TYPE_USER:
            return
        if msg.get("message_state") != MSG_STATE_FINISH:
            return

        from_user = msg.get("from_user_id", "")
        ctx_token = msg.get("context_token", "")
        text = extract_text(msg)

        if not text:
            return

        # 2. 跳过 bot 自己的消息（防止自己回复自己）
        if from_user == self._account_id:
            return

        # 3. 消息去重（用 client_id 防止同一条消息处理两次）
        client_id = msg.get("client_id", "")
        if client_id:
            if not hasattr(self, "_processed_ids"):
                self._processed_ids = set()
            if client_id in self._processed_ids:
                return
            self._processed_ids.add(client_id)
            # 只保留最近 200 个，防止内存泄漏
            if len(self._processed_ids) > 200:
                self._processed_ids = set(list(self._processed_ids)[-100:])

        # 4. 速率限制：同一用户 3 秒内不重复回复
        now = time.time()
        if not hasattr(self, "_last_reply_time"):
            self._last_reply_time = {}
        last_time = self._last_reply_time.get(from_user, 0)
        if now - last_time < 3:
            logger.info(f"[WeChat] rate limit: skip msg from {from_user[:8]}***")
            return
        self._last_reply_time[from_user] = now

        # 更新 context token
        if ctx_token:
            self._context_tokens[from_user] = ctx_token
            save_context_tokens(self._context_tokens)

        self._stats["received"] += 1
        logger.info(f"[WeChat] msg from {from_user[:8]}***: {text[:50]}")

        # ── 访问控制门控 ─────────────────────────────────────
        # bot 主人自动放行
        if from_user == self._owner_user_id:
            if from_user not in self._whitelist:
                self._whitelist.add(from_user)
                save_whitelist(self._whitelist)
        # 已授权用户放行
        elif from_user not in self._whitelist:
            # 检查是否在回复配对码
            if from_user in self._pending_pair:
                if text.strip() == self._pending_pair[from_user]:
                    self._whitelist.add(from_user)
                    save_whitelist(self._whitelist)
                    del self._pending_pair[from_user]
                    await self.send_text(from_user, "✅ 验证通过！现在可以和我聊天了 😊")
                    return
                else:
                    await self.send_text(from_user, "❌ 配对码错误，请重新输入")
                    return
            # 首次消息：生成配对码
            import random
            code = f"{random.randint(100000, 999999)}"
            self._pending_pair[from_user] = code
            await self.send_text(
                from_user,
                f"🔐 访问验证\n\n"
                f"请输入配对码：{code}\n\n"
                f"（在 LocalMindDesk 控制台也可查看此配对码）"
            )
            logger.info(f"[WeChat] 访问控制: {from_user[:8]}*** 需要验证，配对码: {code}")
            return

        # 记录到最近消息
        self._recent_messages.append({
            "time": datetime.now().isoformat(),
            "from": from_user[:8] + "***",
            "text": text[:100],
            "direction": "in",
        })

        # 发送 typing
        await self.send_typing(from_user, True)

        try:
            # ★ 检查是否是确认操作（用户回复“确认/好的/执行/yes”等）
            confirm_words = {"确认", "好的", "执行", "同意", "yes", "ok", "是", "要", "行", "可以", "没问题", "y"}
            if text.strip().lower() in confirm_words and from_user in self._pending_confirm:
                pending = self._pending_confirm.pop(from_user)
                await self._execute_pending_actions(from_user, pending)
                return

            # 取消词检测
            cancel_words = {"取消", "不要", "算了", "不执行", "no", "cancel"}
            if text.strip().lower() in cancel_words and from_user in self._pending_confirm:
                self._pending_confirm.pop(from_user)
                await self.send_text(from_user, "✅ 已取消操作")
                return

            # ★ 角色纠正检测（用户说"她不会这样说"等触发 evolve_correct）
            import re as _re
            correction_patterns = [
                r"(?:她|他|你)不会(?:这样|这么|那样)(?:说|讲|回答|回复)",
                r"(?:这|那)不像(?:她|他)",
                r"(?:她|他)(?:的)?(?:语气|风格|性格)不对",
                r"(?:她|他)说话没(?:这么|那么)",
                r"纠正[:：]",
            ]
            correction_match = any(_re.search(p, text) for p in correction_patterns)
            if correction_match:
                try:
                    from app.soul_manager import get_soul_manager
                    from app.distill_engine import get_distill_engine
                    sm = get_soul_manager()
                    if sm.has_soul and sm._active_slug:
                        slug = sm._active_slug
                        await self.send_text(from_user, f"✏️ 收到纠正反馈，正在修正角色...")
                        result = get_distill_engine().evolve_correct(slug, text)
                        if result.get("success"):
                            await self.send_text(from_user, f"✅ 角色已纠正！\n反馈: {text[:50]}")
                        else:
                            await self.send_text(from_user, f"⚠️ 纠正失败: {result.get('error','')}")
                        return
                except Exception as e:
                    logger.warning(f"[WeChat] 纠正检测异常: {e}")

            # ★ 远程操作命令检测 (Phase 5.2)
            try:
                from app.remote_ops import detect_remote_command, execute_remote_op
                remote_cmd = detect_remote_command(text)
                if remote_cmd:
                    op = remote_cmd["op"]
                    param = remote_cmd.get("param", "")
                    logger.info(f"[WeChat] 远程操作: {op} param={param[:30]}")

                    if remote_cmd.get("needs_confirm"):
                        # 需要二次确认的操作
                        self._pending_confirm[from_user] = [{
                            "tool": f"remote:{op}",
                            "params": {"op": op, "param": param},
                        }]
                        desc = {
                            "run_cmd": f"🖥 执行命令: {param[:100]}",
                            "open_file": f"📂 打开文件: {param[:100]}",
                            "power": "⚡ 关机/重启",
                        }.get(op, f"🔧 {op}: {param[:50]}")
                        await self.send_text(from_user, f"⚠️ 即将执行远程操作:\n{desc}")
                        await self.send_text(from_user, "👆 回复「确认」执行，回复「取消」放弃")
                        return
                    else:
                        # 无需确认，直接执行
                        await self.send_text(from_user, f"⏳ 正在执行: {op}...")
                        import asyncio as _aio
                        loop = _aio.get_event_loop()
                        result = await loop.run_in_executor(
                            None, lambda: execute_remote_op(op, param)
                        )
                        msg = result.get("message", "")
                        if msg:
                            await self.send_text(from_user, msg)
                        # 如果有文件（截图等），发送
                        fpath = result.get("file_path")
                        if fpath and os.path.isfile(fpath):
                            try:
                                await self.send_media(from_user, fpath)
                            except Exception as me:
                                logger.warning(f"[WeChat] 远程截图发送失败: {me}")
                                await self.send_text(from_user, f"📎 文件已生成但发送失败: {os.path.basename(fpath)}")
                        self._stats["replied"] += 1
                        return
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"[WeChat] 远程操作检测异常: {e}")

            # 正常路由到 Agent
            result = await self._route_to_agent(from_user, text)
            reply = result.get("reply", "")
            file_path = result.get("file_path", "")
            action_confirm = result.get("action_confirm")

            if reply:
                # 发送回复到微信
                try:
                    await self.send_text(from_user, reply)
                    self._stats["replied"] += 1
                except Exception as send_err:
                    logger.error(f"[WeChat] send_text failed: {send_err!r}")
                    try:
                        await self.send_text(from_user, reply[:500])
                    except Exception:
                        pass

            # ★ 如果有待确认的操作，缓存并提示用户
            if action_confirm:
                self._pending_confirm[from_user] = action_confirm
                await self.send_text(from_user, "👆 回复「确认」执行以上操作，回复「取消」放弃")

            # 如果有文件（截图等），直接以图片/文件形式发到微信
            if file_path and os.path.isfile(file_path):
                fname = os.path.basename(file_path)
                try:
                    await self.send_media(from_user, file_path, caption=f"📎 {fname}")
                    logger.info(f"[WeChat] 媒体已发送: {file_path}")
                except Exception as media_err:
                    logger.error(f"[WeChat] send_media failed: {media_err!r}, fallback to link")
                    # 降级：发下载链接
                    dl_url = f"http://localhost:8000/api/file/download?path={urllib.parse.quote(file_path)}"
                    await self.send_text(from_user, f"📎 文件已生成: {fname}\n🔗 下载: {dl_url}")

            self._recent_messages.append({
                "time": datetime.now().isoformat(),
                "to": from_user[:8] + "***",
                "text": (reply or "(file)")[:100],
                "direction": "out",
            })
            if reply:
                logger.info(f"[WeChat] replied: {reply[:50]}")

        except Exception as e:
            import traceback
            error_msg = f"处理失败: {repr(e)[:100]}"
            logger.error(f"[WeChat] handle error: {repr(e)}\n{traceback.format_exc()}")
            try:
                await self.send_text(from_user, error_msg)
            except Exception:
                pass
        finally:
            await self.send_typing(from_user, False)

    async def _execute_pending_actions(self, user_id: str, pending: list):
        """执行微信用户确认的挂起操作"""
        import asyncio
        from app.action_engine import execute_action

        await self.send_text(user_id, "⏳ 正在执行...")

        results = []
        for p in pending:
            tool = p.get("tool", "")
            params = p.get("params", {})
            try:
                # ★ 远程操作（remote:xxx）
                if tool.startswith("remote:"):
                    from app.remote_ops import execute_remote_op
                    op = params.get("op", tool.replace("remote:", ""))
                    param = params.get("param", "")
                    result = await loop.run_in_executor(
                        None, lambda o=op, pr=param: execute_remote_op(o, pr)
                    )
                    msg = result.get("message", "")
                    if msg:
                        results.append(f"✓ {op}: {msg[:200]}")
                    else:
                        results.append(f"✓ {op}: 完成")
                    # 文件（截图等）
                    fpath = result.get("file_path")
                    if fpath and os.path.isfile(fpath):
                        try:
                            await self.send_media(user_id, fpath)
                        except Exception:
                            pass
                else:
                    # 常规 action_engine 操作
                    result = await loop.run_in_executor(
                        None, lambda t=tool, pr=params: execute_action(t, pr)
                    )
                    if result.get("success"):
                        msg = result.get("message", "成功")[:200]
                        results.append(f"✓ {tool}: {msg}")
                        # 如果有文件生成，发送
                        if result.get("path") and os.path.isfile(result["path"]):
                            try:
                                await self.send_media(user_id, result["path"])
                            except Exception:
                                pass
                    else:
                        results.append(f"✗ {tool}: {result.get('error', '失败')}")
            except Exception as e:
                results.append(f"✗ {tool}: {str(e)[:100]}")

        reply = "✅ **操作完成：**\n" + "\n".join(results) if results else "⚠️ 无操作执行"
        await self.send_text(user_id, reply)

        self._recent_messages.append({
            "time": datetime.now().isoformat(),
            "to": user_id[:8] + "***",
            "text": reply[:100],
            "direction": "out",
        })

    async def _route_to_agent(self, sender: str, text: str) -> dict:
        """转发到 agent_router，返回完整结果 dict（含 reply, file_path 等）"""
        import asyncio
        from app import agent_router, memory
        from app.config import get_config

        # 获取或创建 session
        if sender not in self._session_map:
            sid = memory.create_session()
            self._session_map[sender] = sid
        session_id = self._session_map[sender]

        # 存储用户消息
        memory.add_message(session_id, "user", text)

        # 获取历史
        msgs = memory.get_session_messages(session_id)
        history = [{"role": m["role"], "content": m["content"]} for m in msgs[-10:]]

        # route() 是同步函数，必须在线程池中运行，否则会阻塞事件循环
        cfg = get_config()

        # 组装完整 prompt：全局基础 + 微信角色模块（soul/user/skills）
        prompt = cfg.system_prompt

        # ★ v2.0: 优先使用 SoulManager 统一角色（PC/微信共享）
        wechat_ctx = ""
        try:
            from app.soul_manager import get_soul_manager
            sm = get_soul_manager()
            if sm.has_soul:
                wechat_ctx = sm.get_identity("wechat")
        except Exception:
            pass
        # 降级: SoulManager 没有 SOUL.md 时，使用旧的微信独立角色
        if not wechat_ctx:
            wechat_ctx = _load_wechat_context()
        if wechat_ctx:
            prompt += "\n\n" + wechat_ctx

        # ★ 微信只使用 data/wechat/skills/ 下的专属技能
        # 不加载全局技能（PC skills 和微信 skills 分离）

        # 注入长期记忆
        try:
            from app.memory import get_memory_text
            mem_text = get_memory_text()
            if mem_text:
                prompt += f"\n\n[长期记忆]:\n{mem_text}"
        except Exception:
            pass
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: agent_router.route(text, history, prompt)
            )
        except Exception as e:
            logger.error(f"[WeChat] agent_router.route() failed: {e}")
            return {"reply": f"处理失败: {str(e)[:200]}"}

        reply = result.get("reply", "...")

        # 存储 AI 回复
        memory.add_message(session_id, "assistant", reply)

        # 截断
        if len(reply) > 4000:
            reply = reply[:3950] + "\n\n... (truncated)"
            result["reply"] = reply

        return result

    # ── 状态查询 ───────────────────────────────────────────────

    def get_status(self) -> dict:
        creds = load_credentials()
        return {
            "online": self.is_online,
            "running": self._running,
            "has_credentials": bool(creds),
            "account_id": (creds.account_id[:8] + "***") if creds and creds.account_id else "",
            "base_url": self._base_url,
            "owner": (self._owner_user_id[:8] + "***") if self._owner_user_id else "",
            "stats": dict(self._stats),
            "active_sessions": len(self._session_map),
            "recent_messages": list(self._recent_messages)[-10:],
        }


# ── 全局单例 ────────────────────────────────────────────────────
_bridge: Optional[WeChatBridge] = None


def get_bridge() -> WeChatBridge:
    global _bridge
    if _bridge is None:
        _bridge = WeChatBridge()
    return _bridge


async def auto_start():
    """启动时自动尝试从已保存的凭证恢复连接（免重新扫码）"""
    creds = load_credentials()
    if creds and creds.token:
        bridge = get_bridge()
        if not bridge.is_online:
            result = await bridge.start()
            if result.get("success"):
                logger.info("[WeChat] 自动重连成功（使用已保存凭证）")
            else:
                logger.warning(f"[WeChat] 自动重连失败: {result.get('error', '')}")
    else:
        logger.info("[WeChat] 无保存凭证，跳过自动连接")
