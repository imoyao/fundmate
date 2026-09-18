#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：禁止在前端业务文件里写裸断点媒体查询（`@media (width <= 768px)`）。

WHY
---
仓库一度并存**三套**响应式词汇：`frontend/design.md` §Viewport 的断点表
（401/601/961/1200/1400，零实现）、各组件手写的 `@media (width <= Npx)`
（N 取 470~1180 之间十余个互不相同的值）、以及 Tailwind 的 `sm:` / `md:` / `lg:`
前缀（已在 32 个文件里生效）。同一个页面在不同文件里按不同阈值换挡，
而这类漂移没有任何自动化拦截——与 #1506 的容器宽度问题是同一类病。

#1571 把断点收口到**单一来源** ``frontend/src/style/_breakpoints.scss``
（数值对齐 Tailwind v4 默认主题，见 docs/spec/decisions.md），并提供
``bp.below("md")`` / ``bp.above("lg")`` mixin。本守卫防止回潮：
业务文件里再写裸 px / rem 断点即 CI 变红。

存量已冻结为 ``BASELINE``（**不得新增**）。基线只减不增，逐个迁到 mixin 后
从基线里删掉；全部清空时守卫会提示可以改用「零容忍」模式。

用法
----
    python scripts/guard_breakpoints.py                 # 扫描 frontend/src 全量
    python scripts/guard_breakpoints.py a.vue b.scss    # 只扫指定文件（pre-commit 场景）

退出码：0 = 通过；1 = 命中栅栏。
"""

from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "frontend" / "src"
SCAN_SUFFIXES = {".vue", ".css", ".scss", ".sass"}

# 断点单一来源：本文件就是「裸值」的定义处，允许出现字面量
SINGLE_SOURCE = Path("frontend/src/style/_breakpoints.scss")

# 同行加此注释可显式豁免（须在 PR 里说明理由）
SKIP_MARKER = "breakpoint-allow"

MEDIA_RE = re.compile(r"@media\b([^{]*)\{")
LENGTH_RE = re.compile(r"\b\d*\.?\d+(?:px|rem|em)\b")

# 存量基线：`相对路径::规范化后的媒体条件` → 出现次数。
# 全部来自 #1571 之前的历史写法（2026-09-17 冻结）。**只允许删，不允许加**：
# 新增断点请 `@use "@/style/breakpoints" as bp;` 后用 bp.below()/bp.above()。
BASELINE: dict[str, int] = {
    "frontend/src/components/Aggregation/AggregationHero.vue::(width <= 768px)": 1,
    "frontend/src/components/Aggregation/AggregationInstitutionCard.vue::(width <= 520px)": 1,
    "frontend/src/components/Aggregation/AggregationPage.vue::(width <= 640px)": 1,
    "frontend/src/components/Aggregation/AggregationProductCard.vue::(width <= 520px)": 1,
    "frontend/src/components/MetricCard/index.vue::(width <= 480px)": 1,
    "frontend/src/components/MetricGrid/index.vue::(width <= 560px)": 1,
    "frontend/src/components/MetricGrid/index.vue::(width <= 960px)": 1,
    "frontend/src/components/PageFooter/index.vue::(width <= 640px)": 1,
    "frontend/src/components/PageSkeleton/index.vue::(width <= 640px)": 2,
    "frontend/src/components/TemperatureGaugeCard/index.vue::(width <= 768px)": 1,
    "frontend/src/layout/components/lay-footer/index.vue::(width <= 720px)": 1,
    "frontend/src/style/element-plus.scss::screen and (width <= 470px)": 1,
    "frontend/src/style/element-plus.scss::"
    "screen and (width > 760px) and (width <= 940px)": 1,
    "frontend/src/style/index.scss::(width <= 960px)": 1,
    "frontend/src/style/login.css::screen and (max-width: 1180px)": 1,
    "frontend/src/style/login.css::screen and (max-width: 968px)": 1,
    "frontend/src/style/sidebar.scss::screen and (width >= 150px) and (width <= 420px)": 1,
    "frontend/src/style/sidebar.scss::screen and (width >= 420px)": 1,
    "frontend/src/views/asset/ledgers/index.vue::(width <= 767px)": 1,
    "frontend/src/views/explore/components/ExploreAssetOverview.vue::(width <= 480px)": 1,
    "frontend/src/views/explore/components/ExploreAssetOverview.vue::(width <= 768px)": 1,
    "frontend/src/views/explore/components/ExploreDetailPanel.vue::(width <= 768px)": 1,
    "frontend/src/views/explore/components/ExploreDetailPanel.vue::(width <= 960px)": 1,
    "frontend/src/views/explore/components/ExploreTemperatureDashboard.vue::(width <= 768px)": 1,
    "frontend/src/views/explore/index.vue::(width <= 768px)": 1,
    "frontend/src/views/login/index.vue::(width <= 480px)": 1,
    "frontend/src/views/login/index.vue::(width <= 768px)": 1,
    "frontend/src/views/login/index.vue::(width <= 968px)": 1,
    "frontend/src/views/login/reset-password.vue::(width <= 768px)": 1,
    "frontend/src/views/login/reset-password.vue::(width <= 968px)": 1,
    "frontend/src/views/profile/index.vue::(width <= 640px)": 1,
}


def _iter_files(targets: list[str]) -> list[Path]:
    """有入参时只扫这些文件（pre-commit 场景）；否则递归扫默认目录。"""
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


def _scan(path: Path) -> collections.Counter[str]:
    """收集文件里的裸断点媒体查询：条件里同时出现 width 与长度单位。"""
    found: collections.Counter[str] = collections.Counter()
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return found

    lines = text.splitlines()
    for match in MEDIA_RE.finditer(text):
        # 定位该 @media 所在行，供 SKIP_MARKER 判断
        lineno = text.count("\n", 0, match.start())
        if SKIP_MARKER in lines[lineno]:
            continue
        cond = " ".join(match.group(1).split())
        if "width" not in cond or not LENGTH_RE.search(cond):
            continue  # prefers-reduced-motion / hover / print 等非宽度条件，放行
        found[cond] += 1
    return found


def main(argv: list[str]) -> int:
    targets = [a for a in argv if not a.startswith("-")]
    files = _iter_files(targets)

    if not files:
        print("OK: 未发现待扫描的前端样式文件")
        return 0

    violations: list[tuple[str, str, int, int]] = []
    seen: collections.Counter[str] = collections.Counter()

    for path in files:
        try:
            rel = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = path.as_posix()
        if rel == SINGLE_SOURCE.as_posix():
            continue  # 断点定义处：本守卫的来源

        for cond, count in _scan(path).items():
            key = f"{rel}::{cond}"
            seen[key] += count
            budget = BASELINE.get(key, 0)
            if count > budget:
                violations.append((rel, cond, count, budget))

    if not violations:
        if not targets and not any(seen.get(k, 0) for k in BASELINE):
            print("OK: 裸断点基线已清零，可把本守卫改为零容忍模式")
        else:
            remain = sum(min(seen.get(k, 0), v) for k, v in BASELINE.items())
            print(
                "OK: 无新增裸断点媒体查询"
                f"（存量基线剩余 {remain} / {sum(BASELINE.values())} 处待迁移）"
            )
        return 0

    print(
        "ERROR: 检测到新的裸断点媒体查询，请改用断点单一来源：\n"
        '         @use "@/style/breakpoints" as bp;\n'
        '         @include bp.below("md") { ... }   // < 768px\n'
        '         @include bp.above("lg") { ... }   // >= 1024px',
        file=sys.stderr,
    )
    for rel, cond, count, budget in violations:
        extra = f"（基线 {budget} 处，现 {count} 处）" if budget else ""
        print(f"  {rel}  @media {cond} {extra}", file=sys.stderr)
    print(
        "\n      断点表：frontend/src/style/_breakpoints.scss（对齐 Tailwind v4 默认断点）\n"
        "      规范：frontend/design.md §Viewport「断点单一来源」\n"
        "      确需例外：在同行加注释 %s 并说明理由" % SKIP_MARKER,
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
