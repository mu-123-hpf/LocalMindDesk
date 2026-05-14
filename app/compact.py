# -*- coding: utf-8 -*-
"""
LocalMindDesk — LLM 对话压缩器 v2
学习 Claude Code 的 compact/prompt.ts + autoCompact.ts

核心改进 (vs v1):
1. 9 段式结构化摘要模板 (来自 Claude Code)
2. 基于消息数的触发 (适配 4K 小模型)
3. 双策略：LLM 压缩 + 规则回退
4. 摘要去重 + 迭代压缩支持
5. 与 SSE 流集成 — 压缩时发出 step 事件
"""
from __future__ import annotations
import json
import time
from typing import Optional
from app import llm_provider


# ============================================================
#  配置
# ============================================================
# 消息数超过此值时触发压缩（为 4K 模型优化）
COMPACT_MSG_THRESHOLD = 10
# 压缩后保留的最近消息条数
KEEP_RECENT = 4
# LLM 摘要最大 token
SUMMARY_MAX_TOKENS = 600

# ============================================================
#  9 段式压缩提示词 (学习 Claude Code compact/prompt.ts)
# ============================================================
COMPACT_SYSTEM_PROMPT = """你是对话压缩专家。请将对话历史压缩为结构化摘要。

要求：
- 用中文输出
- 只输出 <summary> 标签内的内容
- 不要调用任何工具
- 控制在 400 字以内"""

COMPACT_USER_PROMPT = """请将以下对话历史压缩为结构化摘要。

{conversation}

按以下结构输出（省略无内容的段落）：

<summary>
1. 用户需求: [用户要求做什么]
2. 技术概念: [涉及的技术、框架、工具]
3. 文件变更: [修改/创建/读取了哪些文件，关键代码片段]
4. 错误与修复: [遇到了什么错误，如何修复]
5. 用户反馈: [用户对结果的评价或修改要求]
6. 已完成任务: [列出已完成的事项]
7. 待办任务: [用户明确要求但尚未完成的事项]
8. 当前工作: [压缩前正在做什么]
9. 下一步: [接下来应该做什么]
</summary>"""


# ============================================================
#  格式化工具
# ============================================================
def _format_summary(raw: str) -> str:
    """从 LLM 输出中提取并清理 <summary> 内容。"""
    # 去掉 <analysis> 块（如果有）
    import re
    raw = re.sub(r'<analysis>[\s\S]*?</analysis>', '', raw)

    # 提取 <summary> 内容
    m = re.search(r'<summary>([\s\S]*?)</summary>', raw)
    if m:
        return m.group(1).strip()

    # 没有标签，直接用全文
    return raw.strip()


def _estimate_tokens(text: str) -> int:
    """估算 token 数（中文 ~2 字/token，英文 ~4 字符/token）"""
    cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - cn_chars
    return cn_chars // 2 + other_chars // 4


def _estimate_messages_tokens(messages: list[dict]) -> int:
    """估算消息列表的总 token 数"""
    return sum(_estimate_tokens(m.get("content", "")) for m in messages)


# ============================================================
#  Compactor v2
# ============================================================
class ContextCompactor:
    """
    LLM 驱动的对话压缩器。

    工作流:
    1. should_compact() → 消息数 > 阈值时触发
    2. compact() → LLM 生成 9 段式摘要
    3. 返回: [摘要消息] + 最近 N 条原始消息

    特性:
    - 迭代压缩: 旧摘要会被包含在新压缩输入中
    - 回退策略: LLM 失败时用规则提取关键信息
    - 统计追踪: 记录压缩次数和效果
    """

    def __init__(self,
                 msg_threshold: int = COMPACT_MSG_THRESHOLD,
                 keep_recent: int = KEEP_RECENT):
        self.msg_threshold = msg_threshold
        self.keep_recent = keep_recent
        self._compact_count: int = 0
        self._last_compact_time: float = 0
        self._total_messages_compressed: int = 0

    def should_compact(self, messages: list[dict]) -> bool:
        """消息数超过阈值时触发压缩。"""
        if len(messages) <= self.keep_recent + 2:
            return False
        return len(messages) > self.msg_threshold

    def compact(self, messages: list[dict]) -> list[dict]:
        """
        执行对话压缩。

        返回: 压缩后的消息列表
        格式: [{"role": "system", "content": "[摘要] ..."}, ...最近消息]
        """
        if not self.should_compact(messages):
            return messages

        # 分割
        old_messages = messages[:-self.keep_recent]
        recent_messages = messages[-self.keep_recent:]

        # 构建压缩输入
        conversation_text = self._format_for_compression(old_messages)
        old_token_est = _estimate_messages_tokens(messages)

        # 尝试 LLM 压缩
        summary = self._llm_compress(conversation_text)
        if not summary:
            summary = self._fallback_summary(old_messages)

        # 构建压缩后消息
        compacted = [
            {
                "role": "system",
                "content": (
                    f"[对话摘要 — 已压缩 {len(old_messages)} 条旧消息]\n"
                    f"以下是之前对话的结构化总结，最近消息保留原文。\n\n"
                    f"{summary}"
                ),
            }
        ]
        compacted.extend(recent_messages)

        # 统计
        new_token_est = _estimate_messages_tokens(compacted)
        self._compact_count += 1
        self._last_compact_time = time.time()
        self._total_messages_compressed += len(old_messages)

        ratio = round((1 - new_token_est / max(old_token_est, 1)) * 100)
        print(f"[Compact v2] {len(old_messages)} msgs → 摘要 "
              f"(~{old_token_est} → ~{new_token_est} tokens, 压缩率 {ratio}%)")

        return compacted

    def _llm_compress(self, conversation_text: str) -> Optional[str]:
        """使用 LLM 生成结构化摘要。"""
        try:
            prompt = COMPACT_USER_PROMPT.format(conversation=conversation_text)
            raw = llm_provider.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=COMPACT_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=SUMMARY_MAX_TOKENS,
            )
            summary = _format_summary(raw)
            if len(summary) < 20:
                return None  # 摘要太短，视为失败
            return summary
        except Exception as e:
            print(f"[Compact v2] LLM 压缩失败: {e}")
            return None

    def _format_for_compression(self, messages: list[dict]) -> str:
        """格式化旧消息为 LLM 压缩输入。"""
        parts = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # 截断过长消息（保留头尾）
            if len(content) > 400:
                content = content[:300] + "\n...(中间省略)...\n" + content[-100:]

            if role == "user":
                parts.append(f"[用户] {content}")
            elif role == "assistant":
                parts.append(f"[AI] {content}")
            elif role == "system":
                # 包含旧摘要（支持迭代压缩）
                if "[对话摘要" in content:
                    parts.append(f"[之前的摘要] {content[:300]}")
                else:
                    parts.append(f"[系统] {content[:200]}")

        return "\n\n".join(parts)

    def _fallback_summary(self, messages: list[dict]) -> str:
        """LLM 失败时的规则回退摘要。"""
        user_msgs = []
        ai_actions = []

        for msg in messages:
            content = msg.get("content", "")
            if msg.get("role") == "user" and len(content) > 5:
                user_msgs.append(content[:80])
            elif msg.get("role") == "assistant" and len(content) > 10:
                # 提取第一句作为行动概要
                first_line = content.split("\n")[0][:80]
                ai_actions.append(first_line)

        parts = []
        if user_msgs:
            parts.append("1. 用户需求: " + "; ".join(user_msgs[-5:]))
        if ai_actions:
            parts.append("6. 已完成任务: " + "; ".join(ai_actions[-3:]))

        return "\n".join(parts) if parts else "（前序对话无关键内容）"

    def get_stats(self) -> dict:
        """压缩统计。"""
        return {
            "compact_count": self._compact_count,
            "total_messages_compressed": self._total_messages_compressed,
            "last_compact_time": self._last_compact_time,
        }


# ============================================================
#  全局单例
# ============================================================
_compactor: ContextCompactor | None = None


def get_compactor() -> ContextCompactor:
    """获取全局 Compactor 单例"""
    global _compactor
    if _compactor is None:
        _compactor = ContextCompactor()
    return _compactor
