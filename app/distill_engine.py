"""
LocalMindDesk — Persona 蒸馏引擎

将聊天记录/文本描述蒸馏为 5 层 Persona + Memories。
参考 perkfly/ex-skill 的蒸馏方法论，泛化为通用人物蒸馏能力。

蒸馏流程:
  原材料 → 解析器 → 双线分析 → Persona(5层) + Memories → 角色创建

支持模式:
  1. 从聊天记录蒸馏
  2. 从文本描述蒸馏
  3. 混合蒸馏（描述 + 聊天记录）
"""
import os
from dataclasses import dataclass
from typing import Optional

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "distill_prompts")


@dataclass
class DistillResult:
    """蒸馏结果"""
    success: bool = False
    persona: str = ""          # 5 层 Persona markdown
    memories: str = ""         # 共同记忆 markdown
    analysis: str = ""         # 原始分析报告
    name: str = ""
    slug: str = ""
    error: str = ""
    stats: dict = None         # 统计信息

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "persona": self.persona,
            "memories": self.memories,
            "analysis": self.analysis,
            "name": self.name,
            "slug": self.slug,
            "error": self.error,
            "stats": self.stats or {},
        }


def _load_prompt(name: str) -> str:
    """加载 prompt 模板"""
    path = os.path.join(PROMPTS_DIR, name)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


class DistillEngine:
    """通用人物蒸馏引擎"""

    def __init__(self):
        self._persona_analyzer_prompt = _load_prompt("persona_analyzer.md")
        self._memories_analyzer_prompt = _load_prompt("memories_analyzer.md")
        self._persona_builder_prompt = _load_prompt("persona_builder.md")
        self._merger_prompt = _load_prompt("merger.md")

    def distill(self, target_name: str,
                chat_text: str = "",
                description: str = "",
                personality_tags: str = "",
                endpoint=None) -> DistillResult:
        """
        执行蒸馏（统一入口）

        Args:
            target_name: 目标人物名称
            chat_text: 聊天记录文本（可选）
            description: 人物描述（可选）
            personality_tags: 性格标签（可选，如 "ENFP 双子座 焦虑型 爱撒娇"）

        Returns:
            DistillResult
        """
        if not target_name:
            return DistillResult(error="目标人物名称不能为空")

        # 准备原材料
        material = self._prepare_material(
            target_name, chat_text, description, personality_tags
        )
        if not material.strip():
            return DistillResult(error="没有提供任何原材料")

        try:
            from app import llm_provider

            # Step 1: 双线分析
            persona_analysis = self._analyze_persona(material, target_name, endpoint)
            memories_analysis = ""
            if chat_text:
                memories_analysis = self._analyze_memories(material, target_name, endpoint)

            # Step 2: 生成 5 层 Persona
            persona_md = self._build_persona(
                target_name, persona_analysis, personality_tags, endpoint
            )

            # Step 3: 生成 Memories（如果有聊天记录）
            memories_md = ""
            if memories_analysis:
                memories_md = memories_analysis

            # 生成 slug
            import re
            slug = re.sub(r'[^\w]', '_', target_name.strip().lower())
            slug = re.sub(r'_+', '_', slug).strip('_')[:30] or "unnamed"

            return DistillResult(
                success=True,
                persona=persona_md,
                memories=memories_md,
                analysis=persona_analysis,
                name=target_name,
                slug=slug,
                stats={
                    "has_chat": bool(chat_text),
                    "has_description": bool(description),
                    "has_tags": bool(personality_tags),
                    "chat_length": len(chat_text),
                    "persona_length": len(persona_md),
                    "memories_length": len(memories_md),
                },
            )

        except Exception as e:
            return DistillResult(error=f"蒸馏失败: {str(e)}")

    def distill_from_chat_file(self, filepath: str,
                               target_name: str = "",
                               description: str = "",
                               personality_tags: str = "") -> DistillResult:
        """从聊天记录文件蒸馏"""
        from app.chat_parser import ChatParser

        parser = ChatParser()
        result = parser.parse_file(filepath, target_name)

        if not target_name and result.target_name:
            target_name = result.target_name

        if not target_name:
            return DistillResult(error="无法推断目标人物，请指定 target_name")

        return self.distill(
            target_name=target_name,
            chat_text=result.summary_text(max_chars=6000),
            description=description,
            personality_tags=personality_tags,
        )

    def evolve_correct(self, slug: str, feedback: str) -> dict:
        """
        对话纠正：用户说"她不会这样"时触发

        Args:
            slug: 角色标识
            feedback: 用户的纠正反馈
        """
        from app.soul_manager import get_soul_manager
        sm = get_soul_manager()

        current_persona = sm._load_persona(slug)
        if not current_persona:
            return {"success": False, "error": f"角色 '{slug}' 不存在"}

        try:
            from app import llm_provider

            prompt = f"""用户对角色的表现给出了纠正反馈。请根据反馈修正角色的 Persona 定义。

## 当前 Persona
{current_persona}

## 用户反馈
{feedback}

## 修正规则
1. 保持 5 层结构不变
2. 只修改与反馈相关的部分
3. 在修改处标注 [纠正] 标签
4. 如果反馈涉及 Layer 3（情感逻辑），更新表格中的对应行
5. 如果反馈涉及 Layer 2（表达风格），更新对应的用词/语气描述

输出完整的修正后 Persona（不是增量，而是完整文档）。"""

            reply = llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="你是角色定义修正专家。根据用户反馈精确修正角色定义。",
                temperature=0.3,
                max_tokens=3000,
            )

            corrected = reply.strip()
            if not corrected:
                return {"success": False, "error": "修正内容为空"}

            result = sm.save_soul(corrected, slug)
            result["feedback"] = feedback
            return result

        except Exception as e:
            return {"success": False, "error": str(e)}

    def evolve_append(self, slug: str, new_material: str,
                      target_name: str = "") -> dict:
        """
        增量进化：追加新的聊天记录/材料

        Args:
            slug: 角色标识
            new_material: 新增材料
            target_name: 目标人物名称
        """
        from app.soul_manager import get_soul_manager
        sm = get_soul_manager()

        current_memories = sm._load_memories(slug)
        current_persona = sm._load_persona(slug)

        if not current_persona:
            return {"success": False, "error": f"角色 '{slug}' 不存在"}

        try:
            from app import llm_provider

            # 合并 memories
            if current_memories:
                merge_prompt = self._merger_prompt + f"""

=== 已有记忆 ===
{current_memories}

=== 新增材料 ===
{new_material[:4000]}"""

                merged = llm_provider.chat(
                    messages=[{"role": "user", "content": merge_prompt}],
                    system_prompt="你是记忆整合专家。将新材料合并到已有记忆中。",
                    temperature=0.3,
                    max_tokens=3000,
                )
                new_memories = merged.strip()
            else:
                # 没有旧记忆，直接分析新材料
                new_memories = self._analyze_memories(
                    new_material, target_name or slug
                )

            # 保存更新后的 memories
            if new_memories:
                mem_path = os.path.join(
                    "data/soul/personas", slug, "memories.md"
                )
                os.makedirs(os.path.dirname(mem_path), exist_ok=True)
                with open(mem_path, "w", encoding="utf-8") as f:
                    f.write(new_memories)

            return {
                "success": True,
                "slug": slug,
                "memories_updated": bool(new_memories),
                "memories_length": len(new_memories),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 内部方法 ────────────────────────────────────────────────

    def _prepare_material(self, name: str, chat: str,
                          desc: str, tags: str) -> str:
        """整理原材料为统一格式"""
        parts = [f"目标人物: {name}"]
        if desc:
            parts.append(f"\n## 人物描述\n{desc}")
        if tags:
            parts.append(f"\n## 性格标签\n{tags}")
        if chat:
            parts.append(f"\n## 聊天记录\n{chat[:6000]}")
        return "\n".join(parts)

    def _analyze_persona(self, material: str, name: str, endpoint=None) -> str:
        """分析人物性格"""
        from app import llm_provider

        prompt = f"""{self._persona_analyzer_prompt}

---

## 原材料
{material[:6000]}

请对「{name}」进行性格分析。"""

        return llm_provider.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="你是人物性格分析专家。从原材料中精准提取性格特征。",
            temperature=0.3,
            max_tokens=2500,
            endpoint=endpoint,
        ).strip()

    def _analyze_memories(self, material: str, name: str, endpoint=None) -> str:
        """提取共同记忆"""
        from app import llm_provider

        prompt = f"""{self._memories_analyzer_prompt}

---

## 原材料
{material[:6000]}

请提取与「{name}」相关的共同记忆。"""

        return llm_provider.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="你是共同记忆提取专家。从原材料中提取关系信息和共同经历。",
            temperature=0.3,
            max_tokens=2500,
            endpoint=endpoint,
        ).strip()

    def _build_persona(self, name: str, analysis: str,
                       tags: str = "", endpoint=None) -> str:
        """从分析结果生成 5 层 Persona"""
        from app import llm_provider

        prompt = f"""{self._persona_builder_prompt}

---

## 角色名称
{name}

## 性格分析结果
{analysis}

{"## 性格标签" + chr(10) + tags if tags else ""}

请生成完整的 5 层 Persona 文档。"""

        return llm_provider.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="你是角色定义生成专家。根据分析结果生成精准的 5 层 Persona。",
            temperature=0.5,
            max_tokens=3000,
            endpoint=endpoint,
        ).strip()


# ============================================================
#  全局单例
# ============================================================
_engine: Optional[DistillEngine] = None  # noqa: F821


def get_distill_engine() -> DistillEngine:
    global _engine
    if _engine is None:
        _engine = DistillEngine()
    return _engine
