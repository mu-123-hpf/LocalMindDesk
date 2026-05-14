"""
活动流 (Artifacts Activity Feed)
记录 Agent 操作的实时活动日志
"""
from datetime import datetime

_activity_feed: list[dict] = []


def _add_activity(agent: str, status: str, message: str,
                  artifact_type: str = "", artifact: dict = None):
    """添加一条活动"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "agent": agent,
        "status": status,       # working / done / error / confirm
        "message": message,
        "artifact_type": artifact_type,
        "artifact": artifact,
    }
    _activity_feed.append(entry)
    if len(_activity_feed) > 100:
        _activity_feed.pop(0)
    return entry


def get_activity_feed(limit: int = 20) -> list[dict]:
    return _activity_feed[-limit:]
