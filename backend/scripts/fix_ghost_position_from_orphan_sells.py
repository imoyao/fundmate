# -*- coding: utf-8 -*-
"""修正「孤儿卖出挂回但份额未扣减」的幽灵持仓（017074 实测一次性修复）。

## 背景

支付宝交易导入时若库中尚无对应持仓，卖出记录会降级为 `position_id=NULL`
的孤儿流水；`orphan_backfill_job` 后来按身份把它们挂回持仓，但（PR #2430
之前的版本）只补 `position_id`、不重算份额——账面份额停留在「买入总量」，
形成已清仓却显示市值的幽灵持仓。017074（嘉实清洁能源C）实测：买入合计
2857.31 份、卖出合计 2858 份，账面却仍为 2858.29 份（市值约 2350 元）。

代码根因已由 PR #2430 修复（挂回后调 recompute_position_from_transactions），
本脚本负责一次性修正**存量数据**。

## 口径

与 `recompute_position_from_transactions` 的「无锚点」分支逐行对齐：

    net = Σ(buy/deposit/split 的 quantity) − Σ(sell/withdraw 的 quantity)

- net <= 0（含超卖）→ `quantity=0`、`ownership_status='cleared'`、
  `cleared_at=最后一笔卖出/取出的确认日`（业务事实，非墙钟）；
- net > 0 → `quantity=net`、`ownership_status='active'`、`cleared_at=NULL`。

## 安全约束

- 默认 **dry-run**，只打印计划改动；`--apply` 才写入；
- 写入前自动整库备份到 `backend/data/backup_invest_<时间戳>.db`；
- 仅处理**无快照锚点**（`snapshot_quantity IS NULL`）的持仓；有锚点的
  跳过并报错退出——锚点口径不同（快照份额即基线），交人工/对账工作台；
- 同步把该 symbol 的 pending 对账差异置为 `cleared`（修复后理论=实际，
  差异已不存在；与对账任务「无差异的旧差异置 cleared」同语义）。

用法：
    python scripts/fix_ghost_position_from_orphan_sells.py                 # dry-run 全部可疑持仓
    python scripts/fix_ghost_position_from_orphan_sells.py --symbol 017074 # 只看某一只
    python scripts/fix_ghost_position_from_orphan_sells.py --symbol 017074 --apply
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# 份额变动方向（与 position_service._derive_state_from_txns 同口径）
_QTY_IN_TYPES = ('buy', 'deposit', 'split')
_QTY_OUT_TYPES = ('sell', 'withdraw')

DEFAULT_DB = Path(__file__).resolve().parents[1] / 'invest.db'
BACKUP_DIR = Path(__file__).resolve().parents[1] / 'data'


def find_positions(con: sqlite3.Connection, symbol: str) -> list:
    return con.execute(
        'SELECT id, symbol, name, account_name, ledger_id, quantity, avg_price,'
        ' ownership_status, cleared_at, snapshot_quantity, snapshot_date'
        ' FROM positions WHERE symbol = ?',
        (symbol,),
    ).fetchall()


def net_quantity(con: sqlite3.Connection, position_id: int) -> int:
    """流水净份额（min-unit，0.0001 份/单位）。无锚点口径 = 全量流水净额。"""
    row = con.execute(
        'SELECT COALESCE(SUM(CASE WHEN type IN (?, ?, ?) THEN quantity'
        ' WHEN type IN (?, ?) THEN -quantity ELSE 0 END), 0) AS net'
        ' FROM transactions WHERE position_id = ?',
        (*_QTY_IN_TYPES, *_QTY_OUT_TYPES, position_id),
    ).fetchone()
    return int(row['net'] or 0)


def last_sell_confirm_date(con: sqlite3.Connection, position_id: int):
    row = con.execute(
        'SELECT MAX(confirm_date) AS d FROM transactions WHERE position_id = ? AND type IN (?, ?)',
        (position_id, *_QTY_OUT_TYPES),
    ).fetchone()
    return row['d'] if row else None


def plan_one(con: sqlite3.Connection, pos) -> dict | None:
    """计算单个持仓的计划改动；返回 None 表示无需处理。"""
    if pos['snapshot_quantity'] is not None:
        print(
            f'[跳过] position={pos["id"]} {pos["symbol"]} 有快照锚点'
            f'（snapshot_date={pos["snapshot_date"]}），口径不同，交人工/对账工作台处理'
        )
        return None

    net = net_quantity(con, pos['id'])
    current_qty = int(pos['quantity'] or 0)
    if net == current_qty and (net > 0) == (pos['ownership_status'] == 'active'):
        print(f'[无需处理] position={pos["id"]} {pos["symbol"]} 账面与流水一致（{current_qty}）')
        return None

    if net <= 0:
        new_qty = 0
        new_status = 'cleared'
        cleared_at = last_sell_confirm_date(con, pos['id'])
        if cleared_at is None:
            print(f'[异常] position={pos["id"]} {pos["symbol"]} 净额<=0 但无卖出流水，跳过')
            return None
    else:
        new_qty = net
        new_status = 'active'
        cleared_at = None

    return {
        'id': pos['id'],
        'symbol': pos['symbol'],
        'old_qty': current_qty,
        'new_qty': new_qty,
        'old_status': pos['ownership_status'],
        'new_status': new_status,
        'cleared_at': cleared_at,
    }


def apply_one(con: sqlite3.Connection, plan: dict) -> None:
    con.execute(
        'UPDATE positions SET quantity = ?, ownership_status = ?, cleared_at = ?, updated_at = ? WHERE id = ?',
        (plan['new_qty'], plan['new_status'], plan['cleared_at'], datetime.now().isoformat(sep=' '), plan['id']),
    )
    con.execute(
        "UPDATE discrepancies SET status = 'cleared' WHERE symbol = ? AND status = 'pending'",
        (plan['symbol'],),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--symbol', default='017074', help='基金/证券代码（默认 017074）')
    parser.add_argument('--db', default=str(DEFAULT_DB), help='SQLite 库路径')
    parser.add_argument('--apply', action='store_true', help='实际写入（默认 dry-run）')
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f'库不存在: {db_path}')
        return 1

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    positions = find_positions(con, args.symbol)
    if not positions:
        print(f'未找到 symbol={args.symbol} 的持仓')
        con.close()
        return 0

    plans = []
    for pos in positions:
        plan = plan_one(con, pos)
        if plan:
            plans.append(plan)

    if not plans:
        print('没有需要修正的持仓')
        con.close()
        return 0

    print(f'\n待修正 {len(plans)} 条：')
    for p in plans:
        print(
            f'  position={p["id"]} {p["symbol"]}: quantity {p["old_qty"]} -> {p["new_qty"]},'
            f' status {p["old_status"]} -> {p["new_status"]}, cleared_at={p["cleared_at"]}'
        )

    if not args.apply:
        print('\n(dry-run，未写入。加 --apply 执行修正)')
        con.close()
        return 0

    # 写入前整库备份
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = BACKUP_DIR / f'backup_invest_{stamp}.db'
    shutil.copy2(db_path, backup)
    print(f'\n已备份: {backup}')

    for p in plans:
        apply_one(con, p)
    con.commit()
    print(f'已修正 {len(plans)} 条持仓，同步清理 pending 对账差异')

    # 复核
    for pos in find_positions(con, args.symbol):
        print(
            f'  复核 position={pos["id"]} {pos["symbol"]}: quantity={pos["quantity"]},'
            f' status={pos["ownership_status"]}, cleared_at={pos["cleared_at"]}'
        )

    con.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
