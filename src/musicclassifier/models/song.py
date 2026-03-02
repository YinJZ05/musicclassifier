"""歌曲与歌单数据模型"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Song(BaseModel):
    """歌曲信息模型"""

    mid: str = Field(default="", description="歌曲 MID（QQ音乐唯一标识）")
    name: str = Field(description="歌曲名称")
    artists: list[str] = Field(default_factory=list, description="歌手列表")
    album: str = Field(default="", description="专辑名称")
    duration: int = Field(default=0, description="时长（秒）")
    genre: str = Field(default="", description="流派")
    language: str = Field(default="", description="语言")
    tags: list[str] = Field(default_factory=list, description="自定义标签")
    category: str = Field(default="", description="自动分类结果")

    @property
    def artist_str(self) -> str:
        """歌手字符串"""
        return " / ".join(self.artists) if self.artists else "未知"

    @property
    def duration_str(self) -> str:
        """格式化时长 mm:ss"""
        minutes, seconds = divmod(self.duration, 60)
        return f"{minutes}:{seconds:02d}"

    def match_key(self) -> str:
        """用于去重的匹配键（歌名 + 主歌手，忽略大小写）"""
        artist = self.artists[0].strip().lower() if self.artists else ""
        return f"{self.name.strip().lower()}|{artist}"

    def __str__(self) -> str:
        return f"{self.name} - {self.artist_str}"


class Playlist(BaseModel):
    """歌单信息模型"""

    id: str = Field(description="歌单 ID")
    name: str = Field(description="歌单名称")
    description: str = Field(default="", description="歌单描述")
    song_count: int = Field(default=0, description="歌曲数量")
    songs: list[Song] = Field(default_factory=list, description="歌曲列表")

    def __str__(self) -> str:
        return f"[{self.name}] ({self.song_count} 首)"


class ClassifiedResult(BaseModel):
    """分类结果模型"""

    category: str = Field(description="分类名称")
    songs: list[Song] = Field(default_factory=list, description="该分类下的歌曲")

    @property
    def count(self) -> int:
        return len(self.songs)
