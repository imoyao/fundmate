# -*- coding: utf-8 -*-
"""#2284 回归：fund_risk_metrics 补区间收益三列（ret_1m / ret_3m / ret_1y）。

验证 `migrate_fund_risk_metrics_period_returns`：

- 旧库（加列之前的 #167 原始表形）执行后补列成功，且**存量行保持 NULL**
  ——区间收益由 job 按 bump 后的 CALIBER_VERSION 重算写入，迁移不回填不猜数；
- 幂等：重复执行不报错、不重复加列；
- 空库（表不存在）安全 skip，交给 create_all 建表；
- 非 SQLite 引擎（Supabase Postgres）安全 skip，避免误跑 SQLite 专属 SQL。
"""

import sqlite3

from sqlalchemy import create_engine, inspect, text

from app.core.migrations import migrate_fund_risk_metrics_period_returns


def _make_old_db(path) -> None:
    """造一个「区间收益三列之前」的 fund_risk_metrics 表（#167 原始列集）。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE fund_risk_metrics (
            id INTEGER PRIMARY KEY,
            fund_code VARCHAR(6) NOT NULL,
            as_of DATE NOT NULL,
            fund_type_id INTEGER,
            max_drawdown NUMERIC(10, 4),
            current_drawdown NUMERIC(10, 4),
            annual_return NUMERIC(10, 4),
            annual_volatility NUMERIC(10, 4),
            sharpe NUMERIC(10, 4),
            sortino NUMERIC(10, 4),
            calmar NUMERIC(10, 4),
            ulcer_index NUMERIC(10, 4),
            upi NUMERIC(10, 4),
            return_drawdown_ratio NUMERIC(10, 4),
            win_rate NUMERIC(10, 4),
            win_rate_period VARCHAR(8),
            sample_points INTEGER NOT NULL,
            basis VARCHAR(16) NOT NULL,
            window_label VARCHAR(16) NOT NULL,
            caliber_version INTEGER NOT NULL,
            created_at DATETIME,
            updated_at DATETIME,
            CONSTRAINT uq_fund_risk_metrics_code_asof UNIQUE (fund_code, as_of)
        );
        INSERT INTO fund_risk_metrics(fund_code, as_of, sample_points, basis, window_label, caliber_version)
        VALUES ('000001', '2026-10-13', 700, 'acc_nav', '近3年', 1);
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

    result = migrate_fund_risk_metrics_period_returns(engine)
    assert result.startswith('[OK]')

    cols = [c['name'] for c in inspect(engine).get_columns('fund_risk_metrics')]
    assert 'ret_1m' in cols
    assert 'ret_3m' in cols
    assert 'ret_1y' in cols

    with engine.connect() as conn:
        rows = conn.execute(
            text('SELECT fund_code, ret_1m, ret_3m, ret_1y, caliber_version FROM fund_risk_metrics')
        ).fetchall()
    # 关键：不回填。区间收益由 job 按 bump 后的口径（v2）重算写入，
    # 迁移阶段回填要在启动路径里扫全量净值，得不偿失且时机不对。
    assert rows == [('000001', None, None, None, 1)]


def test_idempotent(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    assert migrate_fund_risk_metrics_period_returns(engine).startswith('[OK]')
    second = migrate_fund_risk_metrics_period_returns(engine)
    assert second.startswith('[SKIP]')

    cols = [c['name'] for c in inspect(engine).get_columns('fund_risk_metrics')]
    assert cols.count('ret_1m') == 1
    assert cols.count('ret_3m') == 1
    assert cols.count('ret_1y') == 1


def test_missing_table_skipped(tmp_path):
    """空库：表还不存在 → skip（由 create_all 按新模型建表），不得抛错阻断启动。"""
    engine = _engine_for(tmp_path / 'empty.db')
    assert migrate_fund_risk_metrics_period_returns(engine).startswith('[SKIP]')


class _FakeEngine:
    """只需 url 属性的假引擎：非 SQLite 分支在读 url 后即返回，不会真正连库。"""

    def __init__(self, url: str):
        self.url = url


def test_non_sqlite_skipped():
    assert migrate_fund_risk_metrics_period_returns(_FakeEngine('postgresql://u:p@host/db')).startswith('[SKIP]')
    assert migrate_fund_risk_metrics_period_returns(_FakeEngine('mysql+pymysql://u:p@host/db')).startswith('[SKIP]')
