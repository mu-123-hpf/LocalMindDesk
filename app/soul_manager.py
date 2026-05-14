"""
LocalMindDesk — SoulManager v3（多角色 + 5 层蒸馏结构）

核心升级：
1. 多角色管理：data/soul/personas/{slug}/ 支持切换
2. 5 层 Persona 结构（参考 ex-skill 蒸馏方法论）
3. PC 和微信统一角色库，通过 channel 适配输出
4. 版本管理：自动存档历史版本
5. 向后兼容旧的 data/soul/SOUL.md 单文件模式

目录结构：
  data/soul/
    SOUL.md           — 旧版兼容（如果存在则作为 default 角色）
    SOUL.example.md   — 5 层结构模板
    personas/         — 多角色目录
      {slug}/
        persona.md    — 5 层 Persona 定义
        memories.md   — 共同记忆（可选）
        meta.json     — 元数据
        versions/     — 历史版本存档
"""
import os
import json
import shutil
from datetime import datetime
from typing import Optional, List

SOUL_DIR = "data/soul"
PERSONAS_DIR = os.path.join(SOUL_DIR, "personas")
LEGACY_SOUL_PATH = os.path.join(SOUL_DIR, "SOUL.md")
EXAMPLE_PATH = os.path.join(SOUL_DIR, "SOUL.example.md")
ACTIVE_FILE = os.path.join(SOUL_DIR, ".active_persona")  # 当前激活的角色 slug

# 微信渠道自动追加的简洁规则
_WECHAT_STYLE_RULES = """

## 微信对话适配
- 回答要简洁，像朋友对话一样，不要写长篇大论
- 不要使用 markdown 格式（微信不支持渲染）
- 不要用标题、列表、代码块等格式
- 如果内容较多，分要点用数字编号，每点一句话
- 语气自然亲切，可以用 emoji
- 单次回复控制在 200 字以内"""


class SoulManager:
    """
    多角色管理器 v3

    支持多个蒸馏角色并存，通过 slug 切换。
    PC 端和微信端共享同一个角色库。
    """

    def __init__(self):
        self._cache: dict = {}  # slug -> (content, mtime)
        os.makedirs(PERSONAS_DIR, exist_ok=True)
        # 自动迁移旧的 SOUL.md 到 personas/default/
        self._migrate_legacy()

    # ── 角色管理 ────────────────────────────────────────────────

    def list_personas(self) -> List[dict]:
        """列出所有角色"""
        result = []
        if not os.path.isdir(PERSONAS_DIR):
            return result
        active = self.get_active_slug()
        for slug in sorted(os.listdir(PERSONAS_DIR)):
            persona_dir = os.path.join(PERSONAS_DIR, slug)
            if not os.path.isdir(persona_dir):
                continue
            meta = self._load_meta(slug)
            persona_path = os.path.join(persona_dir, "persona.md")
            has_persona = os.path.isfile(persona_path)
            result.append({
                "slug": slug,
                "name": meta.get("name", slug),
                "description": meta.get("description", ""),
                "created_at": meta.get("created_at", ""),
                "updated_at": meta.get("updated_at", ""),
                "version": meta.get("version", "v1"),
                "active": slug == active,
                "has_persona": has_persona,
                "has_memories": os.path.isfile(os.path.join(persona_dir, "memories.md")),
                "tags": meta.get("tags", {}),
            })
        return result

    def get_active_slug(self) -> str:
        """获取当前激活的角色 slug"""
        if os.path.isfile(ACTIVE_FILE):
            try:
                with open(ACTIVE_FILE, "r", encoding="utf-8") as f:
                    slug = f.read().strip()
                if slug and os.path.isdir(os.path.join(PERSONAS_DIR, slug)):
                    return slug
            except Exception:
                pass
        # 默认：如果有 default 角色就用它
        if os.path.isdir(os.path.join(PERSONAS_DIR, "default")):
            return "default"
        # 没有任何角色
        personas = [d for d in os.listdir(PERSONAS_DIR)
                     if os.path.isdir(os.path.join(PERSONAS_DIR, d))]
        return personas[0] if personas else ""

    def switch_persona(self, slug: str) -> dict:
        """切换激活的角色"""
        persona_dir = os.path.join(PERSONAS_DIR, slug)
        if not os.path.isdir(persona_dir):
            return {"success": False, "error": f"角色 '{slug}' 不存在"}
        with open(ACTIVE_FILE, "w", encoding="utf-8") as f:
            f.write(slug)
        print(f"[SoulManager] 已切换到角色: {slug}")
        return {"success": True, "slug": slug}

    def create_persona(self, slug: str, name: str, persona_content: str,
                       memories_content: str = "", description: str = "",
                       tags: dict = None) -> dict:
        """创建新角色"""
        slug = self._safe_slug(slug)
        persona_dir = os.path.join(PERSONAS_DIR, slug)
        if os.path.isdir(persona_dir):
            return {"success": False, "error": f"角色 '{slug}' 已存在"}

        os.makedirs(os.path.join(persona_dir, "versions"), exist_ok=True)

        # 写 persona.md
        with open(os.path.join(persona_dir, "persona.md"), "w", encoding="utf-8") as f:
            f.write(persona_content)

        # 写 memories.md（如果有）
        if memories_content:
            with open(os.path.join(persona_dir, "memories.md"), "w", encoding="utf-8") as f:
                f.write(memories_content)

        # 写 meta.json
        meta = {
            "name": name,
            "slug": slug,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "version": "v1",
            "tags": tags or {},
        }
        with open(os.path.join(persona_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"[SoulManager] 新角色已创建: {slug} ({name})")
        return {"success": True, "slug": slug, "path": persona_dir}

    def delete_persona(self, slug: str) -> dict:
        """删除角色"""
        if slug == "default":
            return {"success": False, "error": "不能删除默认角色"}
        persona_dir = os.path.join(PERSONAS_DIR, slug)
        if not os.path.isdir(persona_dir):
            return {"success": False, "error": f"角色 '{slug}' 不存在"}
        shutil.rmtree(persona_dir)
        # 如果删的是当前激活的，切回 default
        if self.get_active_slug() == slug:
            self.switch_persona("default")
        print(f"[SoulManager] 角色已删除: {slug}")
        return {"success": True}

    # ── 角色读取 ────────────────────────────────────────────────

    def get_identity(self, channel: str = "pc", slug: str = None) -> str:
        """
        获取角色身份 prompt

        Args:
            channel: "pc" 或 "wechat"
            slug: 指定角色 slug，None 则用当前激活的

        Returns:
            完整的角色 prompt 字符串
        """
        slug = slug or self.get_active_slug()
        if not slug:
            return ""

        persona = self._load_persona(slug)
        if not persona:
            return ""

        # 注入防护扫描
        try:
            from app.privacy_filter import get_filter
            scan = get_filter().scan_context_content(persona, source=f"persona:{slug}")
            if not scan["safe"]:
                persona = scan["cleaned"]
        except Exception:
            pass

        # 附加共同记忆
        memories = self._load_memories(slug)
        full_prompt = persona
        if memories:
            full_prompt += f"\n\n## 共同记忆\n{memories}"

        # 根据渠道适配
        if channel == "wechat":
            return f"[角色设定]:\n{full_prompt}{_WECHAT_STYLE_RULES}"
        else:
            return full_prompt

    @property
    def has_soul(self) -> bool:
        """是否有可用的角色"""
        slug = self.get_active_slug()
        if not slug:
            return False
        return os.path.isfile(os.path.join(PERSONAS_DIR, slug, "persona.md"))

    def get_soul_raw(self) -> str:
        """获取当前角色的原始 persona.md 内容"""
        slug = self.get_active_slug()
        return self._load_persona(slug) if slug else ""

    def save_soul(self, content: str, slug: str = None) -> dict:
        """保存角色 persona.md（带版本存档）"""
        slug = slug or self.get_active_slug()
        if not slug:
            return {"success": False, "error": "没有激活的角色"}

        persona_dir = os.path.join(PERSONAS_DIR, slug)
        os.makedirs(persona_dir, exist_ok=True)
        persona_path = os.path.join(persona_dir, "persona.md")

        # 版本存档
        self._backup_version(slug)

        # 写入新内容
        with open(persona_path, "w", encoding="utf-8") as f:
            f.write(content)
        self._cache.pop(slug, None)

        # 更新 meta
        meta = self._load_meta(slug)
        ver = meta.get("version", "v1")
        try:
            n = int(ver.replace("v", "")) + 1
        except (ValueError, AttributeError):
            n = 2
        meta["version"] = f"v{n}"
        meta["updated_at"] = datetime.now().isoformat()
        self._save_meta(slug, meta)

        print(f"[SoulManager] persona.md 已更新: {slug} → {meta['version']}")
        return {"success": True, "path": persona_path, "version": meta["version"]}

    # ── 版本管理 ────────────────────────────────────────────────

    def list_versions(self, slug: str = None) -> List[dict]:
        """列出角色的历史版本"""
        slug = slug or self.get_active_slug()
        if not slug:
            return []
        versions_dir = os.path.join(PERSONAS_DIR, slug, "versions")
        if not os.path.isdir(versions_dir):
            return []
        result = []
        for fname in sorted(os.listdir(versions_dir), reverse=True):
            if fname.endswith(".md"):
                fpath = os.path.join(versions_dir, fname)
                result.append({
                    "version": fname.replace(".md", ""),
                    "date": datetime.fromtimestamp(os.path.getmtime(fpath)).isoformat(),
                    "size": os.path.getsize(fpath),
                })
        return result

    def rollback(self, slug: str, version: str) -> dict:
        """回滚到指定版本"""
        version_file = os.path.join(PERSONAS_DIR, slug, "versions", f"{version}.md")
        if not os.path.isfile(version_file):
            return {"success": False, "error": f"版本 {version} 不存在"}
        with open(version_file, "r", encoding="utf-8") as f:
            content = f.read()
        return self.save_soul(content, slug)

    # ── 用户画像 ────────────────────────────────────────────────

    def render_user_md(self) -> str:
        """从 FactMemory 自动渲染 USER.md"""
        try:
            from app.fact_memory import get_fact_memory
            fm = get_fact_memory()
            content = fm.render_user_md()
            user_path = os.path.join(SOUL_DIR, "USER.md")
            with open(user_path, "w", encoding="utf-8") as f:
                f.write(content)
            return content
        except Exception as e:
            print(f"[SoulManager] USER.md 渲染失败: {e}")
            return ""

    def get_user_context(self) -> str:
        """获取用户画像上下文"""
        try:
            from app.fact_memory import get_fact_memory
            return get_fact_memory().to_context_text()
        except Exception:
            return ""

    # ── 5 层结构生成 ────────────────────────────────────────────

    def soul_generate(self, description: str, slug: str = None,
                      name: str = None) -> dict:
        """
        用 LLM 从描述生成 5 层结构的 Persona

        Args:
            description: 自由文本描述
            slug: 角色标识（默认自动生成）
            name: 角色名称
        """
        try:
            from app import llm_provider

            prompt = f"""请根据以下描述，生成一份 5 层结构的 AI 角色定义文档。

描述: {description}

请严格按以下结构输出 Markdown 格式：

# [角色名]

## Layer 0 — 硬规则（绝不违反）
列出 5-8 条绝对不能违反的规则（编号列表）

## Layer 1 — 身份
一段简短的身份描述（2-3句话）

## Layer 2 — 表达风格
用列表描述：语气、用词习惯、emoji 偏好、格式偏好、回复长度、口头禅

## Layer 3 — 情感逻辑
用表格描述 6-8 种场景下的情绪反应：
| 触发条件 | 情绪反应 | 表达方式 |

## Layer 4 — 关系行为
用列表描述：亲密度、边界、冲突处理、主动性、记忆体现

## 对话示例
4-6 段对话示例，展示角色的说话风格

只输出 Markdown 内容，不要加任何解释。"""

            reply = llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="你是角色设计专家。根据用户描述生成高质量的 5 层 AI 角色定义文档。",
                temperature=0.7,
                max_tokens=3000,
            )

            content = reply.strip()
            if not content:
                return {"success": False, "error": "生成内容为空"}

            # 提取角色名
            import re
            name_match = re.search(r'^#\s+(.+)', content, re.MULTILINE)
            if not name_match and not name:
                name = "新角色"
            elif name_match and not name:
                name = name_match.group(1).strip()

            # 生成 slug
            if not slug:
                slug = self._safe_slug(name)

            # 创建或更新角色
            persona_dir = os.path.join(PERSONAS_DIR, slug)
            if os.path.isdir(persona_dir):
                result = self.save_soul(content, slug)
            else:
                result = self.create_persona(slug, name, content,
                                             description=description)

            result["content"] = content
            result["name"] = name
            return result

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_status(self) -> dict:
        """获取 SoulManager 状态"""
        active = self.get_active_slug()
        personas = self.list_personas()
        user_facts_count = 0
        try:
            from app.fact_memory import get_fact_memory
            user_facts_count = get_fact_memory().count()
        except Exception:
            pass

        return {
            "has_soul": self.has_soul,
            "active_persona": active,
            "personas_count": len(personas),
            "personas": personas,
            "user_facts_count": user_facts_count,
        }

    # ── 内部方法 ────────────────────────────────────────────────

    def _load_persona(self, slug: str) -> str:
        """加载角色 persona.md（带缓存）"""
        persona_path = os.path.join(PERSONAS_DIR, slug, "persona.md")
        if not os.path.isfile(persona_path):
            return ""
        try:
            mtime = os.path.getmtime(persona_path)
            cached = self._cache.get(slug)
            if cached and cached[1] == mtime:
                return cached[0]
            with open(persona_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            self._cache[slug] = (content, mtime)
            return content
        except Exception as e:
            print(f"[SoulManager] persona.md 加载失败 ({slug}): {e}")
            return ""

    def _load_memories(self, slug: str) -> str:
        """加载角色 memories.md"""
        mem_path = os.path.join(PERSONAS_DIR, slug, "memories.md")
        if not os.path.isfile(mem_path):
            return ""
        try:
            with open(mem_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return ""

    def _load_meta(self, slug: str) -> dict:
        """加载 meta.json"""
        meta_path = os.path.join(PERSONAS_DIR, slug, "meta.json")
        if not os.path.isfile(meta_path):
            return {"name": slug, "version": "v1"}
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"name": slug, "version": "v1"}

    def _save_meta(self, slug: str, meta: dict):
        """保存 meta.json"""
        meta_path = os.path.join(PERSONAS_DIR, slug, "meta.json")
        os.makedirs(os.path.dirname(meta_path), exist_ok=True)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _backup_version(self, slug: str):
        """存档当前版本"""
        persona_path = os.path.join(PERSONAS_DIR, slug, "persona.md")
        if not os.path.isfile(persona_path):
            return
        versions_dir = os.path.join(PERSONAS_DIR, slug, "versions")
        os.makedirs(versions_dir, exist_ok=True)
        meta = self._load_meta(slug)
        ver = meta.get("version", "v1")
        dst = os.path.join(versions_dir, f"{ver}.md")
        try:
            shutil.copy2(persona_path, dst)
        except Exception as e:
            print(f"[SoulManager] 版本存档失败: {e}")

    def _migrate_legacy(self):
        """将旧的 data/soul/SOUL.md 迁移到 personas/default/"""
        if not os.path.isfile(LEGACY_SOUL_PATH):
            return
        default_dir = os.path.join(PERSONAS_DIR, "default")
        default_persona = os.path.join(default_dir, "persona.md")
        if os.path.isfile(default_persona):
            return  # 已经迁移过了

        os.makedirs(os.path.join(default_dir, "versions"), exist_ok=True)
        # 复制 SOUL.md → default/persona.md
        shutil.copy2(LEGACY_SOUL_PATH, default_persona)
        # 创建 meta.json
        meta = {
            "name": "默认角色",
            "slug": "default",
            "description": "从旧版 SOUL.md 迁移的默认角色",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "version": "v1",
            "tags": {},
        }
        with open(os.path.join(default_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"[SoulManager] 旧版 SOUL.md 已迁移到 personas/default/")

        # 同时迁移微信的 soul.md（如果存在）
        wechat_soul = "data/wechat/soul.md"
        if os.path.isfile(wechat_soul):
            wechat_dir = os.path.join(PERSONAS_DIR, "wechat")
            os.makedirs(os.path.join(wechat_dir, "versions"), exist_ok=True)
            shutil.copy2(wechat_soul, os.path.join(wechat_dir, "persona.md"))
            wechat_meta = {
                "name": "微信角色",
                "slug": "wechat",
                "description": "从微信 soul.md 迁移的角色",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "version": "v1",
                "tags": {"channel": "wechat"},
            }
            with open(os.path.join(wechat_dir, "meta.json"), "w", encoding="utf-8") as f:
                json.dump(wechat_meta, f, ensure_ascii=False, indent=2)
            print(f"[SoulManager] 微信 soul.md 已迁移到 personas/wechat/")

    @staticmethod
    def _safe_slug(text: str) -> str:
        """生成安全的 slug"""
        import re
        # 简单：取字母数字和下划线
        slug = re.sub(r'[^\w]', '_', text.strip().lower())
        slug = re.sub(r'_+', '_', slug).strip('_')
        return slug[:30] or "unnamed"


# ============================================================
#  全局单例
# ============================================================
_manager: Optional[SoulManager] = None


def get_soul_manager() -> SoulManager:
    """获取全局 SoulManager 单例"""
    global _manager
    if _manager is None:
        _manager = SoulManager()
    return _manager
