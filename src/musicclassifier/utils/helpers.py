"""通用工具函数"""

from __future__ import annotations

import re
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


def extract_playlist_ids(text: str) -> list[int]:
    """从任意文本中提取歌单 ID。

    支持纯数字、歌单链接、分享文案等混合输入，返回去重且保持顺序的 ID 列表。
    """
    matches = re.findall(r"(\d{5,})", text)
    ordered_unique: list[int] = []
    seen: set[int] = set()
    for raw in matches:
        pid = int(raw)
        if pid in seen:
            continue
        seen.add(pid)
        ordered_unique.append(pid)
    return ordered_unique
