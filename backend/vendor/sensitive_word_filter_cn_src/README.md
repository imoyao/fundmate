# sensitive-word-filter-cn

**High-performance Chinese sensitive word filter with pinyin, symbol interference, and traditional/simplified variant detection.**

高性能中文敏感词过滤工具，支持拼音变体、符号干扰、繁简体变体检测。

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)
[![PyPI Version](https://img.shields.io/badge/pypi-v0.1.0-orange)](https://pypi.org/project/sensitive-word-filter-cn/)
[![Code Style](https://img.shields.io/badge/code%20style-black-black)](https://github.com/psf/black)

---

## Features

- **High Performance** — DFA algorithm, filters million-character text in under 100ms
- **Smart Detection** — Handles pinyin variants, symbol interference, and traditional/simplified Chinese mixing
- **Easy to Use** — Clean Python API and CLI tool out of the box
- **Rich Output** — Beautiful terminal output with progress bars, tables, and highlighting
- **Well Tested** — Comprehensive unit tests and performance benchmarks

## Quick Start

### Installation

```bash
pip install sensitive-word-filter-cn
```

Or with Poetry:

```bash
poetry add sensitive-word-filter-cn
```

### Basic Usage

```python
from sensitive_word_filter_cn import SensitiveWordFilter

filter = SensitiveWordFilter()
filter.load_from_file('words.txt')

text = "你是个大傻*瓜shagua"
filtered = filter.filter(text)           # "你是个大*********"
matches  = filter.find_all(text)         # list of Match objects
has_word = filter.contains(text)         # True
```

## Usage Guide

### Python API

```python
from sensitive_word_filter_cn import SensitiveWordFilter

# Create filter instance
filter = SensitiveWordFilter()

# Load words from file
filter.load_from_file('words.txt')

# Or add words manually
filter.add_words(["傻瓜", "笨蛋"])

# Filter text
text = "你是个大傻*瓜shagua"
filtered = filter.filter(text)  # "你是个大*********"

# Find all matches
matches = filter.find_all(text)
for match in matches:
    print(f"Found: {match.word}  Position: {match.start}-{match.end}")

# Check if text contains sensitive words
if filter.contains(text):
    print("Sensitive word detected!")
```

#### Pinyin Variant Detection

```python
filter.add_word("傻瓜")

filter.contains("你是个shagua")   # full pinyin  → True
filter.contains("你是个sg")       # initials     → True
filter.contains("你是个sha gua")  # spaced pinyin → True
```

#### Symbol Interference Handling

```python
filter.add_word("傻瓜")

filter.contains("你是个傻*瓜")   # True
filter.contains("你是个傻-瓜")   # True
filter.contains("你是个傻@瓜")   # True
```

#### Traditional / Simplified Conversion

```python
filter.add_word("傻瓜")          # simplified

filter.contains("你是個傻瓜")    # traditional → True
```

### CLI Tool

```bash
# Filter text
sensitive-word-filter-cn filter "文本内容" -w words.txt

# Find sensitive words with highlight
sensitive-word-filter-cn find "文本内容" -w words.txt --highlight

# Batch process a file
sensitive-word-filter-cn batch input.txt -w words.txt -o output.txt

# Run performance benchmark
sensitive-word-filter-cn benchmark -w words.txt -t test.txt

# Interactive mode
sensitive-word-filter-cn interactive -w words.txt
```

## Project Structure

```
sensitive-word-filter-cn/
├── src/
│   └── sensitive_word_filter_cn/
│       ├── __init__.py       # Public API
│       ├── __main__.py       # Entry point
│       ├── core.py           # DFA engine & SensitiveWordFilter class
│       ├── cli.py            # CLI commands (click)
│       └── utils.py          # Pinyin / OpenCC helpers
├── tests/
│   ├── test_core.py          # Unit tests
│   ├── test_cli.py           # CLI tests
│   ├── test_utils.py         # Utility tests
│   └── test_performance.py   # Performance benchmarks
├── data/
│   └── sample_words.txt      # Sample sensitive word list
├── examples/
│   └── demo.py               # Usage examples
├── pyproject.toml
├── LICENSE
├── CONTRIBUTING.md
└── README.md
```

## Tech Stack

| Component | Library |
|-----------|---------|
| Core Algorithm | DFA (Deterministic Finite Automaton) |
| Pinyin Conversion | [pypinyin](https://github.com/mozillazg/python-pinyin) |
| Traditional/Simplified | [opencc-python-reimplemented](https://github.com/yichen0831/opencc-python) |
| CLI Framework | [click](https://click.palletsprojects.com/) |
| Terminal UI | [rich](https://github.com/Textualize/rich) |
| Testing | [pytest](https://pytest.org/) + pytest-benchmark |
| Code Style | [black](https://github.com/psf/black) + [ruff](https://github.com/astral-sh/ruff) |

## Performance

| Scenario | Result |
|----------|--------|
| Load 100k words | < 1 second |
| Filter 1M characters | < 100ms |
| Memory (100k words) | < 500MB |

## License

Copyright 2026 Chance Dean (novelnexusai@outlook.com)

Licensed under the [Apache License 2.0](LICENSE).

---

## 特性

- **高性能** — 基于 DFA 算法，百万字文本过滤耗时低于 100ms
- **智能检测** — 支持拼音变体、符号干扰、繁简体混用检测
- **易用性** — 简洁的 Python API 与命令行工具，开箱即用
- **可视化** — 丰富的终端输出，含进度条、表格与高亮显示
- **完整测试** — 包含单元测试与性能基准测试

## 快速开始

### 安装

```bash
pip install sensitive-word-filter-cn
```

或使用 Poetry：

```bash
poetry add sensitive-word-filter-cn
```

### 基本用法

```python
from sensitive_word_filter_cn import SensitiveWordFilter

filter = SensitiveWordFilter()
filter.load_from_file('words.txt')

text = "你是个大傻*瓜shagua"
filtered = filter.filter(text)           # "你是个大*********"
matches  = filter.find_all(text)         # 返回 Match 对象列表
has_word = filter.contains(text)         # True
```

## 使用指南

### Python API

```python
from sensitive_word_filter_cn import SensitiveWordFilter

# 创建过滤器实例
filter = SensitiveWordFilter()

# 从文件加载敏感词
filter.load_from_file('words.txt')

# 或手动添加词语
filter.add_words(["傻瓜", "笨蛋"])

# 过滤文本
text = "你是个大傻*瓜shagua"
filtered = filter.filter(text)  # "你是个大*********"

# 查找所有匹配
matches = filter.find_all(text)
for match in matches:
    print(f"发现: {match.word}  位置: {match.start}-{match.end}")

# 判断是否包含敏感词
if filter.contains(text):
    print("包含敏感词！")
```

#### 拼音变体检测

```python
filter.add_word("傻瓜")

filter.contains("你是个shagua")   # 全拼  → True
filter.contains("你是个sg")       # 首字母 → True
filter.contains("你是个sha gua")  # 带空格 → True
```

#### 符号干扰处理

```python
filter.add_word("傻瓜")

filter.contains("你是个傻*瓜")   # True
filter.contains("你是个傻-瓜")   # True
filter.contains("你是个傻@瓜")   # True
```

#### 繁简体转换

```python
filter.add_word("傻瓜")          # 简体

filter.contains("你是個傻瓜")    # 繁体 → True
```

### 命令行工具

```bash
# 基本过滤
sensitive-word-filter-cn filter "文本内容" -w words.txt

# 查找敏感词（带高亮）
sensitive-word-filter-cn find "文本内容" -w words.txt --highlight

# 批量处理文件
sensitive-word-filter-cn batch input.txt -w words.txt -o output.txt

# 性能基准测试
sensitive-word-filter-cn benchmark -w words.txt -t test.txt

# 交互模式
sensitive-word-filter-cn interactive -w words.txt
```

## 项目结构

```
sensitive-word-filter-cn/
├── src/
│   └── sensitive_word_filter_cn/
│       ├── __init__.py       # 公开 API
│       ├── __main__.py       # 入口点
│       ├── core.py           # DFA 引擎 & SensitiveWordFilter 类
│       ├── cli.py            # CLI 命令（click）
│       └── utils.py          # 拼音 / OpenCC 工具函数
├── tests/
│   ├── test_core.py          # 单元测试
│   ├── test_cli.py           # CLI 测试
│   ├── test_utils.py         # 工具函数测试
│   └── test_performance.py   # 性能基准测试
├── data/
│   └── sample_words.txt      # 示例敏感词库
├── examples/
│   └── demo.py               # 使用示例
├── pyproject.toml
├── LICENSE
├── CONTRIBUTING.md
└── README.md
```

## 技术栈

| 组件 | 依赖库 |
|------|--------|
| 核心算法 | DFA（确定有限状态自动机） |
| 拼音转换 | [pypinyin](https://github.com/mozillazg/python-pinyin) |
| 繁简体转换 | [opencc-python-reimplemented](https://github.com/yichen0831/opencc-python) |
| CLI 框架 | [click](https://click.palletsprojects.com/) |
| 终端美化 | [rich](https://github.com/Textualize/rich) |
| 测试 | [pytest](https://pytest.org/) + pytest-benchmark |
| 代码风格 | [black](https://github.com/psf/black) + [ruff](https://github.com/astral-sh/ruff) |

## 性能指标

| 场景 | 结果 |
|------|------|
| 加载 10 万敏感词 | < 1 秒 |
| 过滤 100 万字文本 | < 100ms |
| 内存占用（10 万词库） | < 500MB |

## 许可证

Copyright 2026 Chance Dean (novelnexusai@outlook.com)

本项目采用 [Apache License 2.0](LICENSE) 授权。
