"""
LocalMindDesk — Meta-Agent（元智能体）
系统灵魂：解析用户自然语言配置需求 → 输出结构化 JSON Delta
"""
import json
import re
from app import llm_provider
from app.agent_profile import load_profile, merge_delta, validate_delta
from app.prompt_loader import load_agent_prompt

# ============================================================
#  元智能体 System Prompt（从 .agents/meta_agent.md 加载）
# ============================================================
def _get_meta_prompt() -> str:
    prompt = load_agent_prompt("meta_agent")
    return prompt or "你是配置助手。分析用户需求，输出 JSON 配置增量。"


# ============================================================
#  配置意图检测
# ============================================================
CONFIG_KEYWORDS = [
    # 身份切换
    "你是", "你现在是", "从现在起你是", "变成", "扮演", "角色",
    "你的身份", "设定为", "切换为",
    # UI 配置
    "界面", "颜色", "主题", "字号", "字体", "布局", "风格",
    "暗色", "亮色", "极客", "绿色", "蓝色", "紫色", "红色",
    # 行为配置
    "回答更", "简短", "详细", "简洁", "学术", "口语",
    "默认", "模型", "自动搜索", "自动记忆",
    # 英文
    "act as", "you are", "become", "theme", "style",
]


def detect_config_intent(message: str) -> bool:
    """快速检测是否包含配置意图（关键词匹配）"""
    lower = message.lower()

    # 排除：疑问句式（"你是xxx吗/嘛/呢？"）不是配置意图
    if re.search(r'你是.{0,10}[吗嘛呢？\?]', lower):
        return False

    score = sum(1 for kw in CONFIG_KEYWORDS if kw in lower)
    # 需要至少命中 2 个关键词才触发（降低误判）
    return score >= 2


# ============================================================
#  调用 Meta-Agent 解析
# ============================================================
def parse_config_request(user_message: str) -> dict:
    """
    调用 LLM 解析配置需求，返回 JSON Delta
    失败时返回空字典
    """
    # 获取当前 profile 摘要作为上下文
    profile = load_profile()
    context = (
        f"当前身份: {profile.get('identity', {}).get('name', 'LocalMindDesk')} "
        f"({profile.get('identity', {}).get('role', '')})\n"
        f"当前模型: {profile.get('model_routing', {}).get('default_model', '')}\n"
        f"当前风格: {profile.get('behavior', {}).get('response_style', '')}"
    )

    prompt = f"{context}\n\n用户配置需求：{user_message}"

    reply = llm_provider.chat(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=_get_meta_prompt(),
        temperature=0.2,
        max_tokens=1200,
    )

    # 解析 JSON
    reply = reply.strip()
    if reply.startswith("```"):
        lines = reply.split("\n")
        reply = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    reply = reply.strip()

    try:
        delta = json.loads(reply)
        if isinstance(delta, dict):
            return delta
    except json.JSONDecodeError:
        m = re.search(r'\{[\s\S]*\}', reply)
        if m:
            try:
                return json.loads(m.group())
            except:
                pass

    try:
        print(f"[Meta-Agent] 解析失败: {reply[:100]}")
    except UnicodeEncodeError:
        print(f"[Meta-Agent] 解析失败 (含特殊字符)")
    return {}


# ============================================================
#  端到端执行
# ============================================================
def apply_evolution(user_message: str) -> dict:
    """
    完整闭环：解析 → 校验 → 合并 → 保存
    返回 {"success": bool, "delta": {...}, "profile": {...}, "summary": "..."}
    """
    # 1. 解析
    delta = parse_config_request(user_message)
    if not delta:
        return {"success": False, "summary": "无法理解配置需求"}

    # 2. 校验
    valid_delta, errors = validate_delta(delta)
    if not valid_delta:
        return {"success": False, "summary": f"无有效配置项。{'; '.join(errors)}"}

    # 3. 合并
    profile = load_profile()
    updated_profile = merge_delta(profile, valid_delta, trigger=user_message)

    # 4. 生成摘要
    changes = []
    for path, value in valid_delta.items():
        field = path.split(".")[-1]
        if isinstance(value, str) and len(value) > 30:
            changes.append(f"{field} 已更新")
        else:
            changes.append(f"{field} → {value}")
    summary = "、".join(changes)

    try:
        print(f"[Meta-Agent] 进化完成: {summary}")
    except UnicodeEncodeError:
        print(f"[Meta-Agent] 进化完成 (含特殊字符)")

    return {
        "success": True,
        "delta": valid_delta,
        "profile": updated_profile,
        "summary": summary,
    }
