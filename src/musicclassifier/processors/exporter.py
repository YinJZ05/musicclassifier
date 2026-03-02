"""歌单数据导出器

支持导出为 CSV、JSON、Excel 格式。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from loguru import logger

from musicclassifier.models.song import Song


def songs_to_dataframe(songs: list[Song]) -> pd.DataFrame:
    """将歌曲列表转换为 DataFrame"""
    records = []
    for s in songs:
        records.append({
            "歌曲MID": s.mid,
            "歌名": s.name,
            "歌手": s.artist_str,
            "专辑": s.album,
            "时长": s.duration_str,
            "流派": s.genre,
            "语言": s.language,
            "分类": s.category,
            "标签": ", ".join(s.tags),
        })
    return pd.DataFrame(records)


def export_csv(songs: list[Song], output_path: str | Path) -> Path:
    """导出为 CSV 文件"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    df = songs_to_dataframe(songs)
    df.to_csv(path, index=False, encoding="utf-8-sig")  # BOM for Excel compatibility

    logger.info(f"已导出 CSV: {path} ({len(songs)} 首)")
    return path


def export_json(songs: list[Song], output_path: str | Path) -> Path:
    """导出为 JSON 文件"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = [s.model_dump() for s in songs]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"已导出 JSON: {path} ({len(songs)} 首)")
    return path


def export_excel(songs: list[Song], output_path: str | Path) -> Path:
    """导出为 Excel 文件"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    df = songs_to_dataframe(songs)
    df.to_excel(path, index=False, engine="openpyxl")

    logger.info(f"已导出 Excel: {path} ({len(songs)} 首)")
    return path


def export_songs(
    songs: list[Song],
    output_path: str | Path,
    fmt: str = "csv",
) -> Path:
    """统一导出入口

    Args:
        songs: 歌曲列表
        output_path: 输出文件路径
        fmt: 格式 ("csv" / "json" / "excel")

    Returns:
        导出文件路径
    """
    exporters = {
        "csv": export_csv,
        "json": export_json,
        "excel": export_excel,
    }

    exporter = exporters.get(fmt.lower())
    if exporter is None:
        raise ValueError(f"不支持的导出格式: {fmt}，可选: {list(exporters.keys())}")

    return exporter(songs, output_path)
