# -*- coding: utf-8 -*-
"""
LocalMindDesk — Post-Processor (Stop Hooks)
Inspired by industry-standard stopHooks.ts — runs after every LLM turn.

Responsibilities:
1. Auto-extract facts/memories from the conversation
2. Record LLM metrics
3. Session auto-titling
"""
import threading
from typing import Optional


class PostProcessor:
    """
    Post-turn validation and extraction pipeline.
    Runs asynchronously after each LLM response to avoid blocking.
    """

    def __init__(self):
        self._lock = threading.Lock()

    def run_async(self, reply: str, user_message: str,
                  history: list[dict], session_id: Optional[str] = None):
        """
        Fire-and-forget post-processing after an LLM turn.
        Runs in a background thread to avoid blocking the SSE stream.
        """
        t = threading.Thread(
            target=self._execute,
            args=(reply, user_message, history, session_id),
            daemon=True,
        )
        t.start()

    def _execute(self, reply: str, user_message: str,
                 history: list[dict], session_id: Optional[str]):
        """Execute all post-processing hooks sequentially."""
        try:
            self._hook_auto_extract_facts(reply, user_message, history, session_id)
        except Exception as e:
            print(f"[PostProcessor] fact extraction error: {e}")

        try:
            self._hook_auto_title(reply, user_message, session_id)
        except Exception as e:
            print(f"[PostProcessor] auto-title error: {e}")

        try:
            self._hook_auto_compact(history, session_id)
        except Exception as e:
            print(f"[PostProcessor] auto-compact error: {e}")

    # ── Hook 1: Auto-extract facts ──

    def _hook_auto_extract_facts(self, reply: str, user_message: str,
                                  history: list[dict], session_id: Optional[str]):
        """
        Check if the conversation is worth extracting facts from.
        Uses FactMemory.should_ingest() as the gate.
        """
        from app.fact_memory import get_fact_memory
        fm = get_fact_memory()

        # Build conversation for ingestion check
        messages = list(history) + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": reply},
        ]

        if not fm.should_ingest(messages):
            return

        # Extract facts using pattern matching (lightweight, no LLM call)
        facts = self._extract_facts_lightweight(user_message, reply)
        if facts:
            fm.add_facts(facts, session_id=session_id or "")
            print(f"[PostProcessor] Auto-extracted {len(facts)} facts")

    @staticmethod
    def _extract_facts_lightweight(user_msg: str, reply: str) -> list[dict]:
        """
        Lightweight fact extraction using patterns — no LLM call needed.
        Extracts user preferences, decisions, and stated facts.
        """
        import re
        facts = []

        # Pattern: user states a preference
        pref_patterns = [
            r"(?:我喜欢|我偏好|我习惯|我倾向于|我一般用|我常用|我prefer)\s*(.{5,60})",
            r"(?:不要|别用|不喜欢|讨厌)\s*(.{3,40})",
        ]
        for p in pref_patterns:
            m = re.search(p, user_msg, re.I)
            if m:
                facts.append({
                    "content": f"用户偏好: {m.group(0).strip()[:100]}",
                    "category": "preference",
                    "confidence": 0.7,
                })

        # Pattern: user mentions their tech stack / environment
        tech_patterns = [
            r"(?:我[们的]?项目|我[们的]?代码|我[们的]?系统)(?:用的?|基于|采用)\s*(.{3,50})",
            r"(?:我用的?是|使用的是|用的)\s*(Python|Java|Go|Rust|TypeScript|React|Vue|Next\.?js|Django|FastAPI|Node)(?:\s|$|\.|,)",
        ]
        for p in tech_patterns:
            m = re.search(p, user_msg, re.I)
            if m:
                facts.append({
                    "content": f"技术栈: {m.group(0).strip()[:100]}",
                    "category": "knowledge",
                    "confidence": 0.8,
                })

        # Pattern: user makes a decision
        decision_patterns = [
            r"(?:就用|就这样|就按|决定用|选择|采用方案)\s*(.{3,60})",
        ]
        for p in decision_patterns:
            m = re.search(p, user_msg, re.I)
            if m:
                facts.append({
                    "content": f"决策: {m.group(0).strip()[:100]}",
                    "category": "decision",
                    "confidence": 0.75,
                })

        return facts

    # ── Hook 2: Auto-title session ──

    def _hook_auto_title(self, reply: str, user_message: str,
                         session_id: Optional[str]):
        """Auto-generate session title if it's still using the default."""
        if not session_id:
            return

        try:
            from app.context_manager import get_session_title, update_session_title
            title = get_session_title(session_id)
            if title and not title.startswith("新对话"):
                return  # Already has a custom title

            # Generate a short title from the first user message
            short = user_message[:30].strip()
            if len(short) < 3:
                return
            # Remove newlines and clean up
            short = short.replace("\n", " ").strip()
            if len(user_message) > 30:
                short += "..."
            update_session_title(session_id, short)
        except Exception:
            pass  # Title generation is best-effort

    # ── Hook 3: Auto-compact ( pattern) ──

    def _hook_auto_compact(self, history: list[dict], session_id: Optional[str]):
        """Trigger background compaction when context gets too large."""
        if not session_id or len(history) < 30:
            return

        try:
            from app.background_tasks import get_task_manager, auto_compact_task
            tm = get_task_manager()

            # Don't spawn if one is already running for this session
            existing = [t for t in tm.list_tasks(include_completed=False)
                        if t.get("type") == "auto_compact"]
            if existing:
                return

            tm.spawn("auto_compact", f"Context compaction ({len(history)} msgs)",
                     auto_compact_task, args=(session_id, history))
        except Exception:
            pass


# ── Global singleton ──
_post_processor: Optional[PostProcessor] = None


def get_post_processor() -> PostProcessor:
    global _post_processor
    if _post_processor is None:
        _post_processor = PostProcessor()
    return _post_processor
