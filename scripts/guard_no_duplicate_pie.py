#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：禁止在 `AssetAllocationDonut` 之外新写 pie / 环形图 option。

WHY
---
`docs/design/components.md` §「AssetAllocationDonut · 资产配置环形图（强制复用）」
写明它是资产配置分布图的**统一组件**，替代各页手写 pie option。但规范只落在文档里、
没有任何机器化拦截，于是同类实现照样长出来 —— #2097 结项时实测到 **4 套**资产分布
实现并存（`AssetAllocationDonut` / `LedgerAllocationCard` / `AggregationHero` /
`IntelligentAnalysis`），而规范标注前者「强制复用」。

本守卫负责把这条规范从「写在文档里」变成「CI 会红」：任何新的自写 pie option 都会被拦下。

判据（只看**画图 option**，不误伤模板里的 `:style` / 图标 prop）
----------------------------------------------------------------
- 命中：`type: "pie"` / `type: 'pie'`（ECharts option 里的系列类型）
- 不命中：CSS 里的 `border-radius: 50%`、模板里的样式绑定、`<AssetAllocationDonut>`
  的调用方 —— 那些是合法消费，不是「又写了一套」

白名单（不是漏洞，是显式登记的例外）
----------------------------------
`frontend/src/components/Aggregation/AggregationHero.vue` —— hero 是横向概览锚点，
空间放不下表格；它把 echarts 原生图例换成「HTML top5 + 其他 N 类」折叠，属**信息分层**
而非「重新实现一套资产分布」。按判据它本该走表内嵌条，但 hero 布局下不可行，故登记为例
并在 components.md 补了说明（#2164）。除它之外的任何新 pie option 都会变红。

用法
----
    python scripts/guard_no_duplicate_pie.py                 # 扫 frontend/src 全量
    python scripts/guard_no_duplicate_pie.py a.vue b.ts      # 只扫指定文件

退出码：0 = 通过；1 = 命中栅栏。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "frontend" / "src"
SCAN_SUFFIXES = {".vue", ".ts", ".tsx", ".js", ".jsx"}

# 统一组件自身：它的 option 就是「那一套」，不能拦自己
UNIFIED_COMPONENT = "frontend/src/components/Charts/AssetAllocationDonut.vue"

# 显式登记的例外（理由见模块 docstring）。新增白名单必须同时更新 components.md 的说明，
# 否则这道守卫会退化成「谁熟谁加白名单」的橡皮图章。
WHITELIST = frozenset(
    {
        "frontend/src/components/Aggregation/AggregationHero.vue",
    }
)

# ECharts 系列类型。只认引号包裹的字面量，避免命中注释里的裸词。
PIE_TYPE_RE = re.compile(r"""type\s*:\s*['"]pie['"]""")


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def iter_files(roots: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in roots:
        p = Path(raw)
        if p.is_file():
            out.append(p)
            continue
        for f in sorted(p.rglob("*")):
            if f.is_file() and f.suffix in SCAN_SUFFIXES:
                out.append(f)
    return out


def main(argv: list[str]) -> int:
    roots = argv[1:] or [str(DEFAULT_ROOT)]
    files = iter_files(roots)

    violations: list[tuple[str, int, str]] = []
    for f in files:
        rel = _rel(f)
        if rel == UNIFIED_COMPONENT or rel in WHITELIST:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if PIE_TYPE_RE.search(line):
                violations.append((rel, lineno, line.strip()))

    if not violations:
        print(
            "OK: 未发现 AssetAllocationDonut 之外的自写 pie option"
            "（白名单 %d 项：%s）" % (len(WHITELIST), ", ".join(sorted(WHITELIST)) or "-")
        )
        return 0

    print(
        "ERROR: 发现 %d 处自写 pie / 环形图 option，违反 components.md"
        "「AssetAllocationDonut 强制复用」：" % len(violations)
    )
    for rel, lineno, snippet in violations:
        print("  %s:%d  %s" % (rel, lineno, snippet[:100]))
    print()
    print("  正解：改用 <AssetAllocationDonut :data=... :colorMap=... />（≤6 类）；")
    print("        7 类以上 / 分类名长且必须读全 → 表内嵌条（参考 ProductIndustrySection.vue）。")
    print("  确属例外（如 hero 横向布局放不下表格）→ 加入本脚本 WHITELIST，")
    print("  并在 docs/design/components.md 的 AssetAllocationDonut 小节补一句理由。")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
