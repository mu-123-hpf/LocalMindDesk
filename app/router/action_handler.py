"""
Action Handler — 操作执行引擎
包含: 代码生成、操作序列执行、安全评估、环境检测
"""
import json
import os
import re
import time
from app import llm_provider
from app.action_planner import plan_actions
from app.action_engine import SafetyGate, execute_action
from .activity import _add_activity


def _guess_file_lang(filepath: str) -> str:
    """根据文件扩展名返回代码语言标识"""
    ext = os.path.splitext(filepath)[1].lower()
    mapping = {
        '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
        '.html': 'html', '.css': 'css', '.json': 'json',
        '.md': 'markdown', '.yaml': 'yaml', '.yml': 'yaml',
        '.toml': 'toml', '.sh': 'bash', '.ps1': 'powershell',
        '.cpp': 'cpp', '.c': 'c', '.h': 'c', '.hpp': 'cpp',
        '.rs': 'rust', '.go': 'go', '.java': 'java', '.rb': 'ruby',
        '.sql': 'sql', '.xml': 'xml', '.swift': 'swift',
        '.kt': 'kotlin', '.cs': 'csharp', '.php': 'php',
        '.txt': 'text', '.ini': 'ini', '.cfg': 'ini',
        '.bat': 'batch', '.cmd': 'batch',
    }
    return mapping.get(ext, 'text')


# ============================================================
#  代码生成到文件
# ============================================================
def _try_code_to_file(user_message: str, workspace_path: str = None) -> dict | None:
    """
    检测 "在 xxx 文件里写一个贪吃蛇游戏" 类请求
    → 用 LLM 生成代码 → file_op.write 写入
    """
    msg = user_message.strip()

    # 匹配: "请你在 xxx 里写/创建/生成一个 yyy"
    m = re.match(
        r'(?:请你)?(?:帮我)?(?:用\w+)?'
        r'\s*(?:在\s*(.+?)\s*(?:里|中|文件里|文档里))?'
        r'\s*(?:写|创建|生成|编写|做)(?:一个|个)?\s*(.+)',
        msg, re.I
    )
    if not m:
        return None

    target_file = m.group(1)
    description = m.group(2).strip()

    if not target_file:
        return None

    target_file = target_file.strip().strip("\"'")

    # 推断文件扩展名
    if '.' not in os.path.basename(target_file):
        desc_lower = description.lower() + ' ' + msg.lower()
        if 'python' in desc_lower or 'py' in desc_lower:
            target_file += '.py'
        elif 'html' in desc_lower or '网页' in desc_lower:
            target_file += '.html'
        elif 'javascript' in desc_lower or 'js' in desc_lower:
            target_file += '.js'
        elif 'java' in desc_lower:
            target_file += '.java'
        elif 'c++' in desc_lower or 'cpp' in desc_lower:
            target_file += '.cpp'
        elif 'c语言' in desc_lower or desc_lower.endswith('用c'):
            target_file += '.c'
        else:
            target_file += '.py'  # 默认 Python

    # 解析路径
    if workspace_path and not os.path.isabs(target_file):
        target_file = os.path.join(workspace_path, target_file)
    target_file = os.path.normpath(target_file)

    # 推断语言
    ext = os.path.splitext(target_file)[1].lower()
    lang_map = {'.py': 'Python', '.js': 'JavaScript', '.html': 'HTML',
                '.java': 'Java', '.cpp': 'C++', '.c': 'C', '.ts': 'TypeScript'}
    lang = lang_map.get(ext, 'Python')

    _add_activity("Action-Agent", "working", f"正在生成代码: {description}")

    # 用 LLM 生成代码
    code_prompt = (
        f"请用 {lang} 编写以下程序：{description}\n\n"
        f"要求：\n"
        f"1. 只输出代码，不要任何解释或 markdown 标记\n"
        f"2. 代码必须完整可运行\n"
        f"3. 包含必要的注释\n"
        f"4. 不要输出 ```python 等代码围栏标记"
    )

    code = llm_provider.chat(
        messages=[{"role": "user", "content": code_prompt}],
        system_prompt=f"你是一个专业的 {lang} 程序员。只输出纯代码，不加任何解释。",
        temperature=0.3,
        max_tokens=2000,
    )

    # 清理代码（去除可能的 markdown 围栏）
    code = code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        if lines[-1].strip() == "```":
            code = "\n".join(lines[1:-1])
        else:
            code = "\n".join(lines[1:])
    code = code.strip()

    if not code:
        return {
            "agent": "Action-Agent",
            "reply": "⚠️ AI 未能生成代码，请尝试更详细的描述。",
        }

    # 写入文件
    result = execute_action("file_op", {
        "action": "write",
        "source": target_file,
        "content": code,
    })

    file_name = os.path.basename(target_file)
    line_count = code.count('\n') + 1

    if result.get("success"):
        _add_activity("Action-Agent", "done", f"代码已写入: {file_name}")
        reply = (
            f"✅ **已生成并写入 `{file_name}`**\n"
            f"> 📄 {line_count} 行 · {lang}\n\n"
            f"文件已保存到工作区，可在右侧文件树中点击查看。"
        )
        return {"agent": "Action-Agent", "reply": reply, "file_changed": True}
    else:
        return {
            "agent": "Action-Agent",
            "reply": f"⚠️ 代码已生成但写入失败: {result.get('error', '未知错误')}",
        }


# ============================================================
#  操作执行
# ============================================================
def exec_action(user_message: str, workspace_path: str = None) -> dict:
    """Action-Agent: 操作执行"""
    _add_activity("Action-Agent", "working", "正在规划操作...")

    # 检测"生成代码到文件"的请求
    code_file_result = _try_code_to_file(user_message, workspace_path)
    if code_file_result:
        return code_file_result

    actions = plan_actions(user_message, workspace_path=workspace_path)
    if not actions:
        return {"agent": "Action-Agent", "reply": ""}

    result = _handle_actions(user_message, actions)
    if result.get("action_confirm"):
        _add_activity("Action-Agent", "confirm", "等待用户确认操作")
    else:
        _add_activity("Action-Agent", "done", "操作完成",
                      "action_result", {"actions_count": len(actions)})
    result["agent"] = "Action-Agent"
    return result


# ============================================================
#  操作序列执行 + 安全评估
# ============================================================
VALID_TOOLS = {"shell_exec", "file_op", "gui_action", "screen_capture", "code_search", "wechat_send", "browser"}


def _handle_actions(user_message: str, actions: list[dict]) -> dict:
    """处理操作序列：安全评估 → 分级响应"""
    results = []
    pending_confirm = []
    file_changed = False
    skipped = []

    # 链式操作变量传递：前一步骤的输出可以传给后一步
    chain_vars = {}

    for i, action in enumerate(actions):
        tool = action.get("tool", "")
        params = action.get("params", {})

        # 跳过无效 tool
        if not tool or tool not in VALID_TOOLS:
            skipped.append(f"步骤 {i+1}: 未知工具 `{tool}`")
            print(f"[Router] 跳过无效 tool: {tool}, params: {params}")
            continue

        # ★ 链式变量替换
        for key, val in params.items():
            if isinstance(val, str) and val in chain_vars:
                params[key] = chain_vars[val]

        assessment = SafetyGate.assess(tool, params)

        if assessment.get("blocked"):
            # ★ 区分黑名单拦截 vs 沙盒外拦截
            blocked_path = ""
            for k in ("source", "destination", "path", "cwd"):
                if k in params and params[k]:
                    blocked_path = params[k]
                    break

            import os as _os
            from app.action_engine import FORBIDDEN_PATHS
            norm_path = _os.path.normpath(_os.path.abspath(blocked_path)) if blocked_path else ""
            is_forbidden = any(norm_path.startswith(f) for f in FORBIDDEN_PATHS)

            if is_forbidden:
                # 黑名单路径 → 永久拒绝，不可授权
                results.append({"step": i+1, "tool": tool, "params": params,
                                "status": "blocked", "reason": f"🚫 系统保护路径，无法访问: {norm_path}"})
            else:
                # 沙盒外路径 → 推入待确认队列，让用户决定
                desc = _describe_action(tool, params)
                pending_confirm.append({
                    "step": i+1, "tool": tool, "params": params,
                    "danger_level": "critical",
                    "description": f"🔒 {desc} (路径超出沙盒)",
                    "reason": f"路径 {norm_path} 不在沙盒允许范围内，需要您的授权",
                    "sandbox_blocked": True,
                    "blocked_path": norm_path,
                })
            continue

        is_chained_followup = (i > 0 and results and results[-1].get("status") == "done")

        if assessment["level"] == "safe" or is_chained_followup:
            _t0 = time.time()
            result = execute_action(tool, params)
            _dur = int((time.time() - _t0) * 1000)
            results.append({"step": i+1, "tool": tool, "params": params, "status": "done", "result": result})

            # ★ v2.0: 记录工具调用（InsightsEngine 数据源）
            try:
                from app.insights_engine import record_tool_call
                record_tool_call(tool, success=result.get("success", False), duration_ms=_dur)
            except Exception:
                pass

            # 提取结果中的路径，存入链式变量
            if tool == "screen_capture" and result.get("success") and result.get("path"):
                chain_vars["__last_screenshot__"] = result["path"]
        else:
            desc = _describe_action(tool, params)
            pending_confirm.append({
                "step": i+1, "tool": tool, "params": params,
                "danger_level": assessment["level"], "description": desc,
                "reason": assessment.get("reason", ""),
            })

    if pending_confirm:
        reply_parts = ["🔒 **以下操作需要确认：**\n"]
        for p in pending_confirm:
            icon = "🔴" if p["danger_level"] == "critical" else "🟡"
            reply_parts.append(f"{icon} **步骤 {p['step']}**: {p['description']}")
            if p["reason"]:
                reply_parts.append(f"   ⚠️ {p['reason']}")
        return {"reply": "\n".join(reply_parts), "action_confirm": pending_confirm}

    if not results and skipped:
        reply_parts = ["⚠️ **AI 规划的操作无法执行：**\n"]
        for s in skipped:
            reply_parts.append(f"  ⚠️ {s}")
        reply_parts.append("\n💡 请尝试更具体的指令，例如：")
        reply_parts.append('  • `新建一个 snake.py，内容是 print("hello")`')
        reply_parts.append('  • `写入 game.py 内容: import pygame`')
        return {"reply": "\n".join(reply_parts)}

    reply_parts = ["✅ **操作完成：**\n"]
    for r in results:
        if r["status"] == "done":
            res = r["result"]
            tool_name = r["tool"]
            params = r.get("params", {})
            if res.get("success"):
                msg = res.get("message", res.get("stdout", "成功")[:200])
                reply_parts.append(f"  ✓ 步骤 {r['step']} ({tool_name}): {msg}")
                # 文件读取→以代码块展示
                if tool_name == "file_op" and res.get("content"):
                    source = params.get("source", params.get("path", ""))
                    lang = _guess_file_lang(source)
                    content = res["content"]
                    if len(content) > 800:
                        content = content[:800] + f"\n... (共 {len(res['content'])} 字符，已截断)"
                    reply_parts.append(f"\n```{lang}\n{content}\n```")
                # 文件列表
                if "entries" in res:
                    for e in res["entries"][:20]:
                        icon = "📁" if e["is_dir"] else "📄"
                        reply_parts.append(f"    {icon} {e['name']}")
                # 代码搜索结果
                if tool_name == "code_search":
                    if res.get("matches"):
                        for match in res["matches"][:20]:
                            reply_parts.append(f"    📍 `{match['file']}:{match['line']}` — {match['content'][:100]}")
                        if res.get("truncated"):
                            reply_parts.append(f"    ... (共 {res['count']} 处匹配，已截断)")
                    elif res.get("files"):
                        for f in res["files"][:20]:
                            reply_parts.append(f"    📄 {f}")
                        if res.get("truncated"):
                            reply_parts.append(f"    ... (共 {res['count']} 个文件，已截断)")
                # 标记文件变更
                if tool_name == "file_op":
                    action_type = params.get("action", "")
                    if action_type in ("write", "edit", "append", "delete", "copy", "move", "mkdir"):
                        file_changed = True
                if tool_name in ("screen_capture", "gui_action"):
                    if res.get("path"):
                        file_changed = True
                if tool_name == "shell_exec":
                    file_changed = True
            else:
                err_msg = res.get('error', '失败')
                reply_parts.append(f"  ✗ 步骤 {r['step']}: {err_msg}")
                if tool_name == "shell_exec":
                    cmd = params.get("command", "").lower()
                    env_hint = _detect_env_issue(cmd, err_msg)
                    if env_hint:
                        reply_parts.append(f"\n{env_hint}")
        elif r["status"] == "blocked":
            reply_parts.append(f"  🚫 步骤 {r['step']}: {r['reason']}")

    result = {"reply": "\n".join(reply_parts)}
    if file_changed:
        result["file_changed"] = True

    # 提取文件路径（截图等），供微信发送下载链接
    for r in results:
        if r["status"] == "done" and r["result"].get("success"):
            res = r["result"]
            if res.get("path") and os.path.isfile(res["path"]):
                result["file_path"] = res["path"]
                result["file_name"] = os.path.basename(res["path"])
                break

    return result


# ============================================================
#  环境检测
# ============================================================
def _detect_env_issue(cmd: str, error_msg: str) -> str | None:
    """检测命令执行失败是否由环境缺失导致，返回友好提示"""
    error_lower = error_msg.lower()
    cmd_lower = cmd.lower()

    env_checks = [
        {
            "keywords": ["python"],
            "errors": ["不是内部或外部命令", "is not recognized", "no such file", "找不到", "'python' 不是"],
            "name": "Python",
            "hint": (
                "💡 **未检测到 Python 环境**\n"
                "  请先安装 Python：\n"
                "  1. 前往 https://www.python.org/downloads/ 下载安装\n"
                "  2. 安装时勾选 **\"Add Python to PATH\"**\n"
                "  3. 安装完成后重启终端，再试一次"
            ),
        },
        {
            "keywords": ["node", "npm", "npx"],
            "errors": ["不是内部或外部命令", "is not recognized", "no such file", "找不到"],
            "name": "Node.js",
            "hint": (
                "💡 **未检测到 Node.js 环境**\n"
                "  请先安装 Node.js：\n"
                "  1. 前往 https://nodejs.org/ 下载 LTS 版本\n"
                "  2. 安装完成后重启终端，再试一次"
            ),
        },
        {
            "keywords": ["gcc", "g++", "make", "cmake"],
            "errors": ["不是内部或外部命令", "is not recognized", "no such file", "找不到"],
            "name": "C/C++ 编译器",
            "hint": (
                "💡 **未检测到 C/C++ 编译器**\n"
                "  请安装 MinGW 或 MSVC：\n"
                "  • MinGW: https://winlibs.com/ 下载并添加到 PATH\n"
                "  • 或安装 Visual Studio Build Tools"
            ),
        },
        {
            "keywords": ["java", "javac"],
            "errors": ["不是内部或外部命令", "is not recognized", "no such file", "找不到"],
            "name": "Java",
            "hint": (
                "💡 **未检测到 Java 环境**\n"
                "  请安装 JDK：\n"
                "  1. 前往 https://adoptium.net/ 下载\n"
                "  2. 安装后确保 JAVA_HOME 已设置"
            ),
        },
        {
            "keywords": ["pip"],
            "errors": ["不是内部或外部命令", "is not recognized", "no module named pip"],
            "name": "pip",
            "hint": (
                "💡 **pip 不可用**\n"
                "  请确认 Python 已正确安装并在 PATH 中。\n"
                "  尝试运行: `python -m ensurepip --upgrade`"
            ),
        },
    ]

    for check in env_checks:
        cmd_match = any(kw in cmd_lower for kw in check["keywords"])
        err_match = any(e in error_lower for e in check["errors"])
        if cmd_match and err_match:
            return check["hint"]

    if "不是内部或外部命令" in error_lower or "is not recognized" in error_lower:
        return (
            "💡 **命令未找到**\n"
            "  所需的程序可能未安装或未添加到系统 PATH 中。\n"
            "  请检查相关软件是否已正确安装。"
        )

    return None


def _describe_action(tool: str, params: dict) -> str:
    if tool == "shell_exec":
        return f"执行命令: `{params.get('command', '')[:60]}`"
    elif tool == "file_op":
        action = params.get("action", "")
        src = params.get("source", params.get("path", ""))
        dst = params.get("destination", "")
        if action == "delete": return f"删除: {src}"
        elif action in ("move", "copy"): return f"{action}: {src} → {dst}"
        elif action == "write": return f"写入: {src}"
        return f"文件操作 ({action}): {src}"
    elif tool == "gui_action":
        action = params.get("action", "")
        if action == "click": return f"点击 ({params.get('x')}, {params.get('y')})"
        elif action == "type": return f"输入: {params.get('text', '')[:30]}"
        elif action == "hotkey": return f"按键: {'+'.join(params.get('keys', []))}"
        return f"GUI: {action}"
    elif tool == "code_search":
        action = params.get("action", "grep")
        pattern = params.get("pattern", "")
        return f"搜索{'代码' if action == 'grep' else '文件'}: `{pattern}`"
    elif tool == "wechat_send":
        action = params.get("action", "send_msg")
        user = params.get("user", "未知")
        if action == "send_file":
            return f"微信发送文件给 {user}"
        return f"微信发送消息给 {user}"
    elif tool == "browser":
        action = params.get("action", "")
        if action == "open": return f"🌐 浏览器打开: {params.get('url', '')[:50]}"
        elif action == "search": return f"🔍 浏览器搜索: {params.get('query', '')[:40]}"
        elif action == "click": return f"🖱️ 浏览器点击: {params.get('text', params.get('selector', ''))[:30]}"
        elif action == "type": return f"⌨️ 浏览器输入: {params.get('text', '')[:30]}"
        elif action == "close": return "❌ 关闭 AI 浏览器"
        return f"🌐 浏览器: {action}"
    return f"{tool}: {json.dumps(params, ensure_ascii=False)[:60]}"
