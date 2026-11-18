# -*- coding: utf-8 -*-
"""只读审计：把 `position_id IS NULL` 的孤儿流水按写入时间聚簇成「导入批次」（#2875）。

背景
----
`audit_orphan_transactions.py`（#950）回答的是「哪些孤儿**本应**挂持仓」；
本脚本回答它的前置问题：**这批孤儿是从哪来的**——按 `created_at` 把 669 笔
切成若干「导入批次」，为每一批给出定性结论，让后续处置（挂回 / 补建清仓
持仓 / 修正 ledger）可以按批决策，而不是逐行猜。

批次判定
--------
- 把 `created_at` 截到分钟；同一分钟内的孤儿视为同一次写入；
- 相邻分钟间隔 ≤ `--gap-minutes`（默认 10）的簇合并为同一批次。
  导入器逐行写入时同批次通常落在同一分钟；10 分钟的间隙足以隔开两次人工操作。

行级定性（与 #950 审计口径一致，互斥）
--------------------------------------
- `legal_cash`：机制内的合法孤儿——`symbol='__CASH__'` 哨兵、存取
  （`type IN ('deposit','withdraw')`）、`asset_type ∈ CASH_EQUIVALENT_ASSET_TYPES`
  （货基 / 逆回购口径 A 记账）。这些**不需要修复**；
- `unanchored`：其余全部——按批次进入 symbol 级判定。

symbol 级判定（仅 `unanchored` 且有 symbol 的行，按 `(ledger_id, 归一化代码)` 聚合）
----------------------------------------------------------------------------------
- `reattachable`：唯一命中同 ledger 现存持仓 → 可直接挂回（走 #950 的
  `emit_sql` 路径，本脚本不代做）；
- `ambiguous`    ：同 ledger 同名持仓 ≥ 2 → 需人工判定；
- `cleared_history`：未命中持仓且买卖净数量 = 0 → 历史上买过又清仓，
  持仓行已不存在（「清仓删行」的历史受害者）；
- `sell_without_buy`：未命中且净数量 < 0 → 库里只有卖出没有买入
  （导入文件缺买入段，典型如券商导出窗口不覆盖建仓期）；
- `unpositioned` ：未命中且净数量 > 0 → 仍持有但从未建仓，
  **总资产存在漏算缺口**，优先级最高。

只读保证：与 #950 审计相同——`mode=ro` 打开，不开写事务，不产出 UPDATE。

用法
----
  pdm run python scripts/audit_orphan_batches.py
  pdm run python scripts/audit_orphan_batches.py --db backend/invest.db
  pdm run python scripts/audit_orphan_batches.py --gap-minutes 10 --json-out batches.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# 归一化 / 持仓索引 / 现金等价类型直接复用 #950 审计的实现，避免第三份复刻
from audit_orphan_transactions import (  # noqa: E402
    CASH_EQUIVALENT_ASSET_TYPES,
    build_position_index,
    normalize_fund_code,
)

DEFAULT_DB = 'invest.db'
DEFAULT_GAP_MINUTES = 10

DEPOSIT_WITHDRAW_TYPES = ('deposit', 'withdraw')
CASH_SENTINEL = '__CASH__'

_ORPHAN_SQL = (
    'SELECT t.id, t.created_at, t.ledger_id, t.symbol, t.asset_type, t.type, '
    '       t.quantity, t.amount, t.trade_date, t.confirm_date, t.position_name '
    'FROM transactions t '
    'WHERE t.position_id IS NULL '
    'ORDER BY t.created_at, t.id'
)

BUY_TYPES = ('buy', 'subscribe')
SELL_TYPES = ('sell', 'redeem')


def is_legal_cash_orphan(symbol: str, asset_type: str | None, txn_type: str) -> bool:
    """机制内合法孤儿：现金哨兵 / 存取 / 货基逆回购（金额即本金，不进持仓桶）。"""
    if symbol == CASH_SENTINEL:
        return True
    if txn_type in DEPOSIT_WITHDRAW_TYPES:
        return True
    return asset_type in CASH_EQUIVALENT_ASSET_TYPES


def _minute_of(created_at: str) -> str:
    """`2026-08-29 16:59:12.3` → `2026-08-29 16:59`。"""
    return (created_at or '')[:16]


def _minute_key(minute: str) -> int:
    return int(minute.replace('-', '').replace(' ', '').replace(':', ''))


def group_by_batch(rows: list[dict], gap_minutes: int) -> list[list[dict]]:
    """按 created_at 分钟聚簇，相邻簇间隔 ≤ gap_minutes 合并成批次。

    行须已按 created_at 排序（SQL 里已保证）。
    """
    by_minute: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_minute[_minute_of(r['created_at'])].append(r)

    batches: list[list[dict]] = []
    for minute in sorted(by_minute):
        if batches and _minute_key(minute) - _minute_key(_minute_of(batches[-1][-1]['created_at'])) <= gap_minutes:
            batches[-1].extend(by_minute[minute])
        else:
            batches.append(list(by_minute[minute]))
    return batches


def _net_qty(txns: list[dict]) -> int:
    """该 symbol 组内的买卖净数量（0.0001 份原始单位）。"""
    net = 0
    for t in txns:
        q = t['quantity'] or 0
        if t['type'] in BUY_TYPES:
            net += q
        elif t['type'] in SELL_TYPES:
            net -= abs(q)
    return net


def judge_symbol_group(code: str, ledger_id: int, txns: list[dict], pos_index: dict) -> str:
    """对同 ledger 同代码的孤儿组给出处置判定（见模块 docstring 五种 verdict）。"""
    hits = pos_index.get((ledger_id, code), [])
    if len(hits) == 1:
        return 'reattachable'
    if len(hits) > 1:
        return 'ambiguous'
    net = _net_qty(txns)
    if net == 0:
        return 'cleared_history'
    return 'sell_without_buy' if net < 0 else 'unpositioned'


def build_batches(conn: sqlite3.Connection, gap_minutes: int) -> dict:
    """主分析：返回批次列表与汇总。纯读取。"""
    pos_index = build_position_index(conn)
    rows = [
        {
            'id': r[0],
            'created_at': r[1],
            'ledger_id': r[2],
            'symbol': r[3],
            'asset_type': r[4],
            'type': r[5],
            'quantity': r[6],
            'amount': r[7],
            'trade_date': r[8],
            'confirm_date': r[9],
            'position_name': r[10],
        }
        for r in conn.execute(_ORPHAN_SQL).fetchall()
    ]
    raw_batches = group_by_batch(rows, gap_minutes)

    batches = []
    for batch_rows in raw_batches:
        legal = [r for r in batch_rows if is_legal_cash_orphan(r['symbol'] or '', r['asset_type'], r['type'])]
        unanchored = [r for r in batch_rows if not is_legal_cash_orphan(r['symbol'] or '', r['asset_type'], r['type'])]

        # symbol 级判定：unanchored 且有 symbol 的行按 (ledger, code) 聚合
        sym_groups: dict[tuple, list[dict]] = defaultdict(list)
        for r in unanchored:
            code = normalize_fund_code(r['symbol'] or '')
            if code:
                sym_groups[(r['ledger_id'], code)].append(r)
        verdicts: dict[str, int] = defaultdict(int)
        for (ledger_id, code), txns in sym_groups.items():
            verdicts[judge_symbol_group(code, ledger_id, txns, pos_index)] += 1

        nosym_unanchored = [r for r in unanchored if not normalize_fund_code(r['symbol'] or '')]
        batches.append(
            {
                'window_start': _minute_of(batch_rows[0]['created_at']),
                'window_end': _minute_of(batch_rows[-1]['created_at']),
                'total': len(batch_rows),
                'legal_cash': len(legal),
                'unanchored': len(unanchored),
                'unanchored_no_symbol': len(nosym_unanchored),
                'ledgers': dict(sorted(_tally(r['ledger_id'] for r in batch_rows).items(), key=lambda x: str(x[0]))),
                'types': dict(_tally(r['type'] for r in batch_rows)),
                'with_trade_date': sum(1 for r in batch_rows if r['trade_date'] is not None),
                'with_confirm_date': sum(1 for r in batch_rows if r['confirm_date'] is not None),
                'net_amount': sum(r['amount'] or 0 for r in batch_rows),
                'symbol_verdicts': dict(verdicts),
                'sample_ids': [r['id'] for r in batch_rows[:5]],
            }
        )

    return {
        'total_orphans': len(rows),
        'batch_count': len(batches),
        'batches': batches,
    }


def _tally(values) -> dict:
    out: dict = defaultdict(int)
    for v in values:
        out[v] += 1
    return dict(out)


def _fmt_batch(i: int, b: dict) -> str:
    lines = [
        '\n批次 %d：[%s ~ %s]  %d 笔（合法现金 %d / 无锚 %d，其中无 symbol %d）'
        % (
            i,
            b['window_start'],
            b['window_end'],
            b['total'],
            b['legal_cash'],
            b['unanchored'],
            b['unanchored_no_symbol'],
        ),
        '  ledger=%s  类型=%s' % (b['ledgers'], b['types']),
        '  trade_date 非空 %d / confirm_date 非空 %d / 净额 %.0f 元'
        % (b['with_trade_date'], b['with_confirm_date'], b['net_amount'] / 100),
    ]
    if b['symbol_verdicts']:
        zh = {
            'reattachable': '可挂回',
            'ambiguous': '歧义',
            'cleared_history': '已清仓历史',
            'sell_without_buy': '无源卖出',
            'unpositioned': '应建仓未建仓',
        }
        parts = ['%s %d 个品种' % (zh[k], v) for k, v in sorted(b['symbol_verdicts'].items())]
        lines.append('  品种判定：%s' % '；'.join(parts))
    lines.append('  样例 id=%s' % b['sample_ids'])
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description='只读审计：孤儿流水按写入时间聚簇成导入批次（#2875）')
    parser.add_argument('--db', default=DEFAULT_DB, help='SQLite 数据库路径（默认 invest.db）')
    parser.add_argument('--gap-minutes', type=int, default=DEFAULT_GAP_MINUTES, help='相邻分钟簇合并阈值（默认 10）')
    parser.add_argument('--json-out', default=None, help='把结果写入 JSON 文件')
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print('[错误] 数据库不存在: %s' % db_path)
        return 1

    conn = sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        missing = {'transactions', 'positions'} - tables
        if missing:
            print('[错误] 目标库缺少表: %s' % ', '.join(sorted(missing)))
            return 1

        result = build_batches(conn, args.gap_minutes)

        print('库: %s' % db_path)
        print('孤儿流水（position_id IS NULL）共 %d 笔 → %d 个批次' % (result['total_orphans'], result['batch_count']))
        for i, b in enumerate(result['batches'], 1):
            print(_fmt_batch(i, b))

        if args.json_out:
            Path(args.json_out).write_text(
                json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8'
            )
            print('\n[JSON 已写入] %s' % args.json_out)

        print('\n[只读] 未修改任何数据。')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
