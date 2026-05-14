"""
LocalMindDesk — WebSocket 连接管理器
替代前端轮询，实时推送消息
"""
import asyncio
import json
from fastapi import WebSocket
from app.logger import get_logger

logger = get_logger("ws")


class ConnectionManager:
    """管理所有 WebSocket 连接"""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WebSocket 连接 +1 (当前 {len(self.active)})")

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        logger.info(f"WebSocket 断开 -1 (当前 {len(self.active)})")

    async def broadcast(self, event: str, data: dict):
        """广播事件到所有连接"""
        msg = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send(self, ws: WebSocket, event: str, data: dict):
        """发送到单个连接"""
        try:
            await ws.send_text(json.dumps({"event": event, "data": data}, ensure_ascii=False))
        except Exception:
            self.disconnect(ws)


# 全局实例
ws_manager = ConnectionManager()
