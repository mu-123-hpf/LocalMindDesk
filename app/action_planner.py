"""
LocalMindDesk — Action Planner（操作规划器）
自然语言 → 结构化操作序列
"""
import os
import json
import re
from app import llm_provider
from app.prompt_loader import load_agent_prompt


def _get_action_prompt() -> str:
    prompt = load_agent_prompt("action_agent")
    return prompt or "你是操作规划器。将用户请求转为 JSON 操作序列。"


# 操作意图关键词
ACTION_KEYWORDS = [
    "打开", "运行", "执行", "启动", "关闭",
    "移动", "复制", "删除", "创建", "新建",
    "安装", "卸载", "下载", "更新", "升级",
    "文件", "文件夹", "目录", "桌面",
    "截屏", "截图", "屏幕",
    "点击", "输入", "按键",
    "终端", "命令", "cmd", "powershell",
    "git", "npm", "pip", "python", "yarn",
    "搜索代码", "grep", "find", "查找代码", "搜索文件",
    "看看", "查看", "列出", "显示",
    "编辑", "修改", "替换", "改成", "写入", "追加",
    "新建文件", "创建文件",
    "open", "run", "exec", "move", "copy", "delete",
    "install", "uninstall", "download", "update", "upgrade",
    "screenshot", "click", "type",
    "edit", "modify", "replace", "create", "write", "append",
    "微信", "发给", "发送", "wechat",
    # 浏览器操作
    "浏览器", "browser", "搜索一下", "网页", "网站",
]


def detect_action_intent(message: str) -> bool:
    """检测是否包含操作意图"""
    # 排除工作区指令（由前端处理）
    if re.search(r'打开(?:项目|文件夹|目录)', message):
        return False
    lower = message.lower()
    score = sum(1 for kw in ACTION_KEYWORDS if kw in lower)
    return score >= 1


def _quick_plan(user_message: str, workspace_path: str = None) -> list[dict] | None:
    """
    对常见操作做快速正则匹配，不依赖 LLM。
    匹配成功返回 actions list，失败返回 None（交给 LLM 处理）
    """
    msg = user_message.strip()

    def _find_in_workspace(filename, ws_root):
        """在工作区中递归搜索文件，返回完整路径"""
        if not ws_root:
            return None
        # 先检查根目录
        direct = os.path.join(ws_root, filename)
        if os.path.exists(direct):
            return os.path.normpath(direct)
        # 递归搜索子目录（最深3层）
        for root, dirs, files in os.walk(ws_root):
            depth = root.replace(ws_root, '').count(os.sep)
            if depth > 3:
                dirs.clear()
                continue
            dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', '.venv'}]
            if filename in files:
                return os.path.normpath(os.path.join(root, filename))
        return None

    # --- 浏览器搜索: "浏览器搜索xxx" / "搜索一下xxx" / "帮我搜xxx" ---
    m = re.match(
        r'(?:请你)?(?:帮我)?(?:在浏览器|在网页|用浏览器|浏览器|用google|用百度|用bing)?'
        r'\s*(?:搜索一下|搜索|搜一下|搜一搜|查一下|查一查|google|百度一下|bing)'
        r'\s+(.+?)$', msg, re.I)
    if m:
        query = m.group(1).strip().strip('"\'')
        # 检测搜索引擎偏好
        engine = "google"
        if re.search(r'百度|baidu', msg, re.I):
            engine = "baidu"
        elif re.search(r'bing', msg, re.I):
            engine = "bing"
        return [{"tool": "browser", "params": {"action": "search", "query": query, "engine": engine}}]

    # --- 浏览器打开网页: "打开百度" / "打开 google.com" / "帮我打开xxx网站" ---
    m = re.match(
        r'(?:请你)?(?:帮我)?(?:在浏览器|用浏览器)?'
        r'\s*(?:打开|访问|进入|open)\s*(?:网页|网站|页面)?\s*(.+?)$', msg, re.I)
    if m:
        target = m.group(1).strip().strip('"\'')
        # 识别是网址还是应用名
        is_url = (
            '.' in target and ' ' not in target and
            any(ext in target.lower() for ext in ['.com', '.cn', '.org', '.net', '.io', '.dev', '.app', 'http'])
        )
        # 常见网站名映射
        site_map = {
            "百度": "https://www.baidu.com",
            "谷歌": "https://www.google.com",
            "google": "https://www.google.com",
            "bilibili": "https://www.bilibili.com", "b站": "https://www.bilibili.com",
            "知乎": "https://www.zhihu.com",
            "github": "https://github.com",
            "youtube": "https://www.youtube.com",
            "淘宝": "https://www.taobao.com",
            "京东": "https://www.jd.com",
            "微博": "https://weibo.com",
        }
        url = site_map.get(target.lower())
        if url:
            return [{"tool": "browser", "params": {"action": "open", "url": url}}]
        elif is_url:
            return [{"tool": "browser", "params": {"action": "open", "url": target}}]
        # 不是网址 → 走后续的应用打开逻辑

    # --- 浏览器控制: "在浏览器输入xxx" / "点击xxx按钮" ---
    m = re.match(r'(?:在浏览器|在网页)(?:里|中|上)?\s*(?:输入|打字|填写)\s+(.+)', msg, re.I)
    if m:
        text = m.group(1).strip().strip('"\'')
        return [{"tool": "browser", "params": {"action": "type", "text": text, "submit": True}}]

    m = re.match(r'(?:在浏览器|在网页)(?:里|中|上)?\s*(?:点击|按|click)\s+(.+)', msg, re.I)
    if m:
        target = m.group(1).strip().strip('"\'')
        return [{"tool": "browser", "params": {"action": "click", "text": target}}]

    # --- 关闭浏览器 ---
    if re.match(r'(?:关闭|关掉|退出)\s*(?:AI)?(?:浏览器|browser)', msg, re.I):
        return [{"tool": "browser", "params": {"action": "close"}}]

    # --- 复合操作: "关闭当前页面打开todesk" （必须在单独关闭/打开之前匹配）---
    m = re.match(r'(?:请你)?(?:帮我)?关闭\s*(.+?)\s*(?:然后|再|并|,|，)?(?:打开|启动)\s*(.+?)$', msg, re.I)
    if m:
        close_target = m.group(1).strip()
        open_target = m.group(2).strip()
        actions = []
        # 关闭
        if re.search(r'当前|页面|窗口', close_target):
            actions.append({"tool": "gui_action", "params": {"action": "hotkey", "keys": ["alt", "F4"]}})
        else:
            actions.append({"tool": "shell_exec", "params": {"command": f"taskkill /im {close_target}.exe /f", "cwd": "."}})
        # 打开
        actions.append({"tool": "shell_exec", "params": {"command": f"start {open_target}", "cwd": "."}})
        return actions

    # --- 打开应用: "打开todesk" / "打开微信" / "打开记事本" ---
    m = re.match(r'(?:请你)?(?:帮我)?(?:打开|启动|运行|open|start)\s*(.+?)(?:\s*(?:软件|程序|应用|app))?$', msg, re.I)
    if m:
        app_name = m.group(1).strip().strip('"\'')
        # 常见应用映射
        app_map = {
            "todesk": "todesk", "远程": "todesk",
            "微信": "WeChat", "wechat": "WeChat",
            "记事本": "notepad", "notepad": "notepad",
            "浏览器": "start chrome", "chrome": "start chrome",
            "资源管理器": "explorer", "explorer": "explorer",
            "任务管理器": "taskmgr", "计算器": "calc",
            "画图": "mspaint", "cmd": "cmd", "终端": "wt",
            "vscode": "code", "vs code": "code",
        }
        cmd = app_map.get(app_name.lower(), f"start {app_name}")
        return [{"tool": "shell_exec", "params": {"command": f"start {cmd}" if not cmd.startswith("start") else cmd, "cwd": "."}}]

    # --- 关闭窗口/应用: "关闭当前页面" / "关闭浏览器" ---
    m = re.match(r'(?:请你)?(?:帮我)?(?:关闭|关掉|退出|close)\s*(.+?)$', msg, re.I)
    if m:
        target = m.group(1).strip().strip('"\'')
        # "关闭当前页面/窗口" → Alt+F4
        if re.search(r'当前|页面|窗口|这个', target):
            return [{"tool": "gui_action", "params": {"action": "hotkey", "keys": ["alt", "F4"]}}]
        # "关闭xxx应用"
        app_kill_map = {
            "todesk": "todesk", "微信": "WeChat", "wechat": "WeChat",
            "浏览器": "chrome", "chrome": "chrome",
            "记事本": "notepad", "notepad": "notepad",
        }
        kill_target = app_kill_map.get(target.lower(), target)
        return [{"tool": "shell_exec", "params": {"command": f"taskkill /im {kill_target}.exe /f", "cwd": "."}}]

    # --- 安装包: "安装 itchat" / "pip install xxx" / "npm install xxx" ---
    m = re.match(r'(?:安装|install|下载安装|帮我安装|帮忙安装)\s+(.+)', msg, re.I)
    if m:
        pkg = m.group(1).strip().strip('"\'')
        # 判断包管理器类型
        if re.match(r'^npm\s', pkg, re.I):
            return [{"tool": "shell_exec", "params": {"command": pkg, "cwd": workspace_path or "."}}]
        elif re.match(r'^yarn\s', pkg, re.I):
            return [{"tool": "shell_exec", "params": {"command": pkg, "cwd": workspace_path or "."}}]
        elif re.match(r'^pip\s', pkg, re.I):
            return [{"tool": "shell_exec", "params": {"command": pkg, "cwd": workspace_path or "."}}]
        else:
            # 默认用 pip
            return [{"tool": "shell_exec", "params": {"command": f"pip install {pkg}", "cwd": workspace_path or "."}}]

    # pip install / npm install 直接命令
    m = re.match(r'(pip\s+install\s+.+|npm\s+install\s+.+|yarn\s+add\s+.+)', msg, re.I)
    if m:
        return [{"tool": "shell_exec", "params": {"command": m.group(1).strip(), "cwd": workspace_path or "."}}]

    # --- 卸载包: "卸载 itchat" / "pip uninstall xxx" ---
    m = re.match(r'(?:卸载|uninstall|删除包|移除)\s+(.+)', msg, re.I)
    if m:
        pkg = m.group(1).strip().strip('"\'')
        if re.match(r'^(pip|npm|yarn)\s', pkg, re.I):
            return [{"tool": "shell_exec", "params": {"command": pkg, "cwd": workspace_path or "."}}]
        else:
            return [{"tool": "shell_exec", "params": {"command": f"pip uninstall -y {pkg}", "cwd": workspace_path or "."}}]

    # --- 运行/执行 文件 ---
    m = re.match(r'(?:运行|执行|启动|跑|run)\s*(?:一下)?\s*(.+)', msg, re.I)
    if m:
        target = m.group(1).strip().strip('"\'')
        # 如果不是绝对路径，在工作区中搜索文件
        if workspace_path and not os.path.isabs(target):
            found = _find_in_workspace(target, workspace_path)
            full_path = found if found else os.path.normpath(os.path.join(workspace_path, target))
        else:
            full_path = os.path.normpath(target)
        cwd = os.path.dirname(full_path) if os.path.dirname(full_path) else workspace_path
        fname = os.path.basename(full_path)
        # exe 文件：用 cmd /k 在工作目录下执行（窗口保持打开）
        if full_path.lower().endswith('.exe'):
            return [{"tool": "shell_exec", "params": {"command": f"cmd /k {fname}", "cwd": cwd}}]
        # py 文件用 python 执行
        elif full_path.lower().endswith('.py'):
            return [{"tool": "shell_exec", "params": {"command": f"python {fname}", "cwd": cwd}}]
        # c 文件先编译再运行
        elif full_path.lower().endswith('.c'):
            out = os.path.splitext(fname)[0] + '.exe'
            return [
                {"tool": "shell_exec", "params": {"command": f"gcc {fname} -o {out}", "cwd": cwd}},
                {"tool": "shell_exec", "params": {"command": f"cmd /k {out}", "cwd": cwd}},
            ]
        # 其他当命令执行
        else:
            return [{"tool": "shell_exec", "params": {"command": target, "cwd": cwd}}]

    # --- 编译 C/C++ ---
    m = re.match(r'(?:编译|compile)\s*(?:一下)?\s*(.+)', msg, re.I)
    if m:
        target = m.group(1).strip().strip('"\'')
        if workspace_path and not os.path.isabs(target):
            target = os.path.join(workspace_path, target)
        target = os.path.normpath(target)
        out = os.path.splitext(target)[0] + '.exe'
        return [{"tool": "shell_exec", "params": {"command": f'gcc "{target}" -o "{out}"', "cwd": workspace_path or os.path.dirname(target)}}]

    # --- 读取/查看 文件（排除"打开项目/文件夹/目录"以避免与工作区冲突） ---
    m = re.match(r'(?:读取|查看|看看|阅读|read|cat)\s*(?:一下)?\s*(.+?)(?:\s*的内容)?$', msg, re.I)
    if m:
        target = m.group(1).strip().strip('"\'')
        if workspace_path and not os.path.isabs(target):
            target = os.path.join(workspace_path, target)
        target = os.path.normpath(target)
        return [{"tool": "file_op", "params": {"action": "read", "source": target}}]

    # --- 列出文件 ---
    if re.match(r'(?:列出|显示|看看|查看)\s*(?:一下)?(?:文件|目录|文件夹|所有)', msg):
        target = workspace_path or os.path.expanduser("~/Desktop")
        return [{"tool": "file_op", "params": {"action": "list", "source": target}}]

    # --- 微信发送（优先于截图匹配） ---
    m_wechat = re.search(r'(?:发给|发送给?|转发给?)\s*(?:微信|wechat)', msg, re.I)
    if m_wechat:
        # 提取用户名
        m_user = re.search(r'(?:用户名?(?:为|叫|是)?|叫|给)\s*["\']?(\S+?)["\']?\s*(?:的|$)', msg)
        target_user = m_user.group(1) if m_user else ""
        # 检查是否包含文件/截图
        has_screenshot = bool(re.search(r'(?:截图|截屏|screenshot)', msg, re.I))
        if has_screenshot:
            # 先截图再发送
            return [
                {"tool": "screen_capture", "params": {"save_to": workspace_path or ""}},
                {"tool": "wechat_send", "params": {"action": "send_file", "user": target_user, "file": "__last_screenshot__"}},
            ]
        else:
            # 发送消息
            m_content = re.search(r'(?:发|说|告诉)\s*(?:给)?\s*\S+?\s+(.+)', msg)
            content = m_content.group(1) if m_content else msg
            return [{"tool": "wechat_send", "params": {"action": "send_msg", "user": target_user, "content": content}}]

    # --- 截屏（扩展匹配，排除"发给"场景） ---
    if not re.search(r'(?:发给|发送)', msg):
        m_screen = re.search(r'(?:截屏|截图|截个[图屏]|screenshot|屏幕截图|界面截[图屏])', msg, re.I)
        if m_screen:
            save_to = ""
            # 提取保存路径：放到/保存到/存到 + 路径/文件夹
            m_save = re.search(r'(?:放到|保存到|存到|放入|存入|放进|复制到)\s*(?:当前)?(?:这个)?(?:文件夹|目录|路径)?(?:\s*中)?', msg)
            if m_save and workspace_path:
                save_to = workspace_path
            return [{"tool": "screen_capture", "params": {"save_to": save_to}}]

    # --- 代码搜索（grep）: "搜索代码 xxx" / "grep xxx" ---
    m = re.match(r'(?:搜索代码|搜索|查找代码|查找|grep)\s+(.+?)(?:\s+(?:在|from)\s+(.+))?$', msg, re.I)
    if m:
        pattern = m.group(1).strip().strip('"\'')
        search_path = m.group(2)
        if search_path:
            search_path = search_path.strip().strip('"\'')
            if workspace_path and not os.path.isabs(search_path):
                search_path = os.path.join(workspace_path, search_path)
        else:
            search_path = workspace_path or os.path.expanduser("~/Desktop")
        return [{"tool": "code_search", "params": {"action": "grep", "pattern": pattern, "path": search_path}}]

    # --- 文件名搜索（find）: "找文件 *.py" / "find *.py" ---
    m = re.match(r'(?:找文件|搜索文件|查找文件|find)\s+(.+?)(?:\s+(?:在|from)\s+(.+))?$', msg, re.I)
    if m:
        pattern = m.group(1).strip().strip('"\'')
        search_path = m.group(2)
        if search_path:
            search_path = search_path.strip().strip('"\'')
            if workspace_path and not os.path.isabs(search_path):
                search_path = os.path.join(workspace_path, search_path)
        else:
            search_path = workspace_path or os.path.expanduser("~/Desktop")
        return [{"tool": "code_search", "params": {"action": "find", "pattern": pattern, "path": search_path}}]

    # --- 新建/创建 文件 ---
    m = re.match(r'(?:新建|创建|create)\s*(?:一个)?\s*(?:文件)?\s*(.+?)(?:[,，]\s*内容(?:是|为)?[:：]?\s*(.+))?$', msg, re.I | re.S)
    if m:
        target = m.group(1).strip().strip('"\'')
        file_content = m.group(2) or ''
        if workspace_path and not os.path.isabs(target):
            target = os.path.join(workspace_path, target)
        target = os.path.normpath(target)
        return [{"tool": "file_op", "params": {"action": "write", "source": target, "content": file_content.strip()}}]

    # --- 删除 文件 ---
    m = re.match(r'(?:删除|删掉|delete|remove|rm)\s*(?:一下)?\s*(.+)', msg, re.I)
    if m:
        target = m.group(1).strip().strip('"\'')
        if workspace_path and not os.path.isabs(target):
            found = _find_in_workspace(target, workspace_path)
            target = found if found else os.path.join(workspace_path, target)
        target = os.path.normpath(target)
        return [{"tool": "file_op", "params": {"action": "delete", "source": target}}]

    # --- 按行编辑: "把 test.py 第5行改成 xxx" ---
    m = re.match(r'把\s*(.+?)\s*(?:的)?\s*第\s*(\d+)\s*行\s*(?:改成|改为|修改为|替换为|换成)\s*(.+)', msg)
    if m:
        target = m.group(1).strip().strip('"\'')
        line_num = int(m.group(2))
        new_content = m.group(3).strip().strip('"\'')
        if workspace_path and not os.path.isabs(target):
            found = _find_in_workspace(target, workspace_path)
            target = found if found else os.path.join(workspace_path, target)
        target = os.path.normpath(target)
        return [{"tool": "file_op", "params": {"action": "edit", "source": target, "line": line_num, "content": new_content}}]

    # --- 搜索替换: "在 test.py 里把 old_text 替换成 new_text" ---
    m = re.match(r'(?:在\s*(.+?)\s*(?:里|中)\s*)?把\s*["\'“]?(.+?)["\'”]?\s*(?:替换成|改成|改为|替换为|换成)\s*["\'“]?(.+?)["\'”]?\s*$', msg)
    if m:
        target_file = m.group(1)
        find_str = m.group(2).strip()
        replace_str = m.group(3).strip()
        if target_file:
            target_file = target_file.strip().strip('"\'')
            if workspace_path and not os.path.isabs(target_file):
                found = _find_in_workspace(target_file, workspace_path)
                target_file = found if found else os.path.join(workspace_path, target_file)
            target_file = os.path.normpath(target_file)
            return [{"tool": "file_op", "params": {"action": "edit", "source": target_file, "find": find_str, "replace": replace_str}}]
        # 如果没指定文件，交给 LLM 处理
        return None

    # --- 写入/覆盖写: "写入 hello.py 内容 xxx" ---
    m = re.match(r'(?:写入|覆盖写|write)\s*(.+?)\s*(?:内容(?:是|为)?)?[:：]\s*(.+)', msg, re.I | re.S)
    if m:
        target = m.group(1).strip().strip('"\'')
        file_content = m.group(2).strip()
        if workspace_path and not os.path.isabs(target):
            target = os.path.join(workspace_path, target)
        target = os.path.normpath(target)
        return [{"tool": "file_op", "params": {"action": "write", "source": target, "content": file_content}}]

    # --- 在文件里写/创建内容: "在 test.py 里写一个贪吃蛇游戏" ---
    m = re.match(r'(?:请你)?\s*(?:在\s*(.+?)\s*(?:里|中|文档里))?\s*(?:写|创建|生成|编写)\s*(?:一个)?\s*(.+)', msg, re.I)
    if m:
        target_file = m.group(1)
        description = m.group(2).strip()
        # 如果指定了文件名，生成代码写入
        if target_file:
            target_file = target_file.strip().strip('"\'')
            # 如果没有扩展名，根据描述推断
            if '.' not in os.path.basename(target_file):
                if 'python' in description.lower() or 'py' in description.lower():
                    target_file += '.py'
                elif 'html' in description.lower():
                    target_file += '.html'
                elif 'javascript' in description.lower() or 'js' in description.lower():
                    target_file += '.js'
                else:
                    target_file += '.py'  # 默认 Python
            if workspace_path and not os.path.isabs(target_file):
                found = _find_in_workspace(target_file, workspace_path)
                target_file = found if found else os.path.join(workspace_path, target_file)
            target_file = os.path.normpath(target_file)
            # 返回 None 让 LLM 生成代码内容，但设置提示
            return None  # 交给 LLM 生成具体代码

    # --- 追加内容: "在 test.py 末尾追加 xxx" ---
    m = re.match(r'(?:在\s*(.+?)\s*(?:末尾|后面|下面))?\s*(?:追加|append)\s*(?:内容)?[:：]?\s*(.+)', msg, re.I | re.S)
    if m and m.group(1):
        target = m.group(1).strip().strip('"\'')
        append_content = m.group(2).strip()
        if workspace_path and not os.path.isabs(target):
            found = _find_in_workspace(target, workspace_path)
            target = found if found else os.path.join(workspace_path, target)
        target = os.path.normpath(target)
        return [{"tool": "file_op", "params": {"action": "append", "source": target, "content": append_content}}]

    return None


def plan_actions(user_message: str, workspace_path: str = None) -> list[dict]:
    """
    用 LLM 将自然语言转为操作序列
    返回 [{"tool": "...", "params": {...}}, ...]
    """
    # 快速匹配常见操作（不依赖 LLM，更可靠）
    quick = _quick_plan(user_message, workspace_path)
    if quick:
        print(f"[ActionPlanner] 快速匹配: {quick}")
        return quick

    home = os.path.expanduser("~").replace("\\", "/")
    context = f"当前用户主目录: {home}\n当前系统: Windows"
    if workspace_path:
        context += f"\n当前工作区路径: {workspace_path}"
        try:
            files = os.listdir(workspace_path)
            context += f"\n工作区文件: {', '.join(files[:30])}"
        except Exception:
            pass

    prompt = f"{context}\n\n用户请求：{user_message}"

    reply = llm_provider.chat(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=_get_action_prompt(),
        temperature=0.1,
        max_tokens=800,
    )

    reply = reply.strip()
    if reply.startswith("```"):
        lines = reply.split("\n")
        reply = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    reply = reply.strip()

    try:
        actions = json.loads(reply)
        if isinstance(actions, list):
            # 验证每个 action 的格式
            valid = []
            for a in actions:
                if isinstance(a, dict) and a.get("tool") and a.get("params"):
                    valid.append(a)
                else:
                    print(f"[ActionPlanner] 跳过无效 action: {a}")
            return valid
    except json.JSONDecodeError:
        m = re.search(r'\[[\s\S]*\]', reply)
        if m:
            try:
                actions = json.loads(m.group())
                if isinstance(actions, list):
                    return [a for a in actions if isinstance(a, dict) and a.get("tool") and a.get("params")]
            except:
                pass

    print(f"[ActionPlanner] LLM 输出无法解析: {reply[:200]}")
    return []
