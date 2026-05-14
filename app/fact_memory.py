"""
LocalMindDesk — FactMemory (SSOT 用户事实知识库) v1
参考 Additive-Only 设计:
  - 旧 fact 不删，靠 superseded_by 链做版本演进
  - MD5 hash 去重
  - 异步矛盾检测 Worker（LLM 辩证推理）
  - 准入控制 should_ingest()

表结构:
  user_facts(
    id, content, content_hash, category, confidence,
    source_session, superseded_by, created_at
  )
"""
import hashlib
import json
import re
import sqlite3
import threading
import time
from datetime import datetime
from typing import Optional

from app.memory import DB_PATH, _get_conn

# ============================================================
#  数据库初始化（由 memory.py init_db 统一调用）
# ============================================================
_FACT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_facts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content         TEXT    NOT NULL,
    content_hash    TEXT    NOT NULL,
    category        TEXT    DEFAULT 'general',
    confidence      REAL    DEFAULT 0.8,
    source_session  TEXT    DEFAULT '',
    superseded_by   INTEGER DEFAULT NULL,
    created_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fact_hash ON user_facts(content_hash);
CREATE INDEX IF NOT EXISTS idx_fact_superseded ON user_facts(superseded_by);
"""

_TOOL_CALL_LOG_SQL = """
CREATE TABLE IF NOT EXISTS tool_call_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT,
    tool_name   TEXT NOT NULL,
    called_at   REAL NOT NULL,
    success     INTEGER DEFAULT 1,
    duration_ms INTEGER DEFAULT NULL
);
"""

_SKILL_USAGE_LOG_SQL = """
CREATE TABLE IF NOT EXISTS skill_usage_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name  TEXT NOT NULL,
    used_at     REAL NOT NULL,
    success     INTEGER DEFAULT 1,
    session_id  TEXT DEFAULT NULL
);
"""

_MEMORY_JOBS_SQL = """
CREATE TABLE IF NOT EXISTS memory_jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    status      TEXT DEFAULT 'pending',
    created_at  TEXT NOT NULL,
    finished_at TEXT DEFAULT NULL,
    facts_added INTEGER DEFAULT 0,
    error       TEXT DEFAULT NULL
);
"""


def init_fact_tables():
    """创建 FactMemory 相关表（由 memory.init_db 调用）"""
    conn = _get_conn()
    for sql in [_FACT_TABLE_SQL, _TOOL_CALL_LOG_SQL,
                _SKILL_USAGE_LOG_SQL, _MEMORY_JOBS_SQL]:
        try:
            conn.executescript(sql)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()
    print("[FactMemory] 表初始化完成")


# ============================================================
#  FactMemory 核心类
# ============================================================
class FactMemory:
    """
    SSOT 用户事实库 — Additive-Only

    核心设计:
    - 新 fact 入库前 MD5 去重
    - 旧 fact 不物理删除，通过 superseded_by 指向新 fact
    - 异步后台 Worker 检测矛盾
    - to_context_text() 输出给 LLM 的用户画像上下文
    """

    # 准入控制阈值
    MIN_TURNS = 3        # 对话轮数 < 3 → 跳过
    MIN_CHARS = 80       # 总字数 < 80 → 跳过

    def __init__(self):
        self._worker_lock = threading.Lock()

    @staticmethod
    def _hash(text: str) -> str:
        """MD5 hash 用于去重"""
        normalized = re.sub(r'\s+', ' ', text.strip().lower())
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()

    # ── 写入 ─────────────────────────────────────────────────

    def add_facts(self, facts: list[dict], session_id: str = "") -> int:
        """
        批量写入事实（Additive-Only + Hash 去重）

        facts: [{"content": "...", "category": "preference/knowledge/decision/feedback", "confidence": 0.8}]
        返回: 实际新增数量
        """
        if not facts:
            return 0

        conn = _get_conn()
        now = datetime.now().isoformat()
        added = 0

        for fact in facts:
            content = fact.get("content", "").strip()
            if not content or len(content) < 5:
                continue

            content_hash = self._hash(content)
            category = fact.get("category", "general")
            confidence = fact.get("confidence", 0.8)

            # Hash 去重：跳过已存在的相同内容
            existing = conn.execute(
                "SELECT id FROM user_facts WHERE content_hash = ? AND superseded_by IS NULL",
                (content_hash,)
            ).fetchone()
            if existing:
                continue

            conn.execute(
                "INSERT INTO user_facts (content, content_hash, category, confidence, "
                "source_session, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (content, content_hash, category, confidence, session_id, now)
            )
            added += 1

        conn.commit()
        conn.close()

        if added > 0:
            print(f"[FactMemory] 新增 {added} 条事实 (session={session_id[:8] if session_id else 'N/A'})")
            # 异步触发矛盾检测
            self._schedule_contradiction_check()

        return added

    # ── 读取 ─────────────────────────────────────────────────

    def get_all_facts(self, limit: int = 100) -> list[dict]:
        """获取所有有效事实（排除已废弃的）"""
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, content, category, confidence, source_session, created_at "
            "FROM user_facts WHERE superseded_by IS NULL "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [{
            "id": r["id"], "content": r["content"],
            "category": r["category"], "confidence": r["confidence"],
            "source_session": r["source_session"], "created_at": r["created_at"],
        } for r in rows]

    def count(self) -> int:
        """有效事实总数"""
        conn = _get_conn()
        row = conn.execute(
            "SELECT COUNT(*) FROM user_facts WHERE superseded_by IS NULL"
        ).fetchone()
        conn.close()
        return row[0] if row else 0

    def search_facts(self, query: str, limit: int = 10) -> list[dict]:
        """模糊搜索事实"""
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, content, category, confidence, created_at "
            "FROM user_facts WHERE superseded_by IS NULL AND content LIKE ? "
            "ORDER BY created_at DESC LIMIT ?",
            (f"%{query}%", limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def to_context_text(self, limit: int = 30) -> str:
        """
        生成给 LLM 的用户画像上下文

        按 category 分组输出，用于注入 system prompt
        """
        facts = self.get_all_facts(limit)
        if not facts:
            return ""

        # 按 category 分组
        groups: dict[str, list[str]] = {}
        category_labels = {
            "preference": "偏好",
            "knowledge": "知识",
            "decision": "决策",
            "feedback": "反馈",
            "general": "一般",
        }
        for f in facts:
            cat = f["category"]
            label = category_labels.get(cat, cat)
            groups.setdefault(label, []).append(f"- {f['content']}")

        parts = []
        for label, items in groups.items():
            parts.append(f"### {label}")
            parts.extend(items[:10])  # 每类最多 10 条

        return "\n".join(parts)

    def render_user_md(self) -> str:
        """
        生成 USER.md 内容（从 FactMemory 自动渲染）

        类似 USER.md — 只读投影
        """
        facts = self.get_all_facts(50)
        if not facts:
            return "# 用户画像\n\n暂无已知信息。随着对话积累，这里会自动填充。\n"

        lines = [
            "# 用户画像",
            "",
            f"> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"> 共 {len(facts)} 条已知事实",
            "",
        ]

        category_labels = {
            "preference": "🎨 偏好",
            "knowledge": "📚 知识",
            "decision": "📋 决策",
            "feedback": "💬 反馈",
            "general": "📝 其他",
        }

        groups: dict[str, list[dict]] = {}
        for f in facts:
            groups.setdefault(f["category"], []).append(f)

        for cat, items in groups.items():
            label = category_labels.get(cat, cat)
            lines.append(f"## {label}")
            for item in items[:15]:
                lines.append(f"- {item['content']}")
            lines.append("")

        return "\n".join(lines)

    # ── 准入控制 ──────────────────────────────────────────────

    @staticmethod
    def should_ingest(messages: list[dict]) -> bool:
        """
        判断一组对话是否值得提取记忆

        条件:
        - 对话轮数 >= MIN_TURNS（user 消息数）
        - 总文字量 >= MIN_CHARS
        - 不是纯工具调用（至少有自然语言回复）
        """
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if len(user_msgs) < FactMemory.MIN_TURNS:
            return False

        total_chars = sum(len(m.get("content", "")) for m in messages)
        if total_chars < FactMemory.MIN_CHARS:
            return False

        # 检查是否有自然语言回复（非纯工具调用）
        assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
        has_natural = any(
            len(m.get("content", "")) > 20 for m in assistant_msgs
        )
        if not has_natural:
            return False

        return True

    # ── 矛盾检测（异步 Worker）────────────────────────────────

    def _schedule_contradiction_check(self):
        """后台启动矛盾检测 Worker（非阻塞）"""
        t = threading.Thread(
            target=self._contradiction_worker,
            daemon=True,
        )
        t.start()

    def _contradiction_worker(self):
        """
        扫描最近新增的 fact，检测是否与已有 fact 矛盾

        流程:
        1. 取最近 5 条未检查的新 fact
        2. 对每条新 fact，用关键词搜索可能冲突的旧 fact
        3. 如果发现潜在冲突，调用 LLM 做辩证推理
        4. 矛盾的旧 fact 标记 superseded_by
        """
        if not self._worker_lock.acquire(blocking=False):
            return  # 已有 worker 在运行
        try:
            self._do_contradiction_check()
        except Exception as e:
            print(f"[FactMemory] 矛盾检测异常: {e}")
        finally:
            self._worker_lock.release()

    def _do_contradiction_check(self):
        """执行矛盾检测"""
        conn = _get_conn()

        # 取最近 5 条新 fact
        new_facts = conn.execute(
            "SELECT id, content, category FROM user_facts "
            "WHERE superseded_by IS NULL "
            "ORDER BY id DESC LIMIT 5"
        ).fetchall()

        if len(new_facts) < 2:
            conn.close()
            return

        latest = new_facts[0]  # 最新的一条
        older = new_facts[1:]  # 之前的

        # 提取关键词做预筛（避免对所有 fact 做 LLM 调用）
        keywords = self._extract_entity_keywords(latest["content"])
        if not keywords:
            conn.close()
            return

        # 用关键词搜索可能冲突的 fact
        candidates = []
        for old in older:
            old_lower = old["content"].lower()
            if any(kw in old_lower for kw in keywords):
                candidates.append(old)

        if not candidates:
            conn.close()
            return

        # LLM 辩证推理
        for candidate in candidates[:3]:  # 最多检查 3 对
            is_contradiction = self._llm_check_contradiction(
                latest["content"], candidate["content"]
            )
            if is_contradiction:
                # 旧 fact 被新 fact 取代
                conn.execute(
                    "UPDATE user_facts SET superseded_by = ? WHERE id = ?",
                    (latest["id"], candidate["id"])
                )
                print(f"[FactMemory] 矛盾调和: fact#{candidate['id']} 被 fact#{latest['id']} 取代")

        conn.commit()
        conn.close()

    @staticmethod
    def _extract_entity_keywords(text: str) -> list[str]:
        """提取实体关键词用于预筛"""
        text_lower = text.lower()
        # 提取中文名词短语（2-4 字）和英文单词
        cn_words = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
        en_words = re.findall(r'[a-zA-Z]{3,}', text_lower)
        # 去掉过于通用的词
        stopwords = {'用户', '喜欢', '使用', '偏好', '习惯', '觉得', '认为',
                     'the', 'and', 'for', 'that', 'this', 'with', 'from'}
        keywords = [w.lower() for w in cn_words + en_words if w.lower() not in stopwords]
        return keywords[:5]

    @staticmethod
    def _llm_check_contradiction(new_fact: str, old_fact: str) -> bool:
        """
        用 LLM 辩证推理判断两条 fact 是否矛盾

        三步推理: 观察 → 分析 → 结论
        """
        try:
            from app import llm_provider

            prompt = (
                f"判断以下两条用户信息是否矛盾（新信息更新了旧信息）。\n\n"
                f"旧信息: {old_fact}\n"
                f"新信息: {new_fact}\n\n"
                f"请用三步推理:\n"
                f"1. 观察: 两条信息分别说了什么？\n"
                f"2. 分析: 它们是否关于同一主题？是互补还是矛盾？\n"
                f"3. 结论: 只回答 YES（矛盾，旧信息已过时）或 NO（不矛盾）\n\n"
                f"最后一行只输出 YES 或 NO。"
            )

            reply = llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="你是信息一致性分析专家。严格按三步推理回答，最后一行只输出 YES 或 NO。",
                temperature=0.1,
                max_tokens=200,
            )

            # 提取最后一行的结论
            lines = reply.strip().split("\n")
            last_line = lines[-1].strip().upper()
            return "YES" in last_line

        except Exception as e:
            print(f"[FactMemory] LLM 矛盾检测失败: {e}")
            return False

    # ── 统计 ─────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """获取 FactMemory 统计信息"""
        conn = _get_conn()
        total = conn.execute("SELECT COUNT(*) FROM user_facts").fetchone()[0]
        active = conn.execute(
            "SELECT COUNT(*) FROM user_facts WHERE superseded_by IS NULL"
        ).fetchone()[0]
        superseded = total - active

        # 按分类统计
        categories = {}
        rows = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM user_facts "
            "WHERE superseded_by IS NULL GROUP BY category"
        ).fetchall()
        for r in rows:
            categories[r["category"]] = r["cnt"]

        conn.close()
        return {
            "total": total,
            "active": active,
            "superseded": superseded,
            "categories": categories,
        }


# ============================================================
#  全局单例
# ============================================================
_fact_memory: Optional[FactMemory] = None


def get_fact_memory() -> FactMemory:
    """获取全局 FactMemory 单例"""
    global _fact_memory
    if _fact_memory is None:
        _fact_memory = FactMemory()
    return _fact_memory
