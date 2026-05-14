# -*- coding: utf-8 -*-
"""
LocalMindDesk — Background Task Manager
Inspired by Claude Code's Task.ts / services/preventSleep.ts

Manages long-running operations that continue after the SSE stream ends:
- Shell commands (pip install, npm build, etc.)
- File processing (PDF generation, code analysis)
- Auto-compact (context window management)

Each task has: id, type, status, output, start/end time.
Frontend polls /api/tasks for status updates.
"""
import json
import threading
import time
import uuid
from enum import Enum
from typing import Optional, Callable


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


class BackgroundTask:
    """A single background task with lifecycle tracking."""

    def __init__(self, task_id: str, task_type: str, description: str):
        self.id = task_id
        self.type = task_type
        self.description = description
        self.status = TaskStatus.PENDING
        self.output_lines: list[str] = []
        self.error: Optional[str] = None
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def duration_ms(self) -> Optional[float]:
        if self.start_time is None:
            return None
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "description": self.description,
            "status": self.status.value,
            "output": self.output_lines[-20:],  # Last 20 lines
            "error": self.error,
            "duration_ms": round(self.duration_ms) if self.duration_ms else None,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


class TaskManager:
    """
    Global background task manager.

    Usage:
        tm = get_task_manager()
        task = tm.spawn("shell", "Installing dependencies", my_func, args=(cmd,))
        status = tm.get_task(task.id)
        all_tasks = tm.list_tasks()
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: dict[str, BackgroundTask] = {}
        # Auto-cleanup old completed tasks (keep last 20)
        self._max_completed = 20

    def spawn(self, task_type: str, description: str,
              func: Callable, args: tuple = (), kwargs: dict = None) -> BackgroundTask:
        """
        Spawn a background task.

        func: callable that receives (task, *args, **kwargs)
              - task.output_lines.append() to emit output
              - raise Exception to mark as failed
        """
        task_id = f"bg_{uuid.uuid4().hex[:8]}"
        task = BackgroundTask(task_id, task_type, description)

        def _worker():
            task.status = TaskStatus.RUNNING
            task.start_time = time.time()
            try:
                func(task, *args, **(kwargs or {}))
                task.status = TaskStatus.COMPLETED
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
            finally:
                task.end_time = time.time()

        task._thread = threading.Thread(target=_worker, daemon=True)
        with self._lock:
            self._tasks[task_id] = task
            self._cleanup_old()
        task._thread.start()

        print(f"[TaskManager] Spawned: {task_id} ({task_type}) — {description}")
        return task

    def get_task(self, task_id: str) -> Optional[dict]:
        """Get task status by ID."""
        with self._lock:
            task = self._tasks.get(task_id)
        return task.to_dict() if task else None

    def list_tasks(self, include_completed: bool = True) -> list[dict]:
        """List all tasks."""
        with self._lock:
            tasks = list(self._tasks.values())
        if not include_completed:
            tasks = [t for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)]
        return [t.to_dict() for t in sorted(tasks, key=lambda t: t.start_time or 0, reverse=True)]

    def kill_task(self, task_id: str) -> bool:
        """Mark a task as killed (thread may continue but output is ignored)."""
        with self._lock:
            task = self._tasks.get(task_id)
        if not task or task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False
        task.status = TaskStatus.KILLED
        task.end_time = time.time()
        return True

    def _cleanup_old(self):
        """Remove old completed tasks beyond the limit."""
        completed = [t for t in self._tasks.values()
                     if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.KILLED)]
        if len(completed) > self._max_completed:
            # Sort by end_time, remove oldest
            completed.sort(key=lambda t: t.end_time or 0)
            for t in completed[:len(completed) - self._max_completed]:
                del self._tasks[t.id]


# ── Auto-Compact Task ──

def auto_compact_task(task: BackgroundTask, session_id: str, messages: list[dict]):
    """
    Background auto-compact: summarize conversation when it gets too long.
    Inspired by Claude Code's autoCompact.ts
    """
    task.output_lines.append(f"Checking context size for session {session_id[:8]}...")

    if len(messages) < 20:
        task.output_lines.append(f"Only {len(messages)} messages — no compaction needed")
        return

    task.output_lines.append(f"Context has {len(messages)} messages — triggering compaction")

    try:
        from app.context_manager import auto_archive
        auto_archive(session_id)
        task.output_lines.append("Compaction complete — cold data archived to L3")
    except Exception as e:
        task.output_lines.append(f"Compaction error: {e}")
        raise


# ── Global singleton ──
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
