"""
LocalMindDesk — Skills Manager
技能管理器：全局技能 + 项目局部技能

设计：
- 全局技能：data/skills.md + data/skills/global/*.md  → 始终存在
- 项目局部技能：data/skills/projects/{hash}/*.md → 打开项目时加载，切走时消失
- 微信专属技能：data/wechat/skills/*.md → 仅微信通道使用（由 wechat_bridge 管理）

项目用路径的 MD5 前 8 位作为哈希标签，确保：
- 同一项目路径始终映射到同一哈希
- 切换项目后局部技能自动切换
- 切回来时原来的局部技能依然存在
"""
import hashlib
import os
import logging

logger = logging.getLogger(__name__)

SKILLS_DIR = "data/skills"
GLOBAL_DIR = os.path.join(SKILLS_DIR, "global")
PROJECTS_DIR = os.path.join(SKILLS_DIR, "projects")


def _project_hash(workspace_path: str) -> str:
    """用项目路径的 MD5 前 8 位作为唯一标识"""
    norm = os.path.normpath(os.path.abspath(workspace_path)).lower()
    return hashlib.md5(norm.encode("utf-8")).hexdigest()[:8]


def get_project_skills_dir(workspace_path: str) -> str:
    """获取项目专属技能目录（不存在则创建）"""
    h = _project_hash(workspace_path)
    d = os.path.join(PROJECTS_DIR, h)
    os.makedirs(d, exist_ok=True)
    # 写一个标记文件记录项目路径（方便人类查看）
    meta_path = os.path.join(d, "_project_path.txt")
    if not os.path.exists(meta_path):
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                f.write(os.path.normpath(workspace_path))
        except Exception:
            pass
    return d


def _load_skills_from_dir(dir_path: str) -> list[dict]:
    """从目录加载所有 .md 技能文件，返回 [{"name": ..., "content": ...}]"""
    skills = []
    if not os.path.isdir(dir_path):
        return skills
    for fname in sorted(os.listdir(dir_path)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(dir_path, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                name = fname.replace(".md", "")
                skills.append({"name": name, "content": content})
        except Exception as e:
            logger.warning(f"[Skills] 加载失败 {fpath}: {e}")
    return skills


def load_global_skills() -> str:
    """加载全局技能（data/skills.md + data/skills/global/*.md）"""
    parts = []

    # 1. 传统单文件 skills.md（向后兼容）
    legacy_path = os.path.join("data", "skills.md")
    if os.path.isfile(legacy_path):
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                parts.append(content)
        except Exception:
            pass

    # 2. 全局技能目录
    global_skills = _load_skills_from_dir(GLOBAL_DIR)
    for s in global_skills:
        parts.append(f"### {s['name']}\n{s['content']}")

    if global_skills:
        logger.info(f"[Skills] 已加载 {len(global_skills)} 个全局技能")

    return "\n\n".join(parts) if parts else ""


def load_project_skills(workspace_path: str) -> str:
    """加载项目局部技能（data/skills/projects/{hash}/*.md）"""
    if not workspace_path:
        return ""

    proj_dir = get_project_skills_dir(workspace_path)
    skills = _load_skills_from_dir(proj_dir)

    if not skills:
        return ""

    h = _project_hash(workspace_path)
    parts = []
    for s in skills:
        parts.append(f"### {s['name']}\n{s['content']}")

    logger.info(f"[Skills] 已加载 {len(skills)} 个项目技能 (hash={h})")
    return "\n\n".join(parts)


def load_all_skills(workspace_path: str = None) -> str:
    """
    加载完整技能上下文：全局 + 项目局部。
    
    返回格式化的字符串，可直接注入到 system prompt。
    """
    sections = []

    # 全局技能
    global_text = load_global_skills()
    if global_text:
        sections.append(f"[全局技能]:\n{global_text}")

    # 项目局部技能
    if workspace_path:
        project_text = load_project_skills(workspace_path)
        if project_text:
            proj_name = os.path.basename(workspace_path)
            sections.append(f"[项目技能 — {proj_name}]:\n{project_text}")

    return "\n\n".join(sections) if sections else ""


def save_project_skill(workspace_path: str, skill_name: str, content: str) -> str:
    """保存一个项目局部技能"""
    proj_dir = get_project_skills_dir(workspace_path)
    # 清理文件名
    safe_name = "".join(c for c in skill_name if c.isalnum() or c in "-_").strip()
    if not safe_name:
        safe_name = "skill"
    fpath = os.path.join(proj_dir, f"{safe_name}.md")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"[Skills] 已保存项目技能: {fpath}")
    return fpath


def save_global_skill(skill_name: str, content: str) -> str:
    """保存一个全局技能"""
    os.makedirs(GLOBAL_DIR, exist_ok=True)
    safe_name = "".join(c for c in skill_name if c.isalnum() or c in "-_").strip()
    if not safe_name:
        safe_name = "skill"
    fpath = os.path.join(GLOBAL_DIR, f"{safe_name}.md")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"[Skills] 已保存全局技能: {fpath}")
    return fpath


def list_skills(workspace_path: str = None) -> dict:
    """列出所有技能（全局 + 项目）"""
    result = {
        "global": [],
        "project": [],
        "project_hash": "",
        "project_path": workspace_path or "",
    }

    # 全局
    if os.path.isdir(GLOBAL_DIR):
        for f in sorted(os.listdir(GLOBAL_DIR)):
            if f.endswith(".md"):
                result["global"].append(f.replace(".md", ""))

    # 项目
    if workspace_path:
        h = _project_hash(workspace_path)
        result["project_hash"] = h
        proj_dir = os.path.join(PROJECTS_DIR, h)
        if os.path.isdir(proj_dir):
            for f in sorted(os.listdir(proj_dir)):
                if f.endswith(".md"):
                    result["project"].append(f.replace(".md", ""))

    return result
