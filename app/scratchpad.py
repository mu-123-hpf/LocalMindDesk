# -*- coding: utf-8 -*-
"""
LocalMindDesk — Scratchpad
Inspired by industry-standard memdir/scratchpad concept.

A per-session scratch space where the AI can:
1. Take notes during complex tasks
2. Store intermediate results
3. Track TODO lists
4. Save code snippets for later reference

Data is persisted in SQLite alongside session data.
"""
import json
import time
from typing import Optional
from app.memory import _get_conn


# ============================================================
#  Database Schema
# ============================================================
_SCRATCHPAD_SQL = """
CREATE TABLE IF NOT EXISTS scratchpad (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    UNIQUE(session_id, key)
);
"""


def init_scratchpad_table():
    """Create scratchpad table (called during DB init)."""
    try:
        conn = _get_conn()
        conn.executescript(_SCRATCHPAD_SQL)
        conn.commit()
        conn.close()
    except Exception:
        pass


# ============================================================
#  Scratchpad API
# ============================================================
class Scratchpad:
    """
    Per-session key-value scratch space.

    Usage:
        pad = Scratchpad("session-123")
        pad.set("todo", "- Fix bug\\n- Write tests")
        pad.set("notes", "User prefers dark theme")
        print(pad.get("todo"))
        print(pad.get_all())  # {todo: ..., notes: ...}
    """

    def __init__(self, session_id: str):
        self.session_id = session_id

    def set(self, key: str, value: str) -> None:
        """Set a scratchpad entry (upsert)."""
        now = time.time()
        conn = _get_conn()
        conn.execute(
            "INSERT INTO scratchpad (session_id, key, value, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (self.session_id, key, value, now, now),
        )
        conn.commit()
        conn.close()

    def get(self, key: str) -> Optional[str]:
        """Get a scratchpad entry."""
        conn = _get_conn()
        row = conn.execute(
            "SELECT value FROM scratchpad WHERE session_id=? AND key=?",
            (self.session_id, key),
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def get_all(self) -> dict[str, str]:
        """Get all scratchpad entries for this session."""
        conn = _get_conn()
        rows = conn.execute(
            "SELECT key, value FROM scratchpad WHERE session_id=? ORDER BY updated_at DESC",
            (self.session_id,),
        ).fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}

    def delete(self, key: str) -> bool:
        """Delete a scratchpad entry."""
        conn = _get_conn()
        cursor = conn.execute(
            "DELETE FROM scratchpad WHERE session_id=? AND key=?",
            (self.session_id, key),
        )
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    def clear(self) -> int:
        """Clear all scratchpad entries for this session."""
        conn = _get_conn()
        cursor = conn.execute(
            "DELETE FROM scratchpad WHERE session_id=?",
            (self.session_id,),
        )
        conn.commit()
        conn.close()
        return cursor.rowcount

    def to_context_text(self) -> Optional[str]:
        """Render scratchpad as context for injection into system prompt."""
        entries = self.get_all()
        if not entries:
            return None
        lines = ["# 便签本 (Scratchpad)"]
        for key, value in entries.items():
            lines.append(f"## {key}")
            lines.append(value)
        return "\n".join(lines)
