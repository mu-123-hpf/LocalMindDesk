"""
LocalMindDesk — Prompt Loader
从 .agents/ 目录动态加载 Agent 提示词（Markdown 文件）
"""
import os
import glob

AGENTS_DIR = ".agents"


def load_agent_prompt(name: str) -> str:
    """
    加载 .agents/{name}.md 文件内容作为 System Prompt
    找不到则返回空字符串
    """
    path = os.path.join(AGENTS_DIR, f"{name}.md")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            print(f"[PromptLoader] 加载 {name} 失败: {e}")
    return ""


def save_agent_prompt(name: str, content: str):
    """保存 Agent 提示词"""
    os.makedirs(AGENTS_DIR, exist_ok=True)
    path = os.path.join(AGENTS_DIR, f"{name}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[PromptLoader] 已保存 {name}")


def list_agents() -> list[dict]:
    """列出所有 Agent 文件"""
    os.makedirs(AGENTS_DIR, exist_ok=True)
    agents = []
    for filepath in glob.glob(os.path.join(AGENTS_DIR, "*.md")):
        name = os.path.splitext(os.path.basename(filepath))[0]
        size = os.path.getsize(filepath)
        agents.append({
            "name": name,
            "file": filepath,
            "size": size,
        })
    return agents
