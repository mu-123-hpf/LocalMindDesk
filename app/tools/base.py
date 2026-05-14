"""
LocalMindDesk — BaseTool 抽象基类 + ToolContext 统一上下文
所有 Tool 继承 BaseTool，通过标准接口注册到 Registry
"""
from __future__ import annotations
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolContext:
    """统一上下文对象，每次工具调用时传入"""
    workspace_path: str | None = None
    session_id: str | None = None
    model_name: str = ""
    file_cache: dict = field(default_factory=dict)


@dataclass
class ToolResult:
    """标准化的工具执行结果"""
    success: bool
    message: str = ""
    error: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {"success": self.success}
        if self.message:
            d["message"] = self.message
        if self.error:
            d["error"] = self.error
        d.update(self.data)
        return d


class BaseTool(ABC):
    """
    所有工具的抽象基类。
    借鉴业界主流 Tool 接口设计:
    - name: 工具唯一标识
    - description: 工具描述
    - danger_level: 默认危险等级（safe/moderate/critical）
    - validate(): 参数验证
    - check_permissions(): 权限检查（返回是否需确认）
    - execute(): 执行工具
    - is_read_only(): 是否只读操作
    - describe_action(): 人类可读的操作描述
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一标识，如 'shell_exec', 'file_op' 等"""
        ...

    @property
    def description(self) -> str:
        """工具描述"""
        return ""

    @property
    def danger_level(self) -> str:
        """默认危险等级: safe / moderate / critical"""
        return "critical"

    def get_danger_level(self, params: dict) -> str:
        """根据具体参数返回危险等级（子类可覆盖）"""
        return self.danger_level

    def validate(self, params: dict, ctx: ToolContext = None) -> tuple[bool, str]:
        """
        参数验证。返回 (ok, error_msg)
        默认通过
        """
        return True, ""

    def check_permissions(self, params: dict, ctx: ToolContext = None) -> dict:
        """
        权限检查。返回 {"level": "safe/moderate/critical", "reason": "", "blocked": False}
        默认使用 danger_level
        """
        return {
            "level": self.get_danger_level(params),
            "reason": "",
            "blocked": False,
        }

    @abstractmethod
    def execute(self, params: dict, ctx: ToolContext = None) -> dict:
        """
        执行工具，返回结果字典
        最少包含 {"success": True/False}
        """
        ...

    def is_read_only(self, params: dict) -> bool:
        """是否只读操作"""
        return False

    def is_destructive(self, params: dict) -> bool:
        """是否破坏性操作（不可逆）"""
        return False

    def describe_action(self, params: dict) -> str:
        """人类可读的操作描述，用于确认弹窗"""
        return f"{self.name}: {params}"

    def get_paths(self, params: dict) -> list[str]:
        """提取参数中的路径列表，用于沙盒检查"""
        paths = []
        for k in ("source", "destination", "path", "cwd"):
            if k in params and params[k]:
                paths.append(params[k])
        return paths
