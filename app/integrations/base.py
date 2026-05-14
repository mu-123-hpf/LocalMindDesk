"""
LocalMindDesk — BaseIntegration 抽象基类
所有外部应用集成（微信、邮件、钉钉等）继承此类
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConfigField:
    """集成配置字段定义"""
    key: str            # 字段 key
    label: str          # 显示名称
    type: str = "text"  # text / password / path / select / toggle
    default: Any = ""   # 默认值
    required: bool = False
    placeholder: str = ""
    options: list = field(default_factory=list)  # select 类型的选项


class BaseIntegration(ABC):
    """
    外部应用集成基类。
    每个集成模块需实现:
    - id/name/icon/description: 元信息
    - config_schema: 需要用户配置的字段
    - connect/disconnect: 连接管理
    - test_connection: 连接测试
    - get_tools: 返回该集成提供的工具
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """唯一标识，如 'wechat', 'email'"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """显示名称，如 '微信'"""
        ...

    @property
    def icon(self) -> str:
        """图标 emoji"""
        return "🔌"

    @property
    def description(self) -> str:
        """功能描述"""
        return ""

    @property
    def config_schema(self) -> list[ConfigField]:
        """需要用户配置的字段列表"""
        return []

    @abstractmethod
    def connect(self, config: dict) -> dict:
        """
        连接/初始化集成
        返回 {"success": True/False, "message": "..."}
        """
        ...

    @abstractmethod
    def disconnect(self) -> dict:
        """断开连接"""
        ...

    @abstractmethod
    def test_connection(self, config: dict) -> dict:
        """
        测试连接
        返回 {"success": True/False, "message": "..."}
        """
        ...

    @abstractmethod
    def get_tools(self) -> list:
        """返回该集成提供的 BaseTool 实例列表"""
        ...

    @property
    def install_commands(self) -> list[dict]:
        """
        安装依赖的命令模板列表。
        每个命令是一个 dict:
        {
            "cmd": "pip install httpx",          # 要执行的命令
            "label": "安装 httpx",               # 显示给用户的描述
            "required": True,                    # 是否必须成功
            "fallback": "pip install httpx==0.28" # 备选命令（可选）
        }
        """
        return []

    def auto_detect(self) -> dict:
        """
        自动检测应用安装位置等信息
        返回 {"found": True/False, "path": "...", "info": "..."}
        """
        return {"found": False, "path": "", "info": "未实现自动检测"}

    def to_dict(self, config: dict = None, enabled: bool = False,
                connected: bool = False) -> dict:
        """序列化为前端可用的字典"""
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "description": self.description,
            "enabled": enabled,
            "connected": connected,
            "config_schema": [
                {
                    "key": f.key,
                    "label": f.label,
                    "type": f.type,
                    "default": f.default,
                    "required": f.required,
                    "placeholder": f.placeholder,
                    "options": f.options,
                }
                for f in self.config_schema
            ],
            "config": config or {},
            "install_commands": self.install_commands,
        }
