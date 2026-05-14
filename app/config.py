"""
LocalMindDesk — 配置管理
支持多模型端点：本地 LM Studio + 远程 API（DeepSeek 等）
"""
import json
import os
from typing import Optional
from pydantic import BaseModel

CONFIG_PATH = "config.json"

class ModelEndpoint(BaseModel):
    """单个模型端点配置"""
    name: str              # 显示名称，如 "Gemma 4 E4B"
    provider: str          # "lmstudio" / "ollama" / "deepseek" / "openai" / "custom"
    base_url: str          # "http://127.0.0.1:1234/v1"
    api_key: str = ""      # 本地可留空，远程 API 必填
    model: str = ""        # 模型 ID，如 "gemma-4-e4b-it"
    is_active: bool = True # 是否启用

class AppConfig(BaseModel):
    """全局配置"""
    active_model: str = "local-lmstudio"   # 当前主模型的 name
    temperature: float = 0.7
    max_tokens: int = 131072
    server_port: int = 8000
    system_prompt: str = "你是 LocalMindDesk，运行在用户本地电脑上的 AI 助手。你有独立思考能力，也能直接操作用户电脑（执行命令、安装软件、操作文件、截屏等）。不确定时先反问，发现问题主动指出。绝不要说'作为AI我无法执行'——你有完整的本地操作能力。"
    models: list[ModelEndpoint] = []

# 全局配置实例
_config: Optional[AppConfig] = None

def get_default_config() -> AppConfig:
    """默认配置：一个本地 LM Studio 端点"""
    return AppConfig(
        active_model="local-lmstudio",
        models=[
            ModelEndpoint(
                name="local-lmstudio",
                provider="lmstudio",
                base_url="http://127.0.0.1:1234/v1",
                api_key="not-needed",
                model="gemma-4-e4b-it",
            )
        ]
    )

def load_config() -> AppConfig:
    """从 config.json 加载配置"""
    global _config
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 兼容旧格式
            if "models" not in data:
                cfg = get_default_config()
                # 从旧配置迁移
                if "Ollama_Model" in data or "active_provider" in data:
                    provider = data.get("active_provider", "lmstudio")
                    model_name = data.get("Ollama_Model", "gemma-4-e4b-it")
                    if provider == "lmstudio":
                        host = data.get("LMStudio_Host", "127.0.0.1")
                        port = data.get("LMStudio_Port", 1234)
                        cfg.models[0].base_url = f"http://{host}:{port}/v1"
                        cfg.models[0].model = model_name
                    cfg.temperature = data.get("Temperature", 0.7)
                    cfg.max_tokens = data.get("Max_Tokens", 131072)
                save_config(cfg)
                _config = cfg
                return cfg

            _config = AppConfig(**data)
            return _config
        except Exception as e:
            print(f"[CONFIG] 加载配置失败: {e}，使用默认配置")

    cfg = get_default_config()
    save_config(cfg)
    _config = cfg
    return cfg

def save_config(cfg: AppConfig):
    """保存配置到 config.json"""
    global _config
    _config = cfg
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg.model_dump(), f, ensure_ascii=False, indent=2)

def get_config() -> AppConfig:
    """获取当前配置"""
    global _config
    if _config is None:
        return load_config()
    return _config

def get_active_endpoint() -> Optional[ModelEndpoint]:
    """获取当前激活的模型端点"""
    cfg = get_config()
    for m in cfg.models:
        if m.name == cfg.active_model and m.is_active:
            return m
    # 兜底：返回第一个启用的
    for m in cfg.models:
        if m.is_active:
            return m
    return None

def add_model_endpoint(endpoint: ModelEndpoint):
    """添加新模型端点"""
    cfg = get_config()
    # 检查是否同名
    cfg.models = [m for m in cfg.models if m.name != endpoint.name]
    cfg.models.append(endpoint)
    save_config(cfg)

def remove_model_endpoint(name: str):
    """删除模型端点"""
    cfg = get_config()
    cfg.models = [m for m in cfg.models if m.name != name]
    if cfg.active_model == name and cfg.models:
        cfg.active_model = cfg.models[0].name
    save_config(cfg)

def set_active_model(name: str) -> bool:
    """切换主模型"""
    cfg = get_config()
    for m in cfg.models:
        if m.name == name:
            cfg.active_model = name
            save_config(cfg)
            return True
    return False

def get_endpoint_by_name(name: str) -> Optional[ModelEndpoint]:
    """根据名称获取模型端点"""
    if not name:
        return None
    cfg = get_config()
    for m in cfg.models:
        if m.name == name and m.is_active:
            return m
    return None
