"""通用工具函数"""

from __future__ import annotations

from pathlib import Path

from loguru import logger


def ensure_dir(path: str | Path) -> Path:
    """确保目录存在，不存在则创建"""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def format_duration(seconds: int) -> str:
    """格式化时长为 mm:ss"""
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def setup_logging(level: str = "INFO", log_file: str = "") -> None:
    """配置 loguru 日志"""
    logger.remove()  # 清除默认处理器

    # 控制台输出
    logger.add(
        lambda msg: print(msg, end=""),
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}",
        colorize=True,
    )

    # 文件输出（如果配置了）
    if log_file:
        logger.add(
            log_file,
            level=level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {message}",
            rotation="10 MB",
            retention=5,
            encoding="utf-8",
        )
