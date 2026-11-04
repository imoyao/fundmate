# -*- coding: utf-8 -*-
"""#2733 C 回归：``pnl_daily_snapshots.net_worth_cents`` 解除 NOT NULL。

钉住四件事：

1. **真能写 NULL**：迁移后插入 NULL 不报 IntegrityError（旧结构会报）；
2. **存量行一条不少**：整表重建把数据按原样搬过去（含 NULL 的 daily_pnl 行）；
3. **索引还在**：重建走「建新表→拷贝→删旧→改名」，`DROP TABLE` 会带走索引，
   漏重建就等于悄悄把唯一约束丢了——这条必须由测试守，不能靠读者自觉；
4. **幂等 + 自校验**：列已可空时返回 SKIP；DDL 与反射打架时抛错而不是静默通过。

PG 侧本地连不上真库，只能钉 SQL 形态（与 `test_migrations_family_members_ownership`
同套路）：写错方言要等生产才发现，那是 #2469 / #2532 两次停摆的同一个坑。
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.migrations import migrate_pnl_snapshot_net_worth_nullable

from .migrations_pg_fake import PgFake

_OLD_DDL = """
CREATE TABLE pnl_daily_snapshots (
    id INTEGER NOT NULL PRIMARY KEY,
    family_id INTEGER NOT NULL,
    ledger_id INTEGER,
    date DATE NOT NULL,
    daily_pnl_cents INTEGER,
    net_worth_cents INTEGER NOT NULL,
    rate_bp INTEGER,
    state VARCHAR(16) NOT NULL,
    caliber_version INTEGER NOT NULL,
    created_at DATETIME
);
CREATE UNIQUE INDEX uq_pnl_daily_snapshots_scope
    ON pnl_daily_snapshots (family_id, COALESCE(ledger_id, -1), date);
CREATE INDEX ix_pnl_daily_snapshots_caliber ON pnl_daily_snapshots (caliber_version);
INSERT INTO pnl_daily_snapshots
    (family_id, ledger_id, date, daily_pnl_cents, net_worth_cents, rate_bp, state, caliber_version)
VALUES
    (1, 13, '2026-02-03', 3000, 123456, 12, 'updown', 3),
    (1, 13, '2026-02-04', NULL, 0, NULL, 'closed', 3);
"""


@pytest.fixture
def old_db(tmp_path):
    path = tmp_path / 'old_market.db'
    conn = sqlite3.connect(str(path))
    conn.executescript(_OLD_DDL)
    conn.commit()
    conn.close()
    engine = create_engine(f'sqlite:///{path}')
    yield engine
    engine.dispose()


def _cols(engine, table='pnl_daily_snapshots'):
    return {c['name']: c for c in inspect(engine).get_columns(table)}


def test_迁移后可写NULL且存量行原样保留(old_db):
    """核心判据：迁移前写 NULL 会炸，迁移后不炸，且旧数据一个字节不变。"""
    with old_db.connect() as conn:
        with pytest.raises(Exception):
            conn.execute(
                text(
                    'INSERT INTO pnl_daily_snapshots'
                    ' (family_id, ledger_id, date, net_worth_cents, state, caliber_version)'
                    " VALUES (1, 99, '2026-03-01', NULL, 'no_price', 3)"
                )
            )
            conn.commit()
        conn.rollback()

    result = migrate_pnl_snapshot_net_worth_nullable(old_db)
    assert result.startswith('[OK]')
    assert _cols(old_db)['net_worth_cents']['nullable'] is True

    with old_db.connect() as conn:
        conn.execute(
            text(
                'INSERT INTO pnl_daily_snapshots'
                ' (family_id, ledger_id, date, net_worth_cents, state, caliber_version)'
                " VALUES (1, 99, '2026-03-01', NULL, 'no_price', 3)"
            )
        )
        conn.commit()
        rows = list(
            conn.execute(text('SELECT date, net_worth_cents, daily_pnl_cents FROM pnl_daily_snapshots ORDER BY date'))
        )
    assert [tuple(r) for r in rows] == [
        ('2026-02-03', 123456, 3000),
        ('2026-02-04', 0, None),  # 旧口径写下的 0 原样保留（历史数据不重写）
        ('2026-03-01', None, None),
    ]


def _index_names(engine, table='pnl_daily_snapshots'):
    """直接读 sqlite_master：表达式索引（`COALESCE(...)`）不会被 SQLAlchemy 反射到。"""
    with engine.connect() as conn:
        return {
            r[0]
            for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:t"),
                {'t': table},
            )
        }


def test_重建后索引与唯一约束仍在(old_db):
    """`DROP TABLE` 会带走索引：漏重建 = 唯一键静默失效（→ 快照重复行）。"""
    before = _index_names(old_db)
    assert 'uq_pnl_daily_snapshots_scope' in before
    migrate_pnl_snapshot_net_worth_nullable(old_db)
    after = _index_names(old_db)
    assert after == before, f'索引在重建中丢失：{before - after}'

    # 唯一约束要真的还生效，而不只是「索引名还在」
    with old_db.connect() as conn:
        with pytest.raises(Exception):
            conn.execute(
                text(
                    'INSERT INTO pnl_daily_snapshots'
                    ' (family_id, ledger_id, date, net_worth_cents, state, caliber_version)'
                    " VALUES (1, 13, '2026-02-03', 1, 'updown', 3)"
                )
            )
            conn.commit()
        conn.rollback()


def test_幂等_已可空则跳过(old_db):
    migrate_pnl_snapshot_net_worth_nullable(old_db)
    second = migrate_pnl_snapshot_net_worth_nullable(old_db)
    assert second.startswith('[SKIP]')
    assert '已是可空' in second


def test_空库安全跳过(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "empty.db"}')
    try:
        assert migrate_pnl_snapshot_net_worth_nullable(engine).startswith('[SKIP]')
    finally:
        engine.dispose()


def test_已可空的历史库不重建(tmp_path):
    """新建库（模型已是可空）上跑迁移：反射判可空 ⇒ SKIP，不做无谓重建。"""
    path = tmp_path / 'conflict.db'
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE pnl_daily_snapshots (
            id INTEGER PRIMARY KEY,
            family_id INTEGER NOT NULL,
            date DATE NOT NULL,
            net_worth_cents INTEGER,
            state VARCHAR(16) NOT NULL,
            caliber_version INTEGER NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()
    engine = create_engine(f'sqlite:///{path}')
    try:
        # 反射看到可空 ⇒ 走 SKIP，不应抛错（正常语义）
        assert migrate_pnl_snapshot_net_worth_nullable(engine).startswith('[SKIP]')
    finally:
        engine.dispose()


def test_PG分支发DROP_NOT_NULL而不是跳过(monkeypatch):
    """PG 侧形态：`ALTER COLUMN ... DROP NOT NULL`，且不再「非 SQLite 就跳过」。"""
    fake = PgFake(
        {'pnl_daily_snapshots': ['id', 'family_id', 'date', 'net_worth_cents', 'state', 'caliber_version']},
        not_null={'pnl_daily_snapshots': ['net_worth_cents']},
    )
    fake.install(monkeypatch)

    result = migrate_pnl_snapshot_net_worth_nullable(fake.engine)

    assert result.startswith('[OK]'), result
    assert any('ALTER TABLE pnl_daily_snapshots ALTER COLUMN net_worth_cents DROP NOT NULL' in s for s in fake.sql), (
        fake.sql
    )
    assert 'net_worth_cents' not in fake.not_null['pnl_daily_snapshots']


def test_PG分支幂等(monkeypatch):
    fake = PgFake(
        {'pnl_daily_snapshots': ['id', 'family_id', 'date', 'net_worth_cents', 'state', 'caliber_version']},
        not_null={'pnl_daily_snapshots': []},
    )
    fake.install(monkeypatch)

    assert migrate_pnl_snapshot_net_worth_nullable(fake.engine).startswith('[SKIP]')
    assert fake.sql == [], f'已可空时不应再发 DDL：{fake.sql}'
