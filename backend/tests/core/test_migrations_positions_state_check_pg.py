# -*- coding: utf-8 -*-
"""TD-012：#2875 库级 CHECK 在**真 Postgres** 上的语义回归。

``migrations_pg_fake.PgFake`` 只把 SQL 记进列表，``backend/tests/conftest.py``
又把 DEV_DATABASE_URL 钉成临时 sqlite，于是 PG 侧此前只钉住了「DDL 文本长什么样」。
本文件补上 PgFake 证不了的三件事：

1. PG 是否真的接受 ``ALTER TABLE ... ADD CONSTRAINT ... CHECK (...)``；
2. ``inspect.get_check_constraints()`` 是否真的回传两个约束名（幂等判重的依据）；
3. 违规写入是否被 PG 自己的 ``IntegrityError`` 拦下，合法边界是否不被误伤。

本地没有 ``TEST_POSTGRES_URL`` 时整文件 skip（本机无 Docker / psql）；CI 的
backend job 挂了 postgres service 并注入该变量，**语义结论只以那条 CI 日志为准**。
接线完整性另由 scripts/guard_pg_migration_ci.py 结构化钉住（注释不算数）。
"""

import os

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.migrations import migrate_positions_state_check_constraints

URL = os.environ.get('TEST_POSTGRES_URL', '')
pytestmark = pytest.mark.skipif(not URL, reason='未注入 TEST_POSTGRES_URL（本机无真 PG）')

CHECK_NAMES = {
    'ck_positions_cleared_zero_qty',
    'ck_positions_anchor_qty_needs_date',
}

# 与 SQLite 侧的 _OLD_DDL 同形，只换 PG 类型：不建索引，本文件专测 CHECK 语义。
DDL = """
CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    family_id INTEGER NOT NULL DEFAULT 1,
    ledger_id INTEGER,
    symbol VARCHAR(30) NOT NULL,
    symbol_norm VARCHAR(64) NOT NULL DEFAULT '',
    quantity INTEGER DEFAULT 0,
    avg_price INTEGER DEFAULT 0,
    ownership_status VARCHAR(20) NOT NULL DEFAULT 'active',
    snapshot_quantity INTEGER,
    snapshot_avg_price INTEGER,
    snapshot_date DATE,
    anchor_kind VARCHAR(20),
    cleared_at TIMESTAMP,
    import_hash VARCHAR(64)
)
"""

INSERT_SQL = """
INSERT INTO positions
    (symbol, symbol_norm, quantity, ownership_status, snapshot_quantity, snapshot_date)
VALUES (:symbol, :symbol_norm, :quantity, :ownership_status, :snapshot_quantity, :snapshot_date)
"""


@pytest.fixture
def pg_engine():
    """每个用例一张干净的表：串行跑（-n 0），无需按 worker 隔离 schema。"""
    engine = create_engine(URL)
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS positions CASCADE'))
        conn.execute(text(DDL))
    yield engine
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS positions CASCADE'))
    engine.dispose()


def _insert(engine, *, symbol, quantity, ownership_status='active', snapshot_quantity=None, snapshot_date=None):
    with engine.begin() as conn:
        conn.execute(
            text(INSERT_SQL),
            {
                'symbol': symbol,
                'symbol_norm': symbol,
                'quantity': quantity,
                'ownership_status': ownership_status,
                'snapshot_quantity': snapshot_quantity,
                'snapshot_date': snapshot_date,
            },
        )


def test_约束真落库且反射回约束名(pg_engine):
    result = migrate_positions_state_check_constraints(pg_engine)
    assert result.startswith('[OK]'), result
    names = {c['name'] for c in inspect(pg_engine).get_check_constraints('positions')}
    assert names == CHECK_NAMES, names


def test_幂等_第二次调用靠反射跳过(pg_engine):
    first = migrate_positions_state_check_constraints(pg_engine)
    second = migrate_positions_state_check_constraints(pg_engine)
    assert first.startswith('[OK]'), first
    assert second.startswith('[SKIP]'), second
    names = {c['name'] for c in inspect(pg_engine).get_check_constraints('positions')}
    assert names == CHECK_NAMES


def test_违规写入被PG自己拒绝(pg_engine):
    assert migrate_positions_state_check_constraints(pg_engine).startswith('[OK]')
    # cleared 却仍有份额：PgFake 只会看到一条 ALTER，看不到 PG 到底拦不拦这一行。
    with pytest.raises(IntegrityError):
        _insert(pg_engine, symbol='000001', quantity=100, ownership_status='cleared')
    # 锚点有份额却无日期（方向式约束）
    with pytest.raises(IntegrityError):
        _insert(pg_engine, symbol='000002', quantity=100, snapshot_quantity=100)


def test_合法边界不被误伤(pg_engine):
    assert migrate_positions_state_check_constraints(pg_engine).startswith('[OK]')
    _insert(pg_engine, symbol='000001', quantity=0, ownership_status='cleared')
    _insert(pg_engine, symbol='000002', quantity=0, snapshot_date='2026-11-10')
    _insert(pg_engine, symbol='000003', quantity=100, snapshot_quantity=100, snapshot_date='2026-11-10')
    with pg_engine.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM positions')).scalar() == 3


def test_存量违反时fail_closed且不改数据(pg_engine):
    _insert(pg_engine, symbol='000001', quantity=777, ownership_status='cleared')
    with pytest.raises(RuntimeError, match='cleared 但仍有份额'):
        migrate_positions_state_check_constraints(pg_engine)
    with pg_engine.connect() as conn:
        assert conn.execute(text('SELECT quantity FROM positions WHERE symbol = :s'), {'s': '000001'}).scalar() == 777
