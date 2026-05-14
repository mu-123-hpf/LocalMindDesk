"""
LocalMindDesk — Agent 路由引擎 v4
向后兼容层：所有逻辑已迁移到 app.router 包

旧代码的导入 `from app.agent_router import route` 仍然有效。
"""
from app.router import route, get_activity_feed, _add_activity

__all__ = ["route", "get_activity_feed", "_add_activity"]
