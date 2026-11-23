#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：禁止「自建 table + 表头 sticky + 无内部滚动容器」三件套（#3200）。

WHY（源 issue #3200：同类优选表头不吸顶，实测坐实）
----------------------------------------------------
`position: sticky` 相对**最近的 scrolling ancestor** 定位。而 CSS 里
`overflow-x: auto` 与 `overflow-y: visible` 无法共存成「横滚 + 纵向不截断」——
只要**任一轴**是 auto / scroll / hidden，该元素就成为 sticky 的截断点。

自建 ``<table>`` 想横向滚动，就必须给容器 ``overflow-x: auto``；于是 ``thead th`` 的
吸顶被锁在这个容器里，页面一滚就跟着走。实测（#3200）：表头 ``top=494px``，
显式再加 ``overflow-y: clip`` 也无效——computed 仍是 ``{x:auto, y:clip}``，x 轴已经
把 sticky 截断了。这不是「样式没写对」，是**结构冲突**，写多少 CSS 都救不回来。

两种合法写法（守卫据此判定）：

  A. **迁 el-table**（推荐）：header / body 是两层 DOM，横滚落在 body 内部的
     el-scrollbar 上，外框可以 ``overflow: clip visible``，header-wrapper 的 sticky
     就能上溯到页面滚动容器。参考 `watchlist/components/WatchlistTableSection.vue`。
  B. **给表格加内部滚动容器**：``max-height`` + ``overflow-y: auto``，表头相对这张
     表格吸顶（表只在卡片内滚）。参考 `product/components/ProductHoldingSection.vue`。

判据（三件同时成立才红，缺一放行）
--------------------------------
1. 文件里有**自建** ``<table`` 元素（``<el-table`` 不算：那是 EP 组件）；
2. 样式里有以 ``thead`` / ``th`` 为目标的 ``position: sticky``；
3. 同一文件里**没有**任何「纵向内部滚动容器」声明
   （``max-height`` + ``overflow-y: auto|scroll``，或 ``overflow: auto|scroll`` 简写）。

为什么要求三件同时成立：只满足 1+2 而表格外面没有横滚时，表头其实吸得住
（table 天然不产生 scrolling ancestor）；只满足 1+3 是方案 B 的合法形态。
把「有横滚」当成隐含条件（自建 table 只要宽度超容器就必然出现横滚）后，
判据退化为上面三条——**判据宁窄勿宽**：误杀会把合法写法一起逼死。

已知不覆盖（如实登记，别指望它兜住）
----------------------------------
- 只做静态文本判定：不校验被命中的 ``thead`` 规则是否真的作用于那张表、也不校验
  内部滚动容器是否真的包住它（要 DOM / 运行时，静态做不到）。宁可漏判，不误杀。
- 跨文件不追：样式写在全局 ``.scss``、表格在另一个 ``.vue`` 的形态判不出
  （各自的文件内都不满足三件套）。本仓表格样式一律与组件同文件，故暂不追。
- 只扫 ``frontend/src`` 的 ``.vue/.css/.scss``；``<style module>`` 同样在扫描范围。

用法
----
    python scripts/guard_sticky_table.py                 # 扫描 frontend/src
    python scripts/guard_sticky_table.py a.vue b.css     # 只扫指定文件

退出码：0 = 通过；1 = 命中栅栏。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "frontend" / "src"
SCAN_SUFFIXES = {".vue", ".css", ".scss"}

# 行内豁免：与其它前端守卫同粒度（本行或紧邻上一行写理由），刻意不支持文件级豁免——
# 文件级豁免一旦开了，整份文件的历史形态就再也拦不住了。
SKIP_MARKER = "sticky-table-allow"

# 自建 table 元素：`<table` 后面必须是空白或 `>`，排除 `<tableXxx`；
# `<el-table` / `<el-table-column` 天然不匹配（前缀是 `el-`）。
SELF_TABLE_RE = re.compile(r"<table[\s>]", re.IGNORECASE)

# 扁平 CSS 规则切分：`选择器 { 声明 }`。SCSS 嵌套时内层块同样能匹到，
# 外层块因子块花括号不匹配而跳过——我们只关心「某条规则是否带某个声明」，
# 这种粒度足够，且不必引入解析器。
RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)

# 目标选择器含 thead / th（含 `thead th`、`.wrapper th`、`th.col` 等写法）。
# 负向边界排除 `.thumb` / `th-cell` 这类词，避免误判。
HEADER_SELECTOR_RE = re.compile(r"(?:^|[\s,>+~])th(?:ead)?(?![\w-])")

STICKY_DECL_RE = re.compile(r"position\s*:\s*sticky", re.IGNORECASE)

# 「纵向内部滚动容器」：max-height + overflow-y:auto|scroll（方案 B 的正解），
# 或 overflow 简写里带 auto|scroll。高度写 height 也算（有确定高度的内滚容器）。
MAX_HEIGHT_RE = re.compile(r"(?:max-)?height\s*:\s*[^;]+", re.IGNORECASE)
OVERFLOW_Y_SCROLL_RE = re.compile(
    r"overflow-y\s*:\s*(?:auto|scroll)", re.IGNORECASE
)
OVERFLOW_SCROLL_RE = re.compile(
    r"overflow\s*:\s*(?:auto|scroll|hidden\s+(?:auto|scroll))", re.IGNORECASE
)


def _mask(text: str, pattern: re.Pattern[str]) -> str:
    """把匹配到的片段替换成**等长空白**（保留换行）——行号不偏移。

    这是本守卫的关键细节：先剥注释再扫描会让报错行号漂走，
    而行号指错的判据等于查不到（AGENTS「正则/字符串类判据的常见错」）。
    """

    def repl(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    return pattern.sub(repl, text)


def _prepare(text: str) -> str:
    """屏蔽注释与 <script> 块，只留下「会被浏览器当结构/样式解读」的文本。

    三件套全是**结构事实**，注释里写 ``<table>`` 或在文档里引用一遍旧写法
    不该判红（本仓 #3200 自己的迁移注释就写了 `<table>`）。
    """
    masked = _mask(text, re.compile(r"<!--.*?-->", re.S))  # HTML 注释
    masked = _mask(masked, re.compile(r"<script\b.*?</script>", re.S | re.I))
    masked = _mask(masked, re.compile(r"/\*.*?\*/", re.S))  # CSS / JS 块注释
    # 行注释只认整行以 `//` 开头的（样式里几乎没有；避免吃掉 url(//...)）
    masked = _mask(masked, re.compile(r"^[ \t]*//[^\n]*", re.M))
    return masked


def _style_spans(masked: str, path: Path) -> list[tuple[int, str]]:
    """返回 [(在文件中的起始偏移, 样式文本)]。

    .vue 取所有 ``<style ...>`` 块；.css/.scss 整份都是样式。
    """
    if path.suffix in {".css", ".scss"}:
        return [(0, masked)]
    spans: list[tuple[int, str]] = []
    for m in re.finditer(r"<style\b[^>]*>(.*?)</style>", masked, re.S | re.I):
        spans.append((m.start(1), m.group(1)))
    return spans


def _rules(spans: list[tuple[int, str]]):
    """产出 (绝对偏移, 选择器, 声明体) —— 偏移用于把行号算回原文。"""
    for base, body in spans:
        for m in RULE_RE.finditer(body):
            selector = " ".join(m.group(1).split())
            yield base + m.start(2), selector, m.group(2)


def _has_vertical_scroll_container(rules: list[tuple[int, str, str]]) -> bool:
    for _, _, decls in rules:
        if not MAX_HEIGHT_RE.search(decls):
            continue
        if OVERFLOW_Y_SCROLL_RE.search(decls) or OVERFLOW_SCROLL_RE.search(decls):
            return True
    return False


def _scan(path: Path) -> list[tuple[int, str]]:
    """返回 [(行号, 选择器)]；空列表 = 放行。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    masked = _prepare(text)
    if not SELF_TABLE_RE.search(masked):
        return []  # 没有自建 table：el-table / 纯 div 布局不在本判据范围

    rules = list(_rules(_style_spans(masked, path)))
    lines = text.splitlines()

    sticky_headers: list[tuple[int, str]] = []
    for body_offset, selector, decls in rules:
        if not HEADER_SELECTOR_RE.search(selector):
            continue
        decl = STICKY_DECL_RE.search(decls)
        if not decl:
            continue
        lineno = text.count("\n", 0, body_offset + decl.start()) + 1
        # 豁免粒度 = 本行 + 上一行（与其它前端守卫一致），不支持文件级豁免
        window = lines[max(0, lineno - 2) : lineno]
        if any(SKIP_MARKER in line for line in window):
            continue
        sticky_headers.append((lineno, selector))

    if not sticky_headers:
        return []
    if _has_vertical_scroll_container(rules):
        return []  # 方案 B：表头相对内部滚动容器吸顶，合法

    return sticky_headers


def _iter_files(targets: list[str]) -> list[Path]:
    if targets:
        files: list[Path] = []
        for raw in targets:
            p = Path(raw)
            if not p.is_absolute():
                p = REPO_ROOT / p
            if p.suffix in SCAN_SUFFIXES and p.is_file():
                files.append(p)
        return files

    if not DEFAULT_ROOT.is_dir():
        return []
    return [
        p
        for p in DEFAULT_ROOT.rglob("*")
        if p.is_file() and p.suffix in SCAN_SUFFIXES and "node_modules" not in p.parts
    ]


def main(argv: list[str]) -> int:
    targets = [a for a in argv if not a.startswith("-")]
    files = _iter_files(targets)

    if not files:
        print("OK: 未发现待扫描的前端文件")
        return 0

    violations: dict[str, list[tuple[int, str]]] = {}
    for path in files:
        try:
            rel = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = str(path)
        hits = _scan(path)
        if hits:
            violations[rel] = hits

    if not violations:
        print(
            "OK: 无「自建 table + 表头 sticky + 无内部滚动容器」的死冲突"
            "（扫描 %d 个文件）" % len(files)
        )
        return 0

    print(
        "ERROR: 检测到「自建 table + 表头 sticky + 无内部滚动容器」——"
        "这种结构下表头吸顶必然失效（sticky 被 overflow 容器截断）：",
        file=sys.stderr,
    )
    for rel in sorted(violations):
        for lineno, selector in violations[rel]:
            print("  %s:%d  %s" % (rel, lineno, selector), file=sys.stderr)
    print(
        "\n      两种正解（二选一）：\n"
        "        ① 迁 el-table（推荐）：header / body 分层，横滚落在 body 内部，\n"
        "           再用 overflow: clip visible + header-wrapper sticky；\n"
        "        ② 给表格加内部滚动容器：max-height + overflow-y: auto，表头相对它吸顶。\n"
        "      规范：frontend/design.md「Table · 表头吸顶」\n"
        "      确需例外：在 position:sticky 同一行加注释 %s 并说明理由" % SKIP_MARKER,
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
