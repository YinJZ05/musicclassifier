"""会话持久化

将登录获取的 Cookie 保存到本地文件，下次启动自动加载。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
from loguru import logger

DEFAULT_SESSION_DIR = Path.home() / ".musicclassifier"
DEFAULT_SESSION_PATH = DEFAULT_SESSION_DIR / "session.json"


def save_session(
    cookie: str,
    login_type: str = "qq",
    path: Path | str = DEFAULT_SESSION_PATH,
) -> Path:
    """保存会话

    Args:
        cookie: Cookie 字符串
        login_type: 登录方式
        path: 保存路径

    Returns:
        保存的文件路径
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "cookie": cookie,
        "login_type": login_type,
        "saved_at": time.time(),
        "saved_at_str": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"会话已保存到 {p}")
    return p


def load_session(path: Path | str = DEFAULT_SESSION_PATH) -> dict | None:
    """加载已保存的会话

    Returns:
        包含 cookie, login_type, saved_at 的字典，不存在返回 None
    """
    p = Path(path)
    if not p.exists():
        return None

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        age_hours = (time.time() - data.get("saved_at", 0)) / 3600
        logger.info(
            f"加载会话: {data.get('login_type', '?')} 登录, "
            f"保存于 {data.get('saved_at_str', '?')} ({age_hours:.1f}h 前)"
        )
        return data
    except Exception as e:
        logger.warning(f"加载会话失败: {e}")
        return None


def delete_session(path: Path | str = DEFAULT_SESSION_PATH) -> None:
    """删除已保存的会话"""
    p = Path(path)
    if p.exists():
        p.unlink()
        logger.info("会话已删除")


def check_cookie_valid(cookie: str) -> bool:
    """检查 Cookie 是否仍然有效

    通过调用一个轻量 API 来验证。

    Args:
        cookie: Cookie 字符串

    Returns:
        True 表示有效
    """
    if not cookie:
        return False

    try:
        resp = httpx.post(
            "https://u.y.qq.com/cgi-bin/musicu.fcg",
            json={
                "req_0": {
                    "module": "QQConnectLogin.LoginServer",
                    "method": "QQLogin_Check",
                    "param": {},
                }
            },
            headers={
                "Cookie": cookie.strip().replace("\n", "").replace("\r", ""),
                "Referer": "https://y.qq.com/",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=10,
        )
        data = resp.json()
        # code == 0 表示登录态有效
        code = data.get("req_0", {}).get("data", {}).get("code", -1)
        return code == 0
    except Exception:
        return False
