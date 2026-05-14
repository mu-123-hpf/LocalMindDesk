"""
LocalMindDesk — Agent Profile（智能体配置核心）
所有可进化的状态维度：身份 / 模型路由 / UI / 行为
"""
import json
import os
import copy
from datetime import datetime
from typing import Any, Optional

PROFILE_PATH = "data/agent_profile.json"

DEFAULT_PROFILE = {
    "version": "2.0",

    # ── 身份 ──
    "identity": {
        "name": "LocalMindDesk",
        "icon": "🧠",
        "role": "通用 AI 助手",
        "description": "高效的本地 AI 助手，擅长编程、写作、分析和创作。",
        "personality_traits": ["professional", "concise", "helpful"],
        "system_prompt": (
            "你是 LocalMindDesk，一个高效的 AI 助手。"
            "回答问题时直接切入要点，不废话。"
            "你能制作 PPT、写文档、联网搜索。"
        ),
    },

    # ── 模型路由 ──
    "model_routing": {
        "default_model": "local-lmstudio",
        "task_rules": [
            {"task_type": "coding",    "preferred_model": "local-lmstudio", "temperature": 0.2, "max_tokens": 8192, "priority": 1},
            {"task_type": "creative",  "preferred_model": "local-lmstudio", "temperature": 0.9, "max_tokens": 4096, "priority": 2},
            {"task_type": "analysis",  "preferred_model": "local-lmstudio", "temperature": 0.3, "max_tokens": 4096, "priority": 3},
        ],
        "fallback_chain": ["local-lmstudio"],
        "auto_route": True,
    },

    # ── UI 偏好 ──
    "ui_preferences": {
        "theme": "dark",
        "accent_hue": 220,
        "accent_color": "#3b82f6",
        "font_size": 14,
        "code_theme": "github-dark-dimmed",
        "message_style": "bubble",
        "sidebar_visible": True,
    },

    # ── 行为模式 ──
    "behavior": {
        "response_style": "balanced",
        "response_length": "medium",
        "language": "zh-CN",
        "auto_search": False,
        "auto_memo": False,
        "max_context_messages": 20,
        "greeting": "你好！有什么可以帮你的？",
    },

    # ── 进化日志 ──
    "evolution_log": [],
    "updated_at": None,
}


# ============================================================
#  持久化
# ============================================================
def load_profile() -> dict:
    if os.path.exists(PROFILE_PATH):
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Profile] 加载失败: {e}")
    p = copy.deepcopy(DEFAULT_PROFILE)
    save_profile(p)
    return p


def save_profile(profile: dict):
    os.makedirs("data", exist_ok=True)
    profile["updated_at"] = datetime.now().isoformat()
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


# ============================================================
#  Dot-path 读写
# ============================================================
def _get_nested(d: dict, path: str) -> Any:
    """按 dot-path 读取值: 'identity.name' → d['identity']['name']"""
    keys = path.split(".")
    for k in keys:
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return None
    return d


def _set_nested(d: dict, path: str, value: Any):
    """按 dot-path 设置值"""
    keys = path.split(".")
    for k in keys[:-1]:
        if k not in d or not isinstance(d[k], dict):
            d[k] = {}
        d = d[k]
    d[keys[-1]] = value


# ============================================================
#  增量合并
# ============================================================
VALID_PATHS = {
    "identity.name", "identity.icon", "identity.role",
    "identity.description", "identity.personality_traits",
    "identity.system_prompt",
    "model_routing.default_model", "model_routing.task_rules",
    "model_routing.fallback_chain", "model_routing.auto_route",
    "ui_preferences.theme", "ui_preferences.accent_hue",
    "ui_preferences.accent_color", "ui_preferences.font_size",
    "ui_preferences.code_theme", "ui_preferences.message_style",
    "ui_preferences.sidebar_visible",
    "behavior.response_style", "behavior.response_length",
    "behavior.language", "behavior.auto_search",
    "behavior.auto_memo", "behavior.max_context_messages",
    "behavior.greeting",
}


def validate_delta(delta: dict) -> tuple[dict, list[str]]:
    """校验 delta，返回 (合法部分, 错误列表)"""
    valid = {}
    errors = []
    for path, value in delta.items():
        if path in VALID_PATHS:
            valid[path] = value
        else:
            errors.append(f"未知字段: {path}")
    return valid, errors


def merge_delta(profile: dict, delta: dict, trigger: str = "") -> dict:
    """
    增量合并 delta 到 profile
    delta 格式: {"identity.name": "新名称", "ui_preferences.accent_hue": 120}
    """
    valid_delta, errors = validate_delta(delta)
    if errors:
        print(f"[Profile] 校验警告: {errors}")

    for path, value in valid_delta.items():
        _set_nested(profile, path, value)

    # 追加进化日志
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "trigger": trigger[:200] if trigger else "manual",
        "changes_summary": ", ".join(f"{k}→{str(v)[:30]}" for k, v in valid_delta.items()),
        "delta_applied": valid_delta,
    }
    if "evolution_log" not in profile:
        profile["evolution_log"] = []
    profile["evolution_log"].append(log_entry)
    # 只保留最近 50 条
    profile["evolution_log"] = profile["evolution_log"][-50:]

    save_profile(profile)
    print(f"[Profile] 已合并 {len(valid_delta)} 项变更")
    return profile


# ============================================================
#  任务级路由
# ============================================================
def get_routing_for_task(task_type: str) -> Optional[dict]:
    """根据任务类型返回模型偏好"""
    profile = load_profile()
    routing = profile.get("model_routing", {})
    if not routing.get("auto_route"):
        return None
    for rule in routing.get("task_rules", []):
        if rule.get("task_type") == task_type:
            return rule
    return None


def get_effective_system_prompt(extra: str = "") -> str:
    """获取当前生效的 system prompt"""
    profile = load_profile()
    prompt = profile.get("identity", {}).get("system_prompt", "")
    if extra:
        prompt += "\n\n" + extra
    return prompt


def reset_profile() -> dict:
    """重置为默认"""
    p = copy.deepcopy(DEFAULT_PROFILE)
    save_profile(p)
    return p
