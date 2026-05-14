"""
LocalMindDesk — Action Engine（操作执行引擎）
Shell / 文件 / GUI 自动化 + 三级安全拦截 + 沙盒

== Phase 1 重构说明 ==
具体工具逻辑已拆分到 app/tools/ 独立模块中:
  - shell_tool.py  → ShellTool
  - file_tool.py   → FileTool
  - gui_tool.py    → GUITool, ScreenCaptureTool
  - search_tool.py → SearchTool（新增）

本文件保留:
  1. 沙盒配置 + SafetyGate（向后兼容）
  2. execute_action() 入口委托给 ToolRegistry
  3. 旧函数别名（exec_shell, exec_file_op 等仍可调用）
"""
import os
import re
import time
from datetime import datetime
from typing import Optional

# ============================================================
#  沙盒配置（保持原有接口，被 registry.py 引用）
# ============================================================
SANDBOX_ROOTS = []  # 默认空 = 全盘可访问（由用户通过 UI 配置）


def add_sandbox_root(path: str):
    """动态添加沙盒根目录（用于打开的工作区）"""
    norm = os.path.normpath(os.path.abspath(path))
    if norm not in SANDBOX_ROOTS:
        SANDBOX_ROOTS.append(norm)
        print(f"[Sandbox] 已添加工作区到沙盒: {norm}")

FORBIDDEN_PATHS = [
    os.path.normpath(r"C:\Windows"),
    os.path.normpath(r"C:\Program Files"),
    os.path.normpath(r"C:\Program Files (x86)"),
    os.path.normpath(os.path.expanduser("~/.ssh")),
    os.path.normpath(os.path.expanduser("~/.gnupg")),
    "/etc", "/usr", "/bin", "/sbin", "/boot",
]

# 从持久化文件加载用户自定义的沙盒配置
_sandbox_file = "data/sandbox.json"
if os.path.exists(_sandbox_file):
    try:
        import json as _json
        with open(_sandbox_file, "r", encoding="utf-8") as _f:
            _saved = _json.load(_f)
        # 正确处理空数组：空 [] 应清空默认值，而不是忽略
        if "sandbox_roots" in _saved:
            SANDBOX_ROOTS.clear()
            SANDBOX_ROOTS.extend([os.path.normpath(p) for p in _saved["sandbox_roots"] if p])
        if "forbidden_paths" in _saved:
            FORBIDDEN_PATHS.clear()
            FORBIDDEN_PATHS.extend([os.path.normpath(p) for p in _saved["forbidden_paths"] if p])
        print(f"[Sandbox] 从 {_sandbox_file} 加载配置: {len(SANDBOX_ROOTS)} 个允许路径, {len(FORBIDDEN_PATHS)} 个禁止路径")
    except Exception as _e:
        print(f"[Sandbox] 加载 {_sandbox_file} 失败: {_e}")

DANGEROUS_CMD_PATTERNS = [
    r"\brm\b.*-r", r"\brmdir\b.*\/[sS]", r"\bdel\b.*\/[sSqQ]",
    r"\bformat\b", r"\bshutdown\b", r"\brestart\b",
    r"\bregedit\b", r"\breg\b.*delete",
    r"\bnet\b.*user", r"\btaskkill\b.*\/[fF]",
    r"\bmkfs\b", r"\bdd\b.*if=",
    r"\bchmod\b.*777", r"\bchown\b",
    r">\s*/dev/", r"\|.*rm\b",
]

# 危险分级（保留用于向后兼容）
DANGER_LEVELS = {
    "shell_exec":         "critical",
    "file_op.read":       "safe",
    "file_op.list":       "safe",
    "file_op.mkdir":      "safe",
    "file_op.write":      "moderate",
    "file_op.edit":       "moderate",
    "file_op.append":     "moderate",
    "file_op.copy":       "moderate",
    "file_op.move":       "moderate",
    "file_op.delete":     "critical",
    "gui_action.screenshot": "safe",
    "gui_action.click":   "moderate",
    "gui_action.type":    "moderate",
    "gui_action.hotkey":  "moderate",
    "screen_capture":     "safe",
    "code_search":        "safe",       # 新增
    "code_search.grep":   "safe",       # 新增
    "code_search.find":   "safe",       # 新增
    "wechat_send":        "moderate",   # 微信发送需确认
}

# ============================================================
#  沙盒检查
# ============================================================
# 应用自身的数据目录始终允许访问（截图、缓存等）
_APP_DATA_DIR = os.path.normpath(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data')))

def _is_path_in_sandbox(filepath: str) -> bool:
    """检查路径是否允许访问（默认拒绝，打开文件夹后该目录可访问）"""
    norm = os.path.normpath(os.path.abspath(filepath))
    # 0. 应用自身的 data/ 目录始终允许（截图保存等）
    if norm.startswith(_APP_DATA_DIR):
        return True
    # 1. 禁止访问黑名单路径
    for forbidden in FORBIDDEN_PATHS:
        if norm.startswith(forbidden):
            return False
    # 2. 检查白名单（包含用户配置 + 打开的工作区文件夹）
    for root in SANDBOX_ROOTS:
        if norm.startswith(root):
            return True
    # 3. 不在白名单内 → 拒绝（默认不可访问）
    return False


def _check_sandbox(paths: list[str]) -> tuple[bool, str]:
    """检查路径列表是否全部在沙盒内"""
    for p in paths:
        if not p:
            continue
        if not _is_path_in_sandbox(p):
            return False, f"路径 {p} 超出沙盒范围。允许的目录: {', '.join(SANDBOX_ROOTS)}"
    return True, ""


def _is_dangerous_command(cmd: str) -> bool:
    """检查命令是否匹配黑名单"""
    for pattern in DANGEROUS_CMD_PATTERNS:
        if re.search(pattern, cmd, re.I):
            return True
    return False


# ============================================================
#  安全门（向后兼容 — 委托给 ToolRegistry）
# ============================================================
class SafetyGate:
    """三级安全拦截器 — 现在委托给 ToolRegistry"""

    @staticmethod
    def assess(tool: str, params: dict) -> dict:
        """
        评估操作危险等级
        返回 {"level": "safe/moderate/critical", "reason": "...", "blocked": bool}
        """
        from app.tools.registry import get_registry
        registry = get_registry()

        # 优先使用新的 Registry 评估
        t = registry.get(tool)
        if t:
            return registry.assess(tool, params)

        # 回退：旧逻辑（兼容未注册的工具）
        action = params.get("action", "")
        if tool == "file_op" and action:
            key = f"file_op.{action}"
        elif tool == "gui_action" and action:
            key = f"gui_action.{action}"
        else:
            key = tool

        level = DANGER_LEVELS.get(key, "critical")
        reason = ""
        blocked = False

        paths = []
        for k in ("source", "destination", "path", "cwd"):
            if k in params and params[k]:
                v = params[k].strip()
                # 跳过占位符 cwd（"." 不算真实路径）
                if k == "cwd" and v in (".", "", ".\\", "./"):
                    continue
                # 对于 shell_exec + start 命令，cwd 不需要沙盒检查（启动应用不涉及文件访问）
                if k == "cwd" and tool == "shell_exec":
                    cmd = params.get("command", "").strip().lower()
                    if cmd.startswith("start ") or cmd.startswith("cmd /k") or cmd.startswith("taskkill"):
                        continue
                paths.append(v)

        if paths:
            ok, msg = _check_sandbox(paths)
            if not ok:
                return {"level": "critical", "reason": msg, "blocked": True}

        if tool == "shell_exec":
            cmd = params.get("command", "")
            if _is_dangerous_command(cmd):
                level = "critical"
                reason = f"危险命令检测: {cmd[:60]}"

        if action == "delete":
            level = "critical"
            reason = f"删除操作: {params.get('source', params.get('path', ''))}"

        return {"level": level, "reason": reason, "blocked": blocked}


# ============================================================
#  统一执行入口（向后兼容 — 委托给 ToolRegistry）
# ============================================================
_action_log: list[dict] = []


def execute_action(tool: str, params: dict) -> dict:
    """
    统一执行入口 — 现在委托给 ToolRegistry
    保持完全向后兼容的签名
    """
    from app.tools.registry import get_registry
    registry = get_registry()

    result = registry.execute(tool, params)

    # 同步日志到旧 _action_log（兼容 get_action_log 调用方）
    if registry._action_log:
        latest = registry._action_log[-1]
        _action_log.append(latest)
        if len(_action_log) > 100:
            _action_log.pop(0)

    return result


def get_action_log() -> list[dict]:
    return list(_action_log)


# ============================================================
#  旧函数别名（向后兼容，直接引用 Tool 实例）
# ============================================================
def exec_shell(command: str, cwd: str = None, timeout: int = 30) -> dict:
    """向后兼容：直接调用 ShellTool"""
    from app.tools.shell_tool import ShellTool
    return ShellTool().execute({"command": command, "cwd": cwd, "timeout": timeout})


def exec_file_op(action: str, source: str = "", destination: str = "",
                 content: str = "", path: str = "", **kwargs) -> dict:
    """向后兼容：直接调用 FileTool"""
    from app.tools.file_tool import FileTool
    params = {"action": action, "source": source, "destination": destination,
              "content": content, "path": path}
    params.update(kwargs)
    return FileTool().execute(params)


def exec_gui_action(action: str, x: int = 0, y: int = 0,
                    text: str = "", keys: list = None, **kw) -> dict:
    """向后兼容：直接调用 GUITool"""
    from app.tools.gui_tool import GUITool
    return GUITool().execute({"action": action, "x": x, "y": y, "text": text, "keys": keys or []})
