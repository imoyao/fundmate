# -*- coding: utf-8 -*-
"""迁移脚本 migrate_ledgers_external_account_code 的单测（#1100/#1101）。"""

import os
import sqlite3
import sys

_SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import migrate_ledgers_external_account_code as m  # noqa: E402


def _make_ledgers(conn, rows):
    conn.execute(
        'CREATE TABLE ledgers ('
        'id INTEGER PRIMARY KEY, name VARCHAR, ledger_type VARCHAR, '
        'family_id INTEGER, sales_institution_id INTEGER)'
    )
    conn.executemany(
        'INSERT INTO ledgers (id, name, ledger_type, family_id, sales_institution_id) VALUES (?,?,?,?,?)',
        rows,
    )
    conn.commit()


def test_migrate_clean_creates_index():
    conn = sqlite3.connect(':memory:')
    try:
        _make_ledgers(
            conn,
            [
                (1, 'L1', 'fund', 1, 10),
                (2, 'L2', 'fund', 1, 20),
                (3, 'L3', 'bank', 2, None),
            ],
        )
        info = m._migrate(conn)
        assert info['added_column'] is True
        assert info['index_created'] is True
        assert info['index_skipped'] is False
        cols = {r[1] for r in conn.execute('PRAGMA table_info(ledgers)')}
        assert 'external_account_code' in cols
        # ALTER DEFAULT 已为存量行填充 'MAIN'
        codes = {r[0] for r in conn.execute('SELECT external_account_code FROM ledgers')}
        assert codes == {m.DEFAULT_CODE}
        idx = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (m.INDEX_NAME,)).fetchone()
        assert idx is not None
    finally:
        conn.close()


def test_migrate_dirty_skips_index_and_reports():
    conn = sqlite3.connect(':memory:')
    try:
        # 同 family+institution 两行 = #1100 脏数据
        _make_ledgers(
            conn,
            [
                (1, '支付宝', 'fund', 1, 10),
                (2, '蚂蚁杭州', 'fund', 1, 10),
                (3, '其他', 'fund', 1, 20),
            ],
        )
        info = m._migrate(conn)
        assert info['index_created'] is False
        assert info['index_skipped'] is True
        assert len(info['duplicates']) == 1
        idx = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (m.INDEX_NAME,)).fetchone()
        assert idx is None
        # 列仍完成
        assert info['added_column'] is True
        codes = {r[0] for r in conn.execute('SELECT external_account_code FROM ledgers')}
        assert codes == {m.DEFAULT_CODE}
    finally:
        conn.close()


def test_migrate_idempotent():
    conn = sqlite3.connect(':memory:')
    try:
        _make_ledgers(conn, [(1, 'L1', 'fund', 1, 10)])
        m._migrate(conn)
        info = m._migrate(conn)
        assert info['added_column'] is False
    finally:
        conn.close()
