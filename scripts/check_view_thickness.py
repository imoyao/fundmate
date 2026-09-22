#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：领域视图层不得继续变厚（视图层职责边界，判据见 #1606）。

WHY
---
`conventions.md` §2.2 与 `architecture.md` §1.3 一直写着「视图只做 HTTP 编排」，
但**没有可执行判据**，于是业务规则持续堆进 views：实测 `domains/ledgers/views.py`
1811 行 / 71 次 DB 调用，`domains/watchlist/views.py` 1445 行 / 45 次 DB 调用；
而 `tech-debt.md` 早已记过「自选模块视图层业务逻辑过重 ✅ 已修复」——属**债务回潮**，
说明当年只做了「抽取动作」，没留下边界、也没有守卫，代码随后在原文件里继续生长。

本守卫把 `decisions.md` 2026-09-19「视图层职责边界」（#1606）钉成机器可执行的判据：

| 指标 | 含义 | 新增上限 |
|---|---|---|
| `lines` | 文件总行数 | 400 |
| `orm_queries` | `*.query(` 调用次数（视图内直接查业务表） | 10 |
| `commits` | `*.commit(` 次数（事务边界；同一函数最多一次） | 5 |
| `max_func` | 最长函数行数（含 docstring，取 `end_lineno - lineno + 1`） | 60 |

存量按 `BASELINE` **冻结、只减不增**（只拦「比基线更厚」，不拦维持现状）：

- 新增 / 改名后的视图文件走上表上限，超标即红；
- 存量文件任一指标超过基线即红（回潮拦截）；
- 基线里已消失的文件会被提示删除（避免基线虚胖）；
- **实测低于基线时打印「请收紧基线」提示**（本脚本不报错——正常收敛不该红掉校验）；
  但「基线必须与实测贴合」由 `backend/tests/test_view_thickness_guard.py::
  test_baseline_matches_current_metrics` 强制：基线只减不增，而「减完不回写」会让该维度
  静默失效（实测 #1606 落地后 `commits` 维度空转了 41/44）。收敛后请**同 PR 内**
  用 `--report` 回写 BASELINE。

为什么不是零容忍：131 个端点的视图批量改写风险远大于收益（同 #1607「判据用边方向、
不用包级双向对数」的思路）——先把边界立住、堵住新增，再按批次收敛。

用法
----
    python scripts/check_view_thickness.py              # 校验（CI / pre-commit）
    python scripts/check_view_thickness.py --report     # 打印当前指标 + 可直接粘贴的基线
    python scripts/check_view_thickness.py -v           # 一并打印达标项

退出码：0 = 通过；1 = 命中栅栏。
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEWS_GLOB = "backend/app/domains/*/views.py"

# 新增 / 改名视图文件的上限（判据本体）
NEW_FILE_LIMITS = {
    "lines": 400,
    "orm_queries": 10,
    "commits": 5,
    "max_func": 60,
}

# 存量基线（2026-09-19 冻结，#1606 批次 1 下沉后重取）。
# **只减不增**：不要手工调大——要走「把业务规则下沉 services」的正当路径；
# 确实因合并等原因需要重取时，用 `--report` 生成新块并说明理由。
# 2026-09-20 重取（合并原因，非放宽）：错误信封补齐（#1610 / D27 要求每个错误响应带 error_code）
# 使 4 个视图文件共 +26 行 —— assets +5 / importers +4(+2 max_func) / ledgers +15(+12 max_func) /
# summary +2；增量全部是信封字段，不含任何业务规则，且相对 #1606 下沉前（ledgers 1811 行）仍是大幅收敛。
# 同批 positions 因 #1607 批次 2 把展示口径移出视图而 −24 行，已一并**收紧**（基线只减不增）。
# 2026-09-21 收紧（**纠「基线虚胖」**，非放宽）：#1609 batch 2/3/4 已把视图层 41 处 `commit()` 改为
# `flush()`（`conventions.md` §2.13 / `decisions.md` D33），但基线仍是收敛前的数字 —— 于是
# `commits` 维度 44 的预算里只剩 `reconciliation` 3 处有效，**把 `flush` 改回 `commit` 不会被拦**，
# 相当于守卫在这一维度空转。本次按 `--report` 实测回写（lines 亦随之 −1）。**教训**：做完「下沉 /
# 去冗余」这类收敛动作必须回写基线，否则守卫形同虚设。
# 2026-09-21 再收紧（#1640）：`reconciliation` 的 3 处 `commit()` 已随「`user_session()` 请求级单会话」
# 改为 `flush()`（#1640 / `conventions.md` §2.13），基线 `commits` 3 → 0 —— **至此全仓视图层 `commits` 归零**
# （#1609 batch 2/3/4 收敛 41 处 + #1640 收敛 3 处）。该维度自此进入**零容忍**：任何视图再出现 `commit()`
# 都会被基线拦下（把 `flush` 改回 `commit` 亦然），不必再依赖「只减不增」的存量冻结。
BASELINE: dict[str, dict[str, int]] = {
    "backend/app/domains/assets/views.py": {"lines": 208, "orm_queries": 4, "commits": 0, "max_func": 44},
    "backend/app/domains/auth/views.py": {"lines": 137, "orm_queries": 3, "commits": 0, "max_func": 45},
    "backend/app/domains/families/views.py": {"lines": 72, "orm_queries": 2, "commits": 0, "max_func": 22},
    "backend/app/domains/funds/views.py": {"lines": 324, "orm_queries": 9, "commits": 0, "max_func": 94},
    "backend/app/domains/importers/views.py": {"lines": 254, "orm_queries": 1, "commits": 0, "max_func": 74},
    "backend/app/domains/ledgers/views.py": {"lines": 723, "orm_queries": 16, "commits": 0, "max_func": 60},
    "backend/app/domains/market/views.py": {"lines": 50, "orm_queries": 0, "commits": 0, "max_func": 35},
    "backend/app/domains/ocr/views.py": {"lines": 262, "orm_queries": 1, "commits": 0, "max_func": 69},
    "backend/app/domains/performance/views.py": {"lines": 93, "orm_queries": 1, "commits": 0, "max_func": 36},
    "backend/app/domains/portfolios/views.py": {"lines": 266, "orm_queries": 5, "commits": 0, "max_func": 104},
    "backend/app/domains/positions/views.py": {"lines": 373, "orm_queries": 8, "commits": 0, "max_func": 81},
    "backend/app/domains/reconciliation/views.py": {"lines": 225, "orm_queries": 2, "commits": 0, "max_func": 48},
    "backend/app/domains/search/views.py": {"lines": 25, "orm_queries": 0, "commits": 0, "max_func": 7},
    "backend/app/domains/securities/views.py": {"lines": 72, "orm_queries": 1, "commits": 0, "max_func": 35},
    "backend/app/domains/strategy/views.py": {"lines": 239, "orm_queries": 9, "commits": 0, "max_func": 98},
    "backend/app/domains/summary/views.py": {"lines": 141, "orm_queries": 0, "commits": 0, "max_func": 20},
    "backend/app/domains/temperature/views.py": {"lines": 140, "orm_queries": 0, "commits": 0, "max_func": 38},
    "backend/app/domains/transactions/views.py": {"lines": 198, "orm_queries": 4, "commits": 0, "max_func": 76},
    "backend/app/domains/usage/views.py": {"lines": 68, "orm_queries": 0, "commits": 0, "max_func": 27},
    "backend/app/domains/users/views.py": {"lines": 115, "orm_queries": 4, "commits": 0, "max_func": 38},
    "backend/app/domains/utils/views.py": {"lines": 126, "orm_queries": 0, "commits": 0, "max_func": 38},
    "backend/app/domains/watchlist/views.py": {"lines": 712, "orm_queries": 14, "commits": 0, "max_func": 104},
}


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def collect_metrics(path: Path) -> dict[str, int]:
    """AST 统计单个视图文件的四项指标（不用正则，避免注释 / 字符串误命中）。"""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    orm_queries = 0
    commits = 0
    max_func = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "query":
                orm_queries += 1
            elif node.func.attr == "commit":
                commits += 1
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            span = (node.end_lineno or node.lineno) - node.lineno + 1
            max_func = max(max_func, span)

    return {
        "lines": source.count("\n") + (0 if source.endswith("\n") else 1),
        "orm_queries": orm_queries,
        "commits": commits,
        "max_func": max_func,
    }


def _iter_views() -> list[Path]:
    return sorted(REPO_ROOT.glob(VIEWS_GLOB))


def _fmt(metrics: dict[str, int]) -> str:
    return " ".join(f"{k}={metrics[k]}" for k in ("lines", "orm_queries", "commits", "max_func"))


def _report(views: list[Path]) -> int:
    print("# 当前指标（可直接粘贴为 BASELINE；键按路径字典序）")
    print("BASELINE: dict[str, dict[str, int]] = {")
    for path in views:
        print(f'    "{_rel(path)}": {collect_metrics(path)!r},')
    print("}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="视图层厚度守卫（#1606）")
    parser.add_argument("--report", action="store_true", help="打印当前指标与可直接粘贴的基线")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印每个文件的指标")
    args = parser.parse_args(argv)

    views = _iter_views()
    if not views:
        print(f"OK: 未找到待扫描的视图文件（{VIEWS_GLOB}）")
        return 0

    if args.report:
        return _report(views)

    violations: list[tuple[str, str, int, int, bool]] = []  # (rel, metric, current, limit, is_baseline)
    seen: set[str] = set()
    measured: dict[str, dict[str, int]] = {}

    for path in views:
        rel = _rel(path)
        seen.add(rel)
        metrics = collect_metrics(path)
        measured[rel] = metrics
        baseline = BASELINE.get(rel)

        if args.verbose:
            mark = "基线" if baseline else "新增"
            print(f"  [{mark}] {rel}  {_fmt(metrics)}")

        if baseline is None:
            for metric, limit in NEW_FILE_LIMITS.items():
                if metrics[metric] > limit:
                    violations.append((rel, metric, metrics[metric], limit, False))
            continue

        for metric, budget in baseline.items():
            if metrics[metric] > budget:
                violations.append((rel, metric, metrics[metric], budget, True))

    stale = sorted(set(BASELINE) - seen)

    # 基线虚胖（非致命）：实测已低于基线却没回写 → 该维度的「只减不增」拦截实际上不起作用。
    loose: list[tuple[str, str, int, int]] = []
    for rel, budget_map in BASELINE.items():
        metrics = measured.get(rel)
        if metrics is None:
            continue
        for metric, budget in budget_map.items():
            if metrics[metric] < budget:
                loose.append((rel, metric, metrics[metric], budget))

    if not violations:
        remaining = {
            "lines": sum(m["lines"] for m in BASELINE.values()),
            "orm_queries": sum(m["orm_queries"] for m in BASELINE.values()),
            "commits": sum(m["commits"] for m in BASELINE.values()),
        }
        print(
            "OK: 视图层厚度无新增（基线存量："
            f"{len(BASELINE) - len(stale)} 个文件 / {remaining['lines']} 行 / "
            f"{remaining['orm_queries']} 次 query / {remaining['commits']} 次 commit；只减不增）"
        )
        if stale:
            print("提示：以下文件已不在基线中，请从 BASELINE 删除对应条目：")
            for rel in stale:
                print(f"  - {rel}")
        if loose:
            print("提示：以下指标已低于基线，请用 `--report` 收紧 BASELINE（只减不增；不收紧该维度会静默失效）：")
            for rel, metric, current, budget in loose:
                print(f"  - {rel}: {metric} = {current}（基线 {budget}）")
        return 0

    print(
        "ERROR: 视图层变厚了——业务规则请下沉 `app/services/`，视图只做 HTTP 编排\n"
        "       判据：docs/spec/decisions.md（2026-09-19 视图层职责边界，#1606）\n"
        "       上限：单函数 ≤ 60 行；新增视图文件 lines ≤ 400 / query ≤ 10 / commit ≤ 5",
        file=sys.stderr,
    )
    for rel, metric, current, limit, is_baseline in violations:
        scope = "基线冻结（只减不增）" if is_baseline else f"新增上限 {limit}"
        print(f"  {rel}: {metric} = {current}（{scope}）", file=sys.stderr)
    print(
        "\n      缩小体积的正解是把业务规则搬到 services（视图只留入参解析 / 归属校验 / 调服务 / 组响应）；\n"
        "      确因合并需要重取基线：python scripts/check_view_thickness.py --report 并说明理由。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
