"""
LocalMindDesk — System Prompt Builder
Inspired by industry-standard modular, sectioned system prompt architecture.

Design principles:
- Each section is a function returning str | None
- None sections are skipped (zero wasted tokens)
- Sections are ordered: identity → rules → tools → safety → mode → context → memory
- Static sections can be cached; dynamic sections rebuild per turn
"""
import os
from typing import Optional


# ============================================================
#  Section 1: Identity & Role
# ============================================================
def _section_identity(profile: dict) -> str:
    """Core identity from agent profile or default."""
    identity = profile.get("identity", {})
    name = identity.get("name", "LocalMindDesk")
    role = identity.get("role", "AI 编程助手")
    system_prompt = identity.get("system_prompt", "")

    if system_prompt:
        return system_prompt

    return f"""你是 {name}，运行在用户本地电脑上的 {role}。你不是普通的聊天 AI——你有独立思考能力，也能直接操作用户的电脑。

你拥有以下真实操作能力：
- 执行 shell 命令（pip, npm, git, python 等）
- 文件操作（读取、写入、创建、删除、搜索）
- 代码搜索（在项目中搜索代码和文件）
- 截屏与 GUI 操作

⚠️ 绝对不要说"作为 AI 我无法执行/安装/操作"——你确实可以！"""


# ============================================================
#  Section 2: Behavior Rules ("Doing Tasks")
# ============================================================
def _section_behavior_rules(profile: dict) -> str:
    """Core behavior rules — coding best practices, communication style."""
    behavior = profile.get("behavior", {})
    style = behavior.get("response_style", "balanced")
    length = behavior.get("response_length", "medium")

    return f"""# 规则
- 先读代码再改，最小变更，不过度设计
- 不要额外重构或添加用户没要求的功能
- 安全第一：防注入、XSS、SQL注入
- 风格: {style}, 长度: {length}, 直奔主题"""


# ============================================================
#  Section 3: Tool-Use Constraints (core)
# ============================================================
def _section_tool_constraints() -> str:
    """Explicit rules about which tools to use for which operations."""
    return """# 工具
优先用专用工具: file_op读写文件, code_search搜索, shell_exec执行命令, screen_capture截屏。
失败时先诊断原因再换策略。"""


# ============================================================
#  Section 4: Safety Gate & Sandbox Rules
# ============================================================
def _section_safety_rules(sandbox_roots: list[str]) -> str:
    """Risk classification + sandbox permission escalation flow."""
    roots_str = ", ".join(sandbox_roots) if sandbox_roots else "(未配置)"

    return f"""# 安全
沙盒目录: {roots_str}
- 低风险(直接做): 读文件、搜索、列目录
- 中风险(告知用户): 写文件、安装依赖、git commit
- 高风险(必须确认): 删除、沙盒外操作、git push

沙盒外访问流程: 请求权限→被拒→找替代方案→替代方案也需沙盒外→再次请求→循环直到解决

禁止: 未经许可删数据、发送敏感信息、修改工作区外系统文件"""


# ============================================================
#  Section 5: Mode Instructions
# ============================================================
def _section_mode(mode: str) -> Optional[str]:
    """Mode-specific behavioral overlay."""
    modes = {
        "plan": """# 当前模式: 📋 计划模式
先制定详细计划，分解步骤，标注风险。不要直接执行操作。
等待用户确认后再开始执行。""",

        "execute": """# 当前模式: 🎯 执行模式
用户指令明确，直接高效完成。保持简洁。""",

        "collaborate": """# 当前模式: 🤝 协作模式
主动提出想法和建议。发现问题先说出来。
重要决策给出 2-3 个选项让用户选择。""",

        "review": """# 当前模式: 🔍 审查模式
逐段深度分析。提供具体改进建议。
给出优先级：哪些必须修、哪些可后续优化。""",
    }
    return modes.get(mode)


# ============================================================
#  Section 6: Workspace Context
# ============================================================
def _section_workspace(workspace_path: Optional[str]) -> Optional[str]:
    """Inject workspace file tree and project context."""
    if not workspace_path or not os.path.isdir(workspace_path):
        return None

    # Delegate to existing scan_project_context
    try:
        from app.thinking_engine import scan_project_context
        ctx = scan_project_context(workspace_path)
        return ctx if ctx else None
    except Exception:
        return None


# ============================================================
#  Section 7: .LocalMindDesk.md Project Memory
# ============================================================
def _section_project_memory(workspace_path: Optional[str]) -> Optional[str]:
    """Load .LocalMindDesk.md from workspace root — project-level persistent instructions."""
    if not workspace_path:
        return None

    md_path = os.path.join(workspace_path, ".LocalMindDesk.md")
    if not os.path.exists(md_path):
        return None

    try:
        with open(md_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(5000)  # Cap at 5K chars
        if content.strip():
            return f"""# 项目指令 (.LocalMindDesk.md)
以下是项目维护者定义的规则和约定，你必须遵守：

{content.strip()}"""
    except Exception:
        pass
    return None


# ============================================================
#  Section 8: Fact Memory & Vector Memory
# ============================================================
def _section_memories() -> Optional[str]:
    """Inject long-term fact memory and episodic memory."""
    parts = []

    try:
        from app.fact_memory import get_fact_memory
        fm = get_fact_memory()
        facts_text = fm.to_context_text()
        if facts_text:
            parts.append(f"<memory-context>\n{facts_text}\n</memory-context>")
    except Exception:
        pass

    return "\n\n".join(parts) if parts else None


# ============================================================
#  Section 9: Skills
# ============================================================
def _section_skills(workspace_path: Optional[str]) -> Optional[str]:
    """Load global + project skills."""
    try:
        from app.skills_manager import load_all_skills
        skills_text = load_all_skills(workspace_path)
        return skills_text if skills_text else None
    except Exception:
        return None


# ============================================================
#  Section 10: Vector (Episodic) Memory
# ============================================================
def _section_vector_memory(user_message: str) -> Optional[str]:
    """Recall relevant episodic memories via vector search."""
    if len(user_message.strip()) < 4:
        return None

    try:
        from app.vector_memory import recall_memories
        recalled = recall_memories(user_message, top_k=3)
        if recalled:
            lines = [f"- (相关度 {r['score']:.2f}) {r['text'][:200]}" for r in recalled]
            return "<episodic-memory>\n" + "\n".join(lines) + "\n</episodic-memory>"
    except Exception:
        pass
    return None


# ============================================================
#  Master Builder
# ============================================================
class SystemPromptBuilder:
    """
    Modular system prompt assembly — .

    Usage:
        builder = SystemPromptBuilder(profile, workspace_path, mode, user_message)
        prompt = builder.build()
    """

    def __init__(
        self,
        profile: dict,
        workspace_path: Optional[str] = None,
        mode: str = "collaborate",
        user_message: str = "",
        sandbox_roots: Optional[list[str]] = None,
    ):
        self.profile = profile
        self.workspace_path = workspace_path
        self.mode = mode
        self.user_message = user_message
        self.sandbox_roots = sandbox_roots or []

    # Max chars for the system prompt (~4 chars/token for Chinese)
    # 2500 chars ≈ 1500-2000 tokens, leaving room for conversation
    MAX_PROMPT_CHARS = 2500

    def build(self) -> str:
        """Assemble all sections into final system prompt with token budget."""
        # Priority order: identity & rules first, context last (droppable)
        core_sections = [
            _section_identity(self.profile),
            _section_behavior_rules(self.profile),
            _section_tool_constraints(),
            _section_safety_rules(self.sandbox_roots),
            _section_mode(self.mode),
        ]
        context_sections = [
            _section_project_memory(self.workspace_path),
            _section_memories(),
            _section_workspace(self.workspace_path),
            _section_skills(self.workspace_path),
            _section_vector_memory(self.user_message),
        ]

        # Build core first (always included)
        parts = [s for s in core_sections if s]
        result = "\n\n".join(parts)

        # Add context sections only if they fit within budget
        for section in context_sections:
            if section is None:
                continue
            candidate = result + "\n\n" + section
            if len(candidate) <= self.MAX_PROMPT_CHARS:
                result = candidate
            else:
                # Budget exceeded — skip remaining context sections
                break

        return result

    def build_sections_list(self) -> list[str]:
        """Return individual sections (for debugging/inspection)."""
        return [
            ("identity", _section_identity(self.profile)),
            ("behavior", _section_behavior_rules(self.profile)),
            ("tools", _section_tool_constraints()),
            ("safety", _section_safety_rules(self.sandbox_roots)),
            ("mode", _section_mode(self.mode)),
            ("project_memory", _section_project_memory(self.workspace_path)),
            ("workspace", _section_workspace(self.workspace_path)),
            ("memories", _section_memories()),
            ("skills", _section_skills(self.workspace_path)),
            ("vector", _section_vector_memory(self.user_message)),
        ]
