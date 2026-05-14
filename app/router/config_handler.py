"""
Config Handler — Meta-Agent 配置进化
"""
from app.meta_agent import apply_evolution
from .activity import _add_activity


def exec_config(user_message: str) -> dict:
    """Meta-Agent: 配置进化"""
    _add_activity("Meta-Agent", "working", "正在解析配置需求...")
    result = apply_evolution(user_message)
    if result["success"]:
        profile = result["profile"]
        identity = profile.get("identity", {})
        _add_activity("Meta-Agent", "done", f"已进化为「{identity.get('name', '')}」",
                      "profile_update", result.get("delta"))
        return {
            "agent": "Meta-Agent",
            "reply": f"{identity.get('icon', '🎭')} **已进化为「{identity.get('name', '')}」**\n> {identity.get('role', '')}\n📋 变更：{result['summary']}",
            "profile_update": True,
            "profile_snapshot": {
                "identity": identity,
                "ui_preferences": profile.get("ui_preferences", {}),
                "behavior": profile.get("behavior", {}),
            },
        }
    return {"agent": "Meta-Agent", "reply": ""}
