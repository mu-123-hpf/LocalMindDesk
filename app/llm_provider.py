"""
LocalMindDesk — 统一 LLM 调用
所有模型走 OpenAI 兼容 /v1/chat/completions 协议
支持：LM Studio / Ollama / DeepSeek / 任何 OpenAI 兼容 API
"""
from openai import OpenAI
from app.config import get_config, get_active_endpoint, ModelEndpoint
from typing import Optional
from app.logger import get_logger
from app.metrics import get_metrics
import time

logger = get_logger("llm")

def get_client(endpoint: Optional[ModelEndpoint] = None) -> tuple[OpenAI, str]:
    """获取 OpenAI 客户端和模型名"""
    if endpoint is None:
        endpoint = get_active_endpoint()
    if endpoint is None:
        raise RuntimeError("没有可用的模型端点，请在设置中添加")

    client = OpenAI(
        base_url=endpoint.base_url,
        api_key=endpoint.api_key or "not-needed",
        timeout=300.0,
    )
    return client, endpoint.model

def chat(
    messages: list[dict],
    system_prompt: str = "",
    temperature: float = -1,
    max_tokens: int = -1,
    endpoint: Optional[ModelEndpoint] = None,
) -> str:
    """
    发送聊天请求，获取回复
    messages: [{"role": "user", "content": "..."}, ...]
    """
    cfg = get_config()
    client, model = get_client(endpoint)

    # 构建完整消息列表
    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    temp = temperature if temperature >= 0 else cfg.temperature
    tokens = max_tokens if max_tokens > 0 else cfg.max_tokens

    try:
        logger.info(f"请求 → {model} (temp={temp})")
        _start = time.time()

        response = client.chat.completions.create(
            model=model,
            messages=full_messages,
            temperature=temp,
            max_tokens=tokens,
        )

        content = response.choices[0].message.content or ""

        # 去除 <think>...</think>（DeepSeek-R1 等模型）
        if "<think>" in content and "</think>" in content:
            start = content.find("<think>")
            end = content.find("</think>") + len("</think>")
            content = content[:start] + content[end:]

        content = content.strip()
        _dur = (time.time() - _start) * 1000
        _in_tok = getattr(response.usage, 'prompt_tokens', 0) if response.usage else 0
        _out_tok = getattr(response.usage, 'completion_tokens', 0) if response.usage else 0
        get_metrics().record_llm_call(model, _in_tok, _out_tok, _dur, success=True)
        logger.info(f"回复 ← {len(content)} 字符 ({_dur:.0f}ms, {_in_tok}+{_out_tok} tok)")
        return content

    except Exception as e:
        error_msg = str(e)
        _dur = (time.time() - _start) * 1000 if '_start' in dir() else 0
        get_metrics().record_llm_call(model, 0, 0, _dur, success=False)
        logger.error(f"错误: {error_msg}")
        if "Connection" in error_msg or "refused" in error_msg:
            return f"⚠️ 无法连接到模型服务。请检查 LM Studio 是否已启动并加载了模型。"
        return f"⚠️ LLM 调用失败: {error_msg}"

def chat_stream(
    messages: list[dict],
    system_prompt: str = "",
    temperature: float = -1,
    max_tokens: int = -1,
    endpoint: Optional[ModelEndpoint] = None,
):
    """
    流式聊天，yield 每个 token chunk (str)
    用法: for chunk in chat_stream(messages): print(chunk, end='')
    """
    cfg = get_config()
    client, model = get_client(endpoint)

    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    temp = temperature if temperature >= 0 else cfg.temperature
    tokens = max_tokens if max_tokens > 0 else cfg.max_tokens

    try:
        logger.info(f"流式请求 → {model} (temp={temp})")

        response = client.chat.completions.create(
            model=model,
            messages=full_messages,
            temperature=temp,
            max_tokens=tokens,
            stream=True,
        )

        in_think = False
        total_chars = 0

        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content is None:
                continue
            text = delta.content

            # 过滤 <think>...</think> 标签（DeepSeek-R1 等模型）
            if "<think>" in text:
                in_think = True
                text = text[:text.find("<think>")]
            if in_think:
                if "</think>" in text:
                    in_think = False
                    text = text[text.find("</think>") + len("</think>"):]
                else:
                    continue  # 跳过 think 内容

            if text:
                total_chars += len(text)
                yield text

        logger.info(f"流式完成 ← {total_chars} 字符")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"流式错误: {error_msg}")
        if "Connection" in error_msg or "refused" in error_msg:
            yield f"⚠️ 无法连接到模型服务。请检查 LM Studio 是否已启动并加载了模型。"
        else:
            yield f"⚠️ LLM 调用失败: {error_msg}"


def health_check(endpoint: Optional[ModelEndpoint] = None) -> dict:
    """健康检查"""
    if endpoint is None:
        endpoint = get_active_endpoint()
    if endpoint is None:
        return {"status": "error", "error": "没有配置模型端点"}

    try:
        client, model = get_client(endpoint)
        models = client.models.list()
        model_ids = [m.id for m in models.data]
        return {
            "status": "ok",
            "provider": endpoint.provider,
            "model": endpoint.model,
            "available_models": model_ids,
        }
    except Exception as e:
        return {
            "status": "error",
            "provider": endpoint.provider,
            "error": str(e),
        }

def list_available_models(endpoint: Optional[ModelEndpoint] = None) -> list[str]:
    """获取端点上可用的模型列表"""
    try:
        client, _ = get_client(endpoint)
        models = client.models.list()
        return [m.id for m in models.data]
    except Exception:
        return []
