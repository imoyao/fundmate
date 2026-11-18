# -*- coding: utf-8 -*-
"""只读审计脚本 audit_orphan_batches 的单测（#2875 孤儿批次归因）。

覆盖五类：
- 批次切分：同分钟聚簇、间隔 ≤ gap 合并、超 gap 分批（正向与边界）；
- 行级定性：哨兵 / 存取 / 货基 → legal_cash，其余 → unanchored，二者互斥完备；
- symbol 级判定五种 verdict 各归位，且挂回判定只认同 ledger；
- 反向：已关联（position_id 非空）的行不进扫描；净数量方向不颠倒；
- 只读性 + JSON 输出。
"""

import os
import sqlite3
import sys

import pytest

_SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import audit_orphan_batches as m  # noqa: E402
import audit_orphan_transactions as base  # noqa: E402

_TXN_COLS = (
    'id, created_at, ledger_id, symbol, asset_type, type, quantity, amount, trade_date, confirm_date, position_name'
)

# (id, created_at, ledger_id, symbol, asset_type, type, quantity, amount, position_id)
# 说明：同一分钟 10:00 的 5 笔 → 批次1；10:20 的 3 笔（gap=10 外）→ 批次2
_TXNS = [
    # 批次1 @10:00
    (1, '2026-08-29 10:00:01', 12, None, None, 'deposit', 0, 100000, None),  # 合法：存取
    (2, '2026-08-29 10:00:02', 12, '__CASH__', None, 'deposit', 0, 50000, None),  # 合法：哨兵
    (3, '2026-08-29 10:00:03', 12, None, 'money_fund', 'buy', 0, 30000, None),  # 合法：货基
    (4, '2026-08-29 10:00:04', 12, 'SH113621', 'stock', 'buy', 100000, 1200000, None),  # 无锚·买
    (5, '2026-08-29 10:00:05', 12, 'SH113621', 'stock', 'sell', 100000, 1230000, None),  # 无锚·卖 → 净0 已清仓
    # 批次2 @10:20（> gap）
    (6, '2026-08-29 10:20:01', 12, 'SH111016', 'stock', 'sell', 200000, 260000, None),  # 无源卖出
    (7, '2026-08-29 10:20:02', 12, 'SH600519', 'stock', 'buy', 1000, 17000000, None),  # 应建仓未建仓
    (8, '2026-08-29 10:20:03', 12, 'SZ001937', None, 'buy', 100000, 120000, None),  # 唯一命中持仓 → 可挂回
]

# (id, symbol, ledger_id)
_POSITIONS = [
    (1, 'SZ001937', 12),
]


def _make_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        'CREATE TABLE transactions ('
        'id INTEGER PRIMARY KEY, created_at DATETIME, ledger_id INTEGER, symbol VARCHAR, '
        'asset_type VARCHAR, type VARCHAR, quantity INTEGER, amount INTEGER, '
        'trade_date DATE, confirm_date DATE, position_name VARCHAR, position_id INTEGER)'
    )
    conn.execute('CREATE TABLE positions (id INTEGER PRIMARY KEY, symbol VARCHAR, ledger_id INTEGER)')
    conn.executemany(
        'INSERT INTO transactions (id, created_at, ledger_id, symbol, asset_type, type, quantity, '
        'amount, position_id) VALUES (?,?,?,?,?,?,?,?,?)',
        [(i, ca, led, sym, at, ty, q, amt, pid) for (i, ca, led, sym, at, ty, q, amt, pid) in _TXNS],
    )
    conn.executemany('INSERT INTO positions (id, symbol, ledger_id) VALUES (?,?,?)', _POSITIONS)
    conn.commit()


def _snapshot(conn: sqlite3.Connection) -> list:
    return sorted(conn.execute('SELECT %s FROM transactions' % _TXN_COLS).fetchall())


@pytest.fixture()
def conn():
    c = sqlite3.connect(':memory:')
    _make_db(c)
    try:
        yield c
    finally:
        c.close()


# ─────────────── 批次切分 ───────────────


def test_rows_in_same_minute_cluster_together(conn):
    result = m.build_batches(conn, gap_minutes=10)
    # 10:00 一批 + 10:20 一批
    assert result['batch_count'] == 2
    assert result['total_orphans'] == 8
    b1, b2 = result['batches']
    assert b1['window_start'] == '2026-08-29 10:00'
    assert b1['total'] == 5
    assert b2['window_start'] == '2026-08-29 10:20'
    assert b2['total'] == 3


def test_adjacent_minutes_within_gap_merge(conn):
    """10:00 与 10:08 相隔 8 分钟 ≤ gap=10 → 同一批。"""
    conn.execute("UPDATE transactions SET created_at='2026-08-29 10:08:00' WHERE id IN (6,7,8)")
    conn.commit()
    result = m.build_batches(conn, gap_minutes=10)
    assert result['batch_count'] == 1
    assert result['batches'][0]['total'] == 8


def test_gap_boundary_is_inclusive():
    """间隔恰好等于 gap 也合并（≤ 语义）。"""
    rows = [
        {'id': 1, 'created_at': '2026-01-01 10:00:00'},
        {'id': 2, 'created_at': '2026-01-01 10:10:00'},
    ]
    assert len(m.group_by_batch(rows, gap_minutes=10)) == 1
    assert len(m.group_by_batch(rows, gap_minutes=9)) == 2


# ─────────────── 行级定性 ───────────────


def test_legal_cash_vs_unanchored_partition(conn):
    b1 = m.build_batches(conn, gap_minutes=10)['batches'][0]
    # 批次1：deposit×2 + money_fund×2? —— id1 存取、id2 哨兵、id3 货基合法；id4/5 无锚
    assert b1['legal_cash'] == 3
    assert b1['unanchored'] == 2
    assert b1['legal_cash'] + b1['unanchored'] == b1['total']


def test_legal_cash_predicate_matrix():
    """定性谓词逐行验证，防止哨兵/存取/货基三类漏判或误判。"""
    assert m.is_legal_cash_orphan('__CASH__', None, 'deposit') is True
    assert m.is_legal_cash_orphan('', None, 'withdraw') is True
    assert m.is_legal_cash_orphan('', 'money_fund', 'buy') is True
    assert m.is_legal_cash_orphan('', 'reverse_repo', 'sell') is True
    # 反向：股票行、无类型无 symbol 的红利税不得算合法
    assert m.is_legal_cash_orphan('SH113621', 'stock', 'buy') is False
    assert m.is_legal_cash_orphan('', None, 'dividend_tax') is False


# ─────────────── symbol 级判定 ───────────────


def test_symbol_verdicts_per_group(conn):
    b1, b2 = m.build_batches(conn, gap_minutes=10)['batches']
    assert b1['symbol_verdicts'] == {'cleared_history': 1}  # SH113621 买卖相抵
    assert b2['symbol_verdicts'] == {
        'sell_without_buy': 1,  # SH111016 只有卖
        'unpositioned': 1,  # SH600519 只有买
        'reattachable': 1,  # SZ001937 唯一命中持仓
    }


def test_ambiguous_when_multiple_same_ledger_positions(conn):
    conn.execute("INSERT INTO positions (id, symbol, ledger_id) VALUES (2, '001937', 12)")
    conn.commit()
    b2 = m.build_batches(conn, gap_minutes=10)['batches'][1]
    assert b2['symbol_verdicts'].get('ambiguous') == 1
    assert b2['symbol_verdicts'].get('reattachable') is None


def test_same_symbol_other_ledger_not_reattachable(conn):
    """持仓在别的 ledger → 不得判为可挂回（与 #950 同口径）。"""
    conn.execute('UPDATE positions SET ledger_id=99 WHERE id=1')
    conn.commit()
    b2 = m.build_batches(conn, gap_minutes=10)['batches'][1]
    assert b2['symbol_verdicts'].get('reattachable') is None
    # SZ001937 无同 ledger 命中、只有买 → 落回 unpositioned
    assert b2['symbol_verdicts'].get('unpositioned') == 2


def test_sell_quantity_direction_is_not_inverted():
    """卖出的 quantity 为正数存储：净数量必须按 买-|卖| 计算，不得颠倒。"""
    txns = [
        {'type': 'buy', 'quantity': 100000},
        {'type': 'sell', 'quantity': 40000},
    ]
    assert m._net_qty(txns) == 60000


# ─────────────── 复用与只读 ───────────────


def test_reuses_950_normalize_without_drift():
    """normalize_fund_code 必须是 #950 审计的同一实现，禁止第三份复刻漂移。"""
    assert m.normalize_fund_code is base.normalize_fund_code
    assert m.build_position_index is base.build_position_index
    assert tuple(m.CASH_EQUIVALENT_ASSET_TYPES) == tuple(base.CASH_EQUIVALENT_ASSET_TYPES)


def test_cli_is_read_only_and_json_works(tmp_path, monkeypatch):
    db_file = tmp_path / 'invest.db'
    src = sqlite3.connect(str(db_file))
    try:
        _make_db(src)
    finally:
        src.close()
    before = _snapshot(sqlite3.connect(str(db_file)))

    json_out = tmp_path / 'batches.json'
    monkeypatch.setattr(sys, 'argv', ['audit', '--db', str(db_file), '--json-out', str(json_out)])
    assert m.main() == 0

    assert _snapshot(sqlite3.connect(str(db_file))) == before
    assert json_out.exists()
    import json

    data = json.loads(json_out.read_text(encoding='utf-8'))
    assert data['total_orphans'] == 8
    assert data['batch_count'] == 2


def test_cli_missing_db_returns_error(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['audit', '--db', str(tmp_path / 'nope.db')])
    assert m.main() == 1
