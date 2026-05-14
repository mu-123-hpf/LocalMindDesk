# LocalMindDesk — 插件化 Tool 系统
# 每个工具独立实现，通过 Registry 统一注册和调用
from app.tools.registry import ToolRegistry, get_registry

__all__ = ["ToolRegistry", "get_registry"]
