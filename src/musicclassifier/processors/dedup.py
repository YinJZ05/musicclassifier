"""歌单去重处理器"""

from __future__ import annotations

from loguru import logger

from musicclassifier.models.song import Song


def deduplicate(songs: list[Song]) -> tuple[list[Song], list[Song]]:
    """歌单去重

    基于歌曲名 + 主歌手进行去重匹配。

    Args:
        songs: 原始歌曲列表

    Returns:
        (去重后的歌曲列表, 被移除的重复歌曲列表)
    """
    seen: dict[str, Song] = {}
    duplicates: list[Song] = []

    for song in songs:
        key = song.match_key()
        if key in seen:
            duplicates.append(song)
            logger.debug(f"发现重复: {song} (与 {seen[key]} 重复)")
        else:
            seen[key] = song

    unique_songs = list(seen.values())
    logger.info(
        f"去重完成: {len(songs)} → {len(unique_songs)} 首 "
        f"(移除 {len(duplicates)} 首重复)"
    )
    return unique_songs, duplicates


def merge_playlists(*song_lists: list[Song]) -> list[Song]:
    """合并多个歌单并去重

    Args:
        song_lists: 多个歌曲列表

    Returns:
        合并去重后的歌曲列表
    """
    all_songs: list[Song] = []
    for sl in song_lists:
        all_songs.extend(sl)

    unique, _ = deduplicate(all_songs)
    logger.info(f"合并 {len(song_lists)} 个歌单, 共 {len(all_songs)} → {len(unique)} 首")
    return unique
