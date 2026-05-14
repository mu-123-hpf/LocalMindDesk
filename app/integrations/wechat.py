"""
LocalMindDesk — 微信集成 (iLink Bot API)
基于腾讯官方 iLink Bot API，QR 码扫描登录
"""
from app.integrations.base import BaseIntegration, ConfigField
from app.tools.base import BaseTool, ToolContext


class WeChatSendTool(BaseTool):
    """微信发送工具"""

    def __init__(self, integration: 'WeChatIntegration'):
        self._integration = integration

    @property
    def name(self) -> str:
        return "wechat_send"

    @property
    def description(self) -> str:
        return "Send a text message to the bot owner via WeChat iLink API"

    @property
    def danger_level(self) -> str:
        return "moderate"

    def describe_action(self, params: dict) -> str:
        return "Send WeChat message"

    def execute(self, params: dict, ctx: ToolContext = None) -> dict:
        content = params.get("content", "")
        if not content:
            return {"success": False, "error": "empty content"}

        from app.wechat_bridge import get_bridge
        bridge = get_bridge()
        if not bridge.is_online:
            return {"success": False, "error": "WeChat bridge not online"}
        if not bridge._owner_user_id:
            return {"success": False, "error": "no owner user_id"}

        # 使用 asyncio 发送
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(bridge.send_text(bridge._owner_user_id, content))
                return {"success": True, "message": "message queued"}
            else:
                loop.run_until_complete(bridge.send_text(bridge._owner_user_id, content))
                return {"success": True, "message": "message sent"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class WeChatIntegration(BaseIntegration):
    """微信集成 — iLink Bot API"""

    def __init__(self):
        self._tool = WeChatSendTool(self)

    @property
    def id(self) -> str:
        return "wechat"

    @property
    def name(self) -> str:
        return "WeChat"

    @property
    def icon(self) -> str:
        return "💬"

    @property
    def description(self) -> str:
        return "WeChat iLink Bot — QR scan login, long-polling messages"

    @property
    def config_schema(self) -> list[ConfigField]:
        return []

    @property
    def install_commands(self) -> list[dict]:
        return [
            {
                "cmd": "pip install httpx cryptography qrcode[pil]",
                "label": "Install iLink dependencies",
                "required": True,
            },
        ]

    def auto_detect(self) -> dict:
        try:
            import httpx
            return {"found": True, "path": "", "info": "httpx available, iLink ready"}
        except ImportError:
            return {"found": False, "path": "", "info": "httpx not installed"}

    def connect(self, config: dict) -> dict:
        return {
            "success": True,
            "message": "Use QR scan to login (POST /api/wechat/qr-login)",
        }

    def disconnect(self) -> dict:
        from app.wechat_bridge import get_bridge
        import asyncio
        bridge = get_bridge()
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(bridge.stop())
            else:
                loop.run_until_complete(bridge.stop())
        except Exception:
            pass
        return {"success": True, "message": "WeChat bridge stopped"}

    def test_connection(self, config: dict) -> dict:
        from app.wechat_bridge import get_bridge
        bridge = get_bridge()
        status = bridge.get_status()
        if status["online"]:
            return {
                "success": True,
                "message": (
                    f"Online | Account: {status['account_id']} | "
                    f"Sessions: {status['active_sessions']}"
                ),
            }
        if status["has_credentials"]:
            return {
                "success": True,
                "message": "Credentials found, call POST /api/wechat/start to connect",
            }
        return {
            "success": False,
            "message": "Not logged in. Scan QR code first (POST /api/wechat/qr-login)",
        }

    def get_tools(self) -> list:
        return [self._tool]
