# 🎵 MusicClassifier - QQ音乐歌单自动处理器

自动获取、分类、管理和分析你的 QQ 音乐歌单。

## 功能

- **歌单获取** — 通过 QQ 音乐接口抓取歌单数据（歌名、歌手、专辑、时长等）
- **自动分类** — 按流派、语言、年代、心情等维度分类歌曲
- **歌单管理** — 合并、拆分、去重歌单
- **数据导出** — 导出为 CSV / JSON / Excel
- **数据分析** — 歌手分布、流派统计、收藏趋势可视化

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/YOUR_USERNAME/musicclassifier.git
cd musicclassifier

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux

# 安装依赖
pip install -e ".[dev]"
```

### 配置

复制示例配置并填写你的信息：

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`，填入 QQ 音乐的 Cookie 或相关凭据。

### 使用

```bash
# 获取歌单
musicclassifier fetch --playlist-id 123456789

# 分类歌单中的歌曲
musicclassifier classify --playlist-id 123456789

# 去重
musicclassifier dedup --playlist-id 123456789

# 导出歌单
musicclassifier export --playlist-id 123456789 --format csv

# 查看歌单统计
musicclassifier stats --playlist-id 123456789
```

## 项目结构

```
src/musicclassifier/
├── cli.py              # 命令行入口
├── config.py           # 配置管理
├── api/
│   └── qq_music.py     # QQ音乐API封装
├── models/
│   └── song.py         # 数据模型
├── processors/
│   ├── classifier.py   # 歌曲分类器
│   ├── dedup.py        # 去重处理
│   └── exporter.py     # 导出功能
└── utils/
    └── helpers.py      # 工具函数
```

## 开发

```bash
# 运行测试
pytest

# 代码格式检查
ruff check src/ tests/
```

## 许可证

[MIT](LICENSE)
