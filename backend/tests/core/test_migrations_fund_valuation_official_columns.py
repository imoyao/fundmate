# -*- coding: utf-8 -*-
"""#2142 回归：fund_valuation_daily 补对照三列（official_nav / deviation / deviation_pct）。

验证 `migrate_fund_valuation_official_columns`：

- 旧库（加列之前，K 卡 #2141 建的表形）执行后补列成功，且**存量行保持 NULL**
  ——对照信息只能由 reconcile job 事后写，迁移不猜数；
- 幂等：重复执行不报错、不重复加列；
- 空库（表不存在）安全 skip，交给 create_all 建表；
- 非 SQLite 引擎（Supabase Postgres）安全 skip，避免误跑 SQLite 专属 SQL。
"""

import sqlite3

from sqlalchemy import create_engine, inspect, text

from app.core.migrations import migrate_fund_valuation_official_columns


def _make_old_db(path) -> None:
    """造一个「对照三列之前」的 fund_valuation_daily 表（K 卡 #2141 原始列集）。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE fund_valuation_daily (
            id INTEGER PRIMARY KEY,
            fund_code VARCHAR(16) NOT NULL,
            est_date DATE NOT NULL,
            estimated_nav NUMERIC(18, 6) NOT NULL,
            change_pct NUMERIC(10, 4),
            source_time VARCHAR(32),
            source VARCHAR(32),
            status VARCHAR(16),
            created_at DATETIME,
            updated_at DATETIME,
            CONSTRAINT uq_fund_valuation_code_date UNIQUE (fund_code, est_date)
        );
        INSERT INTO fund_valuation_daily(fund_code, est_date, estimated_nav, source, status)
        VALUES ('000001', '2026-10-13', 1.234567, 'tiantian_gsz', 'estimated');
        """
    )
    conn.commit()
    conn.close()


def _engine_for(path):
    # Windows 上 as_posix() 才与 SQLAlchemy 的 sqlite URL 约定一致（反斜杠会解析异常）
    return create_engine(f'sqlite:///{path.as_posix()}')


def test_adds_columns_and_leaves_existing_rows_null(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    result = migrate_fund_valuation_official_columns(engine)
    assert result.startswith('[OK]')

    cols = [c['name'] for c in inspect(engine).get_columns('fund_valuation_daily')]
    assert 'official_nav' in cols
    assert 'deviation' in cols
    assert 'deviation_pct' in cols

    with engine.connect() as conn:
        rows = conn.execute(
            text('SELECT fund_code, official_nav, deviation, deviation_pct, status FROM fund_valuation_daily')
        ).fetchall()
    # 关键：不回填。对照三列只能由 reconcile job 在官方净值到位后写，
    # 迁移猜出来的「偏差」没有官方值依据
    assert rows == [('000001', None, None, None, 'estimated')]


def test_idempotent(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    assert migrate_fund_valuation_official_columns(engine).startswith('[OK]')
    second = migrate_fund_valuation_official_columns(engine)
    assert second.startswith('[SKIP]')

    cols = [c['name'] for c in inspect(engine).get_columns('fund_valuation_daily')]
    assert cols.count('official_nav') == 1
    assert cols.count('deviation') == 1
    assert cols.count('deviation_pct') == 1


def test_missing_table_skipped(tmp_path):
    """空库：表还不存在 → skip（由 create_all 按新模型建表），不得抛错阻断启动。"""
    engine = _engine_for(tmp_path / 'empty.db')
    assert migrate_fund_valuation_official_columns(engine).startswith('[SKIP]')


class _FakeEngine:
    """只需 url 属性的假引擎：非 SQLite 分支在读 url 后即返回，不会真正连库。"""

    def __init__(self, url: str):
        self.url = url


def test_non_sqlite_skipped():
    assert migrate_fund_valuation_official_columns(_FakeEngine('postgresql://u:p@host/db')).startswith('[SKIP]')
    assert migrate_fund_valuation_official_columns(_FakeEngine('mysql+pymysql://u:p@host/db')).startswith('[SKIP]')
