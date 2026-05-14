"""
LocalMindDesk — Thinking Engine（批判性思维引擎）
让 AI 从「被动执行者」进化为「主动思考的搭档」

三个核心能力：
1. 对话模式检测（Execute / Collaborate / Review）
2. 反问触发器（模糊需求、风险操作、架构决策时主动提问）
3. 项目感知注入（扫描项目状态，注入上下文）
"""
import os
import re
from datetime import datetime


# ============================================================
#  对话模式
# ============================================================
class ConversationMode:
    PLAN = "plan"               # 先制定计划，确认后执行
    EXECUTE = "execute"        # 直接执行，不多问
    COLLABORATE = "collaborate"  # 讨论协作（默认）
    REVIEW = "review"          # 深度审查

    # 模式描述
    DESCRIPTIONS = {
        "plan": "📋 计划模式 — 先制定计划，确认后执行",
        "execute": "🎯 执行模式 — 直接完成任务",
        "collaborate": "🤝 协作模式 — 讨论方案后再行动",
        "review": "🔍 审查模式 — 深度分析与改进建议",
    }


# ============================================================
#  协作者 System Prompt
# ============================================================
COLLABORATOR_PROMPT = """你是 LocalMindDesk，运行在用户本地电脑上的 AI 助手。你不是普通的聊天 AI——你有独立思考能力，也有能力直接操作用户的电脑。

## 你的能力（重要！）
你运行在 LocalMindDesk 本地环境中，拥有以下真实操作能力：
1. **执行命令** — 可以在用户电脑上运行任何 shell 命令（pip install、npm install、python、git 等）
2. **文件操作** — 读取、写入、创建、删除、移动、复制文件和文件夹
3. **安装软件** — 可以通过 pip、npm、yarn 等包管理器安装软件包
4. **截屏** — 可以截取屏幕截图
5. **微信发送** — 可以通过微信发送消息和文件
6. **代码搜索** — 可以在项目中搜索代码和文件
7. **GUI 操作** — 可以模拟鼠标点击、键盘输入等

⚠️ **绝对不要**说"作为 AI 我无法执行/安装/操作"之类的话！你确实可以！
⚠️ 当用户要求你执行操作时，直接告诉他你正在执行，或者解释你将如何执行。
⚠️ 高危操作会经过安全确认，用户确认后才执行，所以你可以放心操作。

## 核心原则
1. **先理解再执行** — 需求不清晰时，必须先反问澄清，绝不猜测用户意图
2. **主动质疑** — 发现方案有隐患时，先说出你的顾虑，再给出建议
3. **提供选项** — 遇到重要决策时，给出 2-3 个方案并分析利弊，让用户做选择
4. **预见问题** — 执行前思考：这样做会不会引入新问题？有没有更好的方式？
5. **坦诚无知** — 不确定的事情说"我不确定"，而不是编造答案

## 行为模式
- 当用户要求安装软件包时 → 直接执行 pip install / npm install
- 当用户要求执行命令时 → 直接运行，不要说"我无法执行"
- 当用户需求模糊时 → 先提问澄清，再行动
- 当用户方案有风险时 → 先说出顾虑，指出风险
- 当有更好的替代方案时 → "你的方案可行，但我建议也考虑一下..."
- 当涉及架构决策时 → 画出利弊对比，帮助决策

## 禁止行为
- ❌ 绝不说"作为 AI 模型我无法..."——你有操作能力！
- ❌ 不要在不确定时编造代码逻辑
- ❌ 不要对所有请求都说"好的"而不思考
- ❌ 不要忽略明显的安全/性能问题
- ❌ 不要给出没有依据的建议"""


# 针对不同模式的额外指令
MODE_INSTRUCTIONS = {
    ConversationMode.PLAN: """
[当前模式: 计划模式]
用户希望你先制定详细的计划。你应该：
- 分析用户需求，分解为明确的步骤
- 列出每个步骤的具体内容和预期结果
- 标注潜在风险和注意事项
- 不要直接执行任何操作，只输出计划
- 使用编号列表格式，便于用户审阅
- 等待用户确认后再开始执行

输出格式示例：
## 📋 执行计划
1. **步骤一**: 具体内容...
2. **步骤二**: 具体内容...
3. **步骤三**: 具体内容...

⚠️ 注意事项: ...

请确认后我将开始执行。""",

    ConversationMode.EXECUTE: """
[当前模式: 执行模式]
用户的指令很明确，直接高效完成。保持简洁，不需要过度讨论。""",

    ConversationMode.COLLABORATE: """
[当前模式: 协作模式]
用户正在讨论方案或设计功能。你应该：
- 主动提出你的想法和建议
- 如果发现问题，先说出来再动手
- 重要决策给出选项让用户选择
- 适时反问以确保理解正确""",

    ConversationMode.REVIEW: """
[当前模式: 审查模式]
用户希望你深度分析。你应该：
- 逐行/逐段审查，找出问题
- 提供具体的改进建议（不是笼统的）
- 指出性能、安全、可维护性等多维度问题
- 给出优先级：哪些问题必须修、哪些可以后续优化""",
}


# ============================================================
#  对话模式检测
# ============================================================
def detect_mode(user_message: str) -> str:
    """
    根据用户消息自动检测对话模式

    规则：
    - /execute, /collaborate, /review 手动切换
    - 简单操作指令 → execute
    - 功能设计/讨论 → collaborate
    - 代码审查/分析 → review
    """
    msg = user_message.strip().lower()

    # 手动切换
    if msg.startswith('/plan'):
        return ConversationMode.PLAN
    if msg.startswith('/execute') or msg.startswith('/exec'):
        return ConversationMode.EXECUTE
    if msg.startswith('/collaborate') or msg.startswith('/collab'):
        return ConversationMode.COLLABORATE
    if msg.startswith('/review'):
        return ConversationMode.REVIEW

    # 执行模式触发词（简单明确的指令）
    execute_patterns = [
        r'^(?:创建|删除|移动|复制|打开|关闭|运行|执行|启动)\s',
        r'^(?:安装|卸载|下载|更新|升级)\s',
        r'^(?:帮我|帮忙)?(?:安装|卸载|下载|运行|执行)',
        r'^(?:pip|npm|yarn|git|cd|ls|dir|mkdir|python)\s',
        r'^截[图屏]',
    ]
    for p in execute_patterns:
        if re.search(p, msg):
            return ConversationMode.EXECUTE

    # 审查模式触发词
    review_patterns = [
        r'(?:帮我)?(?:看看|检查|审查|review|分析)',
        r'(?:这段|这个)(?:代码|文件|函数).*(?:有没有|是否)',
        r'(?:优化|改进|重构|refactor)',
        r'(?:bug|错误|问题).*(?:在哪|原因)',
    ]
    for p in review_patterns:
        if re.search(p, msg):
            return ConversationMode.REVIEW

    # 协作模式触发词（讨论性质）
    collaborate_patterns = [
        r'(?:我想|我们想|想做|想加|想要|打算)',
        r'(?:怎么|如何|怎样|应该)',
        r'(?:设计|规划|方案|架构|思路)',
        r'(?:你觉得|你认为|你建议)',
        r'(?:可以吗|好不好|行不行|有没有)',
        r'(?:为什么|什么原因)',
    ]
    for p in collaborate_patterns:
        if re.search(p, msg):
            return ConversationMode.COLLABORATE

    # 默认：协作模式（鼓励思考）
    return ConversationMode.COLLABORATE


# ============================================================
#  反问触发器
# ============================================================
def check_clarification_needed(user_message: str, mode: str) -> str | None:
    """
    检查是否需要主动反问澄清

    返回反问提示（注入 system prompt），或 None
    """
    if mode == ConversationMode.EXECUTE:
        return None  # 执行模式不反问

    msg = user_message.strip()

    # 1. 需求过于模糊（少于 10 字且包含功能词）
    if len(msg) < 15 and re.search(r'(?:做|加|写|搞|弄|要|想)', msg):
        return "[反问提示] 用户需求较模糊，在回复中先确认细节再行动。例如问清具体功能、适用场景、技术偏好。"

    # 2. 架构/技术选择（讨论性质）
    if re.search(r'(?:用什么|选什么|哪个好|怎么选|用.*还是)', msg):
        return "[反问提示] 用户在做技术选择。给出 2-3 个选项的利弊对比，帮助决策，而不是直接推荐一个。"

    # 3. 大范围修改
    if re.search(r'(?:重构|重写|全部改|大改|推翻)', msg):
        return "[反问提示] 用户想做大范围修改。先确认影响范围、是否有备份、是否分阶段执行更安全。"

    # 4. 包含"所有""全部"等泛化词
    if re.search(r'(?:所有|全部|每个|整个)', msg) and re.search(r'(?:改|删|换|移)', msg):
        return "[反问提示] 用户指令涉及大范围操作。先确认具体范围，避免误操作。"

    return None


# ============================================================
#  项目感知：扫描项目状态
# ============================================================
def scan_project_context(workspace_path: str) -> str:
    """
    快速扫描工作区，生成项目上下文摘要
    注入到 system prompt 中，让 AI 了解项目全貌
    """
    if not workspace_path or not os.path.isdir(workspace_path):
        return ""

    stats = {
        "files": 0,
        "dirs": 0,
        "languages": {},
        "todos": 0,
        "recent_files": [],
    }

    # 语言检测映射
    lang_map = {
        '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
        '.html': 'HTML', '.css': 'CSS', '.json': 'JSON',
        '.c': 'C', '.cpp': 'C++', '.java': 'Java',
        '.go': 'Go', '.rs': 'Rust', '.rb': 'Ruby',
    }

    skip_dirs = {'.git', '__pycache__', 'node_modules', 'venv', '.venv',
                 'dist', 'build', '.idea', '.vscode'}

    all_files = []

    try:
        for root, dirs, files in os.walk(workspace_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]
            stats["dirs"] += len(dirs)

            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, workspace_path)
                ext = os.path.splitext(f)[1].lower()

                stats["files"] += 1
                if ext in lang_map:
                    lang = lang_map[ext]
                    stats["languages"][lang] = stats["languages"].get(lang, 0) + 1

                # 收集文件修改时间
                try:
                    mtime = os.path.getmtime(full)
                    all_files.append((rel, mtime))
                except OSError:
                    pass

                # 统计 TODO/FIXME（只扫文本文件）
                if ext in lang_map and os.path.getsize(full) < 100000:
                    try:
                        with open(full, 'r', encoding='utf-8', errors='ignore') as fh:
                            content = fh.read()
                            stats["todos"] += len(re.findall(
                                r'(?:TODO|FIXME|HACK|XXX|BUG)\b', content, re.I))
                    except Exception:
                        pass

            # 限制扫描深度
            if len(all_files) > 500:
                break

    except Exception:
        return ""

    # 最近修改的 5 个文件
    all_files.sort(key=lambda x: x[1], reverse=True)
    stats["recent_files"] = [f[0] for f in all_files[:5]]

    # 主要语言排序
    top_langs = sorted(stats["languages"].items(), key=lambda x: x[1], reverse=True)[:4]

    # 构建上下文字符串
    parts = [
        f"\n[当前项目上下文]",
        f"- 项目路径: {workspace_path}",
        f"- 文件数: {stats['files']} 个文件, {stats['dirs']} 个目录",
    ]

    if top_langs:
        lang_str = ", ".join(f"{lang}({count})" for lang, count in top_langs)
        parts.append(f"- 技术栈: {lang_str}")

    if stats["todos"] > 0:
        parts.append(f"- 待办事项: {stats['todos']} 处 TODO/FIXME")

    if stats["recent_files"]:
        recent = ", ".join(stats["recent_files"][:3])
        parts.append(f"- 最近修改: {recent}")

    return "\n".join(parts)


# ============================================================
#  组装增强 System Prompt
# ============================================================
def build_enhanced_prompt(
    base_prompt: str,
    user_message: str,
    workspace_path: str = None,
    mode: str = None,
) -> str:
    """
    组装增强版 System Prompt：
    协作者人格 + 模式指令 + 反问提示 + 项目上下文
    """
    # 1. 检测模式
    if mode is None:
        mode = detect_mode(user_message)

    # 2. 基础人格（优先级：自定义角色标签 > SOUL.md > COLLABORATOR_PROMPT）
    has_custom_identity = "[角色设定]" in (base_prompt or "")
    if has_custom_identity:
        # 微信自定义角色场景：使用 base_prompt 中的角色作为主身份
        enhanced = base_prompt
    else:
        # ★ v2.0: 优先加载 SOUL.md 统一角色
        soul_content = ""
        try:
            from app.soul_manager import get_soul_manager
            soul_content = get_soul_manager().get_identity("pc")
        except Exception:
            pass
        if soul_content:
            enhanced = soul_content
        else:
            # 降级到默认协作者人格
            enhanced = COLLABORATOR_PROMPT

    # 3. 模式指令
    enhanced += MODE_INSTRUCTIONS.get(mode, "")

    # 4. 反问提示
    clarification = check_clarification_needed(user_message, mode)
    if clarification:
        enhanced += f"\n\n{clarification}"

    # 5. 项目上下文
    if workspace_path:
        project_ctx = scan_project_context(workspace_path)
        if project_ctx:
            enhanced += f"\n{project_ctx}"

    # 6. 保留原有的技能库/记忆/工作区/角色/技能信息
    if base_prompt and not has_custom_identity:
        # 所有已知标签
        all_tags = ["[角色设定]", "[用户画像]", "[微信对话规则]", "[微信专属技能]",
                    "[全局技能库]", "[全局技能]", "[项目技能", "[技能库]",
                    "[长期记忆]", "[当前工作区]", "[行为设定]"]
        for tag in all_tags:
            idx = base_prompt.find(tag)
            if idx >= 0:
                # 从第一个标签开始，后面的内容全部保留
                enhanced += "\n\n" + base_prompt[idx:]
                break  # 所有标签是连续的，一次追加即可

    return enhanced

