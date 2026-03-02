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


def main() -> None:
    """入口函数"""
    app()


if __name__ == "__main__":
    main()
