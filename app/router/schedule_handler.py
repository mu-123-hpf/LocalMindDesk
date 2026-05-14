"""
Schedule Handler — 自然语言定时任务管理
支持: 创建 / 取消 / 查看 / 暂停
"""
import json
import re
from app import llm_provider
from .activity import _add_activity


def exec_schedule(user_message: str) -> dict:
    """
    Schedule-Agent: 自然语言 → 定时任务
    解析 "每天6点提醒我早跑" → 创建定时任务
    """
    _add_activity("Schedule-Agent", "working", "正在解析定时任务...")

    from app.scheduler import get_scheduler
    scheduler = get_scheduler()

    msg = user_message.strip()

    # ── 子意图检测（关键词优先，不浪费 LLM 调用）──

    # 1. 查看所有定时任务
    if re.search(r'(?:查看|列出|显示|有哪些|看看).{0,4}(?:定时|提醒|任务|闹钟)', msg):
        tasks = scheduler.get_all()
        if not tasks:
            return {"agent": "Schedule-Agent", "reply": "📋 当前没有定时任务。\n\n试试说：「每天6点提醒我跑步」来创建一个吧~"}

        lines = ["📋 **当前定时任务：**\n"]
        for t in tasks:
            status = "✅" if t.get("enabled") else "⏸️"
            lines.append(
                f"{status} **{t['name']}** — {t.get('cron_description', t.get('cron', ''))}\n"
                f"   💬 {t.get('params', {}).get('message', '')}\n"
                f"   ID: `{t['id']}` · 已执行 {t.get('run_count', 0)} 次"
            )
        _add_activity("Schedule-Agent", "done", f"列出 {len(tasks)} 个任务")
        return {"agent": "Schedule-Agent", "reply": "\n\n".join(lines)}

    # 2. 取消/删除定时任务
    cancel_match = re.search(
        r'(?:取消|删除|关闭|停止|移除|去掉|不要了).{0,6}(?:定时|提醒|任务|闹钟)'
        r'|(?:定时|提醒|任务|闹钟).{0,6}(?:取消|删除|关闭|停止|去掉|不要了)',
        msg
    )
    if cancel_match:
        tasks = scheduler.get_all()
        if not tasks:
            return {"agent": "Schedule-Agent", "reply": "📋 当前没有定时任务可以取消。"}

        task_list_str = "\n".join(
            f"- ID: {t['id']}, 名称: {t['name']}, 内容: {t.get('params', {}).get('message', '')}"
            for t in tasks
        )
        try:
            match_reply = llm_provider.chat(
                messages=[{"role": "user", "content": f"用户说: {msg}\n\n当前任务列表:\n{task_list_str}"}],
                system_prompt=(
                    "用户想取消一个定时任务。根据用户描述匹配最相关的任务。\n"
                    "只输出匹配到的任务 ID，不要解释。如果无法确定，输出 ALL 表示全部取消。\n"
                    "如果用户明确说了取消所有/全部，输出 ALL。"
                ),
                temperature=0.1,
                max_tokens=50,
            )
            target_id = match_reply.strip().strip("`'\"")
        except Exception:
            target_id = "ALL"

        if target_id == "ALL" or len(tasks) == 1:
            deleted_names = []
            for t in tasks:
                scheduler.delete_task(t["id"])
                deleted_names.append(t["name"])
            _add_activity("Schedule-Agent", "done", f"已取消 {len(deleted_names)} 个任务")
            return {"agent": "Schedule-Agent", "reply": f"✅ 已取消 {len(deleted_names)} 个定时任务：\n" + "\n".join(f"  ❌ {n}" for n in deleted_names)}

        result = scheduler.delete_task(target_id)
        if result.get("success"):
            _add_activity("Schedule-Agent", "done", f"已取消任务: {target_id}")
            return {"agent": "Schedule-Agent", "reply": f"✅ 已取消定时任务 `{target_id}`"}
        else:
            lines = ["⚠️ 无法确定要取消哪个任务，当前有：\n"]
            for t in tasks:
                lines.append(f"  • **{t['name']}** (ID: `{t['id']}`)")
            lines.append("\n请说「取消 ID」或「取消所有提醒」")
            return {"agent": "Schedule-Agent", "reply": "\n".join(lines)}

    # 3. 暂停/恢复定时任务
    pause_match = re.search(r'(?:暂停|恢复|启用|禁用).{0,6}(?:定时|提醒|任务)', msg)
    if pause_match:
        tasks = scheduler.get_all()
        if not tasks:
            return {"agent": "Schedule-Agent", "reply": "📋 当前没有定时任务。"}
        for t in tasks:
            result = scheduler.toggle_task(t["id"])
            new_state = "启用 ✅" if result.get("enabled") else "暂停 ⏸️"
            _add_activity("Schedule-Agent", "done", f"任务 {t['name']} → {new_state}")
            return {"agent": "Schedule-Agent", "reply": f"✅ **{t['name']}** 已{new_state}"}

    # ── 4. 默认：创建新的定时任务 ──

    parse_prompt = (
        "你是定时任务解析器。将用户的自然语言提醒/定时需求解析为 JSON。\n\n"
        "输出格式（只输出 JSON，不要解释）:\n"
        '{"name": "任务名称", "cron": "cron表达式", "action": "动作类型", "tags": ["标签"], "params": {"message": "提醒内容", "user": "微信用户(可选)"}}\n\n'
        "规则:\n"
        "- cron 格式: 分 时 日 月 周（5 段）\n"
        "- action 可选: reminder（本地提醒）, send_wechat（微信发送）\n"
        "- 默认 action 为 reminder\n"
        "- tags: 如果涉及微信/发给某人/对象/女朋友，加 [\"wechat\"]；否则 []\n"
        "- 如果提到发微信/微信提醒，action 用 send_wechat，params 中加 user\n\n"
        "示例:\n"
        '"每天6点提醒我早跑" → {"name": "🏃 早跑提醒", "cron": "0 6 * * *", "action": "reminder", "tags": [], "params": {"message": "🏃 起床早跑啦！坚持就是胜利！"}}\n'
        '"16点提醒我给对象发我爱你" → {"name": "❤️ 爱心提醒", "cron": "0 16 * * *", "action": "reminder", "tags": ["wechat"], "params": {"message": "给对象发：我爱你❤️", "user": "文件传输助手"}}\n'
        '"每周一到五9点微信提醒上班" → {"name": "💼 上班提醒", "cron": "0 9 * * 1-5", "action": "send_wechat", "tags": ["wechat"], "params": {"user": "文件传输助手", "message": "💼 该上班了！"}}\n'
    )

    try:
        reply = llm_provider.chat(
            messages=[{"role": "user", "content": f"用户说: {user_message}"}],
            system_prompt=parse_prompt,
            temperature=0.1,
            max_tokens=300,
        )

        reply = reply.strip()
        if reply.startswith("```"):
            lines = reply.split("\n")
            reply = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            reply = reply.strip()

        task_data = json.loads(reply)
        if not isinstance(task_data, dict) or "cron" not in task_data:
            return {"agent": "Schedule-Agent", "reply": ""}

        # ★ 时间校正：从用户原文提取精确时间，覆盖 LLM 可能的错误
        time_patterns = [
            r'(\d{1,2}):(\d{2})',           # 20:08
            r'(\d{1,2})点(\d{1,2})分?',     # 20点08分
            r'(\d{1,2})：(\d{2})',           # 全角冒号
        ]
        for pat in time_patterns:
            m = re.search(pat, user_message)
            if m:
                hour, minute = int(m.group(1)), int(m.group(2))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    cron_parts = task_data["cron"].split()
                    if len(cron_parts) == 5:
                        cron_parts[0] = str(minute)
                        cron_parts[1] = str(hour)
                        task_data["cron"] = " ".join(cron_parts)
                        print(f"[Schedule-Agent] 时间校正: {hour}:{minute:02d} → cron={task_data['cron']}")
                break

        # 自动检测微信关键词
        wechat_keywords = ["微信", "对象", "女朋友", "男朋友", "老婆", "老公", "发给", "发送给"]
        tags = task_data.get("tags", [])
        if "wechat" not in tags and any(kw in user_message for kw in wechat_keywords):
            tags.append("wechat")
            task_data["tags"] = tags

        result = scheduler.add_task(task_data)

        if result.get("success"):
            task = result["task"]
            _add_activity("Schedule-Agent", "done", f"定时任务已创建: {task['name']}")
            tag_info = " · 📱 微信同步" if "wechat" in task.get("tags", []) else ""
            reply_text = (
                f"✅ **定时任务已创建！**\n\n"
                f"📋 **{task['name']}**\n"
                f"⏰ 执行计划: {task.get('cron_description', task.get('cron', ''))}\n"
                f"🎯 动作: {task['action']}{tag_info}\n"
                f"💬 内容: {task.get('params', {}).get('message', '')}\n\n"
                f"任务 ID: `{task['id']}` · 说「取消提醒」可以删除"
            )

            if not scheduler._running:
                scheduler.start()

            return {"agent": "Schedule-Agent", "reply": reply_text}
        else:
            return {"agent": "Schedule-Agent", "reply": f"⚠️ 任务创建失败: {result.get('error', '未知错误')}"}

    except json.JSONDecodeError:
        _add_activity("Schedule-Agent", "error", "解析失败")
        return {"agent": "Schedule-Agent", "reply": "⚠️ 无法解析定时任务，请尝试更明确的描述，例如：\n• 每天早上6点提醒我跑步\n• 每隔30分钟提醒我喝水\n• 每周一到五9点微信提醒我上班"}
    except Exception as e:
        _add_activity("Schedule-Agent", "error", str(e)[:50])
        return {"agent": "Schedule-Agent", "reply": f"⚠️ 创建定时任务失败: {str(e)[:200]}"}
