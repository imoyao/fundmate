# -*- coding: utf-8 -*-
"""#1068 回归：import_hash NULL 回填脚本。

验证脚本对 NULL 行回填占位哈希、保留已有 hash、幂等、回填后全表无 NULL。
"""

import os
import sqlite3
import subprocess
import sys


def _make_db(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE transactions(id INTEGER PRIMARY KEY, ledger_id INTEGER, import_hash TEXT);
        CREATE TABLE positions(id INTEGER PRIMARY KEY, ledger_id INTEGER, import_hash TEXT);
        INSERT INTO transactions(ledger_id, import_hash) VALUES (1, 'abc'), (1, NULL), (2, NULL);
        INSERT INTO positions(ledger_id, import_hash) VALUES (1, NULL), (2, 'xyz'), (3, NULL), (3, NULL);
        """
    )
    conn.commit()
    conn.close()


def _count_null(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM {table} WHERE import_hash IS NULL').fetchone()[0]


def test_backfill_removes_all_null(tmp_path):
    db = tmp_path / 'invest.db'
    _make_db(str(db))

    env = dict(os.environ, DATABASE_URL=f'sqlite:///{db}')
    script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'migrate_backfill_import_hash.py')
    result = subprocess.run([sys.executable, script], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(str(db))
    try:
        assert _count_null(conn, 'transactions') == 0
        assert _count_null(conn, 'positions') == 0
        # 已有 hash 不被改动
        assert conn.execute('SELECT import_hash FROM transactions WHERE id=1').fetchone()[0] == 'abc'
        assert conn.execute('SELECT import_hash FROM positions WHERE id=2').fetchone()[0] == 'xyz'
        # 占位格式
        assert conn.execute('SELECT import_hash FROM transactions WHERE id=2').fetchone()[0] == 'legacy|txn|2'
        assert conn.execute('SELECT import_hash FROM positions WHERE id=1').fetchone()[0] == 'legacy|pos|1'
    finally:
        conn.close()


def test_backfill_idempotent(tmp_path):
    db = tmp_path / 'invest.db'
    _make_db(str(db))

    env = dict(os.environ, DATABASE_URL=f'sqlite:///{db}')
    script = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'migrate_backfill_import_hash.py')
    # 跑两次，第二次应 SKIP 且无新增改动
    r1 = subprocess.run([sys.executable, script], env=env, capture_output=True, text=True)
    r2 = subprocess.run([sys.executable, script], env=env, capture_output=True, text=True)
    assert r1.returncode == 0 and r2.returncode == 0

    conn = sqlite3.connect(str(db))
    try:
        assert _count_null(conn, 'transactions') == 0
        assert _count_null(conn, 'positions') == 0
    finally:
        conn.close()
