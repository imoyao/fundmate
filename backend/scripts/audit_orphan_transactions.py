# -*- coding: utf-8 -*-
"""只读审计：`position_id` 为空的交易里，哪些「本应关联持仓」（#950）。

背景
----
`transactions.position_id IS NULL` 长期被当成「孤儿交易」的同义词，但多数是**合法**的：

- **账户级操作**（`symbol` 为空：存取 / 费用 / 税）——按设计就没有对应持仓；
- **货基 / 逆回购流水**——口径 A 下以孤儿流水记账，**金额即本金**，不进持仓桶。

真正的问题只有一类：**`symbol` 能匹配到同 ledger 同名持仓、却仍 `position_id` 为空**。
这类流水会两边都不算——既不在持仓桶（按 position 聚合），也不在孤儿净额桶
（`summary_service._ORPHAN_FLOW_ASSET_TYPES` 只认 `money_fund` / `reverse_repo`），
却被绩效口径**显式纳入**（`performance/calculators.py:176` 的
`asset_type.is_(None) | not_in(EXCLUDED_ASSET_TYPES)`），因此会进 XIRR 现金流。

写入侧已有挂回机制 `position_service._reattach_orphan_flows`（调用点 `:543` / `:767`），
但它的筛选条件是 `Transaction.asset_type.in_(CASH_EQUIVALENT_ASSET_TYPES)`——
**`asset_type` 为空的历史行永远不匹配**。本脚本要量化的正是这批漏网行。

分类（互斥）
----------
- `typed_cash`：`asset_type ∈ ('money_fund','reverse_repo')`——在既有机制覆盖范围内，
  若仍为孤儿，说明建仓发生在机制启用之前，或走的是不经 `_reattach_orphan_flows` 的路径；
- `untyped`  ：`asset_type IS NULL`——**被既有机制漏掉的那批**，且会进 XIRR；
- `other_typed`：其它显式类型（`stock` / `bond` / `fund` …）——非货基丢关联，属导入缺陷；
- `income_rows`：`is_income = True`——收益行独立成桶（#863 D1），**不参与本金挂回**，
  单独列出仅供核对，不计入上面三类的「待处理」数。

本脚本**只读**：不执行任何写入，连事务都不开。`--emit-sql-out` 只生成候选的
`UPDATE` 与反向 `UPDATE`（人工复核用），不自动执行。

用法
----
  pdm run python scripts/audit_orphan_transactions.py
  pdm run python scripts/audit_orphan_transactions.py --db backend/invest.db
  pdm run python scripts/audit_orphan_transactions.py --json-out audit.json
  pdm run python scripts/audit_orphan_transactions.py --emit-sql-out reattach.sql
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

# 真相源：backend/app/services/fund_utils.py:30（CASH_EQUIVALENT_ASSET_TYPES）
#         backend/app/core/asset_types.py:97（EXCLUDED_ASSET_TYPES）
# 测试 tests/scripts/test_audit_orphan_transactions.py 断言二者与 app 侧一致，
# 防止本脚本的纯 sqlite 实现与应用常量漂移。
CASH_EQUIVALENT_ASSET_TYPES = ('money_fund', 'reverse_repo')
EXCLUDED_ASSET_TYPES = ('money_fund', 'reverse_repo', 'cash')

DEFAULT_DB = 'invest.db'

_ORPHAN_SQL = (
    'SELECT t.id, t.symbol, t.asset_type, t.type, t.ledger_id, t.trade_date, '
    '       t.amount, t.is_income, t.family_id, t.position_name '
    'FROM transactions t '
    "WHERE t.position_id IS NULL AND t.symbol IS NOT NULL AND t.symbol <> '' "
    'ORDER BY t.ledger_id, t.symbol, t.trade_date, t.id'
)

_POSITIONS_SQL = "SELECT id, symbol, ledger_id FROM positions WHERE symbol IS NOT NULL AND symbol <> ''"


def normalize_fund_code(symbol: str) -> str:
    """复刻 `app.services.fund_utils.normalize_fund_code`（纯 sqlite 工具不引 app 包）。

    剥离交易所前缀，返回 6 位代码；无法归一化时返回空串。
    """
    s = (symbol or '').strip().upper()
    if '.' in s:
        s = s.replace('.', '')
    if len(s) > 6 and s[:2] in ('SH', 'SZ', 'BJ'):
        s = s[2:]
    if len(s) > 6 and s[-2:] in ('SH', 'SZ', 'BJ'):
        s = s[:-2]
    return s[-6:] if len(s) >= 6 and s[-6:].isdigit() else ''


def build_position_index(conn: sqlite3.Connection) -> dict[tuple, list[int]]:
    """建 `(ledger_id, 归一化代码) -> [position_id, ...]` 索引。

    一个键可能对应多个持仓（同 ledger 同名品种理论上唯一，但历史数据允许并存），
    全部保留以便报告折叠情况。
    """
    index: dict[tuple, list[int]] = {}
    for pid, symbol, ledger_id in conn.execute(_POSITIONS_SQL).fetchall():
        code = normalize_fund_code(symbol)
        if not code:
            continue
        index.setdefault((ledger_id, code), []).append(pid)
    return index


def collect_candidates(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """收集四类记录。仅统计 `symbol` 能匹配到**同 ledger** 同名持仓的行。

    返回 `{'typed_cash': [...], 'untyped': [...], 'other_typed': [...], 'income_rows': [...]}`。
    前三类互斥且**只含非收益行**；`income_rows` 是命中匹配但 `is_income=True` 的行，
    单独成桶，不参与本金挂回。
    """
    index = build_position_index(conn)
    out: dict[str, list[dict]] = {
        'typed_cash': [],
        'untyped': [],
        'other_typed': [],
        'income_rows': [],
    }

    for row in conn.execute(_ORPHAN_SQL).fetchall():
        tid, symbol, asset_type, txn_type, ledger_id, trade_date, amount, is_income, family_id, pos_name = row
        code = normalize_fund_code(symbol)
        if not code:
            continue
        hits = index.get((ledger_id, code))
        if not hits:
            continue

        item = {
            'id': tid,
            'symbol': symbol,
            'normalized': code,
            'asset_type': asset_type,
            'type': txn_type,
            'ledger_id': ledger_id,
            'trade_date': trade_date,
            'amount': amount,
            'position_ids': hits,
            'position_name': pos_name,
            'in_performance': asset_type is None or asset_type not in EXCLUDED_ASSET_TYPES,
        }

        if is_income:
            out['income_rows'].append(item)
        elif asset_type is None:
            out['untyped'].append(item)
        elif asset_type in CASH_EQUIVALENT_ASSET_TYPES:
            out['typed_cash'].append(item)
        else:
            out['other_typed'].append(item)

    return out


def _lit(value) -> str:
    """把 Python 值转成 SQL 字面量（仅用于生成 SQL 文本）。"""
    if value is None:
        return 'NULL'
    if isinstance(value, str):
        return "'%s'" % value.replace("'", "''")
    return repr(value)


def emit_sql(rows: list[dict]) -> str:
    """生成候选的挂回 UPDATE 与反向 UPDATE（人工复核后自行执行，脚本不代跑）。"""
    lines = [
        '-- #950 候选挂回 SQL（由 audit_orphan_transactions.py 生成）',
        '-- 注意：本文件不会被脚本执行。请人工复核每一条后再手工运行。',
        '-- 回滚：把下方「反向」段整体执行即可还原为 position_id = NULL。',
        '',
        '-- ── 挂回 ──',
    ]
    emitted: list[dict] = []
    for r in rows:
        if len(r['position_ids']) != 1:
            lines.append(
                '-- 跳过 tx#%s（同 ledger 同名持仓有 %d 个，需人工判定）：%s'
                % (r['id'], len(r['position_ids']), r['symbol'])
            )
            continue
        lines.append(
            'UPDATE transactions SET position_id = %s WHERE id = %s AND position_id IS NULL;  -- %s'
            % (_lit(r['position_ids'][0]), _lit(r['id']), r['symbol'])
        )
        emitted.append(r)
    # 反向段只覆盖**真正生成了挂回语句**的行；被跳过的行本就没改，不给出误导性语句
    lines += ['', '-- ── 反向（回滚，仅覆盖上方实际挂回的行）──']
    for r in emitted:
        lines.append('UPDATE transactions SET position_id = NULL WHERE id = %s;' % _lit(r['id']))
    return '\n'.join(lines) + '\n'


def _print_group(title: str, rows: list[dict], note: str = '') -> None:
    print('\n%s（%d 行）%s' % (title, len(rows), ('— ' + note) if note else ''))
    for r in rows:
        flag = '进XIRR' if r['in_performance'] else '不入绩效'
        print(
            '  tx#%-6s %-10s %-11s %-9s ledger=%-3s date=%-20s %-8s -> pos%s'
            % (
                r['id'],
                r['symbol'],
                r['asset_type'] if r['asset_type'] is not None else 'NULL',
                r['type'],
                r['ledger_id'],
                str(r['trade_date']),
                flag,
                r['position_ids'],
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description='只读审计：position_id 为空但本应关联持仓的交易（#950）')
    parser.add_argument('--db', default=DEFAULT_DB, help='SQLite 数据库路径（默认 invest.db）')
    parser.add_argument('--json-out', default=None, help='把结果写入 JSON 文件')
    parser.add_argument('--emit-sql-out', default=None, help='把候选挂回 SQL 写入文件（不会被执行）')
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print('[错误] 数据库不存在: %s' % db_path)
        return 1

    # mode=ro（不用 immutable=1：本机库常带未 checkpoint 的 WAL，immutable 会看不到新行）
    conn = sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        missing = {'transactions', 'positions'} - tables
        if missing:
            print('[错误] 目标库缺少表: %s' % ', '.join(sorted(missing)))
            return 1

        total = conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
        null_pid = conn.execute('SELECT COUNT(*) FROM transactions WHERE position_id IS NULL').fetchone()[0]
        groups = collect_candidates(conn)

        print('库: %s' % db_path)
        print('transactions 总行数 %d；其中 position_id IS NULL %d 行' % (total, null_pid))
        print('（多数为合法无持仓：账户级操作与货基 / 逆回购孤儿流水）')

        _print_group(
            'A. untyped —— asset_type 为空，被 _reattach_orphan_flows 漏掉',
            groups['untyped'],
            '本卡真实残余；且进 XIRR 现金流',
        )
        _print_group(
            'B. typed_cash —— 货基 / 逆回购，在既有机制覆盖范围内却仍为孤儿',
            groups['typed_cash'],
            '建仓早于机制启用，或走了不经挂回的路径',
        )
        _print_group(
            'C. other_typed —— 其它显式类型，非货基丢关联',
            groups['other_typed'],
            '导入缺陷',
        )
        _print_group(
            'D. income_rows —— 命中匹配的收益行',
            groups['income_rows'],
            '独立收益桶（#863 D1），不参与本金挂回，仅供核对',
        )

        pending = groups['untyped'] + groups['typed_cash'] + groups['other_typed']
        print(
            '\n待处理合计（A+B+C）: %d 行；其中会进 XIRR 的: %d 行'
            % (
                len(pending),
                len([r for r in pending if r['in_performance']]),
            )
        )

        if args.json_out:
            payload = {
                'db': str(db_path),
                'transactions_total': total,
                'position_id_null': null_pid,
                'groups': groups,
                'pending_total': len(pending),
            }
            Path(args.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            print('[JSON 已写入] %s' % args.json_out)

        if args.emit_sql_out:
            Path(args.emit_sql_out).write_text(emit_sql(pending), encoding='utf-8')
            print('[SQL 已写入] %s（仅供人工复核，脚本不执行）' % args.emit_sql_out)

        print('\n[只读] 未修改任何数据。')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
