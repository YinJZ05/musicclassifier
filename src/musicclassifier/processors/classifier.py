"""歌曲自动分类器

根据歌曲的流派、语言、歌手等信息自动分类。
"""

from __future__ import annotations

from loguru import logger

from musicclassifier.models.song import ClassifiedResult, Song

# ──────────────────── 内置分类规则 ────────────────────

# 语言分类关键字
LANGUAGE_KEYWORDS: dict[str, list[str]] = {
    "华语": ["国语", "粤语", "中文", "华语", "闽南语"],
    "英语": ["英语", "英文", "English"],
    "日语": ["日语", "日文", "Japanese"],
    "韩语": ["韩语", "韩文", "Korean"],
}

# 流派分类关键字
GENRE_KEYWORDS: dict[str, list[str]] = {
    "流行": ["流行", "Pop", "pop"],
    "摇滚": ["摇滚", "Rock", "rock", "朋克", "Punk"],
    "民谣": ["民谣", "Folk", "folk"],
    "电子": ["电子", "Electronic", "EDM", "House", "Techno", "DJ"],
    "说唱": ["说唱", "嘻哈", "Rap", "Hip-Hop", "Hip Hop", "hiphop"],
    "R&B": ["R&B", "节奏布鲁斯", "Soul", "灵魂"],
    "古典": ["古典", "Classical", "古风", "中国风"],
    "爵士": ["爵士", "Jazz", "jazz"],
    "轻音乐": ["轻音乐", "纯音乐", "Instrumental", "New Age"],
}


class SongClassifier:
    """歌曲分类器"""

    def __init__(
        self,
        genre_rules: dict[str, list[str]] | None = None,
        language_rules: dict[str, list[str]] | None = None,
    ):
        self.genre_rules = genre_rules or GENRE_KEYWORDS
        self.language_rules = language_rules or LANGUAGE_KEYWORDS

    def classify_by_genre(self, songs: list[Song]) -> list[ClassifiedResult]:
        """按流派分类

        Args:
            songs: 歌曲列表

        Returns:
            分类结果列表
        """
        categories: dict[str, list[Song]] = {}

        for song in songs:
            genre = self._match_genre(song)
            song_copy = song.model_copy()
            song_copy.category = genre
            categories.setdefault(genre, []).append(song_copy)

        results = [
            ClassifiedResult(category=cat, songs=song_list)
            for cat, song_list in sorted(categories.items())
        ]

        logger.info(f"按流派分类完成: {len(results)} 个分类, 共 {len(songs)} 首歌")
        return results

    def classify_by_language(self, songs: list[Song]) -> list[ClassifiedResult]:
        """按语言分类"""
        categories: dict[str, list[Song]] = {}

        for song in songs:
            lang = self._match_language(song)
            song_copy = song.model_copy()
            song_copy.category = lang
            categories.setdefault(lang, []).append(song_copy)

        results = [
            ClassifiedResult(category=cat, songs=song_list)
            for cat, song_list in sorted(categories.items())
        ]

        logger.info(f"按语言分类完成: {len(results)} 个分类, 共 {len(songs)} 首歌")
        return results

    def classify_songs(
        self, songs: list[Song], by: str = "genre"
    ) -> list[ClassifiedResult]:
        """统一分类入口

        Args:
            songs: 歌曲列表
            by: 分类维度 ("genre" 或 "language")
        """
        if by == "language":
            return self.classify_by_language(songs)
        return self.classify_by_genre(songs)

    # ────────────────── 内部匹配方法 ──────────────────

    def _match_genre(self, song: Song) -> str:
        """匹配歌曲流派"""
        search_text = f"{song.genre} {song.name} {' '.join(song.tags)}"
        for category, keywords in self.genre_rules.items():
            for kw in keywords:
                if kw.lower() in search_text.lower():
                    return category
        return "其他"

    def _match_language(self, song: Song) -> str:
        """匹配歌曲语言"""
        search_text = f"{song.language} {' '.join(song.tags)}"
        for category, keywords in self.language_rules.items():
            for kw in keywords:
                if kw.lower() in search_text.lower():
                    return category
        return "其他"
