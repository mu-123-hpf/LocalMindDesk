"""
Tool Handler — 工具调用系统
包含: 工具定义、意图检测、工具执行
"""
import json
import re
from app import llm_provider
from app.tools import web_search, ppt_maker, doc_maker
from app.prompt_loader import load_agent_prompt
from .activity import _add_activity


# ============================================================
#  工具定义
# ============================================================
def _handle_ppt(params):
    topic = params.get("topic", "演示文稿")
    filepath = ppt_maker.make_ppt(topic)
    return {"type": "file", "message": f"PPT 已生成: {topic}",
            "file_path": filepath, "file_name": filepath.split("/")[-1]}


def _handle_doc(params):
    title = params.get("title", "文档")
    content = params.get("content", "")
    if not content:
        content = llm_provider.chat(
            messages=[{"role": "user", "content": f"请为以下主题写一份详细的文档内容（Markdown 格式）：\n{title}"}],
            system_prompt="你是一个专业的技术文档撰写专家。输出高质量的 Markdown 格式文档内容。",
        )
    filepath = doc_maker.make_docx(title, content)
    return {"type": "file", "message": f"文档已生成: {title}",
            "file_path": filepath, "file_name": filepath.split("/")[-1]}


def _handle_memo(params):
    content = params.get("content", "")
    if content:
        from app.memory import add_memory
        add_memory(content)
        return {"type": "text", "message": f"已记住: {content[:100]}"}
    return {"type": "text", "message": "没有需要记忆的内容。"}


TOOLS = {
    "search": {
        "name": "联网搜索",
        "fn": lambda params: web_search.web_search(params.get("keyword", "")),
    },
    "make_ppt": {
        "name": "制作 PPT",
        "fn": lambda params: _handle_ppt(params),
    },
    "make_doc": {
        "name": "生成文档",
        "fn": lambda params: _handle_doc(params),
    },
    "memo": {
        "name": "记忆",
        "fn": lambda params: _handle_memo(params),
    },
}


# ============================================================
#  工具意图检测
# ============================================================
def detect_tool_intent(user_message: str) -> dict | None:
    tool_router_prompt = load_agent_prompt("tool_router")
    if not tool_router_prompt:
        tool_router_prompt = "你是意图分类器。只输出 JSON 或 null。"

    prompt = f"用户消息：{user_message}\n\n可用工具: search, make_ppt, make_doc, memo\n输出 JSON 或 null："

    reply = llm_provider.chat(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=tool_router_prompt,
        temperature=0.1, max_tokens=200,
    )

    reply = reply.strip()
    if reply.lower() in ("null", "none", ""):
        return None
    if reply.startswith("```"):
        lines = reply.split("\n")
        reply = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    reply = reply.strip()

    try:
        result = json.loads(reply)
        if isinstance(result, dict) and "tool" in result:
            return result
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', reply, re.S)
        if m:
            try: return json.loads(m.group())
            except: pass
    return None


# ============================================================
#  工具执行
# ============================================================
def exec_tool(user_message: str, history: list, sys_prompt: str) -> dict:
    """Tool-Agent: 工具调用"""
    intent = detect_tool_intent(user_message)
    if not intent or intent.get("tool") not in TOOLS:
        return {"agent": "Tool-Agent", "reply": ""}

    tool_name = intent["tool"]
    params = intent.get("params", {})
    tool = TOOLS[tool_name]
    _add_activity("Tool-Agent", "working", f"调用工具: {tool['name']}")

    if tool_name == "search":
        search_result = tool["fn"](params)
        enhanced = f"用户问题：{user_message}\n\n搜索结果：\n{search_result}\n\n请结合搜索结果回答，注明来源。"
        reply = llm_provider.chat(
            messages=history + [{"role": "user", "content": enhanced}],
            system_prompt=sys_prompt,
        )
        _add_activity("Tool-Agent", "done", f"搜索完成: {params.get('keyword', '')}")
        return {"agent": "Tool-Agent", "reply": f"🔍 已联网搜索「{params.get('keyword', '')}」\n\n{reply}"}

    result = tool["fn"](params)
    if isinstance(result, dict):
        _add_activity("Tool-Agent", "done", result.get("message", "完成"),
                      "file" if result.get("type") == "file" else "text")
        if result.get("type") == "file":
            return {"agent": "Tool-Agent", "reply": f"✅ {result['message']}",
                    "file_path": result.get("file_path", ""),
                    "file_name": result.get("file_name", "")}
        return {"agent": "Tool-Agent", "reply": result.get("message", "完成")}
    return {"agent": "Tool-Agent", "reply": str(result)}
