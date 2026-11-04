# -*- coding: utf-8 -*-
"""#1392 回归：advisor_portfolios 数据来历列（source / extra）迁移。

验证 `migrate_advisor_portfolio_provenance`：
- 旧库（加列之前）执行后补列成功，且**存量行保持 NULL**（不伪造来源）；
- 幂等：重复执行不报错、不重复加列；
- 空库（表不存在）安全 skip，交给 create_all 建表；
- **PG 分支不再早退**（#2534）：生产 user 域是 Supabase Postgres，本仓没有
  Alembic、create_all 也不给存量表加列——「非 SQLite 就跳过」等于生产永远缺列
  并被 `_validate_schema` 拒绝启动（#2469 / #2532 两次停摆的根因）。
"""

import sqlite3

from sqlalchemy import create_engine, inspect, text

from app.core.migrations import migrate_advisor_portfolio_provenance

from .migrations_pg_fake import PgFake


def _make_old_db(path) -> None:
    """造一个「加 source/extra 列之前」的 advisor_portfolios 表。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE advisor_portfolios (
            id INTEGER PRIMARY KEY,
            code VARCHAR(30) NOT NULL UNIQUE,
            platform VARCHAR(20) NOT NULL,
            name VARCHAR(100) NOT NULL,
            max_drawdown NUMERIC(6,2)
        );
        INSERT INTO advisor_portfolios(code, platform, name, max_drawdown)
        VALUES ('ZH012926', 'QIEMAN', '远足', 32.96);
        """
    )
    conn.commit()
    conn.close()


def _engine_for(path):
    # Windows 上 as_posix() 才与 SQLAlchemy 的 sqlite URL 约定一致（反斜杠会解析异常）
    return create_engine(f'sqlite:///{path.as_posix()}')


def test_adds_provenance_columns_and_preserves_rows(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    result = migrate_advisor_portfolio_provenance(engine)
    assert result.startswith('[OK]')

    cols = {c['name'] for c in inspect(engine).get_columns('advisor_portfolios')}
    assert {'source', 'extra'} <= cols

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT code, source, extra FROM advisor_portfolios WHERE code='ZH012926'")).fetchall()
    # 存量行为 NULL → 落库层下次成功抓取时才写入来源，不伪造
    assert rows == [('ZH012926', None, None)]


def test_idempotent(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    assert migrate_advisor_portfolio_provenance(engine).startswith('[OK]')
    assert migrate_advisor_portfolio_provenance(engine).startswith('[SKIP]')

    cols = [c['name'] for c in inspect(engine).get_columns('advisor_portfolios')]
    assert cols.count('source') == 1  # 未重复加列
    assert cols.count('extra') == 1


def test_missing_table_skipped(tmp_path):
    """空库：表还不存在 → skip（由 create_all 按新模型建表），不得抛错阻断启动。"""
    engine = _engine_for(tmp_path / 'empty.db')
    assert migrate_advisor_portfolio_provenance(engine).startswith('[SKIP]')


def test_pg_branch_adds_columns_with_if_not_exists(monkeypatch):
    """#2534：PG 不再早退，两列各发一条 `ADD COLUMN IF NOT EXISTS`。"""
    fake = PgFake({'advisor_portfolios': ['id', 'code', 'platform', 'name']})
    fake.install(monkeypatch)

    result = migrate_advisor_portfolio_provenance(fake.engine)

    assert result.startswith('[OK]'), f'PG 分支不许再返回跳过：{result}'
    assert '非 SQLite' not in result
    assert {'source', 'extra'} <= set(fake.columns['advisor_portfolios'])
    for name, ddl in (('source', 'VARCHAR(20)'), ('extra', 'JSON')):
        expected = f'ALTER TABLE advisor_portfolios ADD COLUMN IF NOT EXISTS {name} {ddl}'
        assert expected in fake.sql, f'{name} 的 DDL 形态不对：{fake.sql}'


def test_pg_branch_idempotent(monkeypatch):
    """PG 上列已齐：不发 DDL，返回已存在。"""
    fake = PgFake({'advisor_portfolios': ['id', 'code', 'platform', 'name', 'source', 'extra']})
    fake.install(monkeypatch)

    result = migrate_advisor_portfolio_provenance(fake.engine)

    assert result.startswith('[SKIP]') and '已存在' in result
    assert fake.sql == [], f'列已齐时不该发 DDL：{fake.sql}'


def test_pg_branch_missing_table_skips(monkeypatch):
    """PG 上表不存在（空库）：安全 skip，不抛错阻断启动。"""
    fake = PgFake({})
    fake.install(monkeypatch)

    assert migrate_advisor_portfolio_provenance(fake.engine).startswith('[SKIP]')
