"""
LocalMindDesk — 自动记忆提取器 v2
集成 FactMemory 的提取管线

每轮对话结束后，后台分析对话内容:
1. 准入判断 should_ingest()
2. LLM 提取 EventSummary + Facts
3. Facts → fact_memory.add_facts()
4. EventSummary → vector_memory 向量存储
5. 兼容旧的 memories 表写入
"""
from __future__ import annotations
import json
import threading
from typing import Optional
from app import llm_provider


# ============================================================
#  提取提示词（v2 — 分离 Facts 和 EventSummary）
# ============================================================
EXTRACT_PROMPT = """你是记忆提取助手。分析以下对话内容，提取两类信息。

## A. 用户事实 (facts)
关于用户本人的持久信息（不会很快过期的知识）：
1. **preference** — 用户偏好（编码风格、语言习惯、UI 喜好、工具偏好）
2. **knowledge** — 项目知识（架构决策、关键路径、约定、技术栈）
3. **decision** — 重要决定（为什么选择某方案、排除了什么选项）
4. **feedback** — 用户反馈（对 AI 输出的评价、改进要求）

## B. 事件摘要 (event_summary)
本次对话的简短摘要（1-2 句话），用于日后检索回顾。

## 规则
- 只提取有长期价值的信息，不要记录临时性操作
- 每条 fact 简洁（< 100 字），不重复
- event_summary 一句话概括对话主题
- 返回纯 JSON，不要包含其他文字

## 输出格式
```json
{
  "facts": [
    {"type": "preference", "content": "用户喜欢简洁的回复"},
    {"type": "knowledge", "content": "项目使用 Electron + Python 架构"}
  ],
  "event_summary": "讨论了项目架构升级方案，决定采用分层记忆系统"
}
```

如果没有值得记忆的信息，返回:
```json
{"facts": [], "event_summary": ""}
```"""


# ============================================================
#  记忆提取器 v2
# ============================================================
class AutoMemoryExtractor:
    """
    自动记忆提取器 — 集成 FactMemory

    用法:
        extractor = get_extractor()
        extractor.extract_after_chat(messages, session_id)
    """

    def __init__(self):
        self._extract_count: int = 0
        self._last_memories: list[dict] = []

    def extract_after_chat(self, messages: list[dict], session_id: str = None):
        """
        异步提取记忆（不阻塞主线程）

        v2: 增加准入控制 + FactMemory 集成
        """
        # 准入控制（学习 NAVI）
        from app.fact_memory import FactMemory
        if not FactMemory.should_ingest(messages):
            return

        # 后台线程执行
        t = threading.Thread(
            target=self._do_extract,
            args=(messages, session_id),
            daemon=True,
        )
        t.start()

    def _do_extract(self, messages: list[dict], session_id: str = None):
        """实际执行提取（在后台线程中）"""
        try:
            # 构建对话文本
            conversation = self._format_conversation(messages)

            # 调用 LLM 提取
            reply = llm_provider.chat(
                messages=[{"role": "user", "content": f"请分析以下对话并提取记忆：\n\n{conversation}"}],
                system_prompt=EXTRACT_PROMPT,
                temperature=0.1,
                max_tokens=600,
            )

            # 解析结果
            result = self._parse_result(reply)
            if not result:
                return

            facts = result.get("facts", [])
            event_summary = result.get("event_summary", "")

            saved_count = 0

            # 1. Facts → FactMemory (SSOT)
            if facts:
                from app.fact_memory import get_fact_memory
                fm = get_fact_memory()
                fact_items = [
                    {"content": f["content"], "category": f.get("type", "general")}
                    for f in facts if f.get("content")
                ]
                added = fm.add_facts(fact_items, session_id=session_id or "")
                saved_count += added

            # 2. Facts → 兼容旧 memories 表
            if facts:
                self._save_to_legacy(facts)

            # 3. EventSummary → 向量记忆 (L3)
            if event_summary:
                self._save_to_vector(event_summary, session_id)

            if saved_count > 0 or event_summary:
                self._extract_count += 1
                self._last_memories = facts
                print(f"[MemoryExtractor v2] 提取 {saved_count} 条事实"
                      f"{' + 事件摘要' if event_summary else ''}")

        except Exception as e:
            print(f"[MemoryExtractor v2] 提取失败: {e}")

    def _format_conversation(self, messages: list[dict]) -> str:
        """格式化最近对话为文本"""
        # 只取最近 10 条，避免输入过长
        recent = messages[-10:]
        parts = []
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if len(content) > 300:
                content = content[:300] + "..."
            if role == "user":
                parts.append(f"用户: {content}")
            elif role == "assistant":
                parts.append(f"AI: {content}")
        return "\n".join(parts)

    def _parse_result(self, reply: str) -> dict | None:
        """解析 LLM 返回的 JSON（兼容 v1 数组格式和 v2 对象格式）"""
        reply = reply.strip()
        # 去除 markdown 代码块
        if reply.startswith("```"):
            lines = reply.split("\n")
            reply = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            reply = reply.strip()

        try:
            result = json.loads(reply)

            # v2 格式: {"facts": [...], "event_summary": "..."}
            if isinstance(result, dict) and "facts" in result:
                valid_facts = []
                for item in result.get("facts", []):
                    if isinstance(item, dict) and "content" in item:
                        valid_facts.append(item)
                return {"facts": valid_facts, "event_summary": result.get("event_summary", "")}

            # v1 兼容: [{"type": "...", "content": "..."}]
            if isinstance(result, list):
                valid = []
                for item in result:
                    if isinstance(item, dict) and "type" in item and "content" in item:
                        valid.append(item)
                return {"facts": valid, "event_summary": ""} if valid else None

        except json.JSONDecodeError:
            pass

        return None

    def _save_to_legacy(self, facts: list[dict]):
        """兼容写入旧 memories 表"""
        from app.memory import get_memories, add_memory

        existing = get_memories(100)
        existing_texts = {m["content"].lower().strip() for m in existing}

        for fact in facts:
            content = fact.get("content", "").strip()
            if not content:
                continue
            content_lower = content.lower()
            is_dup = any(
                content_lower == ex or content_lower in ex or ex in content_lower
                for ex in existing_texts
            )
            if not is_dup:
                add_memory(content, fact.get("type", "general"))
                existing_texts.add(content_lower)

    def _save_to_vector(self, summary: str, session_id: str = None):
        """事件摘要写入向量记忆"""
        try:
            from app.vector_memory import get_vector_store
            store = get_vector_store()
            store.add(summary, metadata={
                "type": "event_summary",
                "session_id": session_id or "",
            })
            print(f"[MemoryExtractor v2] 事件摘要已向量化")
        except Exception as e:
            print(f"[MemoryExtractor v2] 向量化失败: {e}")

    def get_stats(self) -> dict:
        """获取提取统计"""
        fact_stats = {}
        try:
            from app.fact_memory import get_fact_memory
            fact_stats = get_fact_memory().get_stats()
        except Exception:
            pass

        return {
            "extract_count": self._extract_count,
            "last_memories": self._last_memories,
            "fact_memory": fact_stats,
        }


# ============================================================
#  全局单例
# ============================================================
_extractor: AutoMemoryExtractor | None = None


def get_extractor() -> AutoMemoryExtractor:
    """获取全局 AutoMemoryExtractor 单例"""
    global _extractor
    if _extractor is None:
        _extractor = AutoMemoryExtractor()
    return _extractor
