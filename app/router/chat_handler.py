"""
Chat Handler — 普通聊天（通过 ModelRouter 智能路由）
"""
from app import llm_provider
from app.compact import get_compactor
from .activity import _add_activity


def exec_chat(user_message: str, history: list, sys_prompt: str) -> dict:
    """Chat-Agent: 普通聊天（通过 ModelRouter 智能路由）"""
    # 自动压缩过长的对话历史
    compactor = get_compactor()
    effective_history = compactor.compact(history) if compactor.should_compact(history) else history
    messages = effective_history[-20:] + [{"role": "user", "content": user_message}]

    # ★ v3.0: 通过 ModelRouter 智能路由（敏感度评估 → 自动选模型）
    try:
        from app.privacy_filter import get_model_router
        router = get_model_router()
        result = router.route_and_call(
            messages=messages,
            system_prompt=sys_prompt,
        )
        reply = result.get("reply", "")
        route_info = {
            "model_used": result.get("model_used", ""),
            "route": result.get("route", ""),
            "sensitivity": result.get("sensitivity", "safe"),
            "sanitized": result.get("sanitized", False),
        }
        _add_activity("Chat-Agent", "done",
                       f"路由: {route_info['route']} · 敏感度: {route_info['sensitivity']}")
        return {"agent": "Chat-Agent", "reply": reply, "route_info": route_info}
    except Exception as e:
        # 降级: ModelRouter 不可用时直接调用 llm_provider
        import traceback
        print(f"[Router] ModelRouter 降级: {e}\n{traceback.format_exc()}")
        reply = llm_provider.chat(messages=messages, system_prompt=sys_prompt)
        return {"agent": "Chat-Agent", "reply": reply}


def exec_chat_stream(user_message: str, history: list, sys_prompt: str):
    """
    Chat-Agent 流式版本: yield 每个 token (str)
    v2: 通过 model_router 智能选择模型端点
    """
    compactor = get_compactor()
    effective_history = compactor.compact(history) if compactor.should_compact(history) else history
    messages = effective_history[-20:] + [{"role": "user", "content": user_message}]

    # 智能选择模型
    endpoint = None
    try:
        from app.model_router import select_model
        endpoint = select_model(user_message)
    except Exception:
        pass  # 降级到默认模型

    _add_activity("Chat-Agent", "working", "流式生成中...")

    yield from llm_provider.chat_stream(
        messages=messages,
        system_prompt=sys_prompt,
        endpoint=endpoint,
    )

    _add_activity("Chat-Agent", "done", "流式生成完成")
