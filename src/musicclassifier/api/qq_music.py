"""QQ音乐 API 封装

通过 QQ 音乐的 Web API 获取歌单、歌曲信息等数据。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from loguru import logger

from musicclassifier.config import get_settings
from musicclassifier.models.song import Playlist, Song

# QQ音乐 API 基础地址
BASE_URL = "https://c.y.qq.com"
U_URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"

# 通用请求头
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://y.qq.com/",
    "Origin": "https://y.qq.com",
}


class QQMusicAPI:
    """QQ音乐 API 客户端"""

    def __init__(self, cookie: str = "", timeout: float = 30, request_interval: float = 1.0):
        self.cookie = cookie
        self.timeout = timeout
        self.request_interval = request_interval
        self._last_request_time: float = 0

    @classmethod
    def from_config(cls) -> "QQMusicAPI":
        """从配置文件创建实例"""
        settings = get_settings()
        return cls(
            cookie=settings.qq_music.cookie,
            timeout=settings.qq_music.timeout,
            request_interval=settings.qq_music.request_interval,
        )

    def _get_headers(self) -> dict[str, str]:
        """获取请求头"""
        headers = DEFAULT_HEADERS.copy()
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    def _throttle(self) -> None:
        """请求限流"""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.request_interval:
            time.sleep(self.request_interval - elapsed)
        self._last_request_time = time.monotonic()

    def _request(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """发送同步 HTTP 请求"""
        self._throttle()
        logger.debug(f"请求: {url}")
        with httpx.Client(timeout=self.timeout, headers=self._get_headers()) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()

    def _post_request(self, url: str, json_data: dict[str, Any]) -> dict[str, Any]:
        """发送同步 POST 请求"""
        self._throttle()
        logger.debug(f"POST 请求: {url}")
        with httpx.Client(timeout=self.timeout, headers=self._get_headers()) as client:
            resp = client.post(url, json=json_data)
            resp.raise_for_status()
            return resp.json()

    # ────────────────────────── 歌单相关 ──────────────────────────

    def get_playlist_detail(self, playlist_id: int) -> Playlist:
        """获取歌单详情

        Args:
            playlist_id: 歌单 ID（disstid）

        Returns:
            Playlist 对象
        """
        url = f"{BASE_URL}/splcloud/fcgi-bin/fcg_get_diss_by_tag.fcg"

        # 使用新版 musicu 接口
        req_data = {
            "req_0": {
                "module": "srf_diss_info.DissInfoServer",
                "method": "CgiGetDiss",
                "param": {
                    "disstid": playlist_id,
                    "onlysonglist": 0,
                    "song_begin": 0,
                    "song_num": 500,
                },
            }
        }

        data = self._post_request(U_URL, req_data)

        try:
            diss_info = data["req_0"]["data"]
            dirinfo = diss_info.get("dirinfo", {})
            songlist = diss_info.get("songlist", [])
        except (KeyError, TypeError) as e:
            logger.error(f"解析歌单数据失败: {e}")
            logger.debug(f"原始数据: {data}")
            raise ValueError(f"无法解析歌单 {playlist_id} 的数据") from e

        songs = [self._parse_song(item) for item in songlist]

        return Playlist(
            id=str(playlist_id),
            name=dirinfo.get("title", "未知歌单"),
            description=dirinfo.get("desc", ""),
            song_count=len(songs),
            songs=songs,
        )

    def get_user_playlists(self, qq_number: str) -> list[dict[str, Any]]:
        """获取用户创建/收藏的歌单列表

        Args:
            qq_number: 用户 QQ 号

        Returns:
            歌单基础信息列表
        """
        req_data = {
            "req_0": {
                "module": "music.srfDissInfo.aiDissInfo",
                "method": "uniform_get_Ede",
                "param": {
                    "uin": qq_number,
                    "is_query_fav": 1,
                },
            }
        }

        data = self._post_request(U_URL, req_data)

        try:
            disslist = data["req_0"]["data"]["mymusic"]
        except (KeyError, TypeError):
            disslist = []

        playlists = []
        for item in disslist:
            playlists.append({
                "id": item.get("dissid", ""),
                "name": item.get("title", "未知歌单"),
                "song_count": item.get("subtitle", 0),
            })

        return playlists

    def search_songs(self, keyword: str, page: int = 1, page_size: int = 20) -> list[Song]:
        """搜索歌曲

        Args:
            keyword: 搜索关键词
            page: 页码
            page_size: 每页数量

        Returns:
            歌曲列表
        """
        req_data = {
            "req_0": {
                "module": "music.search.SearchCgiService",
                "method": "DoSearchForQQMusicDesktop",
                "param": {
                    "search_type": 0,
                    "query": keyword,
                    "page_num": page,
                    "num_per_page": page_size,
                },
            }
        }

        data = self._post_request(U_URL, req_data)

        try:
            song_list = data["req_0"]["data"]["body"]["song"]["list"]
        except (KeyError, TypeError):
            return []

        return [self._parse_song(item) for item in song_list]

    # ────────────────────────── 内部方法 ──────────────────────────

    @staticmethod
    def _parse_song(raw: dict[str, Any]) -> Song:
        """解析原始歌曲数据为 Song 模型"""
        singers = raw.get("singer", [])
        artist_names = [s.get("name", "未知") for s in singers]

        album_info = raw.get("album", {})

        return Song(
            mid=raw.get("mid", raw.get("songmid", "")),
            name=raw.get("name", raw.get("songname", "未知")),
            artists=artist_names,
            album=album_info.get("name", raw.get("albumname", "")),
            duration=raw.get("interval", 0),
            genre=raw.get("genre", ""),
            language=raw.get("language", ""),
        )
