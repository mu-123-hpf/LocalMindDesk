"""
LocalMindDesk — ShellTool
Shell 命令执行工具，支持同步执行和 exe 非阻塞启动
"""
import os
import re
import subprocess
from app.tools.base import BaseTool, ToolContext

# 危险命令黑名单
DANGEROUS_CMD_PATTERNS = [
    r"\brm\b.*-r", r"\brmdir\b.*\/[sS]", r"\bdel\b.*\/[sSqQ]",
    r"\bformat\b", r"\bshutdown\b", r"\brestart\b",
    r"\bregedit\b", r"\breg\b.*delete",
    r"\bnet\b.*user", r"\btaskkill\b.*\/[fF]",
    r"\bmkfs\b", r"\bdd\b.*if=",
    r"\bchmod\b.*777", r"\bchown\b",
    r">\s*/dev/", r"\|.*rm\b",
]


def _is_dangerous_command(cmd: str) -> bool:
    for pattern in DANGEROUS_CMD_PATTERNS:
        if re.search(pattern, cmd, re.I):
            return True
    return False


class ShellTool(BaseTool):
    @property
    def name(self) -> str:
        return "shell_exec"

    @property
    def description(self) -> str:
        return "执行 Shell 命令（终端命令、脚本、程序启动）"

    @property
    def danger_level(self) -> str:
        return "critical"

    def get_danger_level(self, params: dict) -> str:
        cmd = params.get("command", "")
        if _is_dangerous_command(cmd):
            return "critical"
        return "critical"  # shell 始终 critical

    def check_permissions(self, params: dict, ctx: ToolContext = None) -> dict:
        cmd = params.get("command", "")
        reason = ""
        if _is_dangerous_command(cmd):
            reason = f"危险命令检测: {cmd[:60]}"
        return {"level": "critical", "reason": reason, "blocked": False}

    def is_destructive(self, params: dict) -> bool:
        cmd = params.get("command", "")
        return _is_dangerous_command(cmd)

    def describe_action(self, params: dict) -> str:
        return f"执行命令: `{params.get('command', '')[:60]}`"

    def get_paths(self, params: dict) -> list[str]:
        """
        提取路径列表用于沙盒检查。
        对于启动应用类命令（start/taskkill），cwd 不纳入检查。
        对于 cwd="." 等占位符，直接跳过。
        """
        paths = []
        cwd = params.get("cwd", "")
        cmd = params.get("command", "").strip().lower()

        # cwd 是否需要沙盒检查
        if cwd and cwd.strip() not in (".", "", ".\\", "./"):
            # 启动/关闭应用类命令，不需要检查 cwd
            is_app_cmd = (
                cmd.startswith("start ") or
                cmd.startswith("taskkill ") or
                cmd.startswith("cmd /k") or
                cmd.startswith("cmd /c")
            )
            if not is_app_cmd:
                paths.append(cwd)

        # 其他路径字段
        for k in ("source", "destination", "path"):
            if k in params and params[k]:
                paths.append(params[k])

        return paths

    def execute(self, params: dict, ctx: ToolContext = None) -> dict:
        command = params.get("command", "")
        cwd = params.get("cwd")
        timeout = params.get("timeout", 30)

        try:
            cmd_stripped = command.strip().lower()
            # 检测需要在新终端窗口中运行的命令
            is_interactive = (
                cmd_stripped.endswith('.exe') or
                cmd_stripped.startswith('python ') or
                cmd_stripped.startswith('python3 ') or
                cmd_stripped.startswith('node ') or
                cmd_stripped.startswith('npm ') or
                cmd_stripped.startswith('java ') or
                cmd_stripped.startswith('dotnet ') or
                (cmd_stripped.startswith('cmd /c') or cmd_stripped.startswith('cmd /k'))
                and cmd_stripped.endswith('.exe')
            )

            # start 命令用于启动应用，不应阻塞等待
            is_start_cmd = cmd_stripped.startswith('start ')

            if is_start_cmd:
                # start 命令：非阻塞启动，立即返回
                subprocess.Popen(command, shell=True, cwd=cwd)
                app_name = command.split()[-1] if command.split() else command
                return {"success": True, "message": f"已启动: {app_name}"}
            elif is_interactive:
                start_cmd = f'start "LocalMindDesk" cmd /k "chcp 65001 >nul && cd /d {cwd or "."} && {command}"'
                subprocess.Popen(start_cmd, shell=True, cwd=cwd)
                return {"success": True, "message": "程序已在新终端窗口中启动"}
            else:
                result = subprocess.run(
                    command, shell=True, capture_output=True, text=True,
                    cwd=cwd, timeout=timeout,
                    encoding="utf-8", errors="replace",
                )
                res = {
                    "success": result.returncode == 0,
                    "stdout": result.stdout[:5000],
                    "stderr": result.stderr[:2000],
                    "return_code": result.returncode,
                }
                if result.returncode != 0:
                    res["error"] = result.stderr[:500] or f"命令退出码: {result.returncode}"
                return res
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"命令超时（{timeout}s）"}
        except Exception as e:
            return {"success": False, "error": str(e)}
