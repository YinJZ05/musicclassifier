"""QQ 扫码登录

通过 QQ 的扫码登录机制获取 QQ 音乐的认证 Cookie。
流程：生成二维码 → 用户用手机 QQ 扫码 → 获取认证 Cookie
"""

from __future__ import annotations

import re
import time
from urllib.parse import unquote
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


def _parse_ptui_cb(text: str) -> tuple[str, str, str, str] | None:
    """解析 ptuiCB 回调文本，兼容多种返回格式。"""
    m = re.search(r"ptuiCB\((?P<body>.*)\)\s*;?", text, re.S)
    if not m:
        return None

    body = m.group("body")
    # 常见格式：ptuiCB('66','0','','0','msg',...)
    quoted = re.findall(r"['\"]([^'\"]*)['\"]", body)
    if quoted:
        code = quoted[0] if len(quoted) > 0 else ""
        sub = quoted[1] if len(quoted) > 1 else ""
        url = quoted[2] if len(quoted) > 2 else ""
        # 第 5 个字段通常是消息，缺失时降级到第 4 个字段
        msg = quoted[4] if len(quoted) > 4 else (quoted[3] if len(quoted) > 3 else "")
        return code, sub, url, msg

    # 兜底：至少提取 code
    m2 = re.search(r"^\s*['\"]?(?P<code>\d+)", body)
    if m2:
        return m2.group("code"), "", "", ""

    return None


def _decode_qr_response(content: bytes) -> str:
    """尝试按多种编码解码 QQ 轮询响应。"""
    if not content:
        return ""

    # QQ 返回通常为 utf-8 或 gb18030/gbk 编码的 JS 文本
    for encoding in ("utf-8", "gb18030", "gbk", "latin-1"):
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "ptuiCB" in text or "二维码" in text or "登录" in text:
            return text

    return content.decode("utf-8", errors="ignore")


def _normalize_url(raw: str) -> str:
    """归一化回调中的 URL（处理转义斜杠和 URL 编码）。"""
    if not raw:
        return ""

    s = raw.strip()
    s = s.replace("\\/", "/")
    if s.startswith("http://") or s.startswith("https://"):
        return s

    decoded = unquote(s)
    decoded = decoded.replace("\\/", "/")
    if decoded.startswith("http://") or decoded.startswith("https://"):
        return decoded

    return ""


def _extract_redirect_url(text: str, parsed_url: str) -> str:
    """从回调文本中提取跳转 URL。"""
    url = _normalize_url(parsed_url)
    if url:
        return url

    # 先从所有引号字段中尝试提取
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", text)
    for item in quoted:
        url = _normalize_url(item)
        if url:
            return url

    # 兜底匹配普通/转义 URL
    patterns = [
        r"https?://[^'\"\s]+",
        r"https?:\\/\\/[^'\"\s]+",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            url = _normalize_url(m.group(0))
            if url:
                return url

    return ""


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
    REDIRECT_URL = "https://graph.qq.com/oauth2.0/login_jump"

    XLOGIN_URL = "https://xui.ptlogin2.qq.com/cgi-bin/xlogin"
    QRSHOW_URL = "https://ssl.ptlogin2.qq.com/ptqrshow"
    QRLOGIN_URL = "https://ssl.ptlogin2.qq.com/ptqrlogin"
    QRLOGIN_URL_ALT = "https://ptlogin2.qq.com/ptqrlogin"

    LOGIN_LABEL = "qq"

    @staticmethod
    def _pick_cookie_value(jar: Any, name: str, domain_hint: str = "") -> str:
        """从 cookie jar 选择更可靠的同名 cookie。"""
        candidates: list[tuple[str, str]] = []
        for c in jar:
            if c.name != name:
                continue
            domain = (c.domain or "").lower()
            candidates.append((domain, c.value))

        if not candidates:
            return ""

        if domain_hint:
            domain_hint = domain_hint.lower()
            hinted = [v for d, v in candidates if domain_hint in d]
            if hinted:
                return hinted[-1]

        return candidates[-1][1]

    def __init__(self) -> None:
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=30,
            headers={"User-Agent": _UA, "Referer": "https://xui.ptlogin2.qq.com/"},
        )
        self._qrsig: str = ""
        self._login_sig: str = ""
        self._xlogin_referer: str = "https://xui.ptlogin2.qq.com/"

    # ────────── Step 1: 获取二维码 ──────────

    def get_qrcode(self) -> bytes:
        """获取登录二维码图片（PNG）

        Returns:
            二维码图片的 bytes 数据
        """
        # 先访问 xlogin 获取初始 cookie
        xlogin_params = self._build_xlogin_params()

        xlogin_resp = self._client.get(
            self.XLOGIN_URL,
            params=xlogin_params,
        )

        self._xlogin_referer = str(xlogin_resp.request.url)
        self._login_sig = xlogin_resp.cookies.get("pt_login_sig", "") or self._pick_cookie_value(
            self._client.cookies.jar,
            "pt_login_sig",
            "ptlogin2.qq.com",
        )

        # 获取二维码图片
        resp = self._client.get(self.QRSHOW_URL, params=self._build_qrshow_params())

        # 优先从本次响应里提取 qrsig，再按域名从会话 cookie 选择。
        self._qrsig = resp.cookies.get("qrsig", "")
        if not self._qrsig:
            self._qrsig = self._pick_cookie_value(
                self._client.cookies.jar,
                "qrsig",
                "ptlogin2.qq.com",
            )

        if not self._qrsig:
            # 最后兜底：从 cookie jar 取最后一个同名项，避免误取历史值。
            for cookie in reversed(list(self._client.cookies.jar)):
                if cookie.name == "qrsig":
                    self._qrsig = cookie.value
                    break

        if not self._qrsig:
            raise RuntimeError("无法获取 qrsig，二维码生成失败")

        logger.debug(
            f"获取到 qrsig: {self._qrsig[:20]}... (len={len(self._qrsig)}), login_sig={'yes' if self._login_sig else 'no'}"
        )
        return resp.content

    def _build_qrshow_params(self) -> dict[str, str]:
        """构建 ptqrshow 参数，子类可覆盖。"""
        return {
            "appid": self.APPID,
            "e": "2",
            "l": "M",
            "s": "3",
            "d": "72",
            "v": "4",
            "t": str(time.time()),
            "daid": self.DAID,
            "pt_3rd_aid": self.PT_3RD_AID,
            "pt_qr_app": "0",
        }

    def _build_xlogin_params(self) -> dict[str, str]:
        """构建 xlogin 参数，子类可覆盖。"""
        return {
            "appid": self.APPID,
            "daid": self.DAID,
            "pt_3rd_aid": self.PT_3RD_AID,
            "u1": self.REDIRECT_URL,
            "style": "33",
            "s_url": self.REDIRECT_URL,
            "target": "self",
            "pt_qr_app": "0",
            "hide_title_bar": "1",
            "hide_border": "1",
            "self_regurl": "https://qzs.qq.com/open/mobile/reg/index.html",
            "pt_uistyle": "40",
            "low_login": "0",
            "qlogin_auto_login": "1",
        }

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

        params = {
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
            # ptqrlogin 常见参数名为 aid；部分网关兼容 appid。
            "aid": self.APPID,
            "appid": self.APPID,
            "daid": self.DAID,
            "pt_3rd_aid": self.PT_3RD_AID,
        }
        if self._login_sig:
            params["login_sig"] = self._login_sig

        # 第一次：标准轮询
        resp = self._client.get(self.QRLOGIN_URL, params=params, follow_redirects=False)

        # 遇到 403 时使用更强兼容请求重试：显式带 qrsig 与 xlogin Referer
        if resp.status_code == 403:
            logger.debug("轮询被 403 拒绝，启用兼容重试")
            retry_headers = {
                "Referer": self._xlogin_referer,
                "Cookie": f"qrsig={self._qrsig}",
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            resp = self._client.get(
                self.QRLOGIN_URL,
                params=params,
                headers=retry_headers,
                follow_redirects=False,
            )

        # 再次 403 切备用域名
        if resp.status_code == 403:
            resp = self._client.get(
                self.QRLOGIN_URL_ALT,
                params=params,
                headers={
                    "Referer": self._xlogin_referer,
                    "Cookie": f"qrsig={self._qrsig}",
                    "Accept": "*/*",
                },
                follow_redirects=False,
            )

        logger.debug(
            f"轮询响应: status={resp.status_code}, location={'yes' if resp.headers.get('Location') else 'no'}, bytes={len(resp.content)}"
        )

        if resp.status_code == 403:
            return LOGIN_STATUS_ERROR, "二维码轮询被拒绝(403)，请刷新二维码后重试"

        text = _decode_qr_response(resp.content)

        if not text.strip():
            location = resp.headers.get("Location", "")
            if location:
                return LOGIN_STATUS_SCANNED, "已扫码，等待 QQ 确认（重定向中）"
            return LOGIN_STATUS_WAITING, "等待扫码..."

        parsed = _parse_ptui_cb(text)
        if not parsed:
            location = resp.headers.get("Location", "")
            if location:
                cookie_str = self._follow_redirect(location)
                if cookie_str:
                    return LOGIN_STATUS_SUCCESS, cookie_str
            preview = " ".join(text.split())[:160]
            return LOGIN_STATUS_ERROR, f"无法解析登录状态，响应片段: {preview}"

        code, _sub, redirect_url, msg = parsed
        msg = msg or ""
        logger.debug(f"二维码轮询状态 code={code} msg={msg[:80]}")

        if code == "0" or "登录成功" in msg:
            jump_url = _extract_redirect_url(text, redirect_url)
            if jump_url:
                cookie_str = self._follow_redirect(jump_url)
                return LOGIN_STATUS_SUCCESS, cookie_str
            return LOGIN_STATUS_ERROR, "登录成功但未获取到跳转链接"

        if code == "65":
            return LOGIN_STATUS_EXPIRED, "二维码已过期，请刷新"

        if code in {"67", "68"}:
            return LOGIN_STATUS_SCANNED, msg or "已扫码，请在手机上确认"

        if code == "66":
            return LOGIN_STATUS_WAITING, msg or "等待扫码..."

        if "扫码" in msg or "确认" in msg:
            return LOGIN_STATUS_SCANNED, msg
        if "过期" in msg or "失效" in msg:
            return LOGIN_STATUS_EXPIRED, msg

        preview = " ".join(text.split())[:120]
        return LOGIN_STATUS_ERROR, f"登录状态异常(code={code}): {msg or preview}"

    # ────────── Step 3: 跟随重定向收集 Cookie ──────────

    def _follow_redirect(self, url: str) -> str:
        """跟随登录重定向，收集所有 Cookie 并拼成字符串

        流程：
        1. 跟随 ptlogin2 重定向 → 获取 skey/p_skey/uin 等
        2. 访问 QQ 音乐首页 → 获取音乐相关 cookie
        3. 拼接所有 cookie
        """
        logger.info("登录成功，正在获取认证信息...")

        # Step 1: 跟随 QQ 登录重定向链
        self._client.get(url)

        # Step 2: 访问 QQ 音乐主站获取音乐相关 cookie
        try:
            self._client.get("https://y.qq.com/", headers={"Referer": "https://y.qq.com/"})
        except Exception:
            pass

        try:
            self._client.get(
                "https://u.y.qq.com/cgi-bin/musicu.fcg",
                params={"format": "json", "data": '{"req_0":{"module":"vkey.GetVkeyServer","method":"CgiGetVkey","param":{}}}'},
                headers={"Referer": "https://y.qq.com/"},
            )
        except Exception:
            pass

        # 收集全部 cookie (合并所有域)
        cookies: dict[str, str] = {}
        for cookie in self._client.cookies.jar:
            # 优先保留后设置的（覆盖早期的同名cookie）
            cookies[cookie.name] = cookie.value

        logger.info(f"获取到 {len(cookies)} 个 cookie: {list(cookies.keys())}")

        # 检查关键 cookie
        has_uin = any(k in cookies for k in ("uin", "wxuin", "o_cookie"))
        has_key = any(k in cookies for k in ("p_skey", "skey", "qqmusic_key", "qm_keyst"))
        if not has_uin:
            logger.warning("未获取到 uin cookie，API 调用可能受限")
        if not has_key:
            logger.warning("未获取到认证 key cookie，API 调用可能受限")

        # 拼成完整 cookie 字符串
        return "; ".join(f"{k}={v}" for k, v in cookies.items())

    # ────────── 清理 ──────────

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "QQQRLogin":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class WechatQRLogin(QQQRLogin):
    """微信扫码登录器。

    复用同一套 ptlogin 链路，使用微信登录参数请求二维码。
    """

    LOGIN_LABEL = "wechat"

    def _build_xlogin_params(self) -> dict[str, str]:
        params = super()._build_xlogin_params()
        # pt_login_type=3 为微信扫码登录模式
        params["pt_login_type"] = "3"
        params["pt_qr_app"] = "1"
        return params

    def _build_qrshow_params(self) -> dict[str, str]:
        params = super()._build_qrshow_params()
        params["pt_qr_app"] = "1"
        return params
