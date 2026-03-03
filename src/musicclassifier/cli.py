"""MusicClassifier CLI - 命令行入口

使用 Typer 构建的命令行界面。
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from musicclassifier.api.qq_music import QQMusicAPI
from musicclassifier.config import load_settings
from musicclassifier.processors.classifier import SongClassifier
from musicclassifier.processors.dedup import deduplicate
from musicclassifier.processors.exporter import export_songs
from musicclassifier.utils.helpers import setup_logging

app = typer.Typer(
    name="musicclassifier",
    help="🎵 QQ音乐歌单自动处理器",
    add_completion=False,
)
console = Console()


def _get_api(config_path: str | None) -> QQMusicAPI:
    """根据配置创建 API 客户端"""
    settings = load_settings(config_path)
    setup_logging(level=settings.logging.level, log_file=settings.logging.file)
    return QQMusicAPI(
        cookie=settings.qq_music.cookie,
        timeout=settings.qq_music.timeout,
        request_interval=settings.qq_music.request_interval,
        login_type=settings.qq_music.login_type,
    )


@app.command()
def fetch(
    playlist_id: int = typer.Argument(..., help="歌单 ID"),
    config: str | None = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """获取并展示歌单内容"""
    api = _get_api(config)

    console.print(f"[bold]正在获取歌单 {playlist_id} ...[/bold]")
    playlist = api.get_playlist_detail(playlist_id)

    console.print(f"\n[bold green]{playlist.name}[/bold green] ({playlist.song_count} 首)\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", width=5)
    table.add_column("歌名", min_width=20)
    table.add_column("歌手", min_width=15)
    table.add_column("专辑", min_width=15)
    table.add_column("时长", width=6)

    for i, song in enumerate(playlist.songs, 1):
        table.add_row(str(i), song.name, song.artist_str, song.album, song.duration_str)

    console.print(table)


@app.command(name="list")
def list_playlists(
    qq_number: str = typer.Option("", "--qq", "-q", help="用户标识（QQ号或留空自动从 Cookie 提取）"),
    config: str | None = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """列出用户所有歌单（支持 QQ 登录和微信登录）"""
    settings = load_settings(config)
    api = _get_api(config)

    qq = qq_number or settings.qq_music.qq_number or api.extract_uin_from_cookie()
    if not qq:
        console.print("[bold red]错误: 无法确定用户标识。请通过 --qq 参数传入，或确保 config.yaml / Cookie 中包含用户信息[/bold red]")
        raise typer.Exit(1)

    info = api.get_login_info()
    console.print(f"[dim]登录方式: {info['login_type_display']}  uin: {qq}[/dim]")
    console.print(f"[bold]正在获取歌单列表...[/bold]")
    playlists = api.get_user_playlists(qq)

    if not playlists:
        console.print("[yellow]未找到任何歌单[/yellow]")
        raise typer.Exit(0)

    table = Table(show_header=True, header_style="bold cyan", title=f"QQ {qq} 的歌单 ({len(playlists)} 个)")
    table.add_column("#", width=5)
    table.add_column("歌单 ID", min_width=12)
    table.add_column("歌单名称", min_width=20)
    table.add_column("歌曲数", width=8, justify="right")

    for i, pl in enumerate(playlists, 1):
        table.add_row(str(i), str(pl["id"]), pl["name"], str(pl["song_count"]))

    console.print(table)
    console.print("\n[dim]提示: 使用 fetch <歌单ID> 获取单个歌单详情，或 fetch-all 一次性获取所有歌单[/dim]")


@app.command(name="fetch-all")
def fetch_all(
    qq_number: str = typer.Option("", "--qq", "-q", help="QQ号（留空则使用配置文件中的）"),
    format: str = typer.Option("json", "--format", "-f", help="导出格式: csv / json / excel"),
    output_dir: str = typer.Option("", "--output-dir", "-o", help="输出目录（默认 output/）"),
    config: str | None = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """一次性获取用户所有歌单并导出（支持 QQ 登录和微信登录）"""
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

    settings = load_settings(config)
    api = _get_api(config)

    qq = qq_number or settings.qq_music.qq_number or api.extract_uin_from_cookie()
    if not qq:
        console.print("[bold red]错误: 无法确定用户标识。请通过 --qq 参数传入，或确保 config.yaml / Cookie 中包含用户信息[/bold red]")
        raise typer.Exit(1)

    info = api.get_login_info()
    console.print(f"[dim]登录方式: {info['login_type_display']}  uin: {qq}[/dim]")

    out_dir = Path(output_dir or settings.export.output_dir)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        # 第一步: 获取歌单列表
        task_list = progress.add_task("获取歌单列表...", total=1)
        playlist_infos = api.get_user_playlists(qq)
        progress.update(task_list, completed=1)

        if not playlist_infos:
            console.print("[yellow]未找到任何歌单[/yellow]")
            raise typer.Exit(0)

        total = len(playlist_infos)
        console.print(f"\n[bold]发现 {total} 个歌单，开始逐个获取...[/bold]\n")

        # 第二步: 逐个获取歌单详情
        task_fetch = progress.add_task("获取歌单详情", total=total)
        playlists = []
        failed = []
        for info in playlist_infos:
            pid = info["id"]
            name = info["name"]
            progress.update(task_fetch, description=f"获取: {name[:20]}")
            try:
                pl = api.get_playlist_detail(int(pid))
                playlists.append(pl)
            except Exception as e:
                failed.append((name, pid, str(e)))
            progress.advance(task_fetch)

    # 第三步: 导出
    console.print(f"\n[bold green]成功获取 {len(playlists)}/{total} 个歌单[/bold green]")
    if failed:
        console.print(f"[bold red]失败 {len(failed)} 个:[/bold red]")
        for name, pid, err in failed:
            console.print(f"  ✗ {name} (id={pid}): {err}")

    if playlists:
        console.print(f"\n[bold]正在导出到 {out_dir}/ ...[/bold]")
        all_songs = []
        for pl in playlists:
            # 每个歌单单独导出
            ext_map = {"csv": ".csv", "json": ".json", "excel": ".xlsx"}
            ext = ext_map.get(format, ".csv")
            safe_name = pl.name.replace("/", "_").replace("\\", "_").replace(":", "_")
            path = export_songs(pl.songs, out_dir / f"{safe_name}{ext}", fmt=format)
            console.print(f"  ✓ {pl.name} → {path}")
            all_songs.extend(pl.songs)

        # 汇总导出
        if len(playlists) > 1:
            summary_path = export_songs(all_songs, out_dir / f"_全部歌曲汇总{ext_map.get(format, '.csv')}", fmt=format)
            console.print(f"\n[bold cyan]  汇总文件: {summary_path} ({len(all_songs)} 首)[/bold cyan]")

        # 打印统计
        console.print(f"\n[bold]📊 统计:[/bold]")
        console.print(f"  歌单数: {len(playlists)}")
        console.print(f"  总歌曲: {len(all_songs)} 首")
        unique_artists = set()
        for s in all_songs:
            unique_artists.update(s.artists)
        console.print(f"  歌手数: {len(unique_artists)}")


@app.command()
def classify(
    playlist_id: int = typer.Argument(..., help="歌单 ID"),
    by: str = typer.Option("genre", "--by", "-b", help="分类维度: genre / language"),
    config: str | None = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """对歌单中的歌曲进行自动分类"""
    api = _get_api(config)

    console.print(f"[bold]正在获取歌单 {playlist_id} ...[/bold]")
    playlist = api.get_playlist_detail(playlist_id)

    classifier = SongClassifier()
    results = classifier.classify_songs(playlist.songs, by=by)

    console.print(f"\n[bold green]{playlist.name}[/bold green] — 按 {by} 分类结果:\n")

    for result in results:
        console.print(f"[bold yellow]【{result.category}】[/bold yellow] ({result.count} 首)")
        for song in result.songs:
            console.print(f"  • {song}")
        console.print()


@app.command()
def dedup(
    playlist_id: int = typer.Argument(..., help="歌单 ID"),
    config: str | None = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """检测歌单中的重复歌曲"""
    api = _get_api(config)

    console.print(f"[bold]正在获取歌单 {playlist_id} ...[/bold]")
    playlist = api.get_playlist_detail(playlist_id)

    unique, dups = deduplicate(playlist.songs)

    console.print(f"\n歌单共 {len(playlist.songs)} 首, 唯一 {len(unique)} 首\n")

    if dups:
        console.print("[bold red]重复歌曲:[/bold red]")
        for song in dups:
            console.print(f"  • {song}")
    else:
        console.print("[bold green]没有发现重复歌曲 ✓[/bold green]")


@app.command()
def export(
    playlist_id: int = typer.Argument(..., help="歌单 ID"),
    format: str = typer.Option("csv", "--format", "-f", help="导出格式: csv / json / excel"),
    output: str = typer.Option("", "--output", "-o", help="输出文件路径（默认自动生成）"),
    config: str | None = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """导出歌单为文件"""
    settings = load_settings(config)
    api = _get_api(config)

    console.print(f"[bold]正在获取歌单 {playlist_id} ...[/bold]")
    playlist = api.get_playlist_detail(playlist_id)

    if not output:
        ext_map = {"csv": ".csv", "json": ".json", "excel": ".xlsx"}
        ext = ext_map.get(format, ".csv")
        output_dir = Path(settings.export.output_dir)
        output = str(output_dir / f"{playlist.name}{ext}")

    path = export_songs(playlist.songs, output, fmt=format)
    console.print(f"\n[bold green]已导出到: {path}[/bold green]")


@app.command()
def stats(
    playlist_id: int = typer.Argument(..., help="歌单 ID"),
    config: str | None = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """查看歌单统计信息"""
    api = _get_api(config)

    console.print(f"[bold]正在获取歌单 {playlist_id} ...[/bold]")
    playlist = api.get_playlist_detail(playlist_id)

    songs = playlist.songs

    # 歌手统计
    artist_count: dict[str, int] = {}
    for song in songs:
        for artist in song.artists:
            artist_count[artist] = artist_count.get(artist, 0) + 1

    # 总时长
    total_seconds = sum(s.duration for s in songs)
    hours, remainder = divmod(total_seconds, 3600)
    mins, secs = divmod(remainder, 60)

    console.print(f"\n[bold green]📊 {playlist.name} 统计[/bold green]\n")
    console.print(f"  歌曲总数: {len(songs)}")
    console.print(f"  总时长:   {hours}h {mins}m {secs}s")
    console.print(f"  歌手数:   {len(artist_count)}")

    # Top 10 歌手
    top_artists = sorted(artist_count.items(), key=lambda x: x[1], reverse=True)[:10]
    console.print("\n[bold cyan]  Top 10 歌手:[/bold cyan]")
    for i, (name, count) in enumerate(top_artists, 1):
        console.print(f"    {i:>2}. {name} ({count} 首)")


@app.command()
def ui(
    port: int = typer.Option(8501, "--port", "-p", help="端口号"),
) -> None:
    """启动 Web UI 界面"""
    import subprocess
    import sys

    ui_path = Path(__file__).parent / "ui" / "app.py"
    console.print(f"[bold green]🚀 正在启动 Web UI (端口 {port})...[/bold green]")
    console.print(f"[dim]打开浏览器访问: http://localhost:{port}[/dim]\n")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", str(ui_path),
        "--server.port", str(port),
        "--server.headless", "false",
    ])


def main() -> None:
    """入口函数"""
    app()


if __name__ == "__main__":
    main()
