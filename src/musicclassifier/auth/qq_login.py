"""QQ 扫码登录

通过 QQ 的扫码登录机制获取 QQ 音乐的认证 Cookie。
流程：生成二维码 → 用户用手机 QQ 扫码 → 获取认证 Cookie
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx
from loguru import logger

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _hash33(s: str) -> int:
    """计算 ptqrtoken（QQ 登录专用哈希）"""
    h = 0
    for c in s:
        h += (h << 5) + ord(c)
    return h & 0x7FFFFFFF


# ────────────────────── 登录状态码 ──────────────────────

LOGIN_STATUS_WAITING = "waiting"       # 等待扫码
LOGIN_STATUS_SCANNED = "scanned"       # 已扫码，等待确认
LOGIN_STATUS_SUCCESS = "success"       # 登录成功
LOGIN_STATUS_EXPIRED = "expired"       # 二维码已过期
LOGIN_STATUS_ERROR = "error"           # 出错


class QQQRLogin:
    """QQ 扫码登录器"""

    APPID = "716027609"
    DAID = "383"
    PT_3RD_AID = "100497308"
    REDIRECT_URL = (
        "https://y.qq.com/portal/wx_redirect.html"
        "?login_type=1&surl=https://y.qq.com/"
    )

    XLOGIN_URL = "https://xui.ptlogin2.qq.com/cgi-bin/xlogin"
    QRSHOW_URL = "https://ssl.ptlogin2.qq.com/ptqrshow"
    QRLOGIN_URL = "https://ssl.ptlogin2.qq.com/ptqrlogin"

    def __init__(self) -> None:
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=30,
            headers={"User-Agent": _UA, "Referer": "https://xui.ptlogin2.qq.com/"},
        )
        self._qrsig: str = ""

    # ────────── Step 1: 获取二维码 ──────────

    def get_qrcode(self) -> bytes:
        """获取登录二维码图片（PNG）

        Returns:
            二维码图片的 bytes 数据
        """
        # 先访问 xlogin 获取初始 cookie
        self._client.get(
            self.XLOGIN_URL,
            params={
                "appid": self.APPID,
                "daid": self.DAID,
                "pt_3rd_aid": self.PT_3RD_AID,
                "u1": self.REDIRECT_URL,
                "style": "33",
                "s_url": "https://y.qq.com/",
            },
        )

        # 获取二维码图片
        resp = self._client.get(
            self.QRSHOW_URL,
            params={
                "appid": self.APPID,
                "e": "2",
                "l": "M",
                "s": "3",
                "d": "72",
                "v": "4",
                "t": str(time.time()),
                "daid": self.DAID,
                "pt_3rd_aid": self.PT_3RD_AID,
            },
        )

        # 提取 qrsig
        self._qrsig = ""
        for cookie in self._client.cookies.jar:
            if cookie.name == "qrsig":
                self._qrsig = cookie.value
                break

        if not self._qrsig:
            raise RuntimeError("无法获取 qrsig，二维码生成失败")

        logger.debug(f"获取到 qrsig: {self._qrsig[:20]}...")
        return resp.content

    # ────────── Step 2: 检查一次登录状态 ──────────

    def check_status(self) -> tuple[str, str]:
        """检查一次登录状态（非阻塞）

        Returns:
            (status, message)
            status 为 LOGIN_STATUS_* 常量之一
        """
        if not self._qrsig:
            return LOGIN_STATUS_ERROR, "请先调用 get_qrcode()"

        ptqrtoken = _hash33(self._qrsig)

        resp = self._client.get(
            self.QRLOGIN_URL,
            params={
                "u1": self.REDIRECT_URL,
                "ptqrtoken": str(ptqrtoken),
                "ptredirect": "0",
                "h": "1",
                "t": "1",
                "g": "1",
                "from_ui": "1",
                "ptlang": "2052",
                "action": f"0-0-{int(time.time() * 1000)}",
                "js_ver": "24112817",
                "js_type": "1",
                "pt_uistyle": "40",
                "appid": self.APPID,
                "daid": self.DAID,
                "pt_3rd_aid": self.PT_3RD_AID,
            },
        )

        text = resp.text

        # 解析 ptuiCB 返回值
        if "ptuiCB('0'" in text or "登录成功" in text:
            match = re.search(r"ptuiCB\('0','0','(https?://[^']+)'", text)
            if match:
                redirect_url = match.group(1)
                cookie_str = self._follow_redirect(redirect_url)
                return LOGIN_STATUS_SUCCESS, cookie_str
            return LOGIN_STATUS_ERROR, "登录成功但无法提取认证信息"

        if "ptuiCB('65'" in text or "二维码已失效" in text:
            return LOGIN_STATUS_EXPIRED, "二维码已过期，请刷新"

        if "ptuiCB('67'" in text or "二维码认证中" in text:
            return LOGIN_STATUS_SCANNED, "已扫码，请在手机上确认"

        if "ptuiCB('66'" in text or "二维码未失效" in text:
            return LOGIN_STATUS_WAITING, "等待扫码..."

        return LOGIN_STATUS_ERROR, f"未知状态: {text[:100]}"

    # ────────── Step 3: 跟随重定向收集 Cookie ──────────

    def _follow_redirect(self, url: str) -> str:
        """跟随登录重定向，收集所有 Cookie 并拼成字符串"""
        logger.info("登录成功，正在获取认证信息...")

        self._client.get(url)

        # 收集全部 cookie
        cookies: dict[str, str] = {}
        for cookie in self._client.cookies.jar:
            cookies[cookie.name] = cookie.value

        logger.info(f"获取到 {len(cookies)} 个 cookie")

        # 拼成完整 cookie 字符串
        return "; ".join(f"{k}={v}" for k, v in cookies.items())

    # ────────── 清理 ──────────

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "QQQRLogin":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
