"""
LocalMindDesk — 可观测性指标收集
记录 LLM 调用次数、token 用量、响应时间
"""
import time
import threading
from dataclasses import dataclass, field
from typing import Optional
from app.logger import get_logger

logger = get_logger("metrics")


@dataclass
class LLMCallRecord:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: float = 0
    success: bool = True
    timestamp: float = 0
    method: str = "sync"  # sync / stream


class MetricsCollector:
    """全局指标收集器（线程安全）"""

    def __init__(self):
        self._lock = threading.Lock()
        self._llm_calls: list[LLMCallRecord] = []
        self._api_durations: dict[str, list[float]] = {}
        self._tool_calls: dict[str, dict] = {}  # tool_name -> {success: int, fail: int}
        self._start_time = time.time()
        # ★ Per-turn token budget tracking ()
        self._session_tokens: int = 0      # cumulative output tokens this session
        self._turn_history: list[dict] = []  # last N turn records

    # ── LLM 调用记录 ──

    def record_llm_call(self, model: str, input_tokens: int, output_tokens: int,
                        duration_ms: float, success: bool = True, method: str = "sync"):
        record = LLMCallRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            success=success,
            timestamp=time.time(),
            method=method,
        )
        with self._lock:
            self._llm_calls.append(record)
            # 保留最近 500 条
            if len(self._llm_calls) > 500:
                self._llm_calls = self._llm_calls[-500:]

    # ── API 耗时记录 ──

    def record_api_duration(self, endpoint: str, duration_ms: float):
        with self._lock:
            if endpoint not in self._api_durations:
                self._api_durations[endpoint] = []
            self._api_durations[endpoint].append(duration_ms)
            # 保留最近 100 条
            if len(self._api_durations[endpoint]) > 100:
                self._api_durations[endpoint] = self._api_durations[endpoint][-100:]

    # ── 工具调用记录 ──

    def record_tool_call(self, tool_name: str, success: bool):
        with self._lock:
            if tool_name not in self._tool_calls:
                self._tool_calls[tool_name] = {"success": 0, "fail": 0}
            key = "success" if success else "fail"
            self._tool_calls[tool_name][key] += 1

    # ── Per-turn token tracking ──

    def record_turn_tokens(self, output_tokens: int, duration_ms: float = 0):
        """Record tokens generated in a single turn."""
        with self._lock:
            self._session_tokens += output_tokens
            self._turn_history.append({
                "tokens": output_tokens,
                "duration_ms": duration_ms,
                "timestamp": time.time(),
            })
            if len(self._turn_history) > 50:
                self._turn_history = self._turn_history[-50:]

    def get_session_token_stats(self) -> dict:
        """Get session-level token usage stats for frontend display."""
        with self._lock:
            turns = self._turn_history.copy()
            total = self._session_tokens
        return {
            "session_total_tokens": total,
            "turn_count": len(turns),
            "avg_tokens_per_turn": round(total / max(len(turns), 1)),
            "last_turn_tokens": turns[-1]["tokens"] if turns else 0,
        }

    # ── 导出统计 ──

    def get_summary(self) -> dict:
        with self._lock:
            calls = self._llm_calls.copy()
            api_d = {k: v.copy() for k, v in self._api_durations.items()}
            tools = {k: v.copy() for k, v in self._tool_calls.items()}

        total_calls = len(calls)
        total_input = sum(c.input_tokens for c in calls)
        total_output = sum(c.output_tokens for c in calls)
        success_count = sum(1 for c in calls if c.success)
        avg_duration = sum(c.duration_ms for c in calls) / max(total_calls, 1)

        # 按模型统计
        model_stats = {}
        for c in calls:
            if c.model not in model_stats:
                model_stats[c.model] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
            model_stats[c.model]["calls"] += 1
            model_stats[c.model]["input_tokens"] += c.input_tokens
            model_stats[c.model]["output_tokens"] += c.output_tokens

        # API P50/P99
        api_stats = {}
        for endpoint, durations in api_d.items():
            if durations:
                sorted_d = sorted(durations)
                api_stats[endpoint] = {
                    "count": len(sorted_d),
                    "p50_ms": round(sorted_d[len(sorted_d) // 2], 1),
                    "p99_ms": round(sorted_d[int(len(sorted_d) * 0.99)], 1),
                    "avg_ms": round(sum(sorted_d) / len(sorted_d), 1),
                }

        uptime = time.time() - self._start_time

        return {
            "uptime_seconds": round(uptime),
            "llm": {
                "total_calls": total_calls,
                "success_rate": round(success_count / max(total_calls, 1), 3),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "avg_duration_ms": round(avg_duration, 1),
                "by_model": model_stats,
            },
            "api": api_stats,
            "tools": tools,
        }


# ── 全局实例 ──
_metrics: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
