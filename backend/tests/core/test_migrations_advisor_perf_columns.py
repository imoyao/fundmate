# -*- coding: utf-8 -*-
"""投顾详情页 P0（2026-10-29）：`advisor_portfolios` 2/3 年区间 + 基准收益列迁移。

验证 `migrate_advisor_portfolio_perf_columns`：

- 旧库（加列之前）执行后补 **10 列**成功，且**存量行保持 NULL**（不回填、不伪造）；
- 幂等：重复执行 `[SKIP]`，不重复加列；
- 表不存在（空库）安全 skip，交给 `create_all`；
- **PG 分支也要加列**（#2534）：生产 user 域是 Postgres，本仓没有 Alembic、
  `create_all` 又不给存量表加列 —— 「非 SQLite 就跳过」等于生产永远缺列并被
  `_validate_schema` 拒绝启动。

## 为什么列数要逐个数

设计稿 v2 估的是「3 列」（当时只探了 `BENCHSYL_LN` / `BENCHSYL_1N` 两个键），实网复测
`BENCHSYL_*` 9 档全有值，落地为 **8 个基准列 + 2 个区间列**。少建一列 = 业绩表整行
永远渲染 `—`，而数据明明在手里；多建一列 = 违反数据准入「新列必须当场指定读者」。
所以这里用**集合相等**钉死，而不是 `issubset`。
"""

import sqlite3

from sqlalchemy import create_engine, inspect, text

from app.core.migrations import migrate_advisor_portfolio_perf_columns

from .migrations_pg_fake import PgFake

#: 本次新增的 10 列（与模型 / `CANONICAL_OVERVIEW_COLUMNS` 三处一致）
EXPECTED_COLUMNS = {
    'return_2y',
    'return_3y',
    'benchmark_return_1m',
    'benchmark_return_1q',
    'benchmark_return_6m',
    'benchmark_return_ytd',
    'benchmark_return_1y',
    'benchmark_return_2y',
    'benchmark_return_3y',
    'benchmark_return_since_incep',
}


def _make_old_db(path) -> None:
    """造一个「这 10 列都还没有」的 advisor_portfolios 表（带一行业绩数据）。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE advisor_portfolios (
            id INTEGER PRIMARY KEY,
            code VARCHAR(30) NOT NULL UNIQUE,
            platform VARCHAR(20) NOT NULL,
            name VARCHAR(100) NOT NULL,
            return_1y NUMERIC(7,2),
            return_since_incep NUMERIC(7,2)
        );
        INSERT INTO advisor_portfolios(code, platform, name, return_1y, return_since_incep)
        VALUES ('XCOVSEX', 'TIANTIAN', '越海', -3.02, 18.46);
        """
    )
    conn.commit()
    conn.close()


def _engine_for(path):
    # Windows 上 as_posix() 才与 SQLAlchemy 的 sqlite URL 约定一致（反斜杠会解析异常）
    return create_engine(f'sqlite:///{path.as_posix()}')


def test_adds_all_ten_columns_and_preserves_rows(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    result = migrate_advisor_portfolio_perf_columns(engine)
    assert result.startswith('[OK]'), result

    cols = {c['name'] for c in inspect(engine).get_columns('advisor_portfolios')}
    missing = EXPECTED_COLUMNS - cols
    assert not missing, f'缺列：{sorted(missing)}'

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                'SELECT code, return_since_incep, return_2y, benchmark_return_since_incep '
                "FROM advisor_portfolios WHERE code='XCOVSEX'"
            )
        ).fetchall()
    # 存量行：老列原值保留，新列 NULL（等下一次同步写入，不回填 0）
    assert rows == [('XCOVSEX', 18.46, None, None)]


def test_idempotent(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    assert migrate_advisor_portfolio_perf_columns(engine).startswith('[OK]')
    assert migrate_advisor_portfolio_perf_columns(engine).startswith('[SKIP]')

    names = [c['name'] for c in inspect(engine).get_columns('advisor_portfolios')]
    for col in EXPECTED_COLUMNS:
        assert names.count(col) == 1, f'{col} 被重复添加'


def test_missing_table_skipped(tmp_path):
    """空库：表还不存在 → skip（由 create_all 按新模型建表），不得抛错阻断启动。"""
    engine = _engine_for(tmp_path / 'empty.db')
    assert migrate_advisor_portfolio_perf_columns(engine).startswith('[SKIP]')


def test_pg_branch_adds_columns_with_if_not_exists(monkeypatch):
    """#2534：PG 分支必须真的发 DDL，不许「非 SQLite 就跳过」。"""
    fake = PgFake({'advisor_portfolios': ['id', 'code', 'platform', 'name']})
    fake.install(monkeypatch)

    result = migrate_advisor_portfolio_perf_columns(fake.engine)

    assert result.startswith('[OK]'), f'PG 分支不许返回跳过：{result}'
    assert '非 SQLite' not in result
    assert EXPECTED_COLUMNS <= set(fake.columns['advisor_portfolios'])
    for name in ('return_2y', 'return_3y', 'benchmark_return_since_incep'):
        expected = f'ALTER TABLE advisor_portfolios ADD COLUMN IF NOT EXISTS {name} NUMERIC(7,2)'
        assert expected in fake.sql, f'{name} 的 DDL 形态不对：{fake.sql}'


def test_pg_branch_idempotent(monkeypatch):
    fake = PgFake({'advisor_portfolios': ['id', 'code', 'platform', 'name', *sorted(EXPECTED_COLUMNS)]})
    fake.install(monkeypatch)

    result = migrate_advisor_portfolio_perf_columns(fake.engine)

    assert result.startswith('[SKIP]') and '已存在' in result
    assert fake.sql == [], f'列已齐时不该发 DDL：{fake.sql}'
