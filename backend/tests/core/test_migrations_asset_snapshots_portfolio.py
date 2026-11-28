# -*- coding: utf-8 -*-
"""D135 回归：``asset_snapshots`` 长出组合维度（加列 + 重建唯一键）。

钉住四件事：

1. **加列**：`portfolio_id` 真的进了库，且老数据一条不少；
2. **唯一键真的换了**：同日**两个不同组合**的行能共存（旧三列键会撞），而
   「同 family + 同日期 + 同档位」仍然去重——只加列不重建键 = 第二个组合行
   永远写不进去（IntegrityError 让整批回滚），这是这条迁移的**唯一**存在理由；
3. **幂等**：已迁过的库第二次跑返回 SKIP，不再发 DDL；
4. **PG 分支**：发 `ADD COLUMN` 与含 `COALESCE(portfolio_id, -1)` 的
   `CREATE UNIQUE INDEX`，不出现「非 SQLite 就跳过」（#2534 的两次停摆教训）。

第 2 条必须真插行验证，不能只看索引名还在——「名字对、表达式错」是这条迁移最可能的
失手形态（`COALESCE` 那维漏掉时，索引依然能建成功）。
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.migrations_snapshots import migrate_asset_snapshots_portfolio_scope

from .migrations_pg_fake import PgFake

_OLD_DDL = """
CREATE TABLE asset_snapshots (
    id INTEGER NOT NULL PRIMARY KEY,
    family_id INTEGER NOT NULL,
    ledger_id INTEGER,
    snapshot_date DATE NOT NULL,
    total_assets INTEGER NOT NULL,
    total_liabilities INTEGER NOT NULL,
    net_worth INTEGER NOT NULL,
    realized_pnl_cents INTEGER NOT NULL DEFAULT 0,
    unrealized_pnl_cents INTEGER NOT NULL DEFAULT 0,
    total_pnl_cents INTEGER NOT NULL DEFAULT 0,
    money_fund_income_cents INTEGER
);
CREATE UNIQUE INDEX uq_asset_snapshots_scope
    ON asset_snapshots (family_id, COALESCE(ledger_id, -1), snapshot_date);
CREATE INDEX idx_asset_snapshots_ledger_date ON asset_snapshots (ledger_id, snapshot_date);
INSERT INTO asset_snapshots
    (family_id, ledger_id, snapshot_date, total_assets, total_liabilities, net_worth)
VALUES
    (1, NULL, '2026-11-01', 100000, 0, 100000),
    (1, 3, '2026-11-01', 40000, 0, 40000);
"""


@pytest.fixture
def old_db(tmp_path):
    path = tmp_path / 'old_user.db'
    conn = sqlite3.connect(str(path))
    conn.executescript(_OLD_DDL)
    conn.commit()
    conn.close()
    engine = create_engine(f'sqlite:///{path}')
    yield engine
    engine.dispose()


def _index_sql(engine, name='uq_asset_snapshots_scope') -> str:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='index' AND name=:n"), {'n': name}).first()
    return (row[0] or '') if row else ''


def _insert(engine, *, ledger_id, portfolio_id, total=1) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                'INSERT INTO asset_snapshots'
                ' (family_id, ledger_id, portfolio_id, snapshot_date, total_assets,'
                '  total_liabilities, net_worth)'
                " VALUES (1, :l, :p, '2026-11-02', :t, 0, :t)"
            ),
            {'l': ledger_id, 'p': portfolio_id, 't': total},
        )


def test_迁移加列且存量行原样保留(old_db):
    result = migrate_asset_snapshots_portfolio_scope(old_db)
    assert result.startswith('[OK]')
    assert 'portfolio_id' in {c['name'] for c in inspect(old_db).get_columns('asset_snapshots')}

    with old_db.connect() as conn:
        rows = list(
            conn.execute(text('SELECT ledger_id, portfolio_id, net_worth FROM asset_snapshots ORDER BY ledger_id'))
        )
    # 存量行 portfolio_id 全 NULL（= 家庭 / 账户档），金额不动
    assert [(r[0], r[1], r[2]) for r in rows] == [(None, None, 100000), (3, None, 40000)]


def test_同日两个组合行能共存而同档仍去重(old_db):
    """只加列不重建键时，两条组合行会撞旧三列键 —— 这条用例就是那个洞的回归网。"""
    migrate_asset_snapshots_portfolio_scope(old_db)

    _insert(old_db, ledger_id=None, portfolio_id=1, total=111)
    _insert(old_db, ledger_id=None, portfolio_id=2, total=222)

    with old_db.connect() as conn:
        rows = dict(
            (r[0], r[1])
            for r in conn.execute(
                text("SELECT portfolio_id, net_worth FROM asset_snapshots WHERE snapshot_date='2026-11-02'")
            )
        )
    assert rows == {1: 111, 2: 222}

    # 同一档位同一天再插必须被唯一键拦下（重建键没把去重弄丢）
    with pytest.raises(Exception):
        _insert(old_db, ledger_id=None, portfolio_id=1, total=999)


def test_索引表达式含组合维度(old_db):
    migrate_asset_snapshots_portfolio_scope(old_db)
    sql = _index_sql(old_db)
    assert 'COALESCE(portfolio_id, -1)' in sql, sql
    assert 'COALESCE(ledger_id, -1)' in sql, sql
    # 次要索引也要建（跨账户 / 跨组合的按日期扫描）
    assert 'idx_asset_snapshots_portfolio_date' in _index_sql(old_db, 'idx_asset_snapshots_portfolio_date')


def test_幂等_已迁移则跳过(old_db):
    migrate_asset_snapshots_portfolio_scope(old_db)
    second = migrate_asset_snapshots_portfolio_scope(old_db)
    assert second.startswith('[SKIP]')
    assert '唯一键已含组合维度' in second


def test_空库安全跳过(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "empty.db"}')
    try:
        assert migrate_asset_snapshots_portfolio_scope(engine).startswith('[SKIP]')
    finally:
        engine.dispose()


def test_PG分支发加列与重建唯一索引(monkeypatch):
    fake = PgFake(
        {
            'asset_snapshots': [
                'id',
                'family_id',
                'ledger_id',
                'snapshot_date',
                'total_assets',
                'total_liabilities',
                'net_worth',
            ]
        }
    )
    fake.install(monkeypatch)

    result = migrate_asset_snapshots_portfolio_scope(fake.engine)

    assert result.startswith('[OK]'), result
    assert any('ALTER TABLE asset_snapshots ADD COLUMN' in s and 'portfolio_id' in s for s in fake.sql), fake.sql
    assert any(
        'CREATE UNIQUE INDEX uq_asset_snapshots_scope' in s and 'COALESCE(portfolio_id, -1)' in s for s in fake.sql
    ), fake.sql
    assert 'portfolio_id' in fake.columns['asset_snapshots']
