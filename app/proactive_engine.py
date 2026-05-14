"""
LocalMindDesk — ProactiveEngine（主动对话引擎）
学习 NAVI 的双系统架构，适配编程助手场景

双系统:
  System 1（事件驱动）: 微信新消息通知、定时任务触发
  System 2（定时巡检）: 空闲检测、TODO 提醒、每日问候

门控机制 (GateKeeper):
  - 冷却时间（同类触发间隔 ≥ 30 分钟）
  - 每日上限（最多 10 次主动消息）
  - 安静时间（22:00-08:00 不打扰）

前端集成:
  通过 SSE 推送主动消息到前端
"""
import asyncio
import sys
import time
import threading
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional, Callable


def _safe_print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        try:
            sys.stdout.buffer.write((msg + "\n").encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
        except Exception:
            pass

# 主动消息类型
MSG_TYPE_GREETING = "greeting"        # 问候
MSG_TYPE_REMINDER = "reminder"        # 提醒
MSG_TYPE_WECHAT_NOTIFY = "wechat"     # 微信新消息通知
MSG_TYPE_IDLE = "idle"                # 空闲关怀
MSG_TYPE_INSIGHT = "insight"          # 行为洞察
MSG_TYPE_SCHEDULER = "scheduler"      # 定时任务触发


# ============================================================
#  GateKeeper 门控
# ============================================================
class GateKeeper:
    """
    主动消息门控 — 防骚扰

    规则:
    1. 同类型消息冷却时间 ≥ 30 分钟
    2. 每日主动消息总量 ≤ 10 次
    3. 安静时间 22:00-08:00 不发送（除非紧急）
    """

    COOLDOWN_MINUTES = 15
    DAILY_LIMIT = 10
    QUIET_START = 22  # 22:00
    QUIET_END = 8     # 08:00

    def __init__(self):
        self._last_send: dict[str, float] = {}  # msg_type → last timestamp
        self._daily_count: int = 0
        self._daily_date: str = ""  # 当天日期 YYYY-MM-DD

    def should_send(self, msg_type: str, urgent: bool = False) -> tuple[bool, str]:
        """
        判断是否应该发送主动消息

        Returns:
            (allowed, reason)
        """
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        # 重置每日计数
        if today != self._daily_date:
            self._daily_count = 0
            self._daily_date = today

        # 1. 安静时间检查
        hour = now.hour
        if not urgent and (hour >= self.QUIET_START or hour < self.QUIET_END):
            return False, f"安静时间 ({self.QUIET_START}:00-{self.QUIET_END}:00)"

        # 2. 每日上限
        if self._daily_count >= self.DAILY_LIMIT:
            return False, f"已达每日上限 ({self.DAILY_LIMIT} 次)"

        # 3. 冷却时间
        last = self._last_send.get(msg_type, 0)
        elapsed = (time.time() - last) / 60  # 分钟
        if elapsed < self.COOLDOWN_MINUTES:
            remaining = int(self.COOLDOWN_MINUTES - elapsed)
            return False, f"冷却中 (还需 {remaining} 分钟)"

        return True, "OK"

    def record_send(self, msg_type: str):
        """记录一次发送"""
        self._last_send[msg_type] = time.time()
        self._daily_count += 1

    def get_stats(self) -> dict:
        return {
            "daily_count": self._daily_count,
            "daily_limit": self.DAILY_LIMIT,
            "cooldown_minutes": self.COOLDOWN_MINUTES,
            "quiet_hours": f"{self.QUIET_START}:00-{self.QUIET_END}:00",
        }


# ============================================================
#  主动消息数据
# ============================================================
class ProactiveMessage:
    def __init__(self, msg_type: str, content: str, urgent: bool = False):
        self.msg_type = msg_type
        self.content = content
        self.urgent = urgent
        self.created_at = datetime.now().isoformat()


# ============================================================
#  ProactiveEngine 主引擎
# ============================================================
class ProactiveEngine:
    """
    主动对话引擎

    管理两个后台循环:
    - System 2 定时巡检（检查空闲、生成主动消息）
    - 事件队列处理（System 1 回调）

    前端通过 get_pending_messages() 轮询获取主动消息。
    """

    PATROL_INTERVAL = 60  # System 2 巡检间隔（秒）

    def __init__(self):
        self._gatekeeper = GateKeeper()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._pending_messages: list[dict] = []  # 待推送的主动消息
        self._message_history: list[dict] = []   # 历史记录
        self._on_message: Optional[Callable] = None  # 消息回调
        self._last_user_activity: float = time.time()  # 最后用户活动时间
        self._event_queue: list[ProactiveMessage] = []  # System 1 事件队列

    @property
    def gatekeeper(self) -> GateKeeper:
        return self._gatekeeper

    # ── 启动/停止 ──────────────────────────────────────────────

    def start(self):
        """启动主动对话引擎"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._patrol_loop, daemon=True)
        self._thread.start()
        _safe_print(f"[ProactiveEngine] 已启动 (巡检间隔 {self.PATROL_INTERVAL}s)")

    def stop(self):
        self._running = False
        _safe_print("[ProactiveEngine] 已停止")

    # ── System 1: 事件驱动 ─────────────────────────────────────

    def notify_wechat_message(self, sender: str, preview: str):
        """微信收到新消息时通知 PC 端"""
        msg = ProactiveMessage(
            MSG_TYPE_WECHAT_NOTIFY,
            f"📱 微信消息 ({sender}): {preview[:50]}",
            urgent=False,
        )
        self._enqueue(msg)

    def notify_scheduler_trigger(self, task_name: str, result: str):
        """定时任务触发时通知"""
        msg = ProactiveMessage(
            MSG_TYPE_SCHEDULER,
            f"⏰ 定时任务「{task_name}」已执行: {result[:100]}",
            urgent=False,
        )
        self._enqueue(msg)

    def record_user_activity(self):
        """记录用户活动（每次收到用户消息时调用）"""
        self._last_user_activity = time.time()

    # ── System 2: 定时巡检 ─────────────────────────────────────

    def _patrol_loop(self):
        """后台巡检循环"""
        while self._running:
            try:
                self._process_event_queue()
                self._check_idle()
            except Exception as e:
                _safe_print(f"[ProactiveEngine] 巡检异常: {e}")
            time.sleep(self.PATROL_INTERVAL)

    def _process_event_queue(self):
        """处理 System 1 事件队列"""
        while self._event_queue:
            msg = self._event_queue.pop(0)
            # scheduler 触发的通知不受安静时间限制（用户主动设的任务）
            if msg.msg_type == "scheduler":
                self._push_message(msg)
                continue
            allowed, reason = self._gatekeeper.should_send(msg.msg_type, msg.urgent)
            if allowed:
                self._push_message(msg)
            else:
                _safe_print(f"[ProactiveEngine] 门控拦截: {msg.msg_type} — {reason}")

    def _check_idle(self):
        """检查用户是否长时间空闲"""
        idle_minutes = (time.time() - self._last_user_activity) / 60

        # 超过 15 分钟无活动 → 发送关怀消息
        if idle_minutes > 15:
            now = datetime.now()
            hour = now.hour

            # 根据时间段生成不同的关怀消息
            if 8 <= hour < 12:
                content = "☀️ 早上好！有什么我可以帮忙的吗？"
            elif 12 <= hour < 14:
                content = "🍚 午餐时间到了，记得吃饭哦~"
            elif 14 <= hour < 18:
                content = "☕ 下午了，需要帮你做点什么吗？"
            elif 18 <= hour < 22:
                content = "🌆 忙了一天了，有什么未完成的任务需要处理吗？"
            else:
                return  # 安静时间不发

            msg = ProactiveMessage(MSG_TYPE_IDLE, content)
            allowed, reason = self._gatekeeper.should_send(MSG_TYPE_IDLE)
            if allowed:
                self._push_message(msg)

    # ── 消息管理 ───────────────────────────────────────────────

    def _enqueue(self, msg: ProactiveMessage):
        """添加到事件队列并立即处理"""
        self._event_queue.append(msg)
        # 立即处理，不等待巡检周期
        self._process_event_queue()

    def _push_message(self, msg: ProactiveMessage):
        """推送主动消息（PC 前端 + 微信 + 系统通知三同步）"""
        entry = {
            "type": msg.msg_type,
            "content": msg.content,
            "urgent": msg.urgent,
            "created_at": msg.created_at,
        }
        self._pending_messages.append(entry)
        self._message_history.append(entry)
        self._gatekeeper.record_send(msg.msg_type)

        # 只保留最近 50 条历史
        if len(self._message_history) > 50:
            self._message_history = self._message_history[-30:]

        _safe_print(f"[ProactiveEngine] 推送: [{msg.msg_type}] {msg.content[:50]}")

        # ★ 同步到微信（如果在线）
        self._sync_to_wechat(msg.content)

        # ★ 同步到 Windows 系统通知
        self._sync_to_toast(msg.content)

        # 触发回调
        if self._on_message:
            try:
                self._on_message(entry)
            except Exception:
                pass

    def _sync_to_wechat(self, content: str):
        """将主动消息同步发送到微信"""
        try:
            from app.wechat_bridge import get_bridge
            bridge = get_bridge()
            if not bridge.is_online or not bridge._owner_user_id:
                return  # 微信未在线，静默跳过

            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(bridge.send_text(bridge._owner_user_id, f"[LocalMindDesk] {content}"))
                else:
                    loop.run_until_complete(bridge.send_text(bridge._owner_user_id, f"[LocalMindDesk] {content}"))
            except RuntimeError:
                # 没有事件循环 → 新建一个
                loop = asyncio.new_event_loop()
                loop.run_until_complete(bridge.send_text(bridge._owner_user_id, f"[LocalMindDesk] {content}"))
                loop.close()

            _safe_print(f"[ProactiveEngine] 微信同步: {content[:30]}")
        except Exception as e:
            _safe_print(f"[ProactiveEngine] 微信同步失败: {e}")

    def _sync_to_toast(self, content: str):
        """发送 Windows 系统通知 (Toast)"""
        try:
            # 尝试使用 Windows 10/11 原生 toast
            from ctypes import windll
            # 使用 PowerShell 发送 toast（兼容性最好）
            import subprocess
            ps_script = (
                f'[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, '
                f'ContentType = WindowsRuntime] > $null; '
                f'$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(0); '
                f'$text = $template.GetElementsByTagName("text"); '
                f'$text.Item(0).AppendChild($template.CreateTextNode("LocalMindDesk")) > $null; '
                f'$text.Item(1).AppendChild($template.CreateTextNode("{content}")) > $null; '
                f'$toast = [Windows.UI.Notifications.ToastNotification]::new($template); '
                f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("LocalMindDesk").Show($toast)'
            )
            subprocess.Popen(
                ["powershell", "-WindowStyle", "Hidden", "-Command", ps_script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
        except Exception:
            pass  # 通知失败不影响主流程

    def get_pending_messages(self) -> list[dict]:
        """获取并清空待推送的主动消息（前端轮询调用）"""
        messages = self._pending_messages.copy()
        self._pending_messages.clear()
        return messages

    def set_on_message(self, callback: Callable):
        """设置消息推送回调"""
        self._on_message = callback

    def get_history(self, limit: int = 20) -> list[dict]:
        return self._message_history[-limit:]

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "idle_minutes": round((time.time() - self._last_user_activity) / 60, 1),
            "pending_count": len(self._pending_messages),
            "history_count": len(self._message_history),
            "gatekeeper": self._gatekeeper.get_stats(),
        }


# ============================================================
#  全局单例
# ============================================================
_engine: Optional[ProactiveEngine] = None


def get_proactive_engine() -> ProactiveEngine:
    """获取全局 ProactiveEngine 单例"""
    global _engine
    if _engine is None:
        _engine = ProactiveEngine()
    return _engine
