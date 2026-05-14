"""
LocalMindDesk — 上下文管理器 (Context Manager)
三层记忆组装中枢：L1 前端快照 ← L2 滑动窗口 ← L3 向量召回
"""
import re
from app.memory import (
    get_hot_context, get_cold_messages, mark_archived,
    estimate_tokens, list_sessions, get_session_messages,
    MAX_CONTEXT_TOKENS,
)
from app.vector_memory import archive_to_vector, recall_memories
from app.agent_profile import load_profile

# Token 预算分配
SYSTEM_PROMPT_BUDGET = 400   # system prompt
COLD_RECALL_BUDGET = 300     # L3 冷记忆召回
HOT_WINDOW_BUDGET = MAX_CONTEXT_TOKENS  # L2 热窗口


# ============================================================
#  Prompt 组装（核心）
# ============================================================
def assemble_prompt(session_id: str, user_message: str) -> tuple[str, list[dict]]:
    """
    组装完整 Prompt，严格控制 Token 总量
    
    返回 (system_prompt, messages)
    
    总 Token ≤ SYSTEM_PROMPT_BUDGET + COLD_RECALL_BUDGET + HOT_WINDOW_BUDGET
             ≈ 400 + 300 + 3500 = 4200 tokens (安全线)
    """
    # 1. System Prompt (L1 — 从 Agent Profile)
    profile = load_profile()
    sys_prompt = profile.get("identity", {}).get("system_prompt", "你是 LocalMindDesk，一个高效的 AI 助手。")
    behavior = profile.get("behavior", {})
    sys_prompt += f"\n[行为设定] 风格:{behavior.get('response_style','balanced')}, 长度:{behavior.get('response_length','medium')}"

    # Token 截断 system prompt
    sys_tokens = estimate_tokens(sys_prompt)
    if sys_tokens > SYSTEM_PROMPT_BUDGET:
        # 粗暴截断（保留前 N 个字符）
        ratio = SYSTEM_PROMPT_BUDGET / sys_tokens
        sys_prompt = sys_prompt[:int(len(sys_prompt) * ratio)]

    # 2. L3 冷记忆召回
    cold_results = recall_memories(user_message, top_k=3)
    if cold_results:
        cold_text_parts = []
        cold_tokens = 0
        for mem in cold_results:
            t = mem["text"][:150]
            tok = estimate_tokens(t)
            if cold_tokens + tok > COLD_RECALL_BUDGET:
                break
            cold_text_parts.append(f"- {t}")
            cold_tokens += tok
        if cold_text_parts:
            sys_prompt += "\n\n[历史记忆（自动召回）]\n" + "\n".join(cold_text_parts)

    # 3. 长期记忆（手动记忆）
    from app.memory import get_memory_text
    memo = get_memory_text()
    if memo:
        memo_tokens = estimate_tokens(memo)
        if memo_tokens <= 200:  # 不超过 200 tokens
            sys_prompt += f"\n\n[长期记忆]\n{memo}"

    # 4. L2 热窗口
    hot = get_hot_context(session_id, max_tokens=HOT_WINDOW_BUDGET)
    messages = [{"role": m["role"], "content": m["content"]} for m in hot]

    # 5. Token 总量检查
    total = estimate_tokens(sys_prompt) + sum(m.get("token_count", estimate_tokens(m["content"])) for m in hot)
    print(f"[Context] 总 Token ≈ {total} (sys:{estimate_tokens(sys_prompt)} + hot:{total - estimate_tokens(sys_prompt)})")

    return sys_prompt, messages


# ============================================================
#  冷数据自动归档（滑动窗口溢出 → L3）
# ============================================================
def auto_archive(session_id: str):
    """
    检查冷数据，自动归档到向量库
    每次对话后调用
    """
    cold = get_cold_messages(session_id)
    if not cold:
        return

    # 只归档未归档的冷消息
    to_archive = [m for m in cold if not m.get("archived")]
    if not to_archive:
        return

    # 归档到 L3 向量库
    archive_to_vector(to_archive)

    # 标记为已归档
    ids = [m["id"] for m in to_archive]
    mark_archived(ids)
    print(f"[Context] 自动归档 {len(ids)} 条冷消息到 L3")


# ============================================================
#  冷启动恢复
# ============================================================
def get_boot_context() -> dict:
    """
    开机恢复数据包 — 前端 GET /api/boot 调用
    返回上次状态的完整快照
    """
    profile = load_profile()

    # 获取最近的会话
    sessions = list_sessions(limit=20)
    last_session = None
    hot_context = []

    if sessions:
        last_sid = sessions[0]["id"]
        last_session = {
            "id": last_sid,
            "title": sessions[0]["title"],
        }
        # 加载热上下文
        hot = get_hot_context(last_sid)
        hot_context = [{"role": m["role"], "content": m["content"]} for m in hot]

    return {
        "profile": {
            "identity": profile.get("identity", {}),
            "ui_preferences": profile.get("ui_preferences", {}),
            "behavior": profile.get("behavior", {}),
        },
        "lastSession": last_session,
        "hotContext": hot_context,
        "sessions": sessions[:10],
        "vectorMemoryCount": _get_vector_count(),
    }


def _get_vector_count() -> int:
    try:
        from app.vector_memory import get_vector_store
        return get_vector_store().count()
    except:
        return 0
