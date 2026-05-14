"""
LocalMindDesk — 统一日志系统
替代散落各处的 print()，提供结构化日志
"""
import logging
import sys

# 自定义格式器 — 带颜色和模块标签
class ClawFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[36m",    # 青色
        logging.INFO: "\033[32m",     # 绿色
        logging.WARNING: "\033[33m",  # 黄色
        logging.ERROR: "\033[31m",    # 红色
        logging.CRITICAL: "\033[35m", # 紫色
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelno, self.RESET)
        # 支持 GBK 终端
        try:
            msg = super().format(record)
        except Exception:
            msg = str(record.msg)
        return f"{color}{msg}{self.RESET}"


def get_logger(name: str) -> logging.Logger:
    """
    获取模块级 logger
    用法: logger = get_logger(__name__)
         logger.info("消息")
    """
    logger = logging.getLogger(f"LocalMindDesk.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(ClawFormatter(
            fmt="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    return logger


# 预建常用 logger
log = get_logger("core")
