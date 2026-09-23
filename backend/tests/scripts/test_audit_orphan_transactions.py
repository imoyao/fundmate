# -*- coding: utf-8 -*-
"""只读审计脚本 audit_orphan_transactions 的单测（#950）。

覆盖四类：
- 正向：`asset_type IS NULL` + 同 ledger 同名持仓 → 命中 `untyped`；
- 反向：无 symbol / 无同名持仓 / **跨 ledger** / 已关联 一律不得命中；
- 分类互斥：`typed_cash` / `other_typed` / `income_rows` 各自归位，收益行不混入本金组；
- 只读性 + 常量一致性：CLI 跑完库零变化；脚本内常量与应用侧真相源逐值相等。
"""

import os
import sqlite3
import sys

import pytest

_SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import audit_orphan_transactions as m  # noqa: E402

_TXN_COLS = (
    'id, symbol, asset_type, type, trade_date, amount, is_income, family_id, position_name, ledger_id, position_id'
)

# (id, symbol, asset_type, type, ledger_id, is_income, position_id, note)
_TXNS = [
    # 正向 A：asset_type 为空 + 同名持仓 → 被 _reattach_orphan_flows 漏掉
    (1, 'SZ001937', None, 'deposit', 20, None, None, 'untyped 命中'),
    (2, '010710', None, 'sell', 13, None, None, 'untyped 命中'),
    (9, 'SH688223', None, 'sell', 12, None, None, 'untyped 命中（股票亦然）'),
    # 反向：不满足匹配条件
    (3, None, None, 'tax', 20, None, None, '无 symbol'),
    (4, '999999', None, 'buy', 20, None, None, '无同名持仓'),
    (5, '000001', None, 'buy', 7, None, None, '持仓在别的 ledger'),
    (10, 'SZ001937', None, 'buy', 20, None, 1, '已关联，不在扫描范围'),
    # 分类型
    (6, '001937', 'money_fund', 'buy', 20, None, None, 'typed_cash 命中（靠前缀归一化）'),
    (8, 'SH688223', 'stock', 'sell', 12, None, None, 'other_typed 命中'),
    # 收益行：独立桶，不参与本金挂回
    (7, 'SZ001937', None, 'deposit', 20, True, None, 'income_rows'),
]

# (id, symbol, ledger_id)
_POSITIONS = [
    (1, 'SZ001937', 20),
    (2, '010710', 13),
    (3, 'SH688223', 12),
    (4, '000001', 99),
]


def _make_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        'CREATE TABLE transactions ('
        'id INTEGER PRIMARY KEY, symbol VARCHAR, asset_type VARCHAR, type VARCHAR, '
        'trade_date DATE, amount INTEGER, is_income BOOLEAN, family_id INTEGER, '
        'position_name VARCHAR, ledger_id INTEGER, position_id INTEGER)'
    )
    conn.execute('CREATE TABLE positions (id INTEGER PRIMARY KEY, symbol VARCHAR, ledger_id INTEGER)')
    conn.executemany(
        'INSERT INTO transactions (%s) VALUES (?,?,?,?,?,?,?,?,?,?,?)' % _TXN_COLS,
        [(i, sym, at, ty, '2026-01-01', 100, inc, 1, None, led, pid) for (i, sym, at, ty, led, inc, pid, _n) in _TXNS],
    )
    conn.executemany('INSERT INTO positions (id, symbol, ledger_id) VALUES (?,?,?)', _POSITIONS)
    conn.commit()


def _ids(rows: list[dict]) -> list[int]:
    return sorted(r['id'] for r in rows)


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


# ─────────────── 正向 ───────────────


def test_untyped_hits_null_asset_type_with_same_ledger_position(conn):
    g = m.collect_candidates(conn)
    assert _ids(g['untyped']) == [1, 2, 9]


def test_typed_cash_hits_and_normalizes_prefix(conn):
    """持仓存 'SZ001937'、流水存 '001937'，归一化后必须视为同一品种。"""
    g = m.collect_candidates(conn)
    assert _ids(g['typed_cash']) == [6]
    assert g['typed_cash'][0]['normalized'] == '001937'


def test_other_typed_hits_explicit_non_cash_type(conn):
    g = m.collect_candidates(conn)
    assert _ids(g['other_typed']) == [8]


def test_income_rows_separated_from_principal_groups(conn):
    g = m.collect_candidates(conn)
    assert _ids(g['income_rows']) == [7]
    # 收益行不得混入任何本金组（#863 D1：收益桶独立）
    for key in ('untyped', 'typed_cash', 'other_typed'):
        assert 7 not in _ids(g[key])


# ─────────────── 反向：不得误报 ───────────────


def test_rows_without_symbol_are_never_candidates(conn):
    g = m.collect_candidates(conn)
    all_ids = _ids(g['untyped'] + g['typed_cash'] + g['other_typed'] + g['income_rows'])
    assert 3 not in all_ids


def test_rows_without_matching_position_are_never_candidates(conn):
    g = m.collect_candidates(conn)
    all_ids = _ids(g['untyped'] + g['typed_cash'] + g['other_typed'] + g['income_rows'])
    assert 4 not in all_ids


def test_same_symbol_in_other_ledger_is_not_a_match(conn):
    """同名持仓在别的 ledger → 不得跨 ledger 误关联。"""
    g = m.collect_candidates(conn)
    all_ids = _ids(g['untyped'] + g['typed_cash'] + g['other_typed'] + g['income_rows'])
    assert 5 not in all_ids


def test_already_linked_rows_are_out_of_scope(conn):
    g = m.collect_candidates(conn)
    all_ids = _ids(g['untyped'] + g['typed_cash'] + g['other_typed'] + g['income_rows'])
    assert 10 not in all_ids


def test_performance_flag_marks_untyped_as_in_xirr(conn):
    """`asset_type IS NULL` 会被绩效口径显式纳入（calculators.py:176），须标注。"""
    g = m.collect_candidates(conn)
    assert all(r['in_performance'] is True for r in g['untyped'])
    # 货基在 EXCLUDED 之列，不入绩效
    assert g['typed_cash'][0]['in_performance'] is False


# ─────────────── 只读性 ───────────────


def test_cli_is_read_only(tmp_path, monkeypatch):
    db_file = tmp_path / 'invest.db'
    src = sqlite3.connect(str(db_file))
    try:
        _make_db(src)
    finally:
        src.close()

    before = _snapshot(sqlite3.connect(str(db_file)))
    monkeypatch.setattr(sys, 'argv', ['audit', '--db', str(db_file)])
    assert m.main() == 0
    assert _snapshot(sqlite3.connect(str(db_file))) == before


def test_cli_writes_json_and_sql_without_touching_db(tmp_path, monkeypatch):
    db_file = tmp_path / 'invest.db'
    src = sqlite3.connect(str(db_file))
    try:
        _make_db(src)
    finally:
        src.close()
    before = _snapshot(sqlite3.connect(str(db_file)))

    json_out = tmp_path / 'audit.json'
    sql_out = tmp_path / 'reattach.sql'
    monkeypatch.setattr(
        sys,
        'argv',
        ['audit', '--db', str(db_file), '--json-out', str(json_out), '--emit-sql-out', str(sql_out)],
    )
    assert m.main() == 0

    assert _snapshot(sqlite3.connect(str(db_file))) == before
    assert json_out.exists() and sql_out.exists()
    text = sql_out.read_text(encoding='utf-8')
    assert 'UPDATE transactions SET position_id = 1 WHERE id = 1' in text
    assert 'UPDATE transactions SET position_id = NULL WHERE id = 1' in text


def test_emit_sql_skips_ambiguous_multiple_positions():
    """同 ledger 同名持仓有多个时不得替人做决定，只出注释；且反向段不得覆盖被跳过的行。"""
    rows = [
        {
            'id': 42,
            'symbol': 'SZ001937',
            'position_ids': [1, 2],
            'asset_type': None,
        }
    ]
    sql = m.emit_sql(rows)
    assert '需人工判定' in sql
    # 既不得生成挂回语句，也不得在反向段出现该行（它本就没被改）
    assert 'UPDATE transactions SET position_id = 1' not in sql
    assert 'id = 42' not in sql


def test_emit_sql_roundtrip_covers_only_emitted_rows():
    """单持仓行：挂回段与反向段各出现一次且互相抵消。"""
    rows = [
        {'id': 1, 'symbol': 'SZ001937', 'position_ids': [7], 'asset_type': None},
        {'id': 2, 'symbol': '010710', 'position_ids': [8, 9], 'asset_type': None},
    ]
    sql = m.emit_sql(rows)
    assert sql.count('UPDATE transactions SET position_id = 7 WHERE id = 1') == 1
    assert sql.count('UPDATE transactions SET position_id = NULL WHERE id = 1') == 1
    assert 'id = 2' not in sql


# ─────────────── 常量一致性（防漂移） ───────────────


def test_constants_match_application_truth_source():
    """脚本为纯 sqlite 工具，常量是复刻；此处断言与应用侧真相源逐值相等。"""
    from app.core.asset_types import EXCLUDED_ASSET_TYPES
    from app.services.fund_utils import CASH_EQUIVALENT_ASSET_TYPES

    assert tuple(m.EXCLUDED_ASSET_TYPES) == tuple(EXCLUDED_ASSET_TYPES)
    assert tuple(m.CASH_EQUIVALENT_ASSET_TYPES) == tuple(CASH_EQUIVALENT_ASSET_TYPES)


@pytest.mark.parametrize(
    'raw',
    [
        'SZ001937',
        'sz001937',
        '001937',
        'SH600519',
        '600519.SH',
        'sh.510300',
        '510300',
        '510300.SZ',
        'OF.001234',
        # 尾串必须为数字：这些必须归一化为空串，否则会与「恰好同名的非代码串」误匹配
        'SZABCDEF',
        'OF.ABCDEF',
        '',
        'AB',
        '   ',
    ],
)
def test_normalize_fund_code_matches_application(raw):
    from app.services.fund_utils import normalize_fund_code as app_normalize

    assert m.normalize_fund_code(raw) == app_normalize(raw)


def test_normalize_rejects_non_digit_tail():
    """独立断言：归一化结果要么是 6 位数字，要么是空串——不存在第三种形态。"""
    for raw in ['SZABCDEF', 'OF.ABCDEF', 'ABCDEF', '00001A', 'SZ00001A']:
        got = m.normalize_fund_code(raw)
        assert got == '' or (len(got) == 6 and got.isdigit()), (raw, got)
