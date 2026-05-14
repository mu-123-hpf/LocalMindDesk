"""
LocalMindDesk — iLink Bot API 客户端（平台无关层）

纯 iLink API 封装，不含任何 LocalMindDesk 业务逻辑。
可被 wechat_bridge.py、MCP Server 等复用。

API 文档: https://ilinkai.weixin.qq.com
参考: cc-weixin (github.com/qufei1993/cc-weixin)
"""
import asyncio
import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, AsyncGenerator

import httpx

logger = logging.getLogger("LocalMindDesk.ilink")

# ── iLink API 常量 ──────────────────────────────────────────────
ILINK_CV = (2 << 16) | (2 << 8) | 0  # 131584
CHANNEL_VERSION = "2.2.0"
ILINK_APP_ID = "bot"

EP_GET_UPDATES = "ilink/bot/getupdates"
EP_SEND_MESSAGE = "ilink/bot/sendmessage"
EP_SEND_TYPING = "ilink/bot/sendtyping"
EP_GET_BOT_QR = "ilink/bot/get_bot_qrcode"
EP_GET_QR_STATUS = "ilink/bot/get_qrcode_status"
EP_GET_UPLOAD_URL = "ilink/bot/getuploadurl"

LONG_POLL_TIMEOUT = 35
API_TIMEOUT = 15
QR_TIMEOUT = 35

# 消息 item 类型
ITEM_TEXT = 1
ITEM_IMAGE = 2
ITEM_VOICE = 3
ITEM_FILE = 4
ITEM_VIDEO = 5

# 媒体类型
MEDIA_IMAGE = 1
MEDIA_VIDEO = 2
MEDIA_FILE = 3
MEDIA_VOICE = 4

MSG_TYPE_USER = 1
MSG_STATE_FINISH = 2
MAX_MSG_LEN = 4000

DATA_DIR = "data/wechat"


# ── 数据类 ──────────────────────────────────────────────────────

@dataclass
class Credentials:
    account_id: str
    token: str
    base_url: str
    user_id: str = ""
    saved_at: str = ""


@dataclass
class QRState:
    qrcode: str = ""
    qrcode_url: str = ""
    status: str = "pending"  # pending | scanned | confirmed | expired | error
    credentials: Optional[Credentials] = None
    error: Optional[str] = None


# ── 工具函数 ────────────────────────────────────────────────────

def _random_uin() -> str:
    import random
    return base64.b64encode(str(random.randint(0, 0xFFFFFFFF)).encode()).decode()


def _base_info() -> dict:
    return {"channel_version": CHANNEL_VERSION}


def _build_headers(token: Optional[str], body_bytes: bytes) -> dict:
    h = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Content-Length": str(len(body_bytes)),
        "X-WECHAT-UIN": _random_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_CV),
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


async def ilink_post(
    client: httpx.AsyncClient,
    base_url: str,
    endpoint: str,
    payload: dict,
    token: Optional[str],
    timeout: float = API_TIMEOUT,
) -> dict:
    """发送 iLink API 请求"""
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    body = json.dumps(payload).encode("utf-8")
    try:
        resp = await client.post(
            url, content=body,
            headers=_build_headers(token, body),
            timeout=timeout,
        )
    except httpx.TimeoutException:
        if endpoint == EP_GET_UPDATES:
            return {"ret": 0, "msgs": [], "get_updates_buf": payload.get("get_updates_buf", "")}
        raise
    if resp.status_code != 200:
        raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def ilink_post_sync(
    base_url: str,
    endpoint: str,
    payload: dict,
    token: Optional[str],
    timeout: float = API_TIMEOUT,
) -> dict:
    """同步版 iLink API 请求（供子线程调用）"""
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    body = json.dumps(payload).encode("utf-8")
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, content=body, headers=_build_headers(token, body))
    if resp.status_code != 200:
        raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def extract_text(msg: dict) -> str:
    """从 iLink 消息中提取文本"""
    parts = []
    for item in msg.get("item_list", []):
        if item.get("type") == ITEM_TEXT and item.get("text_item", {}).get("text"):
            parts.append(item["text_item"]["text"])
        elif item.get("voice_item", {}).get("text"):
            parts.append(f"[voice: {item['voice_item']['text']}]")
    return "\n".join(parts).strip()


def split_message(text: str, max_len: int = MAX_MSG_LEN) -> list[str]:
    """长文本自动分片"""
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, max_len)
        if cut < max_len // 2:
            cut = max_len
        chunks.append(text[:cut])
        text = text[cut:].lstrip()
    return chunks


# ── 加密工具 ────────────────────────────────────────────────────

def aes_128_ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    """AES-128-ECB 加密 + PKCS7 padding"""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as sym_padding
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    enc = cipher.encryptor()
    return enc.update(padded) + enc.finalize()


def get_mime_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
        ".mp4": "video/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav",
        ".pdf": "application/pdf", ".txt": "text/plain",
        ".doc": "application/msword", ".zip": "application/zip",
    }
    return mime_map.get(ext, "application/octet-stream")


def get_media_item_type(mime_type: str) -> tuple[int, int]:
    """返回 (media_type, item_type)"""
    if mime_type.startswith("image/"):
        return MEDIA_IMAGE, ITEM_IMAGE
    if mime_type.startswith("video/"):
        return MEDIA_VIDEO, ITEM_VIDEO
    if mime_type.startswith("audio/"):
        return MEDIA_VOICE, ITEM_VOICE
    return MEDIA_FILE, ITEM_FILE


def generate_qr_b64(content: str) -> str:
    try:
        import io
        import qrcode
        qr = qrcode.QRCode(box_size=8, border=4)
        qr.add_data(content)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
    except ImportError:
        return ""


# ── 凭证持久化 ──────────────────────────────────────────────────

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def save_credentials(creds: Credentials):
    ensure_data_dir()
    with open(f"{DATA_DIR}/credentials.json", "w", encoding="utf-8") as f:
        json.dump({
            "account_id": creds.account_id, "token": creds.token,
            "base_url": creds.base_url, "user_id": creds.user_id,
            "saved_at": creds.saved_at,
        }, f, ensure_ascii=False, indent=2)


def load_credentials() -> Optional[Credentials]:
    path = f"{DATA_DIR}/credentials.json"
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return Credentials(**json.load(f))
    except Exception:
        return None


def delete_credentials():
    path = f"{DATA_DIR}/credentials.json"
    if os.path.exists(path):
        os.remove(path)


def load_whitelist() -> set:
    """加载已授权用户白名单"""
    path = f"{DATA_DIR}/whitelist.json"
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_whitelist(users: set):
    """保存白名单"""
    ensure_data_dir()
    with open(f"{DATA_DIR}/whitelist.json", "w", encoding="utf-8") as f:
        json.dump(list(users), f, ensure_ascii=False, indent=2)


def save_sync_buf(buf: str):
    ensure_data_dir()
    with open(f"{DATA_DIR}/sync_buf.json", "w", encoding="utf-8") as f:
        json.dump({"get_updates_buf": buf}, f)


def load_sync_buf() -> str:
    path = f"{DATA_DIR}/sync_buf.json"
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("get_updates_buf", "")
    except Exception:
        return ""


def save_context_tokens(tokens: dict):
    ensure_data_dir()
    with open(f"{DATA_DIR}/context_tokens.json", "w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)


def load_context_tokens() -> dict:
    path = f"{DATA_DIR}/context_tokens.json"
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ── QR 登录流程 ─────────────────────────────────────────────────

async def qr_login(base_url: str = "https://ilinkai.weixin.qq.com") -> AsyncGenerator[QRState, None]:
    """
    QR 码登录流程，返回 AsyncGenerator[QRState]
    前端通过 SSE 或轮询获取状态更新
    """
    async with httpx.AsyncClient() as client:
        current_base = base_url
        try:
            # Step 1: 获取 QR 码
            qr_resp = await ilink_post(
                client, current_base,
                f"{EP_GET_BOT_QR}?bot_type=3",
                {}, None, QR_TIMEOUT,
            )
            if qr_resp.get("ret", -1) != 0 or not qr_resp.get("qrcode"):
                yield QRState(status="error", error=qr_resp.get("errmsg", "get QR failed"))
                return

            qrcode = qr_resp["qrcode"]

            # 获取 QR 图片
            qr_img_b64 = qr_resp.get("qrcode_img_content_base64", "") \
                or qr_resp.get("img_content", "")
            qr_img_url = qr_resp.get("qrcode_img_url", "") \
                or qr_resp.get("qrcode_url", "") \
                or qr_resp.get("qrcode_img_content", "")

            if qr_img_b64:
                qrcode_url = qr_img_b64 if qr_img_b64.startswith("data:") \
                    else f"data:image/png;base64,{qr_img_b64}"
            elif qr_img_url:
                try:
                    resp = await client.get(qr_img_url, timeout=10)
                    ct = resp.headers.get("content-type", "").split(";")[0].strip()
                    if ct.startswith("image/"):
                        qrcode_url = f"data:{ct};base64,{base64.b64encode(resp.content).decode()}"
                    else:
                        qrcode_url = generate_qr_b64(qr_img_url)
                except Exception:
                    qrcode_url = generate_qr_b64(qr_img_url)
            else:
                qrcode_url = ""

            yield QRState(qrcode=qrcode, qrcode_url=qrcode_url, status="pending")

            # Step 2: 轮询扫码状态（最多 8 分钟）
            deadline = time.time() + 480
            refresh_count = 0

            while time.time() < deadline:
                await asyncio.sleep(1.5)
                try:
                    st_resp = await ilink_post(
                        client, current_base,
                        f"{EP_GET_QR_STATUS}?qrcode={qrcode}",
                        {}, None, QR_TIMEOUT,
                    )
                    status = st_resp.get("status", "wait")

                    if status == "scaned":
                        yield QRState(qrcode=qrcode, qrcode_url=qrcode_url, status="scanned")
                    elif status == "scaned_but_redirect":
                        if st_resp.get("redirect_host"):
                            current_base = f"https://{st_resp['redirect_host']}"
                    elif status == "expired":
                        refresh_count += 1
                        if refresh_count > 3:
                            yield QRState(status="expired", error="QR expired too many times")
                            return
                        new_qr = await ilink_post(
                            client, base_url, f"{EP_GET_BOT_QR}?bot_type=3",
                            {}, None, QR_TIMEOUT,
                        )
                        if new_qr.get("qrcode"):
                            qrcode = new_qr["qrcode"]
                            qrcode_url = generate_qr_b64(qrcode)
                            yield QRState(qrcode=qrcode, qrcode_url=qrcode_url, status="pending")
                    elif status == "confirmed":
                        creds = Credentials(
                            account_id=st_resp.get("ilink_bot_id", ""),
                            token=st_resp.get("bot_token", ""),
                            base_url=st_resp.get("baseurl", current_base),
                            user_id=st_resp.get("ilink_user_id", ""),
                            saved_at=datetime.now().isoformat(),
                        )
                        if not creds.account_id or not creds.token:
                            yield QRState(status="error", error="incomplete credentials")
                            return
                        save_credentials(creds)
                        yield QRState(
                            qrcode=qrcode, qrcode_url=qrcode_url,
                            status="confirmed", credentials=creds,
                        )
                        return
                except Exception as e:
                    logger.warning(f"[iLink] QR poll error: {e}")

            yield QRState(status="expired", error="login timeout")
        except Exception as e:
            yield QRState(status="error", error=str(e))


# ── 消息构建工具 ────────────────────────────────────────────────

def build_text_payload(user_id: str, text: str, ctx_token: str = "") -> dict:
    """构建文本消息 payload"""
    return {
        "msg": {
            "from_user_id": "",
            "to_user_id": user_id,
            "client_id": f"lmd-{int(time.time()*1000)}-{secrets.token_hex(4)}",
            "message_type": 2,
            "message_state": MSG_STATE_FINISH,
            "context_token": ctx_token,
            "item_list": [
                {"type": ITEM_TEXT, "text_item": {"text": text}},
            ],
        },
        "base_info": _base_info(),
    }


def build_media_payload(
    user_id: str, item: dict, ctx_token: str = "", caption: str = ""
) -> dict:
    """构建媒体消息 payload"""
    item_list = [item]
    if caption:
        item_list.append({"type": ITEM_TEXT, "text_item": {"text": caption}})
    return {
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
