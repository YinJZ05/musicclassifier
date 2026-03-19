"""
MusicClassifier Web UI

简化流程：登录 → 自动加载歌单 → 选择歌单操作
启动方式: streamlit run src/musicclassifier/ui/app.py
"""

from __future__ import annotations

import time

import streamlit as st

from musicclassifier.utils.helpers import extract_playlist_ids

st.set_page_config(
    page_title="🎵 QQ音乐歌单处理器",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ══════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════

def get_api(cookie: str):
    """创建 API 客户端"""
    from musicclassifier.api.qq_music import QQMusicAPI
    return QQMusicAPI(cookie=cookie, timeout=30, request_interval=1.0)


def songs_to_df(songs):
    """歌曲列表转 DataFrame"""
    import pandas as pd
    return pd.DataFrame([
        {
            "歌名": s.name,
            "歌手": s.artist_str,
            "专辑": s.album,
            "时长": s.duration_str,
            "流派": s.genre,
            "语言": s.language,
        }
        for s in songs
    ])


def auto_load_playlists(cookie: str):
    """登录后自动加载歌单列表"""
    api = get_api(cookie)
    uin = api.extract_uin_from_cookie()
    if uin:
        return api.get_user_playlists(uin)
    return []


# ══════════════════════════════════════════════════
# 页面 1: 登录
# ══════════════════════════════════════════════════

def show_login_page():
    st.markdown(
        "<h1 style='text-align:center'>🎵 QQ音乐歌单处理器</h1>"
        "<p style='text-align:center;color:gray'>登录后自动读取你的所有歌单</p>",
        unsafe_allow_html=True,
    )

    st.write("")

    # ── 尝试自动恢复会话 ──
    from musicclassifier.auth.session import load_session

    saved = load_session()
    if saved and saved.get("cookie"):
        age_hours = (time.time() - saved.get("saved_at", 0)) / 3600
        st.info(
            f"🔄 发现已保存的登录信息 "
            f"({saved.get('login_type', '?')}登录, {age_hours:.0f}小时前)"
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ 使用已保存的登录", type="primary", use_container_width=True):
                _do_login(saved["cookie"], saved.get("login_type", "qq"))
                return
        with col2:
            if st.button("🔄 重新登录", use_container_width=True):
                from musicclassifier.auth.session import delete_session
                delete_session()
                st.rerun()
        st.divider()

    # ── 四种登录方式 ──
    tab_qq, tab_wechat, tab_cookie, tab_public = st.tabs([
        "🐧 QQ 扫码登录",
        "💬 微信登录QQ音乐",
        "📋 粘贴 Cookie",
        "🔗 公开歌单（免登录）",
    ])

    # ──── Tab 1: QQ 扫码 ────
    with tab_qq:
        st.markdown("**用手机 QQ 扫码，一键登录**")
        st.caption("适合 QQ 用户，扫码后自动获取认证")

        if st.button("📱 生成二维码", type="primary", key="gen_qr", use_container_width=True):
            _do_qr_login("qq")

    # ──── Tab 2: 微信扫码 ────
    with tab_wechat:
        st.markdown("**用手机微信扫码登录 QQ 音乐**")
        st.caption("将生成微信扫码通道二维码，请使用微信扫描（不要用QQ扫描）")

        if st.button("💬 生成微信二维码", type="primary", key="gen_qr_wechat", use_container_width=True):
            _do_qr_login("wechat")

    # ──── Tab 3: 粘贴 Cookie ────
    with tab_cookie:
        st.markdown("**粘贴 QQ音乐 Cookie（QQ / 微信登录均支持）**")
        st.caption(
            "浏览器登录 [y.qq.com](https://y.qq.com) → F12 → Network → "
            "找任意 `musicu.fcg` 请求 → 复制 Cookie"
        )
        cookie_login_type = st.radio(
            "登录方式",
            ["qq", "wechat"],
            format_func=lambda x: "QQ" if x == "qq" else "微信",
            horizontal=True,
            key="cookie_login_type",
        )
        cookie_input = st.text_area(
            "Cookie",
            height=120,
            placeholder="粘贴完整的 Cookie 内容...",
            label_visibility="collapsed",
        )
        if st.button("🔑 登录", type="primary", key="cookie_login", use_container_width=True):
            if cookie_input.strip():
                _do_login(cookie_input.strip(), cookie_login_type)
            else:
                st.warning("请粘贴 Cookie")

    # ──── Tab 4: 公开歌单 ────
    with tab_public:
        st.markdown("**无需登录，直接粘贴公开歌单 ID / 链接 / 分享文本**")
        st.caption("支持一次输入多个歌单（每行一个或一段分享文案）")
        url_input = st.text_area(
            "歌单 ID / 链接 / 分享文案",
            height=120,
            placeholder=(
                "例:\n"
                "8032497163\n"
                "https://y.qq.com/n/ryqq/playlist/8032497163\n"
                "分享文案里包含数字 ID 也可识别"
            ),
        )
        if st.button("📥 读取歌单", type="primary", key="public_fetch", use_container_width=True):
            if url_input.strip():
                _fetch_playlists_from_text("", url_input.strip(), is_public=True)
            else:
                st.warning("请输入歌单 ID 或链接")


def _do_login(cookie: str, login_type: str):
    """执行登录：保存会话 → 切到主页 → 在主页自动加载歌单"""
    from musicclassifier.auth.session import save_session

    save_session(cookie, login_type)
    st.session_state["cookie"] = cookie
    st.session_state["login_type"] = login_type
    st.session_state["logged_in"] = True
    st.session_state["playlist_infos"] = st.session_state.get("playlist_infos", [])
    st.session_state["pending_auto_load"] = True

    # 检查 Cookie 内容
    api = get_api(cookie)
    uin = api.extract_uin_from_cookie()
    login_info = api.detect_login_type()
    st.session_state["detected_uin"] = uin
    st.session_state["detected_login"] = login_info

    if not uin:
        # UIN 提取失败，不阻塞，进主页让用户手动输入
        st.session_state["playlist_infos"] = []
        st.session_state["pending_auto_load"] = False
        st.session_state["login_error"] = (
            "Cookie 中未找到用户标识 (uin)，可能 Cookie 不完整。\n"
            "请在下一页手动输入 QQ 号来加载歌单。"
        )
        st.rerun()
        return

    st.rerun()


def _do_qr_login(login_mode: str = "qq"):
    """扫码登录流程（QQ / 微信）"""
    from musicclassifier.auth.qq_login import (
        QQQRLogin,
        WechatQRLogin,
        LOGIN_STATUS_SUCCESS,
        LOGIN_STATUS_EXPIRED,
        LOGIN_STATUS_SCANNED,
        LOGIN_STATUS_ERROR,
    )

    try:
        login = WechatQRLogin() if login_mode == "wechat" else QQQRLogin()
        qr_bytes = login.get_qrcode()
    except Exception as e:
        st.error(f"二维码生成失败: {e}")
        return

    # 显示二维码
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        caption = "用手机微信扫描此二维码" if login_mode == "wechat" else "用手机 QQ 扫描此二维码"
        st.image(qr_bytes, caption=caption, width=280)

    # 轮询登录状态
    status_box = st.empty()
    progress = st.progress(0)

    max_wait = 240  # 秒
    interval = 2.0
    steps = int(max_wait / interval)

    for i in range(steps):
        progress.progress((i + 1) / steps)
        status, message = login.check_status()

        if status == LOGIN_STATUS_SUCCESS:
            status_box.success("✅ 登录成功！")
            progress.empty()
            login.close()
            _do_login(message, login_mode)
            return

        elif status == LOGIN_STATUS_EXPIRED:
            status_box.error("⏰ 二维码已过期，请重新生成")
            progress.empty()
            login.close()
            return

        elif status == LOGIN_STATUS_SCANNED:
            status_box.info(f"📱 {message}")
        elif status == LOGIN_STATUS_ERROR:
            status_box.error(f"❌ 登录状态异常: {message}")
            progress.empty()
            login.close()
            return
        else:
            status_box.info(f"⏳ {message}")

        time.sleep(interval)

    status_box.warning("⏰ 登录超时，请重试")
    progress.empty()
    login.close()


# ══════════════════════════════════════════════════
# 页面 2: 歌单列表 + 操作
# ══════════════════════════════════════════════════

def show_main_page():
    import pandas as pd

    cookie = st.session_state.get("cookie", "")
    login_type = st.session_state.get("login_type", "?")

    # ── 顶栏 ──
    col_title, col_logout = st.columns([5, 1])
    with col_title:
        label = {
            "qq": "🐧 QQ",
            "wechat": "💬 微信",
            "cookie": "🔑 Cookie",
            "public": "🔗 公开",
        }.get(login_type, "?")
        st.title(f"🎵 我的歌单  {label}")
    with col_logout:
        st.write("")
        st.write("")
        if st.button("🚪 退出登录"):
            from musicclassifier.auth.session import delete_session
            delete_session()
            for key in [
                "logged_in", "cookie", "login_type",
                "playlist_infos", "all_playlists",
            ]:
                st.session_state.pop(key, None)
            st.rerun()

    st.divider()

    # ── 显示登录状态信息 ──
    login_error = st.session_state.pop("login_error", None)
    detected_uin = st.session_state.get("detected_uin", "")

    # 登录后首次进入主页时，自动加载一次歌单列表，避免在登录按钮动作里卡住页面。
    should_auto_load = (
        st.session_state.get("pending_auto_load", False)
        and login_type != "public"
        and bool(cookie)
    )
    if should_auto_load:
        with st.spinner("正在自动加载歌单列表..."):
            try:
                playlists = auto_load_playlists(cookie)
                st.session_state["playlist_infos"] = playlists
                if not playlists and detected_uin:
                    st.session_state["login_error"] = (
                        f"已识别用户 {detected_uin}，但未获取到歌单列表。\n"
                        "可能 Cookie 已过期或接口返回为空。"
                    )
            except Exception as e:
                st.session_state["playlist_infos"] = []
                st.session_state["login_error"] = f"歌单列表加载失败: {e}"
            finally:
                st.session_state["pending_auto_load"] = False
        st.rerun()

    if login_error:
        st.warning(f"⚠️ {login_error}")

    if detected_uin:
        st.caption(f"👤 当前用户: {detected_uin}")

    playlist_infos = st.session_state.get("playlist_infos", [])

    # ── 如果有歌单列表但尚未加载详情 ──
    if playlist_infos and "all_playlists" not in st.session_state:
        st.subheader(f"📋 共 {len(playlist_infos)} 个歌单")

        df = pd.DataFrame(playlist_infos)
        df.index = range(1, len(df) + 1)
        if list(df.columns) == ["id", "name", "song_count"]:
            df.columns = ["歌单 ID", "歌单名称", "歌曲数"]
        st.dataframe(df, use_container_width=True, height=min(400, 40 + len(df) * 35))

        col1, col2 = st.columns(2)
        with col1:
            if st.button("📦 读取全部歌单详情", type="primary", use_container_width=True):
                _fetch_all_playlists(cookie, playlist_infos)
        with col2:
            selected_id = st.text_input("或输入歌单 ID / 链接读取", placeholder="歌单 ID 或链接")
            if selected_id:
                if st.button("📥 读取", use_container_width=True):
                    _fetch_playlists_from_text(cookie, selected_id, is_public=False)

    # ── 已加载详情后，进入操作面板 ──
    elif "all_playlists" in st.session_state:
        show_operations_panel()

    # ── 没有歌单列表：提供手动输入和重试 ──
    else:
        st.info("📝 未自动获取到歌单列表，你可以：")

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("**方式 1：输入 QQ 号手动加载**")
            manual_uin = st.text_input(
                "QQ 号", placeholder="输入你的 QQ 号", key="manual_uin",
            )
            if st.button("📋 加载歌单列表", type="primary", use_container_width=True, key="load_by_uin"):
                if manual_uin.strip():
                    _load_playlists_by_uin(cookie, manual_uin.strip())
                else:
                    st.warning("请输入 QQ 号")

        with col_b:
            st.markdown("**方式 2：粘贴歌单 ID / 链接 / 分享文本**")
            direct_id = st.text_area(
                "歌单 ID / 链接 / 分享文本",
                placeholder="支持一次输入多个歌单（每行一个）",
                key="direct_playlist_id",
                height=120,
            )
            if st.button("📥 读取歌单", type="primary", use_container_width=True, key="direct_fetch"):
                if direct_id.strip():
                    _fetch_playlists_from_text(cookie, direct_id.strip(), is_public=False)
                else:
                    st.warning("请输入歌单 ID")

        st.divider()
        if st.button("🔄 重新登录"):
            from musicclassifier.auth.session import delete_session
            delete_session()
            for key in ["logged_in", "cookie", "login_type", "playlist_infos",
                        "all_playlists", "detected_uin", "detected_login"]:
                st.session_state.pop(key, None)
            st.rerun()


def _load_playlists_by_uin(cookie: str, uin: str):
    """通过手动输入的 QQ 号加载歌单列表"""
    api = get_api(cookie)
    with st.spinner(f"正在加载 {uin} 的歌单..."):
        try:
            playlists = api.get_user_playlists(uin)
            if playlists:
                st.session_state["playlist_infos"] = playlists
                st.session_state["detected_uin"] = uin
                st.rerun()
            else:
                st.error(f"未获取到 {uin} 的歌单，请确认 QQ 号是否正确")
        except Exception as e:
            st.error(f"加载失败: {e}")


def _fetch_all_playlists(cookie: str, infos: list):
    """批量获取所有歌单详情"""
    api = get_api(cookie)
    progress = st.progress(0, text="开始读取...")
    playlists = []
    failed = []

    for i, info in enumerate(infos):
        pid = info.get("id") or info.get("歌单 ID")
        name = info.get("name") or info.get("歌单名称") or str(pid)
        progress.progress((i + 1) / len(infos), text=f"[{i + 1}/{len(infos)}] {name}")
        try:
            pl = api.get_playlist_detail(int(pid))
            playlists.append(pl)
        except Exception as e:
            failed.append(f"{name}: {e}")

    progress.empty()
    st.session_state["all_playlists"] = playlists

    st.success(f"✅ 成功读取 {len(playlists)}/{len(infos)} 个歌单")
    if failed:
        with st.expander(f"⚠️ {len(failed)} 个失败"):
            for f in failed:
                st.write(f"- {f}")

    st.rerun()


def _fetch_playlists_from_text(cookie: str, input_text: str, is_public: bool):
    """从输入文本中解析并读取一个或多个歌单。"""
    ids = extract_playlist_ids(input_text)
    if not ids:
        st.error("无法识别歌单 ID，请输入 ID、链接或分享文本")
        return

    api = get_api(cookie)
    playlists = []
    failed = []
    progress = st.progress(0, text="开始读取...")

    for i, pid in enumerate(ids):
        progress.progress((i + 1) / len(ids), text=f"[{i + 1}/{len(ids)}] 读取歌单 {pid}")
        try:
            playlists.append(api.get_playlist_detail(pid))
        except Exception as e:
            failed.append(f"{pid}: {e}")

    progress.empty()

    if not playlists:
        st.error("读取失败：未成功获取任何歌单")
        if failed:
            with st.expander(f"查看失败详情（{len(failed)}）"):
                for item in failed:
                    st.write(f"- {item}")
        return

    st.session_state["all_playlists"] = playlists
    st.session_state["playlist_infos"] = [
        {"id": p.id, "name": p.name, "song_count": p.song_count} for p in playlists
    ]

    if is_public:
        st.session_state["logged_in"] = True
        st.session_state["cookie"] = ""
        st.session_state["login_type"] = "public"

    st.success(f"✅ 成功读取 {len(playlists)}/{len(ids)} 个歌单")
    if failed:
        with st.expander(f"⚠️ {len(failed)} 个读取失败"):
            for item in failed:
                st.write(f"- {item}")
    st.rerun()


def show_operations_panel():
    import pandas as pd

    playlists = st.session_state.get("all_playlists", [])
    all_songs = []
    for pl in playlists:
        all_songs.extend(pl.songs)

    # 摘要
    col1, col2, col3 = st.columns(3)
    col1.metric("🎵 歌单数", len(playlists))
    col2.metric("🎶 总歌曲", len(all_songs))
    unique_artists: set[str] = set()
    for s in all_songs:
        unique_artists.update(s.artists)
    col3.metric("🎤 歌手数", len(unique_artists))

    st.divider()

    # 返回歌单列表
    if st.button("⬅️ 返回歌单列表"):
        st.session_state.pop("all_playlists", None)
        st.rerun()

    # 功能标签页
    tab_list, tab_classify, tab_dedup, tab_export, tab_stats = st.tabs([
        "📋 歌单内容",
        "🏷️ 分类",
        "🔄 去重",
        "📤 导出",
        "📊 统计",
    ])

    # ── 歌单内容 ──
    with tab_list:
        if len(playlists) > 1:
            names = [f"{pl.name} ({pl.song_count}首)" for pl in playlists]
            selected = st.selectbox("选择歌单", names)
            idx = names.index(selected)
            show_songs = playlists[idx].songs
            st.subheader(playlists[idx].name)
        else:
            show_songs = playlists[0].songs if playlists else []
            if playlists:
                st.subheader(playlists[0].name)

        if show_songs:
            df = songs_to_df(show_songs)
            st.dataframe(df, use_container_width=True, height=500)
        else:
            st.info("歌单为空")

    # ── 分类 ──
    with tab_classify:
        from musicclassifier.processors.classifier import SongClassifier

        classify_by = st.selectbox(
            "分类维度",
            ["genre", "language"],
            format_func=lambda x: "按流派" if x == "genre" else "按语言",
        )

        if st.button("🏷️ 开始分类", type="primary", key="do_classify"):
            classifier = SongClassifier()
            results = classifier.classify_songs(all_songs, by=classify_by)

            for r in results:
                with st.expander(f"**{r.category}** ({r.count} 首)"):
                    st.dataframe(songs_to_df(r.songs), use_container_width=True)

            try:
                import plotly.express as px

                chart_data = pd.DataFrame(
                    [{"分类": r.category, "数量": r.count} for r in results]
                )
                fig = px.pie(chart_data, values="数量", names="分类", title="分类分布")
                st.plotly_chart(fig, use_container_width=True)
            except ImportError:
                pass

    # ── 去重 ──
    with tab_dedup:
        from musicclassifier.processors.dedup import deduplicate

        if st.button("🔄 检测重复", type="primary", key="do_dedup"):
            unique, dups = deduplicate(all_songs)

            c1, c2, c3 = st.columns(3)
            c1.metric("原始", len(all_songs))
            c2.metric("唯一", len(unique))
            c3.metric("重复", len(dups), delta=f"-{len(dups)}", delta_color="inverse")

            if dups:
                st.subheader("重复歌曲")
                st.dataframe(songs_to_df(dups), use_container_width=True)
            else:
                st.success("✅ 没有重复歌曲")

    # ── 导出 ──
    with tab_export:
        import io
        import json as json_mod

        export_fmt = st.selectbox("格式", ["csv", "json", "excel"])

        if st.button("📤 生成下载", type="primary", key="do_export"):
            df = songs_to_df(all_songs)

            if export_fmt == "csv":
                data = df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "⬇️ 下载 CSV", data, "歌单导出.csv",
                    "text/csv", use_container_width=True,
                )
            elif export_fmt == "json":
                records = [s.model_dump() for s in all_songs]
                data = json_mod.dumps(records, ensure_ascii=False, indent=2).encode("utf-8")
                st.download_button(
                    "⬇️ 下载 JSON", data, "歌单导出.json",
                    "application/json", use_container_width=True,
                )
            elif export_fmt == "excel":
                buf = io.BytesIO()
                df.to_excel(buf, index=False, engine="openpyxl")
                st.download_button(
                    "⬇️ 下载 Excel", buf.getvalue(), "歌单导出.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

            st.info(f"共 {len(all_songs)} 首歌曲")

    # ── 统计 ──
    with tab_stats:
        total_seconds = sum(s.duration for s in all_songs)
        h, rem = divmod(total_seconds, 3600)
        m, sec = divmod(rem, 60)

        artist_count: dict[str, int] = {}
        for song in all_songs:
            for a in song.artists:
                artist_count[a] = artist_count.get(a, 0) + 1

        c1, c2, c3 = st.columns(3)
        c1.metric("🎵 歌曲", len(all_songs))
        c2.metric("⏱️ 总时长", f"{h}h{m}m{sec}s")
        c3.metric("🎤 歌手", len(artist_count))

        try:
            import plotly.express as px

            # Top 歌手
            top = sorted(artist_count.items(), key=lambda x: x[1], reverse=True)[:20]
            fig = px.bar(
                pd.DataFrame(top, columns=["歌手", "歌曲数"]),
                x="歌手", y="歌曲数", title="Top 歌手", color="歌曲数",
            )
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

            # 时长分布
            durs = [s.duration for s in all_songs if s.duration > 0]
            if durs:
                fig2 = px.histogram(
                    pd.DataFrame({"秒": durs}), x="秒", nbins=30, title="时长分布",
                )
                st.plotly_chart(fig2, use_container_width=True)

            # 各歌单歌曲数
            if len(playlists) > 1:
                pl_data = pd.DataFrame(
                    [{"歌单": p.name, "歌曲数": p.song_count} for p in playlists]
                )
                fig3 = px.bar(
                    pl_data.sort_values("歌曲数", ascending=True),
                    x="歌曲数", y="歌单", orientation="h",
                    title="各歌单规模", color="歌曲数",
                )
                fig3.update_layout(height=max(400, len(playlists) * 30))
                st.plotly_chart(fig3, use_container_width=True)
        except ImportError:
            st.info("安装 plotly 可查看图表: pip install plotly")


# ══════════════════════════════════════════════════
# 路由
# ══════════════════════════════════════════════════

if st.session_state.get("logged_in"):
    show_main_page()
else:
    show_login_page()
