"""
LocalMindDesk — 记忆与会话持久化（SQLite）v2
三层记忆架构 L2：滑动窗口 + Token 管控
"""
import sqlite3
import json
import os
import re
from datetime import datetime
from typing import Optional

DB_PATH = "data/LocalMindDesk.db"

# Token 预算（给 system prompt + 冷记忆留 500 tokens）
MAX_CONTEXT_TOKENS = 3500


def _get_conn() -> sqlite3.Connection:
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """初始化数据库表（v2 含 token_count + archived）"""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '新对话',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER DEFAULT 0,
            archived INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id);
    """)
    # 兼容升级：如果旧表缺少新字段，静默添加
    try:
        conn.execute("ALTER TABLE messages ADD COLUMN token_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE messages ADD COLUMN archived INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    # 在确保 archived 列存在后再建索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_archived ON messages(session_id, archived)")
    conn.commit()
    conn.close()
    # 初始化 FactMemory 相关表（v3 — 2.0 升级）
    try:
        from app.fact_memory import init_fact_tables
        init_fact_tables()
    except Exception as e:
        print(f"[DB] FactMemory 表初始化跳过: {e}")
    print("[DB] 数据库初始化完成 (v3)")


# ============================================================
#  Token 估算
# ============================================================
def estimate_tokens(text: str) -> int:
    """
    轻量 Token 估算（无需 tokenizer 依赖）
    中文 ≈ 1.5 tokens/字，英文 ≈ 0.75 tokens/word，标点/空格 ≈ 0.1
    """
    if not text:
        return 0
    cn_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    en_words = len(re.findall(r'[a-zA-Z]+', text))
    others = len(text) - cn_chars - sum(len(w) for w in re.findall(r'[a-zA-Z]+', text))
    return int(cn_chars * 1.5 + en_words * 0.75 + others * 0.1) + 4  # +4 for role tokens


# ============================================================
#  会话管理
# ============================================================
def create_session(title: str = "新对话") -> str:
    import uuid
    sid = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    conn = _get_conn()
    conn.execute("INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?,?,?,?)",
                 (sid, title, now, now))
    conn.commit()
    conn.close()
    return sid


def list_sessions(limit: int = 50) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, title, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [{"id": r["id"], "title": r["title"], "updated_at": r["updated_at"]} for r in rows]


def get_session_messages(session_id: str) -> list[dict]:
    """获取会话的所有消息（含 token_count）"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, role, content, token_count, archived, created_at FROM messages WHERE session_id=? ORDER BY id",
        (session_id,)
    ).fetchall()
    conn.close()
    return [{"id": r["id"], "role": r["role"], "content": r["content"],
             "token_count": r["token_count"], "archived": r["archived"]} for r in rows]


def add_message(session_id: str, role: str, content: str) -> int:
    """添加消息，自动估算 token_count，返回消息 ID"""
    now = datetime.now().isoformat()
    tokens = estimate_tokens(content)
    conn = _get_conn()
    cursor = conn.execute(
        "INSERT INTO messages (session_id, role, content, token_count, created_at) VALUES (?,?,?,?,?)",
        (session_id, role, content, tokens, now))
    msg_id = cursor.lastrowid
    conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))
    conn.commit()
    conn.close()
    return msg_id


def update_session_title(session_id: str, title: str):
    conn = _get_conn()
    conn.execute("UPDATE sessions SET title=? WHERE id=?", (title, session_id))
    conn.commit()
    conn.close()


def delete_session(session_id: str):
    conn = _get_conn()
    conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
    conn.commit()
    conn.close()


def auto_title(session_id: str, first_message: str):
    title = first_message[:20].replace("\n", " ").strip()
    if len(first_message) > 20:
        title += "..."
    update_session_title(session_id, title)


# ============================================================
#  L2 滑动窗口 — 热上下文提取
# ============================================================
def get_hot_context(session_id: str, max_tokens: int = None) -> list[dict]:
    """
    滑动窗口：从最新消息向前累加，直到 token 上限
    类似 OS 的 LRU 页面置换 — 最近的数据留在"内存"中
    """
    if max_tokens is None:
        max_tokens = MAX_CONTEXT_TOKENS

    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, role, content, token_count FROM messages "
        "WHERE session_id=? ORDER BY id DESC",
        (session_id,)
    ).fetchall()
    conn.close()

    window = []
    total_tokens = 0
    cold_ids = []

    for row in rows:
        tokens = row["token_count"] or estimate_tokens(row["content"])
        if total_tokens + tokens > max_tokens:
            cold_ids.append(row["id"])
            continue
        window.insert(0, {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "token_count": tokens,
        })
        total_tokens += tokens

    print(f"[Memory L2] 热窗口: {len(window)} 条, {total_tokens} tokens (上限 {max_tokens})")
    return window


def get_cold_messages(session_id: str) -> list[dict]:
    """获取已超出热窗口的冷数据（未归档的）"""
    hot = get_hot_context(session_id)
    hot_ids = {m["id"] for m in hot}

    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, role, content, token_count FROM messages "
        "WHERE session_id=? AND archived=0 ORDER BY id",
        (session_id,)
    ).fetchall()
    conn.close()

    cold = []
    for r in rows:
        if r["id"] not in hot_ids:
            cold.append({
                "id": r["id"], "role": r["role"],
                "content": r["content"], "token_count": r["token_count"]
            })
    return cold


def mark_archived(message_ids: list[int]):
    """标记消息为已归档（已向量化到 L3）"""
    if not message_ids:
        return
    conn = _get_conn()
    placeholders = ",".join("?" * len(message_ids))
    conn.execute(f"UPDATE messages SET archived=1 WHERE id IN ({placeholders})", message_ids)
    conn.commit()
    conn.close()
    print(f"[Memory L2] 已归档 {len(message_ids)} 条消息")


# ============================================================
#  记忆管理（保留兼容）
# ============================================================
def add_memory(content: str, category: str = "general"):
    now = datetime.now().isoformat()
    conn = _get_conn()
    conn.execute("INSERT INTO memories (content, category, created_at) VALUES (?,?,?)",
                 (content, category, now))
    conn.commit()
    conn.close()


def get_memories(limit: int = 50) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT content, category, created_at FROM memories ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [{"content": r["content"], "category": r["category"], "created_at": r["created_at"]} for r in rows]


def get_memory_text() -> str:
    memories = get_memories(30)
    if not memories:
        return ""
    lines = [f"- [{m['created_at'][:10]}] {m['content']}" for m in memories]
    return "\n".join(lines)


# 初始化
init_db()
