# -*- coding: utf-8 -*-
"""修复脚本 fix_orphan_ledger_null 的单测（#2875 存量 ledger NULL 回填）。

覆盖四类：
- 正向：account_name 与同 family 账本精确同名 ⇒ 回填；
- 反向：account_name 为空 / 无同名 / 同 family 同名多条（歧义）一律跳过并列原因；
- 边界：同 family 匹配、跨 family **不**匹配（family_id 必须参与判据）；
- apply 幂等：二次运行剩余为 0，已回填行不再被触碰。
"""

import os
import sqlite3
import sys

import pytest

_SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import fix_orphan_ledger_null as m  # noqa: E402


def _make_db(conn: sqlite3.Connection) -> None:
    conn.execute('CREATE TABLE ledgers (id INTEGER PRIMARY KEY, name VARCHAR, family_id INTEGER)')
    conn.execute(
        'CREATE TABLE transactions ('
        'id INTEGER PRIMARY KEY, ledger_id INTEGER, family_id INTEGER, position_id INTEGER, '
        'type VARCHAR, symbol VARCHAR, account_name VARCHAR, amount INTEGER, created_at DATETIME)'
    )
    # family 1：银河（正常）；family 2：同名银河（跨 family 不得串）；
    # family 1 另有一个「重名账户」两条同名（歧义场景）
    conn.executemany(
        'INSERT INTO ledgers (id, name, family_id) VALUES (?,?,?)',
        [(12, '同花顺（银河证券）', 1), (99, '同花顺（银河证券）', 2)],
    )
    conn.executemany(
        'INSERT INTO ledgers (id, name, family_id) VALUES (?,?,?)',
        [(30, '重名账户', 1), (31, '重名账户', 1)],
    )
    conn.executemany(
        'INSERT INTO transactions (id, ledger_id, family_id, position_id, type, symbol, '
        'account_name, amount, created_at) VALUES (?,?,?,?,?,?,?,?,?)',
        [
            (1, None, 1, None, 'dividend_tax', None, '同花顺（银河证券）', -1750, '2026-11-02 14:24:00'),
            (2, None, 1, None, 'bond_redeem', None, '同花顺（银河证券）', 1243000, '2026-11-02 14:24:10'),
            (3, None, 2, None, 'dividend_tax', None, '同花顺（银河证券）', -100, '2026-11-02 14:24:20'),
            (4, None, 1, None, 'dividend_tax', None, '不存在的账户', -50, '2026-11-02 14:24:30'),
            (5, None, 1, None, 'dividend_tax', None, '', -50, '2026-11-02 14:24:40'),
            (6, None, 1, None, 'dividend_tax', None, '重名账户', -50, '2026-11-02 14:24:50'),
            (7, 12, 1, None, 'dividend', None, '同花顺（银河证券）', 500, '2026-11-02 14:25:00'),
        ],
    )
    conn.commit()


@pytest.fixture()
def conn():
    c = sqlite3.connect(':memory:')
    _make_db(c)
    try:
        yield c
    finally:
        c.close()


def test_plan_separates_fixable_and_manual(conn):
    fixable, manual = m.plan_fixes(conn)
    # tx7 有 ledger，不在候选里；tx1/2/3 各自同 family 唯一同名可回填；tx4/5/6 人工
    assert [r['id'] for r in fixable] == [1, 2, 3]
    assert [r['id'] for r in manual] == [4, 5, 6]
    reasons = {r['id']: r['reason'] for r in manual}
    assert reasons[4] == "同 family 下无名为 '不存在的账户' 的账本"
    assert reasons[5] == 'account_name 为空，无法归属'
    assert '歧义' in reasons[6]


def test_plan_respects_family_boundary(conn):
    """tx3 在 family 2，其 family 下同名账本是 99 —— 不得回填成 family 1 的 12。"""
    fixable = dict((r['id'], r) for r in m.plan_fixes(conn)[0])
    assert fixable[3]['ledger_id'] == 99


def test_resolve_ledger_rejects_ambiguous(conn):
    lid, reason = m.resolve_ledger(conn, 1, '重名账户')
    assert lid is None
    assert '2 个同名账本' in reason


def test_apply_is_scoped_and_idempotent(conn):
    fixable, _ = m.plan_fixes(conn)
    conn.execute('BEGIN')
    changed = m.apply_fixes(conn, fixable)
    conn.commit()
    assert changed == 3  # tx1/2/3

    # 二次运行：NULL 候选只剩人工行，fixable 为空、无更新
    fixable2, manual2 = m.plan_fixes(conn)
    assert [r['id'] for r in fixable2] == []
    assert [r['id'] for r in manual2] == [4, 5, 6]
    conn.execute('BEGIN')
    assert m.apply_fixes(conn, fixable2) == 0
    conn.commit()

    # 已回填的行带着正确 ledger；未动过的行仍是 NULL
    rows = dict(conn.execute('SELECT id, ledger_id FROM transactions').fetchall())
    assert rows[1] == 12 and rows[2] == 12 and rows[3] == 99
    assert rows[7] == 12  # 原本就有 ledger 的行不被触碰
    assert rows[4] is None and rows[5] is None and rows[6] is None
