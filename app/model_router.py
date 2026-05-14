"""
LocalMindDesk — 智能模型路由
简单问题 → 小/快模型   复杂问题 → 大/强模型
支持 A/B 对比模式
"""
from app.config import get_config, get_endpoint_by_name, ModelEndpoint
from app.logger import get_logger
from typing import Optional

logger = get_logger("model_router")

# 复杂度关键词（触发大模型）
COMPLEX_KEYWORDS = [
    # 编程
    "代码", "编程", "函数", "调试", "bug", "重构", "架构", "设计模式",
    "code", "debug", "refactor", "implement", "algorithm",
    # 分析
    "分析", "对比", "评估", "论证", "解释原理", "深入",
    "analyze", "compare", "evaluate", "explain",
    # 长文
    "文章", "报告", "论文", "总结全文", "详细说明",
    "write", "essay", "report", "document",
    # 推理
    "为什么", "如何", "原因", "逻辑", "推理", "证明",
    "why", "how", "reason", "prove",
]

# 简单问题关键词（可用小模型）
SIMPLE_KEYWORDS = [
    "你好", "hello", "hi", "嗨", "谢谢", "好的", "再见",
    "翻译", "translate", "是什么", "定义", "几点",
    "天气", "日期", "时间",
]


def estimate_complexity(message: str) -> str:
    """
    估算问题复杂度
    返回: "simple" | "medium" | "complex"
    """
    lower = message.lower()
    length = len(message)

    complex_hits = sum(1 for kw in COMPLEX_KEYWORDS if kw in lower)
    simple_hits = sum(1 for kw in SIMPLE_KEYWORDS if kw in lower)

    # 长消息倾向复杂
    if length > 200:
        complex_hits += 2
    elif length < 20:
        simple_hits += 1

    if complex_hits >= 2:
        return "complex"
    elif simple_hits > complex_hits:
        return "simple"
    else:
        return "medium"


def select_model(message: str, preferred: Optional[str] = None) -> Optional[ModelEndpoint]:
    """
    智能选择模型端点
    - preferred: 用户手动指定的模型名（优先使用）
    - 否则按复杂度自动路由
    """
    cfg = get_config()

    # 用户手动指定
    if preferred:
        ep = get_endpoint_by_name(preferred)
        if ep:
            return ep

    # 只有一个模型时直接返回
    active_models = [m for m in cfg.models if m.is_active]
    if len(active_models) <= 1:
        return active_models[0] if active_models else None

    complexity = estimate_complexity(message)

    # 尝试按 provider 分类
    # 小模型：lmstudio 本地小模型
    # 大模型：deepseek / openai 等远程大模型
    local_models = [m for m in active_models if m.provider in ("lmstudio", "ollama")]
    remote_models = [m for m in active_models if m.provider not in ("lmstudio", "ollama")]

    if complexity == "simple" and local_models:
        selected = local_models[0]
        logger.info(f"路由 → {selected.name} (简单问题, 本地快速)")
        return selected
    elif complexity == "complex" and remote_models:
        selected = remote_models[0]
        logger.info(f"路由 → {selected.name} (复杂问题, 远程强模型)")
        return selected
    else:
        # medium 或没有对应类型 → 默认模型
        default = get_endpoint_by_name(cfg.active_model)
        return default or active_models[0]


def get_all_active_models() -> list[dict]:
    """获取所有活跃模型信息（用于前端展示）"""
    cfg = get_config()
    return [
        {
            "name": m.name,
            "provider": m.provider,
            "model": m.model,
            "is_default": m.name == cfg.active_model,
        }
        for m in cfg.models if m.is_active
    ]
