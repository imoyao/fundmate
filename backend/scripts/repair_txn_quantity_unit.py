# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/26
"""修复历史导入交易 quantity 单位 bug（issue #1103）。

背景（根因，2026-08-26 排查）：
2026-06-16 d4d2b86 之前，PositionService.process_buy_or_deposit 把 quantity
以「份」数值直接入库（未乘 10000 转最小单位），price/amount 单位（分）正确。
受灾行特征：quantity * price ≈ amount（正确行应为 quantity * price ≈ amount * 10000）。
全库扫描（2026-08-26）：66 行受灾，全部为导入链路产物（带 import_hash）。

用法（backend 目录）：
pdm run python scripts/repair_txn_quantity_unit.py                 # DRY-RUN（默认）
pdm run python scripts/repair_txn_quantity_unit.py --apply         # 备份后执行修复
pdm run python scripts/repair_txn_quantity_unit.py --rollback      # 从备份表回滚
pdm run python scripts/repair_txn_quantity_unit.py --db <path>     # 指定库文件

安全措施：
- 默认 DRY-RUN，只列待修行，不写库；
- --apply 前自动建备份表 transactions_qty_repair_backup_20260826；
- --rollback 从备份表还原 quantity（备份表保留不删，可重复回滚）；
- 持仓表同批「份尺度」受害者只扫描报告，不自动改（快照覆盖语义需人工判断）。
"""

import argparse
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / 'invest.db'
BACKUP_TABLE = 'transactions_qty_repair_backup_20260826'

# 受灾特征：quantity(份) * price(分) ≈ amount(分)，2% 容差吸收手续费/舍入
DETECT_SQL = """
SELECT id, ledger_id, symbol, type, quantity, price, amount, confirm_date,
       import_hash IS NOT NULL AS has_hash
FROM transactions
WHERE quantity > 0 AND price > 0 AND amount > 0
  AND ABS(quantity * price - amount) <= amount * 0.02
"""


def detect(cur):
    """圈定受灾行：quantity*price ≈ amount（份尺度特征）。"""
    return cur.execute(DETECT_SQL).fetchall()


def scan_positions(cur):
    """扫描持仓表同批受害者（只报告不修改）。

    持仓 quantity 若为份尺度，会比其名下交易最小单位之和小约 10000 倍。
    """
    return cur.execute(
        """
        SELECT p.id, p.symbol, p.quantity AS pos_qty, SUM(t.quantity) AS txn_sum
        FROM positions p
        JOIN transactions t ON t.position_id = p.id
        WHERE p.quantity > 0
        GROUP BY p.id
        HAVING SUM(t.quantity) >= p.quantity * 10000
        """
    ).fetchall()


def do_repair(conn, rows):
    """备份后执行修复：quantity * 10000（份 → 最小单位）。"""
    cur = conn.cursor()
    ids = [r['id'] for r in rows]
    placeholders = ','.join('?' * len(ids))
    # 备份（幂等：已存在则跳过，保留最早一次快照）
    cur.execute(
        f'CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} AS SELECT * FROM transactions WHERE id IN ({placeholders})',
        ids,
    )
    cur.execute(
        f'UPDATE transactions SET quantity = quantity * 10000 WHERE id IN ({placeholders})',
        ids,
    )
    conn.commit()


def do_rollback(conn):
    """从备份表还原 quantity（按备份表快照覆盖，可重复执行）。"""
    cur = conn.cursor()
    cur.execute(
        f'UPDATE transactions SET quantity = (SELECT quantity FROM {BACKUP_TABLE} '
        f'WHERE {BACKUP_TABLE}.id = transactions.id) '
        f'WHERE id IN (SELECT id FROM {BACKUP_TABLE})'
    )
    conn.commit()
    print(f'[rollback] 已从 {BACKUP_TABLE} 还原 {cur.rowcount} 行')


def main():
    parser = argparse.ArgumentParser(description='修复历史导入交易 quantity 单位（#1103）')
    parser.add_argument('--apply', action='store_true', help='执行修复（默认 DRY-RUN）')
    parser.add_argument('--rollback', action='store_true', help='从备份表回滚')
    parser.add_argument('--db', default=str(DEFAULT_DB), help='SQLite 库文件路径')
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if args.rollback:
        do_rollback(conn)
        return

    rows = detect(cur)
    print(f'[detect] 受灾行: {len(rows)}')
    for r in rows:
        print(
            f'  id={r["id"]} ledger={r["ledger_id"]} {r["symbol"]} {r["type"]} '
            f'qty={r["quantity"]} price={r["price"]} amount={r["amount"]} '
            f'date={r["confirm_date"]} hash={"Y" if r["has_hash"] else "N"}'
        )

    if not rows:
        print('[done] 无受灾行，无需修复')
        return

    if not args.apply:
        print(f'[DRY-RUN] 共 {len(rows)} 行待修（quantity * 10000）。确认后加 --apply 执行。')
        return

    do_repair(conn, rows)
    print(f'[apply] 已修复 {len(rows)} 行，备份表: {BACKUP_TABLE}')

    # 修复后持仓扫描（报告不修改）
    suspects = scan_positions(cur)
    print(f'[position-scan] 持仓「份尺度」疑似受害者: {len(suspects)}')
    for s in suspects:
        print(
            f'  position id={s["id"]} {s["symbol"]} pos_qty={s["pos_qty"]} '
            f'txn_sum={s["txn_sum"]}（疑似份尺度，需人工判断）'
        )

    conn.close()


if __name__ == '__main__':
    main()
