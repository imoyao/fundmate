#!/usr/bin/env python3
"""TD-010 / TD-011 收口守卫（静态锚点；纯标准库，CI 用 python 即可，无需 pytest 环境）。

TD-010 市值基准统一：家庭总资产（summary_service._per_ledger_buckets）与品类聚合
（position_aggregation）必须同源走库内 T 日最新净值。锚点 = 两条链路都把
``effective_nav`` 注入 ``market_value_cents(..., effective_nav_yuan=...)``。
任一处回退到快照价 current_price，市值即分叉 → 守卫红。

TD-011 已实现盈亏唯一口径：asset_snapshots 四列（移动加权平均）已废弃，唯一真值源
= FIFO（cleared_cycles）。锚点 = models.py 四列带 ``[DEPRECATED TD-011]`` 标记。

退出码：0 = 收口成立；1 = 任一口径回退（CI 阻断）。
运行时更强证明由 backend 契约测试提供：
- tests/services/test_valuation_baseline_contract.py （两链路市值分差=0）
- tests/services/test_snapshot_pnl.py::TestMarketValueBasisUnification / ::TestFifoCanonicalRealizedPnl
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (相对路径, 正则, 说明)
CHECKS: list[tuple[str, str, str]] = [
    (
        "backend/app/services/summary_service.py",
        r"market_value_cents\(\s*p,\s*rate=rate,\s*effective_nav_yuan=effective_nav\s*\)",
        "TD-010: 家庭总资产走 T 日最新净值（effective_nav 注入 market_value_cents）",
    ),
    (
        "backend/app/services/position_aggregation.py",
        r"effective_nav_yuan=effective_nav",
        "TD-010: 品类聚合走 T 日最新净值（与 summary 同源）",
    ),
    (
        "backend/app/domains/summary/models.py",
        r"\[DEPRECATED TD-011\]",
        "TD-011: asset_snapshots 四列标废弃，唯一盈亏真值源=FIFO",
    ),
]


def _code_body(path: Path) -> str:
    """剥掉整行 ``#`` 注释，避免注释里的同名字面量假绿（#2453）。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines if not ln.lstrip().startswith("#")]
    return "\n".join(kept)


def main() -> int:
    ok = True
    for rel, pattern, desc in CHECKS:
        p = ROOT / rel
        if not p.is_file():
            print(f"[FAIL] 文件缺失: {rel} —— {desc}")
            ok = False
            continue
        if re.search(pattern, _code_body(p)):
            print(f"[OK]   {desc}")
        else:
            print(f"[FAIL] {desc}（未在 {rel} 命中 {pattern!r}）")
            ok = False
    if not ok:
        print("guard_basis_unification: 收口被破坏，请回退对应改动")
        return 1
    print("guard_basis_unification: TD-010/TD-011 收口成立")
    return 0


if __name__ == "__main__":
    sys.exit(main())
