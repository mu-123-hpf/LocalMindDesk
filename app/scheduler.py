"""
LocalMindDesk — 定时任务调度器
支持 cron 表达式和简单间隔，后台线程执行，持久化到 data/schedules.json
"""
import os
import json
import time
import uuid
import threading
from datetime import datetime, timedelta
from typing import Optional, Callable
import sys


def _safe_print(msg: str):
    """Windows GBK 安全打印，避免 emoji 导致 UnicodeEncodeError"""
    try:
        print(msg)
    except UnicodeEncodeError:
        try:
            sys.stdout.buffer.write((msg + "\n").encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
        except Exception:
            pass  # 实在打印不了就放弃


# ============================================================
#  轻量 Cron 解析器
# ============================================================
class CronParser:
    """
    支持标准 5 段 cron: 分 时 日 月 周
    例: "0 8 * * *" = 每天8点, "*/5 * * * *" = 每5分钟
    """

    @staticmethod
    def matches(cron_expr: str, dt: datetime) -> bool:
        """判断给定时间是否匹配 cron 表达式"""
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return False

        fields = [dt.minute, dt.hour, dt.day, dt.month, dt.weekday()]
        # weekday: cron 用 0=Sunday, Python 用 0=Monday，转换
        ranges = [
            (0, 59),   # minute
            (0, 23),   # hour
            (1, 31),   # day
            (1, 12),   # month
            (0, 6),    # weekday (0=Sunday in cron)
        ]

        for i, part in enumerate(parts):
            value = fields[i]
            # 转换周几：Python Monday=0 → cron Sunday=0
            if i == 4:
                value = (value + 1) % 7  # Python Mon=0 → cron Mon=1, Sun=0

            if not CronParser._field_matches(part, value, ranges[i]):
                return False
        return True

    @staticmethod
    def _field_matches(field: str, value: int, valid_range: tuple) -> bool:
        """解析单个 cron 字段"""
        if field == "*":
            return True

        for item in field.split(","):
            # 处理 step: */5 或 1-10/2
            if "/" in item:
                range_part, step = item.split("/", 1)
                step = int(step)
                if range_part == "*":
                    if value % step == 0:
                        return True
                elif "-" in range_part:
                    start, end = map(int, range_part.split("-"))
                    if start <= value <= end and (value - start) % step == 0:
                        return True
            # 处理范围: 1-5
            elif "-" in item:
                start, end = map(int, item.split("-"))
                if start <= value <= end:
                    return True
            # 精确值
            else:
                if int(item) == value:
                    return True
        return False

    @staticmethod
    def describe(cron_expr: str) -> str:
        """将 cron 表达式转为人类可读描述"""
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return cron_expr

        minute, hour, day, month, weekday = parts
        desc = []

        if weekday != "*":
            week_names = {
                "0": "周日", "1": "周一", "2": "周二", "3": "周三",
                "4": "周四", "5": "周五", "6": "周六",
                "1-5": "工作日", "0,6": "周末",
            }
            desc.append(week_names.get(weekday, f"周{weekday}"))

        if day != "*":
            desc.append(f"每月{day}日")

        if hour != "*" and minute != "*":
            desc.append(f"{hour}:{minute.zfill(2)}")
        elif hour != "*":
            desc.append(f"{hour}点")

        if minute.startswith("*/"):
            desc.append(f"每{minute[2:]}分钟")
        elif hour.startswith("*/"):
            desc.append(f"每{hour[2:]}小时")

        return " ".join(desc) if desc else "自定义"


# ============================================================
#  任务安全等级
# ============================================================
class SafetyLevel:
    SAFE = "safe"              # 自动执行（发消息、查询等）
    SENSITIVE = "sensitive"    # 需要确认（删文件、执行命令等）

    # 安全动作列表
    SAFE_ACTIONS = {
        "send_wechat", "send_message", "reminder",
        "query_weather", "query_time", "notify",
    }

    @staticmethod
    def classify(action: str) -> str:
        if action in SafetyLevel.SAFE_ACTIONS:
            return SafetyLevel.SAFE
        return SafetyLevel.SENSITIVE


# ============================================================
#  调度任务数据模型
# ============================================================
class ScheduledTask:
    def __init__(self, **kwargs):
        self.id: str = kwargs.get("id", str(uuid.uuid4())[:8])
        self.name: str = kwargs.get("name", "未命名任务")
        self.cron: str = kwargs.get("cron", "")           # cron 表达式
        self.interval_min: int = kwargs.get("interval_min", 0)  # 间隔（分钟），0=用cron
        self.action: str = kwargs.get("action", "reminder")     # 动作类型
        self.params: dict = kwargs.get("params", {})            # 动作参数
        self.tags: list = kwargs.get("tags", [])                # 标签（如 ["wechat"]）
        self.enabled: bool = kwargs.get("enabled", True)
        self.safety: str = kwargs.get("safety", "")       # 安全等级（空=自动判断）
        self.created_at: str = kwargs.get("created_at", datetime.now().isoformat())
        self.last_run: str = kwargs.get("last_run", "")
        self.run_count: int = kwargs.get("run_count", 0)
        self._last_check: Optional[datetime] = None  # 防止同一分钟重复触发

    @property
    def safety_level(self) -> str:
        return self.safety or SafetyLevel.classify(self.action)

    @property
    def cron_description(self) -> str:
        if self.interval_min > 0:
            if self.interval_min >= 60:
                return f"每{self.interval_min // 60}小时"
            return f"每{self.interval_min}分钟"
        return CronParser.describe(self.cron)

    def should_run(self, now: datetime) -> bool:
        """判断当前时间是否应触发"""
        if not self.enabled:
            return False

        if self.interval_min > 0:
            # 间隔模式
            if not self.last_run:
                return True
            last = datetime.fromisoformat(self.last_run)
            return (now - last) >= timedelta(minutes=self.interval_min)
        elif self.cron:
            # cron 模式：同一分钟只触发一次
            minute_key = now.replace(second=0, microsecond=0)
            if self._last_check == minute_key:
                return False
            if CronParser.matches(self.cron, now):
                self._last_check = minute_key
                return True
        return False

    def mark_run(self):
        self.last_run = datetime.now().isoformat()
        self.run_count += 1

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "cron": self.cron,
            "interval_min": self.interval_min,
            "action": self.action,
            "params": self.params,
            "tags": self.tags,
            "enabled": self.enabled,
            "safety": self.safety_level,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "run_count": self.run_count,
            "cron_description": self.cron_description,
        }


# ============================================================
#  预设任务模板
# ============================================================
TASK_TEMPLATES = [
    {
        "id": "tpl-morning",
        "name": "☀️ 每日学习提醒",
        "cron": "0 8 * * *",
        "action": "send_wechat",
        "params": {"user": "文件传输助手", "message": "☀️ 早上好！该学习了，坚持就是胜利！💪"},
    },
    {
        "id": "tpl-workday",
        "name": "💼 工作日开机问候",
        "cron": "0 9 * * 1-5",
        "action": "send_wechat",
        "params": {"user": "文件传输助手", "message": "💼 工作日开始了，今天也要加油！"},
    },
    {
        "id": "tpl-night",
        "name": "🌙 晚间休息提醒",
        "cron": "0 22 * * *",
        "action": "send_wechat",
        "params": {"user": "文件传输助手", "message": "🌙 晚上了，注意休息，别熬夜哦！"},
    },
    {
        "id": "tpl-hourly",
        "name": "⏰ 每小时提醒",
        "cron": "0 * * * *",
        "action": "reminder",
        "params": {"message": "⏰ 又过了一小时，起来活动一下！"},
    },
]


# ============================================================
#  Scheduler 调度器
# ============================================================
_DATA_FILE = "data/schedules.json"


class Scheduler:
    """后台定时任务调度器"""

    def __init__(self):
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._action_handler: Optional[Callable] = None  # 任务执行回调
        self._log: list[dict] = []  # 最近执行日志
        self._load()

    def set_action_handler(self, handler: Callable):
        """设置任务执行回调函数"""
        self._action_handler = handler

    # ---------- CRUD ----------

    def add_task(self, data: dict) -> dict:
        task = ScheduledTask(**data)
        self._tasks[task.id] = task
        self._save()
        return {"success": True, "task": task.to_dict()}

    def update_task(self, task_id: str, data: dict) -> dict:
        task = self._tasks.get(task_id)
        if not task:
            return {"success": False, "error": "任务不存在"}
        for key in ["name", "cron", "interval_min", "action", "params", "tags", "enabled", "safety"]:
            if key in data:
                setattr(task, key, data[key])
        self._save()
        return {"success": True, "task": task.to_dict()}

    def delete_task(self, task_id: str) -> dict:
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._save()
            return {"success": True}
        return {"success": False, "error": "任务不存在"}

    def toggle_task(self, task_id: str) -> dict:
        task = self._tasks.get(task_id)
        if not task:
            return {"success": False, "error": "任务不存在"}
        task.enabled = not task.enabled
        self._save()
        return {"success": True, "enabled": task.enabled}

    def run_now(self, task_id: str) -> dict:
        """立即执行一次"""
        task = self._tasks.get(task_id)
        if not task:
            return {"success": False, "error": "任务不存在"}
        return self._execute_task(task)

    def get_all(self) -> list[dict]:
        return [t.to_dict() for t in self._tasks.values()]

    def get_templates(self) -> list[dict]:
        return TASK_TEMPLATES

    def get_log(self, limit: int = 20) -> list[dict]:
        return self._log[-limit:]

    # ---------- 调度循环 ----------

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        _safe_print(f"[Scheduler] 已启动，{len(self._tasks)} 个任务")

    def stop(self):
        self._running = False
        _safe_print("[Scheduler] 已停止")

    def _loop(self):
        while self._running:
            now = datetime.now()
            for task in list(self._tasks.values()):
                if task.should_run(now):
                    try:
                        self._execute_task(task)
                    except Exception as e:
                        _safe_print(f"[Scheduler] 任务 {task.name} 执行异常: {e}")
            time.sleep(10)  # 每10秒检查一次

    def _execute_task(self, task: ScheduledTask) -> dict:
        """执行任务"""
        _safe_print(f"[Scheduler] 执行任务: {task.name} ({task.action})")
        task.mark_run()
        self._save()

        result = {"task_id": task.id, "task_name": task.name, "time": task.last_run}

        if self._action_handler:
            try:
                r = self._action_handler(task.action, task.params, task.safety_level, task.tags)
                result["success"] = r.get("success", False)
                result["output"] = r.get("message", r.get("output", ""))
            except Exception as e:
                result["success"] = False
                result["output"] = str(e)
        else:
            result["success"] = False
            result["output"] = "未设置任务处理器"

        self._log.append(result)
        if len(self._log) > 100:
            self._log = self._log[-50:]

        # ★ v2.0: 通知主动对话引擎
        try:
            from app.proactive_engine import get_proactive_engine
            pe = get_proactive_engine()
            output = result.get("output", "")[:100]
            pe.notify_scheduler_trigger(task.name, output)
        except Exception:
            pass

        return result

    # ---------- 持久化 ----------

    def _save(self):
        os.makedirs("data", exist_ok=True)
        data = {tid: t.to_dict() for tid, t in self._tasks.items()}
        with open(_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not os.path.exists(_DATA_FILE):
            return
        try:
            with open(_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for tid, tdata in data.items():
                self._tasks[tid] = ScheduledTask(**tdata)
            _safe_print(f"[Scheduler] 已加载 {len(self._tasks)} 个定时任务")
        except Exception as e:
            _safe_print(f"[Scheduler] 加载失败: {e}")


# ============================================================
#  全局单例
# ============================================================
_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler
