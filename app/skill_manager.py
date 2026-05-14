"""
LocalMindDesk — Skill Manager
全局/局部技能管理 + GitHub 学习
"""
import os
import re
import json
from datetime import datetime
from pathlib import Path

GLOBAL_SKILLS_DIR = "data/skills/global"
PROJECTS_SKILLS_DIR = "data/skills/projects"


def _project_hash(project_dir: str) -> str:
    """用项目路径的 MD5 前 8 位作为唯一标识"""
    import hashlib
    norm = os.path.normpath(os.path.abspath(project_dir)).lower()
    return hashlib.md5(norm.encode("utf-8")).hexdigest()[:8]


def _get_local_dir(project_dir: str) -> str:
    """获取项目局部技能目录"""
    h = _project_hash(project_dir)
    d = os.path.join(PROJECTS_SKILLS_DIR, h)
    os.makedirs(d, exist_ok=True)
    # 写标记文件
    meta = os.path.join(d, "_project_path.txt")
    if not os.path.exists(meta):
        try:
            with open(meta, "w", encoding="utf-8") as f:
                f.write(os.path.normpath(project_dir))
        except Exception:
            pass
    return d


def _ensure_dirs():
    os.makedirs(GLOBAL_SKILLS_DIR, exist_ok=True)


def _parse_skill_file(filepath: str) -> dict:
    """解析单个 .md 技能文件为结构化数据"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    # 提取标题
    title_match = re.search(r'^#\s+(.+)', content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else Path(filepath).stem

    # 提取描述（第一段非空非标题文本）
    desc = ""
    for line in content.split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("[!["):
            desc = line[:120]
            break

    # 提取日期
    date_match = re.search(r'\[(\d{4}-\d{2}-\d{2})', content)
    date = date_match.group(1) if date_match else None

    # 提取来源
    source_match = re.search(r'https?://github\.com/[\w\-]+/[\w\-]+', content)
    source = source_match.group(0) if source_match else None

    return {
        "title": title,
        "description": desc,
        "date": date,
        "source": source,
        "filename": Path(filepath).name,
        "content": content[:5000],
    }


def list_skills(project_dir: str = None) -> dict:
    """列出全局 + 局部技能（v2: 含使用统计 + 按频率排序）"""
    _ensure_dirs()
    result = {"global": [], "local": []}

    # ★ v2.0: 获取 skill 使用统计
    usage_stats = {}
    try:
        from app.insights_engine import get_skill_usage_stats
        usage_stats = get_skill_usage_stats(days=30)
    except Exception:
        pass

    # 全局技能
    if os.path.isdir(GLOBAL_SKILLS_DIR):
        for f in sorted(os.listdir(GLOBAL_SKILLS_DIR)):
            if f.endswith(".md"):
                skill = _parse_skill_file(os.path.join(GLOBAL_SKILLS_DIR, f))
                if skill:
                    skill["scope"] = "global"
                    # 注入使用统计
                    name = skill.get("title", f.replace(".md", ""))
                    stats = usage_stats.get(name, {})
                    skill["usage_count"] = stats.get("count", 0)
                    skill["fail_rate"] = stats.get("fail_rate", 0.0)
                    skill["last_used"] = stats.get("days_since")
                    result["global"].append(skill)

    # 局部技能（基于项目路径哈希存储）
    if project_dir:
        local_dir = _get_local_dir(project_dir)
        if os.path.isdir(local_dir):
            for f in sorted(os.listdir(local_dir)):
                if f.endswith(".md"):
                    skill = _parse_skill_file(os.path.join(local_dir, f))
                    if skill:
                        skill["scope"] = "local"
                        name = skill.get("title", f.replace(".md", ""))
                        stats = usage_stats.get(name, {})
                        skill["usage_count"] = stats.get("count", 0)
                        skill["fail_rate"] = stats.get("fail_rate", 0.0)
                        skill["last_used"] = stats.get("days_since")
                        result["local"].append(skill)

    # ★ 按使用频率排序（高频在前）
    result["global"].sort(key=lambda s: s.get("usage_count", 0), reverse=True)
    result["local"].sort(key=lambda s: s.get("usage_count", 0), reverse=True)

    return result



def migrate_legacy_skills():
    """将旧的 data/skills.md 迁移到新的多文件结构"""
    legacy = "data/skills.md"
    if not os.path.exists(legacy):
        return

    _ensure_dirs()
    with open(legacy, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        return

    # 按 ### [日期] 分割
    sections = re.split(r'\n(?=### \[)', content)
    migrated = 0
    for section in sections:
        section = section.strip()
        if not section:
            continue
        # 提取技能名
        title_match = re.search(r'^#\s+(.+)', section, re.MULTILINE)
        if title_match:
            name = re.sub(r'[^\w\-]', '_', title_match.group(1).strip())[:50]
        else:
            name = f"skill_{migrated}"

        filepath = os.path.join(GLOBAL_SKILLS_DIR, f"{name}.md")
        if not os.path.exists(filepath):
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(section)
            migrated += 1

    if migrated > 0:
        print(f"[Skills] 已迁移 {migrated} 个技能到 {GLOBAL_SKILLS_DIR}")


def add_skill(name: str, content: str, scope: str = "global",
              project_dir: str = None) -> dict:
    """手动添加技能"""
    safe_name = re.sub(r'[^\w\-]', '_', name)[:50]
    if scope == "local" and project_dir:
        target_dir = _get_local_dir(project_dir)
    else:
        target_dir = GLOBAL_SKILLS_DIR

    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, f"{safe_name}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return {"success": True, "path": filepath}


def delete_skill(filename: str, scope: str = "global",
                 project_dir: str = None) -> dict:
    """删除技能"""
    if scope == "local" and project_dir:
        filepath = os.path.join(_get_local_dir(project_dir), filename)
    else:
        filepath = os.path.join(GLOBAL_SKILLS_DIR, filename)

    if os.path.exists(filepath):
        os.remove(filepath)
        return {"success": True}
    return {"success": False, "error": "文件不存在"}


def learn_from_github(url: str, scope: str = "global",
                      project_dir: str = None) -> dict:
    """
    从 GitHub URL 学习技能
    支持格式:
      - https://github.com/user/repo
      - https://github.com/user/repo/tree/main/path
    """
    import urllib.request
    import urllib.error

    url = url.strip().rstrip("/")

    # 解析 GitHub URL
    match = re.match(r'https?://github\.com/([\w\-]+)/([\w\-]+)(?:/tree/(\w+)(?:/(.+))?)?', url)
    if not match:
        return {"success": False, "error": "无效的 GitHub URL"}

    owner, repo, branch, subpath = match.groups()
    branch = branch or "main"

    # 尝试多个文件：SKILL.md → README.md
    candidates = []
    if subpath:
        candidates.append(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{subpath}/SKILL.md")
        candidates.append(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{subpath}/README.md")
    candidates.append(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/SKILL.md")
    candidates.append(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md")

    content = None
    fetched_url = None
    for raw_url in candidates:
        try:
            req = urllib.request.Request(raw_url, headers={"User-Agent": "LocalMindDesk/2.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                fetched_url = raw_url
                break
        except (urllib.error.HTTPError, urllib.error.URLError):
            continue

    if not content:
        return {"success": False, "error": f"无法从 {url} 获取 README 或 SKILL.md"}

    # 添加元数据头
    header = f"\n### [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n"
    header += f"从 GitHub ({url}) 学习到的技能文档：\n"
    full_content = header + content

    # 生成文件名
    skill_name = repo
    if subpath:
        skill_name = subpath.split("/")[-1] or repo

    result = add_skill(skill_name, full_content, scope, project_dir)
    result["title"] = skill_name
    result["source"] = url
    print(f"[Skills] 从 GitHub 学习: {url} → {result.get('path')}")
    return result


# 启动时自动迁移
migrate_legacy_skills()
