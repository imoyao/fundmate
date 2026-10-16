#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：禁止在「总资产」唯一聚合实现之外再写一份累加（#2154 → #2179）。

WHY
---
`summary_service.py` 里「总资产」曾经有**四处**各自累加，其中两处漏改以后真实分叉：
balance 模式（无份额无价格、市值靠 `market_value_override`）的持仓在
`/api/summary/` 算 123456.78 元、在 `account_groups` 里**恒为 0**——同一个接口两个数。
#2154 把它们收敛成 `family_totals` 这一个出口，并加了契约测试（多出口数值必须相等）。

但那一轮**留下了一个同型的第五处**：`get_ledger_distributions`（账户级快照）把
`family_totals` 的累加逻辑**逐字重写了一遍**——持仓走 `market_value_cents`、
排除非正数资产、负债单独归桶、孤儿流水并入，一模一样。它当时被划出范围是合理的
（账户级、归哨兵键 0、有独立契约），但它就是本卡要杀的**那个形态本身**：
口径一旦再变，这里就是「下次漏改的那一处」。它当时只靠
`test_account_snapshots.py` 里一条埋在别处的断言兜着——**靠人找**。

#2179 已让两处共用 `_per_ledger_buckets`（家庭桶 = 各账户桶按位相加）。
本守卫负责把这条从「写在注释里」变成「CI 会红」：**新增的累加必须委托唯一实现**。

判据（AST，纯标准库，只扫摘要聚合这一个文件）
------------------------------------------------
在 `backend/app/services/summary_service.py` 里，出现
「对 `total_assets` / `total_liabilities` / `net_worth` 做 `+=`」即报红——
那是「又有人手写了一份累加」的唯一信号。

**合法的是委托**：`family_totals` 与 `get_ledger_distributions` 现在都只是
`_per_ledger_buckets` 的消费者，自身一个 `+=` 都没有。

> 初版还写了第二判据「加载了 `_load_user_assets` 却不委托唯一实现」，
> 上线即报出 4 处**全是误报**（`get_account_groups` 按账户名分组、`get_position_groups`
> 出明细、`family_pnl_cents` / `get_ledger_pnl` 算盈亏）——那三个函数算的根本不是总资产。
> 判据「函数碰了什么数据」拦不住这事：**碰同一批数据是常态，累加同一个桶才是分叉信号**。
> 故删掉第二判据（宁可漏判形态怪异的写法，不可把正常函数全判红——恒红的检查等于没有检查）。

白名单（`ALLOWED_HELPERS`）
----------------------------
- `_per_ledger_buckets`：唯一累加实现本身（它就是「那一份」）；
- `family_totals`：只做桶相加，允许它出现 `+=`（但它必须调 `_per_ledger_buckets`）。

判据边界（刻意，写下来免得下一个人以为是漏判）
------------------------------------------------
- **只扫这一个文件**：这是「总资产口径」的归属文件。别处（如 `ledger_service`）的桶
  属账户资金全景，各有独立契约，不是本守卫的射程。
- **只认 `+=` 与 `total_assets` / `total_liabilities`**：不做全量数据流分析。
  代价是「用 `sum(...)` 或局部变量绕开」会漏判——但那种写法一眼就看得出来，
  且它绕开的是**本守卫**而不是**契约测试**（数值仍然会被 `test_summary_total_assets_contract.py` 咬住）。
- 行内豁免：在**声明行或其上一行**加注释 ``summary-aggregation-allow`` 并写明理由。

用法
----
    python scripts/guard_summary_aggregation.py            # 扫默认文件
    python scripts/guard_summary_aggregation.py a.py       # 只扫指定文件（合成样例 / 局部验证）

退出码：0 = 通过；1 = 命中栅栏；2 = 参数/文件错误。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILE = REPO_ROOT / 'backend' / 'app' / 'services' / 'summary_service.py'

SKIP_MARKER = 'summary-aggregation-allow'

# 被聚合的三个桶名
BUCKET_NAMES = {'total_assets', 'total_liabilities', 'net_worth'}
# 允许做桶相加的出口：唯一实现本身 + 家庭级出口（它 = 各账户桶按位相加）
ALLOWED_HELPERS = {'_per_ledger_buckets', 'family_totals'}


def _line_marked(lines: list[str], lineno: int) -> bool:
    """声明行或其上一行带豁免标记即放行（行号从 1 开始）。"""
    for idx in (lineno, lineno - 1):
        if 1 <= idx <= len(lines) and SKIP_MARKER in lines[idx - 1]:
            return True
    return False


def _buckets_augmented_in(node: ast.AST) -> list[tuple[int, str]]:
    """找出函数体里所有对桶名的累加：`x += ...` 与 `x = x + ...` 两种写法都算。

    只认「对桶名本身赋值」：构造桶（`total_assets = 0.0`）不是累加，放行。
    """
    out: list[tuple[int, str]] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.AugAssign):
            name = _bucket_name(sub.target)
            if name:
                out.append((sub.lineno, name))
        elif isinstance(sub, ast.Assign) and isinstance(sub.value, ast.BinOp) and isinstance(sub.value.op, ast.Add):
            # `x = x + y`：左边是桶、右边引用同名桶，才算累加（`total = a + b` 不算）
            for target in sub.targets:
                name = _bucket_name(target)
                if name and _bucket_name(sub.value.left) == name:
                    out.append((sub.lineno, name))
                    break
    return out


def _bucket_name(target: ast.expr) -> str | None:
    """把 `total_assets` / `bucket['total_assets']` / `totals[k]['total_assets']` 归一成桶名。"""
    if isinstance(target, ast.Name) and target.id in BUCKET_NAMES:
        return target.id
    if isinstance(target, ast.Subscript):
        sl = target.slice
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str) and sl.value in BUCKET_NAMES:
            return sl.value
    return None


def _functions(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def scan(path: Path) -> tuple[list[str], int]:
    """返回 (违规列表, 文件数)。文件不可读时抛 OSError 交调用方处理。"""
    raw = path.read_text(encoding='utf-8')
    lines = raw.splitlines()
    tree = ast.parse(raw, filename=str(path))
    rel = path.relative_to(REPO_ROOT).as_posix() if path.is_absolute() and REPO_ROOT in path.parents else str(path)

    violations: list[str] = []
    for fn in _functions(tree):
        hits = _buckets_augmented_in(fn)
        if not hits:
            continue
        if fn.name in ALLOWED_HELPERS:
            continue
        for lineno, bucket in hits:
            if _line_marked(lines, lineno):
                continue
            violations.append(
                f'{rel}:{lineno}  函数 {fn.name}() 自己累加 `{bucket} += ...`'
                ' —— 请委托 _per_ledger_buckets / family_totals（#2179）'
            )

    return violations, 1


def main(argv: list[str]) -> int:
    targets = [a for a in argv if not a.startswith('-')]
    paths = [Path(t) for t in targets] if targets else [DEFAULT_FILE]

    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        # 拿不到输入 ≠ 没有违规：退 2 并说清，不得退化成「通过」（#171 的失败态纪律）
        print(f'ERROR: 目标文件不存在：{", ".join(missing)}', file=sys.stderr)
        return 2

    violations: list[str] = []
    for path in paths:
        try:
            found, _ = scan(path)
        except (UnicodeDecodeError, SyntaxError, OSError) as exc:
            print(f'ERROR: 无法解析 {path}：{exc}', file=sys.stderr)
            return 2
        violations.extend(found)

    if violations:
        print('ERROR: 发现「总资产」的又一份手写累加（#2154 / #2179）：', file=sys.stderr)
        for v in violations:
            print(f'  - {v}', file=sys.stderr)
        print(
            '\n正确做法：累加只在 _per_ledger_buckets 里做一次；'
            '家庭级用 family_totals()、账户级用 get_ledger_distributions()。',
            file=sys.stderr,
        )
        return 1

    print(f'OK: 总资产聚合未分叉（扫描 {len(paths)} 个文件，唯一实现 _per_ledger_buckets 有效）')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
