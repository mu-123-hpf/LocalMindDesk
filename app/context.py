"""
LocalMindDesk — 统一上下文管理器
借鉴业界主流 ToolUseContext + context.ts 设计

统一管理会话状态：工作区、历史、文件缓存、模型配置等。
所有 Agent / Tool 调用时共用同一个 Context 实例。
"""
from __future__ import annotations
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SessionContext:
    """
    统一会话上下文 — 每次用户发消息时创建/更新

    借鉴业界主流 ToolUseContext:
    - workspace_path: 当前工作区
    - messages: 完整消息历史
    - system_prompt: 系统提示词
    - model_name: 当前模型
    - session_id: 会话 ID
    - file_cache: 文件内容缓存（避免重复读取）
    - tool_decisions: 本轮工具决策记录
    - token_usage: token 使用估算
    """
    workspace_path: str | None = None
    messages: list[dict] = field(default_factory=list)
    system_prompt: str = ""
    model_name: str = ""
    session_id: str | None = None
    user_message: str = ""

    # 文件缓存（路径 → 内容），避免同一轮对话中多次读取同一文件
    file_cache: dict[str, str] = field(default_factory=dict)

    # 本轮工具决策记录
    tool_decisions: list[dict] = field(default_factory=list)

    # token 使用估算
    token_usage: dict = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    })

    # 会话开始时间
    start_time: float = field(default_factory=time.time)

    # 工作区文件信息（延迟加载）
    _workspace_info: dict | None = field(default=None, repr=False)

    def estimate_context_tokens(self) -> int:
        """估算当前上下文的 token 数（粗略：每4字符≈1 token）"""
        total_chars = len(self.system_prompt)
        for msg in self.messages:
            content = msg.get("content", "")
            total_chars += len(content)
        return total_chars // 4

    def get_recent_messages(self, n: int = 20) -> list[dict]:
        """获取最近 n 条消息"""
        return self.messages[-n:] if self.messages else []

    def get_workspace_info(self) -> dict:
        """获取工作区信息（延迟加载 + 缓存）"""
        if self._workspace_info is not None:
            return self._workspace_info

        if not self.workspace_path or not os.path.isdir(self.workspace_path):
            self._workspace_info = {"exists": False}
            return self._workspace_info

        # 统计工作区基本信息
        file_count = 0
        dir_count = 0
        total_size = 0
        file_types = {}
        exclude = {'.git', '__pycache__', 'node_modules', '.venv', 'venv',
                    'dist', 'build', '.idea', '.vs'}

        for root, dirs, files in os.walk(self.workspace_path):
            dirs[:] = [d for d in dirs if d not in exclude]
            depth = root.replace(self.workspace_path, '').count(os.sep)
            if depth > 3:
                dirs.clear()
                continue
            dir_count += len(dirs)
            for f in files:
                file_count += 1
                ext = os.path.splitext(f)[1].lower()
                file_types[ext] = file_types.get(ext, 0) + 1
                try:
                    total_size += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass

        # 按数量排序的文件类型
        top_types = sorted(file_types.items(), key=lambda x: -x[1])[:5]

        self._workspace_info = {
            "exists": True,
            "path": self.workspace_path,
            "file_count": file_count,
            "dir_count": dir_count,
            "total_size_mb": round(total_size / 1024 / 1024, 1),
            "top_file_types": top_types,
        }
        return self._workspace_info

    def add_tool_decision(self, tool: str, params: dict, result: dict):
        """记录工具决策"""
        self.tool_decisions.append({
            "tool": tool,
            "params": {k: str(v)[:80] for k, v in params.items()},
            "success": result.get("success", False),
            "time": time.time(),
        })

    def cache_file(self, path: str, content: str):
        """缓存文件内容"""
        norm = os.path.normpath(path)
        self.file_cache[norm] = content
        # 限制缓存大小
        if len(self.file_cache) > 20:
            oldest = next(iter(self.file_cache))
            del self.file_cache[oldest]

    def get_cached_file(self, path: str) -> str | None:
        """获取缓存的文件内容"""
        return self.file_cache.get(os.path.normpath(path))


# ============================================================
#  全局会话上下文管理
# ============================================================
_current_context: SessionContext | None = None


def get_context() -> SessionContext:
    """获取当前会话上下文（如果没有则创建空的）"""
    global _current_context
    if _current_context is None:
        _current_context = SessionContext()
    return _current_context


def create_context(
    user_message: str,
    history: list[dict],
    system_prompt: str,
    workspace_path: str = None,
    model_name: str = "",
) -> SessionContext:
    """
    为新的用户消息创建/更新会话上下文
    每次 route() 调用时调用此函数
    """
    global _current_context
    _current_context = SessionContext(
        workspace_path=workspace_path,
        messages=history,
        system_prompt=system_prompt,
        model_name=model_name,
        user_message=user_message,
    )
    return _current_context
