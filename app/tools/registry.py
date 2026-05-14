"""
LocalMindDesk — ToolRegistry
工具注册表：统一注册、查找、执行工具
借鉴 Claude Code 的 tools.ts 设计
"""
import time
from datetime import datetime
from typing import Optional
from app.tools.base import BaseTool, ToolContext


class ToolRegistry:
    """
    工具注册表 — 所有工具的统一管理中心

    用法:
        registry = ToolRegistry()
        registry.register(ShellTool())
        result = registry.execute("shell_exec", {"command": "dir"})
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._action_log: list[dict] = []

    def register(self, tool: BaseTool) -> None:
        """注册一个工具"""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """注销一个工具"""
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[BaseTool]:
        """按名称获取工具"""
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        """列出所有已注册的工具"""
        return [
            {
                "name": t.name,
                "description": t.description,
                "danger_level": t.danger_level,
            }
            for t in self._tools.values()
        ]

    def get_tool_names(self) -> list[str]:
        """获取所有工具名称"""
        return list(self._tools.keys())

    def assess(self, tool_name: str, params: dict) -> dict:
        """
        安全评估（兼容旧 SafetyGate.assess 接口）
        返回 {"level": "...", "reason": "...", "blocked": bool}
        """
        tool = self.get(tool_name)
        if not tool:
            return {"level": "critical", "reason": f"未知工具: {tool_name}", "blocked": True}

        # 沙盒检查
        paths = tool.get_paths(params)
        if paths:
            from app.action_engine import _check_sandbox
            ok, msg = _check_sandbox(paths)
            if not ok:
                return {"level": "critical", "reason": msg, "blocked": True}

        return tool.check_permissions(params)

    def execute(self, tool_name: str, params: dict, ctx: ToolContext = None) -> dict:
        """
        统一执行入口（兼容旧 execute_action 接口）
        """
        start = time.time()

        tool = self.get(tool_name)
        if not tool:
            return {"success": False, "error": f"未知工具: {tool_name}"}

        # 验证参数
        ok, err = tool.validate(params, ctx)
        if not ok:
            return {"success": False, "error": err}

        # 执行
        result = tool.execute(params, ctx)

        # 记录耗时
        duration = int((time.time() - start) * 1000)
        result["duration_ms"] = duration

        # 写入日志
        log = {
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "params": {k: str(v)[:100] for k, v in params.items()},
            "success": result.get("success", False),
            "duration_ms": duration,
            "result": result,  # 存储完整结果，供链式操作查询
        }
        self._action_log.append(log)
        if len(self._action_log) > 100:
            self._action_log.pop(0)

        return result

    def get_action_log(self) -> list[dict]:
        return list(self._action_log)


# ============================================================
#  全局单例 + 默认工具自动注册
# ============================================================
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """获取全局 ToolRegistry 单例（首次调用时自动注册所有内置工具）"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_builtin_tools(_registry)
    return _registry


def _register_builtin_tools(reg: ToolRegistry):
    """注册所有内置工具"""
    from app.tools.shell_tool import ShellTool
    from app.tools.file_tool import FileTool
    from app.tools.gui_tool import GUITool, ScreenCaptureTool
    from app.tools.search_tool import SearchTool
    from app.tools.browser_tool import BrowserTool
    from app.integrations.wechat import WeChatSendTool, WeChatIntegration

    reg.register(ShellTool())
    reg.register(FileTool())
    reg.register(GUITool())
    reg.register(ScreenCaptureTool())
    reg.register(SearchTool())
    reg.register(BrowserTool())
    reg.register(WeChatSendTool(WeChatIntegration()))

    print(f"[ToolRegistry] 已注册 {len(reg.get_tool_names())} 个工具: {', '.join(reg.get_tool_names())}")
