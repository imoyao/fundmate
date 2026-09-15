# -*- coding: utf-8 -*-
"""#1392 回归：advisor_portfolios 数据来历列（source / extra）迁移。

验证 `migrate_advisor_portfolio_provenance`：
- 旧库（加列之前）执行后补列成功，且**存量行保持 NULL**（不伪造来源）；
- 幂等：重复执行不报错、不重复加列；
- 空库（表不存在）安全 skip，交给 create_all 建表；
- 非 SQLite 引擎（Supabase Postgres）安全 skip，避免误跑 SQLite 专属 SQL。
"""

import sqlite3

from sqlalchemy import create_engine, inspect, text

from app.core.migrations import migrate_advisor_portfolio_provenance


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


class _FakeEngine:
    """只需 url 属性的假引擎：非 SQLite 分支在读 url 后即返回，不会真正连库。"""

    def __init__(self, url: str):
        self.url = url


def test_non_sqlite_skipped():
    assert migrate_advisor_portfolio_provenance(_FakeEngine('postgresql://u:p@host/db')).startswith('[SKIP]')
    assert migrate_advisor_portfolio_provenance(_FakeEngine('mysql+pymysql://u:p@host/db')).startswith('[SKIP]')
