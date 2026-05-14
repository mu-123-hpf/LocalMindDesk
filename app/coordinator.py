# -*- coding: utf-8 -*-
"""
LocalMindDesk — Task Coordinator
Inspired by Claude Code's coordinatorMode.ts — orchestrates multi-step tasks.

Design principles (from Claude Code):
1. Break complex requests into discrete steps
2. Each step is self-contained with clear inputs/outputs
3. Steps emit SSE events for the collapsible UI
4. Coordinator synthesizes results — never delegates understanding

Usage:
    coordinator = TaskCoordinator(llm_provider, workspace_path)
    async for event in coordinator.execute(user_message, history, sys_prompt):
        yield event  # SSE events (step_start, step_update, step_end, delta)
"""
import json
import re
import time
import uuid
from typing import Generator, Optional


class TaskStep:
    """A single step in a coordinated task."""

    def __init__(self, step_id: str, step_type: str, summary: str,
                 action: str = "", params: dict = None):
        self.id = step_id
        self.type = step_type      # thinking, tool, file, search, command
        self.summary = summary
        self.action = action       # e.g. "file_op.read", "shell_exec"
        self.params = params or {}
        self.result = None
        self.duration_ms = 0
        self.status = "pending"    # pending, running, done, error

    def to_sse_start(self) -> str:
        return json.dumps({
            "step_start": {
                "id": self.id,
                "type": self.type,
                "summary": self.summary,
            }
        }, ensure_ascii=False)

    def to_sse_end(self, summary: str = None) -> str:
        return json.dumps({
            "step_end": {
                "id": self.id,
                "summary": summary or self.summary,
            }
        }, ensure_ascii=False)


class TaskCoordinator:
    """
    Lightweight task orchestrator that breaks complex requests into steps.

    For simple queries: passes through to direct LLM chat (no overhead).
    For complex queries: decomposes into research → plan → execute steps.
    """

    # Keywords that suggest a complex, multi-step task
    COMPLEX_PATTERNS = [
        r"(?:然后|接着|之后|最后|第一步|第二步)",  # Sequential instructions
        r"(?:创建.*并且|修改.*同时|先.*再)",          # Compound operations
        r"(?:重构|重写|迁移|升级|部署)",              # Large-scope operations
        r"(?:分析.*并.*生成|搜索.*然后.*修改)",       # Multi-phase tasks
    ]

    def __init__(self, workspace_path: Optional[str] = None):
        self.workspace_path = workspace_path

    def is_complex_task(self, user_message: str) -> bool:
        """Detect if a user message requires multi-step coordination."""
        msg = user_message.strip()

        # Too short to be complex
        if len(msg) < 20:
            return False

        # Check for complexity patterns
        for pattern in self.COMPLEX_PATTERNS:
            if re.search(pattern, msg):
                return True

        # Multiple sentences with action verbs
        sentences = re.split(r'[。！？\n]', msg)
        action_sentences = 0
        for s in sentences:
            if re.search(r'(?:创建|修改|删除|搜索|运行|安装|添加|移除|更新|生成)', s):
                action_sentences += 1
        if action_sentences >= 2:
            return True

        return False

    def decompose(self, user_message: str) -> list[TaskStep]:
        """
        Break a complex request into sequential steps.
        Returns a list of TaskStep objects.

        Note: This is a lightweight, pattern-based decomposition.
        For full LLM-based planning, use the /plan mode instead.
        """
        steps = []
        step_num = 0

        # Step 0: Always start with analysis
        step_num += 1
        steps.append(TaskStep(
            step_id=f"coord_{step_num}",
            step_type="thinking",
            summary="分析任务需求...",
            action="analyze",
        ))

        # Parse sequential instructions
        parts = re.split(r'(?:然后|接着|之后|再|并且)\s*', user_message)
        if len(parts) <= 1:
            # Try splitting by sentences
            parts = re.split(r'[。\n]', user_message)
            parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 5]

        for part in parts:
            step_num += 1
            step_type = self._classify_step(part)
            steps.append(TaskStep(
                step_id=f"coord_{step_num}",
                step_type=step_type,
                summary=part[:60] + ("..." if len(part) > 60 else ""),
                action=part,
            ))

        # Final synthesis step
        step_num += 1
        steps.append(TaskStep(
            step_id=f"coord_{step_num}",
            step_type="thinking",
            summary="综合结果...",
            action="synthesize",
        ))

        return steps

    @staticmethod
    def _classify_step(text: str) -> str:
        """Classify a step's type based on its content."""
        text_lower = text.lower()
        if re.search(r'(?:文件|读取|写入|创建文件|修改文件)', text_lower):
            return "file"
        if re.search(r'(?:搜索|查找|grep|find)', text_lower):
            return "search"
        if re.search(r'(?:运行|执行|安装|pip|npm|git)', text_lower):
            return "command"
        if re.search(r'(?:分析|检查|审查|理解)', text_lower):
            return "thinking"
        return "tool"

    def emit_plan_events(self, steps: list[TaskStep]) -> Generator[str, None, None]:
        """
        Emit SSE events for the task plan (displayed in collapsible UI).
        This shows the user what steps will be executed.
        """
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        plan_summary = f"计划: {len(steps)} 个步骤"

        yield f"data: {json.dumps({'step_start': {'id': plan_id, 'type': 'thinking', 'summary': plan_summary}}, ensure_ascii=False)}\n\n"

        plan_content = "\n".join(
            f"{i+1}. [{s.type}] {s.summary}" for i, s in enumerate(steps)
        )
        yield f"data: {json.dumps({'step_update': {'id': plan_id, 'content': plan_content}}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'step_end': {'id': plan_id, 'summary': plan_summary}}, ensure_ascii=False)}\n\n"


# ── Global singleton ──
_coordinator: Optional[TaskCoordinator] = None


def get_coordinator(workspace_path: Optional[str] = None) -> TaskCoordinator:
    global _coordinator
    if _coordinator is None or workspace_path != _coordinator.workspace_path:
        _coordinator = TaskCoordinator(workspace_path)
    return _coordinator
