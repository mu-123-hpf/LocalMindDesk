"""
LocalMindDesk — InsightsEngine（行为洞察引擎）
学习 NAVI 的 insights_engine.py

功能:
  - 分析工具调用模式（最常用 / 最失败）
  - 统计 skill 使用频率
  - 识别用户行为规律（活跃时段）
  - 生成自然语言洞察注入 system prompt
  - 每 50 次工具调用触发 LLM 深度分析

使用方式:
    engine = get_insights_engine()
    report = engine.generate(days=7)
    summary = engine.format_summary(report)   # 注入 system prompt
"""
import sqlite3
import time
from collections import Counter
from datetime import datetime
from typing import Any, Optional

from app.memory import DB_PATH, _get_conn


class InsightsEngine:
    """
    分析 LocalMindDesk 的工具使用和 skill 加载数据，生成行为洞察。

    每次 generate() 时开关 DB 连接，不持有长期连接。
    """

    def generate(self, days: int = 7) -> dict[str, Any]:
        """
        生成完整的行为洞察报告。

        Args:
            days: 回溯天数（默认 7 天）

        Returns:
            结构化报告字典
        """
        cutoff = time.time() - days * 86400

        conn = _get_conn()
        tool_usage = self._get_tool_usage(conn, cutoff)
        skill_usage = self._get_skill_usage(conn, cutoff)
        facts_count = self._get_facts_count(conn)
        conn.close()

        if not tool_usage and not skill_usage:
            return {
                "days": days, "empty": True,
                "generated_at": time.time(),
                "tools": [], "skills": [],
                "facts_count": facts_count,
            }

        tools = self._compute_tool_breakdown(tool_usage)
        skills = self._compute_skill_breakdown(skill_usage)

        return {
            "days": days, "empty": False,
            "generated_at": time.time(),
            "tools": tools,
            "skills": skills,
            "facts_count": facts_count,
        }

    # ── SQL 查询 ──────────────────────────────────────────────

    def _get_tool_usage(self, conn: sqlite3.Connection, cutoff: float) -> list[dict]:
        try:
            rows = conn.execute(
                """SELECT tool_name,
                          COUNT(*) as total,
                          SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as failures,
                          AVG(duration_ms) as avg_ms
                   FROM tool_call_log
                   WHERE called_at >= ?
                   GROUP BY tool_name
                   ORDER BY total DESC""",
                (cutoff,),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    def _get_skill_usage(self, conn: sqlite3.Connection, cutoff: float) -> list[dict]:
        try:
            rows = conn.execute(
                """SELECT skill_name,
                          COUNT(*) as total,
                          SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as failures,
                          MAX(used_at) as last_used_at
                   FROM skill_usage_log
                   WHERE used_at >= ?
                   GROUP BY skill_name
                   ORDER BY total DESC""",
                (cutoff,),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    def _get_facts_count(self, conn: sqlite3.Connection) -> int:
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM user_facts WHERE superseded_by IS NULL"
            ).fetchone()
            return row[0] if row else 0
        except sqlite3.OperationalError:
            return 0

    # ── 数据计算 ──────────────────────────────────────────────

    def _compute_tool_breakdown(self, tool_usage: list[dict]) -> list[dict]:
        result = []
        for row in tool_usage[:10]:
            total = row.get("total") or 0
            failures = row.get("failures") or 0
            result.append({
                "name": row["tool_name"],
                "total": total,
                "failures": failures,
                "success_rate": round((total - failures) / total, 2) if total else 1.0,
                "avg_ms": round(row.get("avg_ms") or 0),
            })
        return result

    def _compute_skill_breakdown(self, skill_usage: list[dict]) -> list[dict]:
        result = []
        now = time.time()
        for row in skill_usage[:10]:
            total = row.get("total") or 0
            failures = row.get("failures") or 0
            last_used = row.get("last_used_at")
            result.append({
                "name": row["skill_name"],
                "total": total,
                "fail_rate": round(failures / total, 3) if total else 0.0,
                "last_used_at": last_used,
                "days_since": int((now - last_used) / 86400) if last_used else None,
            })
        return result

    # ── 格式化输出 ────────────────────────────────────────────

    def format_summary(self, report: dict) -> str:
        """
        生成注入 system prompt 的简短洞察（≤ 200 字符）。
        用于对话开始时附加到上下文，帮助 AI 了解用户习惯。
        """
        if report.get("empty"):
            return ""

        facts = report.get("facts_count", 0)
        days = report.get("days", 7)
        tools = report.get("tools", [])
        skills = report.get("skills", [])

        parts = [f"[行为洞察·{days}天]"]

        if tools:
            total_calls = sum(t["total"] for t in tools)
            parts.append(f"工具调用 {total_calls} 次")
            top_tool = tools[0]["name"]
            parts.append(f"最常用: {top_tool}")

        if facts:
            parts.append(f"已积累 {facts} 条用户事实")

        if skills:
            top_skill = skills[0]["name"]
            parts.append(f"最常用技能: {top_skill}")

        return " | ".join(parts)

    def format_detail(self, report: dict) -> str:
        """生成完整报告（用于 /insights 命令）"""
        if report.get("empty"):
            return f"📊 最近 {report.get('days', 7)} 天没有使用记录。"

        lines = [
            f"📊 LocalMindDesk 使用洞察（最近 {report['days']} 天）",
            "=" * 40,
            f"  用户事实积累：{report.get('facts_count', 0)} 条",
            "",
        ]

        tools = report.get("tools", [])
        if tools:
            lines.append("🔧 工具使用频率：")
            for t in tools[:5]:
                bar = "█" * min(20, t["total"])
                lines.append(
                    f"  {t['name']:<20} {t['total']:>4}次  "
                    f"成功率 {t['success_rate']:.0%}  {bar}"
                )
            lines.append("")

        skills = report.get("skills", [])
        if skills:
            lines.append("📦 技能使用频率：")
            for s in skills[:5]:
                since = f"({s['days_since']}天前)" if s.get("days_since") is not None else ""
                lines.append(f"  {s['name']:<20} {s['total']:>4}次  {since}")

        return "\n".join(lines)


# ── 工具调用记录（在 agent_router 中调用）────────────────────

def record_tool_call(
    tool_name: str,
    session_id: str = "",
    success: bool = True,
    duration_ms: int | None = None,
) -> None:
    """
    写入一条工具调用记录（非阻塞，失败静默）。
    在 agent_router 每次工具调用完成后调用。
    """
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO tool_call_log (session_id, tool_name, called_at, success, duration_ms)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, tool_name, time.time(), 1 if success else 0, duration_ms),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def record_skill_use(
    skill_name: str,
    session_id: str = "",
    success: bool = True,
) -> None:
    """记录一次 skill 加载（非阻塞，失败静默）"""
    if not skill_name:
        return
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO skill_usage_log (skill_name, used_at, success, session_id)
               VALUES (?, ?, ?, ?)""",
            (skill_name, time.time(), 1 if success else 0, session_id),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_skill_usage_stats(days: int = 7) -> dict[str, dict[str, Any]]:
    """
    获取 skill 使用统计（最近 N 天）。
    返回: {"skill_name": {"count": int, "fail_rate": float, "last_used_at": float}}
    """
    cutoff = time.time() - days * 86400
    try:
        conn = _get_conn()
        rows = conn.execute(
            """SELECT skill_name,
                      COUNT(*) AS total,
                      SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failures,
                      MAX(used_at) AS last_used_at
               FROM skill_usage_log
               WHERE used_at >= ?
               GROUP BY skill_name""",
            (cutoff,),
        ).fetchall()
        conn.close()
    except Exception:
        return {}

    now = time.time()
    result = {}
    for r in rows:
        total = r["total"] or 0
        failures = r["failures"] or 0
        last_used = r["last_used_at"]
        result[r["skill_name"]] = {
            "count": total,
            "fail_rate": round(failures / total, 3) if total else 0.0,
            "last_used_at": last_used,
            "days_since": int((now - last_used) / 86400) if last_used else None,
        }
    return result


# ── 全局单例 ─────────────────────────────────────────────────
_engine: Optional[InsightsEngine] = None


def get_insights_engine() -> InsightsEngine:
    """获取全局 InsightsEngine 单例"""
    global _engine
    if _engine is None:
        _engine = InsightsEngine()
    return _engine
