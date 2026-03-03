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
    """QQ音乐 API 客户端

    支持 QQ 登录和微信登录两种方式，通过 Cookie 鉴权。
    """

    def __init__(
        self,
        cookie: str = "",
        timeout: float = 30,
        request_interval: float = 1.0,
        login_type: str = "auto",
    ):
        self.cookie = cookie.strip().replace("\n", "").replace("\r", "")
        self.timeout = timeout
        self.request_interval = request_interval
        self.login_type = login_type  # "qq" / "wechat" / "auto"
        self._last_request_time: float = 0

    @classmethod
    def from_config(cls) -> "QQMusicAPI":
        """从配置文件创建实例"""
        settings = get_settings()
        return cls(
            cookie=settings.qq_music.cookie,
            timeout=settings.qq_music.timeout,
            request_interval=settings.qq_music.request_interval,
            login_type=settings.qq_music.login_type,
        )

    # ────────────────────────── 登录检测 ──────────────────────────

    def detect_login_type(self) -> str:
        """从 Cookie 自动检测登录类型

        Returns:
            "qq" 或 "wechat"
        """
        if self.login_type in ("qq", "wechat"):
            return self.login_type

        # 自动检测：微信登录的 Cookie 中包含 wxuin
        if "wxuin" in self.cookie:
            logger.info("检测到微信登录")
            return "wechat"
        logger.info("检测到 QQ 登录")
        return "qq"

    def extract_uin_from_cookie(self) -> str:
        """从 Cookie 中提取用户标识 (uin)

        QQ 登录: 提取 uin=xxx
        微信登录: 提取 wxuin=xxx

        Returns:
            用户标识字符串
        """
        import re

        login = self.detect_login_type()

        if login == "wechat":
            # 微信登录：wxuin=xxx
            match = re.search(r'wxuin=(\d+)', self.cookie)
            if match:
                return match.group(1)
        else:
            # QQ 登录：uin=oXXXX 或 uin=XXXXX
            match = re.search(r'uin=o?(\d+)', self.cookie)
            if match:
                return match.group(1)

        return ""

    def get_login_info(self) -> dict[str, str]:
        """获取当前登录信息摘要

        Returns:
            包含 login_type, uin 的字典
        """
        login = self.detect_login_type()
        uin = self.extract_uin_from_cookie()
        return {
            "login_type": login,
            "login_type_display": "微信登录" if login == "wechat" else "QQ 登录",
            "uin": uin,
        }

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

    def get_user_playlists(self, uin: str = "") -> list[dict[str, Any]]:
        """获取用户创建/收藏的歌单列表

        同时支持 QQ 登录和微信登录。如未传入 uin，会自动从 Cookie 提取。

        Args:
            uin: 用户标识（QQ号 或 微信uin），留空自动提取

        Returns:
            歌单基础信息列表
        """
        if not uin:
            uin = self.extract_uin_from_cookie()
            if not uin:
                logger.warning("无法从 Cookie 中提取用户标识，请手动传入 QQ 号或微信 uin")
                return []

        login = self.detect_login_type()
        logger.info(f"获取歌单列表 (登录方式: {login}, uin: {uin})")

        # 方式一：通用接口（QQ/微信均可尝试）
        req_data = {
            "req_0": {
                "module": "music.srfDissInfo.aiDissInfo",
                "method": "uniform_get_Ede",
                "param": {
                    "uin": uin,
                    "is_query_fav": 1,
                },
            }
        }

        data = self._post_request(U_URL, req_data)

        playlists = self._parse_playlist_list(data)

        # 方式二：如果方式一没结果，尝试备用接口
        if not playlists:
            logger.info("主接口未返回数据，尝试备用接口...")
            req_data_alt = {
                "req_0": {
                    "module": "musichall.song_list_server",
                    "method": "GetSongList",
                    "param": {
                        "uin": uin,
                        "start": 0,
                        "size": 200,
                    },
                }
            }
            data_alt = self._post_request(U_URL, req_data_alt)
            playlists = self._parse_playlist_list_alt(data_alt)

        return playlists

    def _parse_playlist_list(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """解析主接口返回的歌单列表"""
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

    def _parse_playlist_list_alt(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """解析备用接口返回的歌单列表"""
        try:
            disslist = data["req_0"]["data"]["v_playlist"]
        except (KeyError, TypeError):
            disslist = []

        playlists = []
        for item in disslist:
            playlists.append({
                "id": str(item.get("tid", item.get("dissid", ""))),
                "name": item.get("diss_name", item.get("title", "未知歌单")),
                "song_count": item.get("song_cnt", item.get("subtitle", 0)),
            })
        return playlists

    def fetch_all_playlists(
        self,
        qq_number: str,
        on_progress: Any = None,
    ) -> list[Playlist]:
        """一次性获取用户所有歌单的详细信息

        先获取歌单列表，再逐个拉取歌单详情（含歌曲）。

        Args:
            qq_number: 用户 QQ 号
            on_progress: 可选的进度回调 fn(current, total, playlist_name)

        Returns:
            所有歌单的 Playlist 列表
        """
        playlist_infos = self.get_user_playlists(qq_number)
        if not playlist_infos:
            logger.warning(f"未获取到 QQ {qq_number} 的歌单")
            return []

        total = len(playlist_infos)
        logger.info(f"共发现 {total} 个歌单，开始逐个获取详情...")

        playlists: list[Playlist] = []
        for i, info in enumerate(playlist_infos, 1):
            pid = info["id"]
            name = info["name"]
            if on_progress:
                on_progress(i, total, name)
            try:
                pl = self.get_playlist_detail(int(pid))
                playlists.append(pl)
                logger.info(f"[{i}/{total}] ✓ {pl.name} ({pl.song_count} 首)")
            except Exception as e:
                logger.error(f"[{i}/{total}] ✗ {name} (id={pid}): {e}")

        logger.info(f"获取完成: 成功 {len(playlists)}/{total} 个歌单")
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

    # QQ音乐流派 ID → 名称映射
    GENRE_MAP: dict[int, str] = {
        1: "流行", 2: "摇滚", 3: "民谣", 4: "电子", 5: "爵士",
        6: "古典", 7: "R&B", 8: "说唱", 9: "轻音乐", 10: "乡村",
        11: "蓝调", 14: "世界音乐", 15: "拉丁", 19: "新世纪",
        20: "古风", 21: "后摇", 22: "Bossa Nova",
    }

    # QQ音乐语言 ID → 名称映射
    LANGUAGE_MAP: dict[int, str] = {
        0: "华语", 1: "英语", 2: "韩语", 3: "日语", 4: "粤语",
        5: "其他", 6: "纯音乐",
    }

    @staticmethod
    def _parse_song(raw: dict[str, Any]) -> Song:
        """解析原始歌曲数据为 Song 模型"""
        singers = raw.get("singer", [])
        artist_names = [s.get("name", "未知") for s in singers]

        album_info = raw.get("album", {})

        # genre 和 language 可能是 int ID，转为字符串名称
        genre_raw = raw.get("genre", "")
        if isinstance(genre_raw, int):
            genre_raw = QQMusicAPI.GENRE_MAP.get(genre_raw, str(genre_raw))
        
        language_raw = raw.get("language", "")
        if isinstance(language_raw, int):
            language_raw = QQMusicAPI.LANGUAGE_MAP.get(language_raw, str(language_raw))

        return Song(
            mid=str(raw.get("mid", raw.get("songmid", ""))),
            name=raw.get("name", raw.get("songname", "未知")),
            artists=artist_names,
            album=album_info.get("name", raw.get("albumname", "")),
            duration=raw.get("interval", 0),
            genre=str(genre_raw),
            language=str(language_raw),
        )
