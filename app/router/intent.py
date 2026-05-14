"""
意图分析器
快速关键词检测所有意图类型
"""
from app.meta_agent import detect_config_intent
from app.action_planner import detect_action_intent


def analyze_intents(user_message: str) -> list[str]:
    """
    快速关键词检测所有意图类型
    返回 ["config", "action", "tool", "schedule", "chat"]
    """
    intents = []

    if detect_config_intent(user_message):
        intents.append("config")

    if detect_action_intent(user_message):
        intents.append("action")

    # ★ v2.0: 定时/提醒意图检测（含创建/取消/查看/暂停）
    schedule_kw = ["提醒", "定时", "每天", "每周", "每小时", "每隔", "闹钟",
                   "remind", "schedule", "cron", "每日", "定期",
                   "点提醒", "点叫我", "点通知",
                   "取消提醒", "删除提醒", "取消定时", "删除定时",
                   "查看提醒", "查看定时", "有哪些提醒", "有哪些定时",
                   "暂停提醒", "恢复提醒"]
    lower = user_message.lower()
    if any(kw in lower for kw in schedule_kw):
        intents.append("schedule")

    # 工具意图关键词
    tool_kw = ["搜索", "查一下", "ppt", "幻灯片", "演示", "文档", "word",
               "记住", "记一下", "search", "memo"]
    if any(kw in lower for kw in tool_kw):
        intents.append("tool")

    if not intents:
        intents.append("chat")

    return intents
