# -*- coding: utf-8 -*-
"""修正 ``asset_snapshots`` 历史行里被「跨账本重复导入虚增」污染的值（默认 dry-run）。

## 背景（2026-10-28）

``ledger 3``（微众银行）因 #1076 放行机制导错账本，混入了 415 笔银河交割单副本，
其中 152 笔货基孤儿流水按 ``_ledger_snapshot`` 口径计入类现金，使 ``asset_snapshots``
的每一行都虚高。2026-10-28 已删除这 415 笔流水，删除后家庭总资产精确减少
506,021.09 元——这是虚增常量的**实证值**（不是推导值）。

## 为什么这次「修历史」是允许的（对 D62 的边界补充）

D62 禁止的是**用当下的引擎写一条标签为历史日期的行**（伪造）。
本脚本做的是**修错**：日期是对的、值是错的，且正确值可精确推导——

- 孤儿货基流水（152 笔）按日累计全部落在 2022-12-23 ~ 2023-12-01，
  此后累计净额**恒为常量** 506,021.09 元；
- 快照区间（2026-08-10 起）完全晚于 2023-12-01，故每一行的虚增都是同一常量；
- 删除操作前后的总资产差额实证了这个常量。

所以每行修正 = 原值 − 常量，不是估算、不是贴当下的值。

## 修正规则

- **账户级（ledger 3）**：``total_assets`` / ``net_worth`` 各减 ``INFLATION_CENTS``；
  ``total_liabilities`` 不动（孤儿是资产侧）。
- **家庭级（ledger_id IS NULL）**：同样各减常量。依据三重：
  ① 家庭级由实时全量数据计算，不依赖账户级行是否存在，虚增自 2023-12-01 起恒定；
  ② 家庭级序列无 ``|step| == INFLATION_CENTS`` 的精确台阶（虚增从未中途消失）；
  ③ 09-01 起有账户级行相伴，修正后可用「家庭级 == Σ账户级」硬断言。
  08-10 ~ 08-29 的行无账户级伴随（当时根本没有账户级快照），只有①②依据，
  脚本会逐日列出供人工复核。

## 断言（apply 前单事务内全量复验，任一失败即回滚）

1. 每行 ``net_worth == total_assets - total_liabilities``；
2. 有账户级行的日期：修正后家庭级 == Σ账户级。

## 安全设计

- 必须显式 ``--db``；标准库 sqlite3 直连，不导入应用会话。
- 默认 dry-run；``--apply`` 先 ``Connection.backup()`` 整库备份，再单事务执行。

## 用法

    python scripts/fix_asset_snapshots_orphan_inflation.py --db invest.db           # dry-run
    python scripts/fix_asset_snapshots_orphan_inflation.py --db invest.db --apply   # 执行
"""

from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

# 虚增常量（分）。来源：删除 415 笔跨账本副本流水后，家庭总资产精确减少的量。
# 备份库逐日累计复算：152 笔孤儿货基流水净额累计自 2023-12-01 起恒为此值。
INFLATION_CENTS = 50_602_109
LEDGER_ID = 3


def _backup(db_path: Path) -> Path:
    bak = db_path.with_name(f'{db_path.name}.bak-{dt.datetime.now():%Y%m%d-%H%M%S}-snapshot-fix')
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(bak))
    src.backup(dst)
    dst.close()
    src.close()
    return bak


def _fetch_rows(con: sqlite3.Connection) -> list[sqlite3.Row]:
    con.row_factory = sqlite3.Row
    return con.execute(
        'SELECT id, ledger_id, snapshot_date, total_assets, total_liabilities, net_worth'
        ' FROM asset_snapshots ORDER BY snapshot_date, ledger_id IS NOT NULL, ledger_id'
    ).fetchall()


def _group_by_date(rows: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
    by_date: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        by_date.setdefault(r['snapshot_date'], []).append(r)
    return by_date


def _plan(con: sqlite3.Connection) -> tuple[list[int], list[int], list[str]]:
    """返回 (账户级待修 id, 家庭级待修 id, 报告行)。"""
    rows = _fetch_rows(con)
    by_date = _group_by_date(rows)

    # 前置校验②：家庭级序列不得出现 |step| == 常量的台阶（否则虚增曾中途消失/出现，
    # 「每行同减常量」不成立）
    fam_rows = [r for r in rows if r['ledger_id'] is None]
    fam_rows.sort(key=lambda r: r['snapshot_date'])
    for prev, cur in zip(fam_rows, fam_rows[1:]):
        step = cur['total_assets'] - prev['total_assets']
        if abs(step) == INFLATION_CENTS:
            print(
                f'前置校验失败: {prev["snapshot_date"]} -> {cur["snapshot_date"]} '
                f'台阶 {step} == 虚增常量，序列形态与本脚本假设矛盾，拒绝执行',
                file=sys.stderr,
            )
            raise SystemExit(2)

    acct_ids = [r['id'] for r in rows if r['ledger_id'] == LEDGER_ID]
    fam_ids = [r['id'] for r in fam_rows]
    report: list[str] = []
    for day in sorted(by_date):
        day_rows = by_date[day]
        has_acct = any(r['ledger_id'] == LEDGER_ID for r in day_rows)
        if not has_acct:
            fam = [r for r in day_rows if r['ledger_id'] is None]
            if fam:
                report.append(
                    f'{day}: 家庭级将修正，但当日无账户级行伴随'
                    '（依据「实时全量计算 + 序列无台阶」，无汇总断言，需人工复核）'
                )
    return acct_ids, fam_ids, report


def _apply(con: sqlite3.Connection, acct_ids: list[int], fam_ids: list[int]) -> None:
    cur = con.cursor()
    for tid in acct_ids + fam_ids:
        cur.execute(
            'UPDATE asset_snapshots'
            ' SET total_assets = total_assets - ?, net_worth = net_worth - ?,'
            '     updated_at = CURRENT_TIMESTAMP'
            ' WHERE id = ?',
            (INFLATION_CENTS, INFLATION_CENTS, tid),
        )


def _verify(
    con: sqlite3.Connection,
    acct_ids: list[int],
    fam_ids: list[int],
    baseline: dict[str, tuple[int, int]],
) -> list[str]:
    """baseline: 修正前每日 (家庭级 total_assets, Σ账户级 total_assets)。

    断言 2 是**不变式**而非强制等式：修正前就相等的日期，修正后必须仍相等；
    修正前就不相等的（快照体系既有债：账户级行不全/取数时点扰动，与本次虚增
    无关），不阻断，只列为差异报告供人工复核。
    """
    errs: list[str] = []
    rows = _fetch_rows(con)
    # 断言 1：净等式逐行成立
    for r in rows:
        if (r['total_assets'] - r['total_liabilities']) != r['net_worth']:
            errs.append(f'id={r["id"]} {r["snapshot_date"]}: net_worth != assets - liabilities')
    # 断言 2（不变式）：基线相等的日期，修正后仍相等
    by_date = _group_by_date(rows)
    for day, (fam_before, sum_before) in sorted(baseline.items()):
        if fam_before != sum_before:
            continue
        day_rows = by_date.get(day, [])
        sum_acct = sum(r['total_assets'] for r in day_rows if r['ledger_id'] is not None)
        for fam in (r for r in day_rows if r['ledger_id'] is None):
            if fam['total_assets'] != sum_acct:
                errs.append(f'{day}: 基线相等，修正后失恒：家庭级 {fam["total_assets"]} != Σ账户级 {sum_acct}')
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--db', required=True, help='SQLite 库文件路径')
    ap.add_argument('--apply', action='store_true', help='真正写入（默认 dry-run）')
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f'库不存在: {db_path}', file=sys.stderr)
        return 2

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        # 前置校验①：当前库 ledger 3 应已无孤儿货基流水（已清理），否则常量不再成立
        leftover = con.execute(
            'SELECT COUNT(*) FROM transactions WHERE ledger_id=? AND position_id IS NULL'
            " AND asset_type IN ('money_fund','reverse_repo') AND COALESCE(is_income,0)=0"
            " AND type IN ('buy','deposit','sell','withdraw')",
            (LEDGER_ID,),
        ).fetchone()[0]
        if leftover:
            print(
                f'ledger {LEDGER_ID} 仍有 {leftover} 笔孤儿货基流水，常量不成立，拒绝执行',
                file=sys.stderr,
            )
            return 2

        acct_ids, fam_ids, report = _plan(con)
        rows = {r['id']: r for r in _fetch_rows(con)}
        print(f'账户级待修（ledger {LEDGER_ID}）: {len(acct_ids)} 行')
        print(f'家庭级待修: {len(fam_ids)} 行')
        if report:
            print(f'无账户级伴随日（仍将修正，需人工复核）: {len(report)}')
            for line in report:
                print('  -', line)
        if acct_ids:
            r = rows[acct_ids[0]]
            print(
                f'示例 {r["snapshot_date"]}: {r["total_assets"] / 100:,.2f}'
                f' -> {(r["total_assets"] - INFLATION_CENTS) / 100:,.2f}'
            )
        if fam_ids:
            r = rows[fam_ids[-1]]
            print(
                f'家庭级末日 {r["snapshot_date"]}: {r["total_assets"] / 100:,.2f}'
                f' -> {(r["total_assets"] - INFLATION_CENTS) / 100:,.2f}'
            )

        if not args.apply:
            print('\n[dry-run] 未写入。加 --apply 执行。')
            return 0

        # 基线：修正前每日 (家庭级, Σ账户级)，用于断言 2 的不变式判定
        rows_before = _fetch_rows(con)
        baseline: dict[str, tuple[int, int]] = {}
        for day, day_rows in _group_by_date(rows_before).items():
            fam = [r for r in day_rows if r['ledger_id'] is None]
            acct = [r for r in day_rows if r['ledger_id'] is not None]
            if fam and acct:
                baseline[day] = (
                    fam[0]['total_assets'],
                    sum(r['total_assets'] for r in acct),
                )
        equal_days = sum(1 for f, s in baseline.values() if f == s)
        uneven_days = len(baseline) - equal_days
        print(
            f'基线: {len(baseline)} 天有账户级伴随（相等 {equal_days} / 不等 {uneven_days}，'
            '不等的为快照体系既有债，仅报告不阻断）'
        )
        for day, (f, s) in sorted(baseline.items()):
            if f != s:
                print(f'  既有债 {day}: 家庭级−Σ账户级 = {(f - s) / 100:+,.2f} 元')

        bak = _backup(db_path)
        print(f'已备份: {bak}')
        con.execute('BEGIN')
        _apply(con, acct_ids, fam_ids)
        errs = _verify(con, acct_ids, fam_ids, baseline)
        if errs:
            con.rollback()
            for e in errs:
                print('VERIFY FAIL:', e, file=sys.stderr)
            print('已回滚，未落任何改动', file=sys.stderr)
            return 1
        con.commit()
        print(
            f'完成: 账户级 {len(acct_ids)} 行 + 家庭级 {len(fam_ids)} 行，'
            f'每行减 {INFLATION_CENTS} 分（{INFLATION_CENTS / 100:,.2f} 元）。'
        )
        return 0
    finally:
        con.close()


if __name__ == '__main__':
    raise SystemExit(main())
