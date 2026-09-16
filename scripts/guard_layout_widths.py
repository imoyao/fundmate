#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：禁止在前端容器上写死布局宽度字面量（1280px / 1400px）。

WHY
---
内容列宽度一度以 ``max-width: 1280px`` 硬编码散落 9 个文件（13 处），外壳另有一套
``1400px`` 散落 4 处；两档并存且无单一来源，直接后果是「探市页页头（壳）与内容区
（内容列）左右边缘错开 60px」，而这类漂移此前没有任何自动化拦截（issue #1506）。

#1506 已把两档收口为 CSS 令牌 ``--layout-content-width`` / ``--layout-shell-width``
（定义在 ``frontend/src/style/colors.css``，见 frontend/design.md §Viewport）。
本守卫负责防止回潮：任何新的容器宽度字面量都会在 CI 变红。

用法
----
    python scripts/guard_layout_widths.py                 # 扫描 frontend/src 全量
    python scripts/guard_layout_widths.py a.vue b.scss    # 只扫指定文件（CI/CD 场景）

退出码：0 = 通过；1 = 命中栅栏。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "frontend" / "src"
SCAN_SUFFIXES = {".vue", ".css", ".scss", ".sass", ".ts", ".tsx", ".js", ".jsx"}

# 令牌定义处允许出现字面量（否则守卫会拦住自己的来源）
TOKEN_DEFINITION_FILE = Path("frontend/src/style/colors.css")

# 受管的外观布局宽度：新增的值必须先在 colors.css 定义同名令牌再来这里登记，
# 否则这道守卫形同虚设（写死别的数字照样能绕过去）。
MANAGED_WIDTHS = ("1280", "1400")

CSS_WIDTH_RE = re.compile(
    r"(?<![-\w])(?:max-width|min-width|width)\s*:\s*(?:%s)px\b" % "|".join(MANAGED_WIDTHS)
)
TAILWIND_ARBITRARY_RE = re.compile(
    r"(?<![-\w])(?:max-w|min-w|w)-\[(?:%s)px\]" % "|".join(MANAGED_WIDTHS)
)

SKIP_MARKER = "layout-width-allow"


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


def _scan(path: Path) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return hits

    for lineno, line in enumerate(text.splitlines(), start=1):
        if SKIP_MARKER in line:
            continue
        for pattern in (CSS_WIDTH_RE, TAILWIND_ARBITRARY_RE):
            if pattern.search(line):
                hits.append((lineno, line.strip()))
                break
    return hits


def main(argv: list[str]) -> int:
    targets = [a for a in argv if not a.startswith("-")]
    files = _iter_files(targets)

    if not files:
        print("OK: 未发现待扫描的前端样式文件")
        return 0

    violations: dict[str, list[tuple[int, str]]] = {}
    for path in files:
        try:
            rel = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = str(path)
        if rel == TOKEN_DEFINITION_FILE.as_posix():
            continue  # 令牌定义处：允许出现字面量
        hits = _scan(path)
        if hits:
            violations[rel] = hits

    if not violations:
        print("OK: 无写死的容器宽度字面量（受管宽度：%s px）" % " / ".join(MANAGED_WIDTHS))
        return 0

    print(
        "ERROR: 检测到写死的容器宽度字面量，请改用布局令牌 "
        "(--layout-content-width / --layout-shell-width)：",
        file=sys.stderr,
    )
    for rel in sorted(violations):
        for lineno, line in violations[rel]:
            print("  %s:%d  %s" % (rel, lineno, line), file=sys.stderr)
    print(
        "\n      令牌定义：frontend/src/style/colors.css\n"
        "      规范：frontend/design.md §Viewport「容器宽度单一来源」\n"
        "      确需例外：在同行加注释 %s 并说明理由" % SKIP_MARKER,
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
