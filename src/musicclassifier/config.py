"""配置管理

使用 pydantic-settings 从 YAML 文件和环境变量加载配置。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel


class QQMusicConfig(BaseModel):
    """QQ音乐相关配置"""
    cookie: str = ""
    qq_number: str = ""
    timeout: float = 30
    request_interval: float = 1.0


class ClassifierConfig(BaseModel):
    """分类器配置"""
    rules_file: str = ""


class ExportConfig(BaseModel):
    """导出配置"""
    output_dir: str = "output"
    default_format: str = "csv"


class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"
    file: str = ""


class Settings(BaseModel):
    """应用总配置"""
    qq_music: QQMusicConfig = QQMusicConfig()
    classifier: ClassifierConfig = ClassifierConfig()
    export: ExportConfig = ExportConfig()
    logging: LoggingConfig = LoggingConfig()


CONFIG_FILENAME = "config.yaml"

# 配置搜索路径优先级
CONFIG_SEARCH_PATHS = [
    Path.cwd() / CONFIG_FILENAME,
    Path.home() / ".musicclassifier" / CONFIG_FILENAME,
]


def load_settings(config_path: str | Path | None = None) -> Settings:
    """加载配置文件

    Args:
        config_path: 配置文件路径（为 None 时自动搜索）

    Returns:
        Settings 实例
    """
    if config_path is not None:
        p = Path(config_path)
        if p.exists():
            return _parse_yaml(p)
        raise FileNotFoundError(f"配置文件不存在: {p}")

    # 自动搜索
    for p in CONFIG_SEARCH_PATHS:
        if p.exists():
            return _parse_yaml(p)

    # 没找到配置文件，使用默认设置
    return Settings()


def _parse_yaml(path: Path) -> Settings:
    """解析 YAML 配置文件"""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Settings(**raw)


@lru_cache
def get_settings() -> Settings:
    """获取全局配置（带缓存）"""
    return load_settings()
