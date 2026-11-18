# -*- coding: utf-8 -*-
"""#3089 归置列迁移：SQLite 旧库补列 / 幂等 / 空库跳过 / PG 不早退且失败显性。

与 #2532 / #2534 同构：本地没有 PG 可连，PG 分支用 ``PgFake`` 钉 SQL 形态，
避免再出现「非 SQLite 就跳过 ⇒ 生产 user 域缺列 ⇒ 启动被拒」。
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.migrations import migrate_transaction_covered_position
from tests.core.migrations_pg_fake import PgFake

_COLUMN = 'covered_position_id'


def _make_old_db(path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY,
            symbol VARCHAR(30),
            position_id INTEGER,
            amount INTEGER
        );
        INSERT INTO transactions (id, symbol, position_id, amount) VALUES (1, 'MF001', NULL, 10000);
        INSERT INTO transactions (id, symbol, position_id, amount) VALUES (2, 'MF002', NULL, 20000);
        """
    )
    conn.commit()
    conn.close()


def _columns(engine) -> set:
    return {c['name'] for c in inspect(engine).get_columns('transactions')}


def test_sqlite_old_db_gets_column_without_touching_rows(tmp_path):
    db = tmp_path / 'old.db'
    _make_old_db(db)
    engine = create_engine(f'sqlite:///{db}')

    result = migrate_transaction_covered_position(engine)

    assert result.startswith('[OK]')
    assert _COLUMN in _columns(engine)
    with engine.connect() as conn:
        rows = conn.execute(text(f'SELECT id, position_id, amount, {_COLUMN} FROM transactions ORDER BY id')).fetchall()
    assert [r[0] for r in rows] == [1, 2], '迁移不许丢行'
    assert [r[1:] for r in rows] == [(None, 10000, None), (None, 20000, None)], '只加列不回填'


def test_idempotent(tmp_path):
    db = tmp_path / 'old.db'
    _make_old_db(db)
    engine = create_engine(f'sqlite:///{db}')

    assert migrate_transaction_covered_position(engine).startswith('[OK]')
    second = migrate_transaction_covered_position(engine)
    assert second.startswith('[SKIP]') and '已存在' in second


def test_missing_table_skipped(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "empty.db"}')
    result = migrate_transaction_covered_position(engine)
    assert result.startswith('[SKIP]') and 'transactions 表不存在' in result


def test_pg_branch_adds_column_with_if_not_exists(monkeypatch):
    fake = PgFake({'transactions': ['id', 'symbol', 'position_id']})
    fake.install(monkeypatch)

    result = migrate_transaction_covered_position(fake.engine)

    assert result.startswith('[OK]'), f'PG 分支不许早退：{result}'
    assert '非 SQLite' not in result
    assert _COLUMN in fake.columns['transactions']
    assert any('ADD COLUMN IF NOT EXISTS covered_position_id INTEGER' in s for s in fake.sql)


def test_pg_ddl_silently_ignored_raises(monkeypatch):
    fake = PgFake({'transactions': ['id', 'symbol']}, apply_ddl=False)
    fake.install(monkeypatch)

    with pytest.raises(RuntimeError, match='加列后仍缺列'):
        migrate_transaction_covered_position(fake.engine)
