"""
LocalMindDesk — SearchTool
代码搜索工具：grep（内容搜索）+ glob（文件名搜索）
新增工具，借鉴 Claude Code 的 GrepTool 和 GlobTool
"""
import os
import re
import subprocess
from app.tools.base import BaseTool, ToolContext


class SearchTool(BaseTool):
    """代码搜索工具 — grep + find"""

    @property
    def name(self) -> str:
        return "code_search"

    @property
    def description(self) -> str:
        return "代码搜索（按内容 grep / 按文件名 find）"

    @property
    def danger_level(self) -> str:
        return "safe"

    def is_read_only(self, params: dict) -> bool:
        return True

    def describe_action(self, params: dict) -> str:
        action = params.get("action", "grep")
        pattern = params.get("pattern", "")
        return f"搜索: {action} '{pattern}'"

    def execute(self, params: dict, ctx: ToolContext = None) -> dict:
        action = params.get("action", "grep")
        pattern = params.get("pattern", "")
        search_path = params.get("path", "")

        if not pattern:
            return {"success": False, "error": "未指定搜索模式 (pattern)"}

        # 确定搜索路径
        if not search_path:
            if ctx and ctx.workspace_path:
                search_path = ctx.workspace_path
            else:
                return {"success": False, "error": "未指定搜索路径，且无工作区"}

        if not os.path.exists(search_path):
            return {"success": False, "error": f"路径不存在: {search_path}"}

        if action == "grep":
            return self._grep(pattern, search_path, params)
        elif action == "find":
            return self._find(pattern, search_path, params)
        else:
            return {"success": False, "error": f"未知搜索类型: {action}，支持 grep / find"}

    def _grep(self, pattern: str, search_path: str, params: dict) -> dict:
        """按内容搜索（递归 grep）"""
        max_results = params.get("max_results", 50)
        case_insensitive = params.get("case_insensitive", True)
        include = params.get("include", "")  # 文件类型过滤，如 "*.py"

        # 排除常见二进制/缓存目录
        exclude_dirs = {'.git', '__pycache__', 'node_modules', '.venv',
                        'venv', 'dist', 'build', '.idea', '.vs'}

        results = []
        try:
            flags = re.IGNORECASE if case_insensitive else 0
            compiled = re.compile(pattern, flags)
        except re.error as e:
            # pattern 不是合法正则，当作纯文本搜索
            compiled = None

        try:
            for root, dirs, files in os.walk(search_path):
                # 排除目录
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                depth = root.replace(search_path, '').count(os.sep)
                if depth > 5:
                    dirs.clear()
                    continue

                for fname in files:
                    # 文件类型过滤
                    if include:
                        from fnmatch import fnmatch
                        if not fnmatch(fname, include):
                            continue

                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                            for i, line in enumerate(f, 1):
                                matched = False
                                if compiled:
                                    matched = compiled.search(line)
                                else:
                                    if case_insensitive:
                                        matched = pattern.lower() in line.lower()
                                    else:
                                        matched = pattern in line

                                if matched:
                                    rel = os.path.relpath(fpath, search_path)
                                    results.append({
                                        "file": rel,
                                        "line": i,
                                        "content": line.rstrip()[:200],
                                    })
                                    if len(results) >= max_results:
                                        break
                        if len(results) >= max_results:
                            break
                    except (OSError, UnicodeDecodeError):
                        continue
                if len(results) >= max_results:
                    break

            return {
                "success": True,
                "matches": results,
                "count": len(results),
                "truncated": len(results) >= max_results,
                "message": f"找到 {len(results)} 处匹配",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _find(self, pattern: str, search_path: str, params: dict) -> dict:
        """按文件名搜索"""
        max_results = params.get("max_results", 50)
        exclude_dirs = {'.git', '__pycache__', 'node_modules', '.venv',
                        'venv', 'dist', 'build', '.idea', '.vs'}

        results = []
        try:
            from fnmatch import fnmatch
            for root, dirs, files in os.walk(search_path):
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                depth = root.replace(search_path, '').count(os.sep)
                if depth > 5:
                    dirs.clear()
                    continue

                for fname in files:
                    if fnmatch(fname.lower(), pattern.lower()):
                        rel = os.path.relpath(os.path.join(root, fname), search_path)
                        results.append(rel)
                        if len(results) >= max_results:
                            break
                if len(results) >= max_results:
                    break

            return {
                "success": True,
                "files": results,
                "count": len(results),
                "truncated": len(results) >= max_results,
                "message": f"找到 {len(results)} 个文件",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
