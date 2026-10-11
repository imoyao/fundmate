# -*- coding: utf-8 -*-
"""#2007 回归：positions 补「当日盈亏」的基准列（`prev_close` / `price_date`）。

验证 `migrate_positions_price_columns`：

- 旧库（加列之前）执行后补列成功，且**存量行保持 NULL**——当日盈亏降级「—」，
  绝不由迁移猜一个数出来；
- **只加列、不回填**：`prev_close` 是「上一确认价」，只能由行情链路在写 `current_price`
  的**同一批**里取到，事后凭历史数据补不出时点正确的值（补错比空着更糟）；
- 幂等：重复执行不报错、不重复加列；
- 空库（表不存在）安全 skip，交给 create_all 建表；
- 非 SQLite 引擎（Supabase Postgres）安全 skip，避免误跑 SQLite 专属 SQL。
"""

import sqlite3

from sqlalchemy import create_engine, inspect, text

from app.core.migrations import migrate_positions_price_columns


def _make_old_db(path) -> None:
    """造一个「加 prev_close / price_date 之前」的 positions 表（保留真实列以贴近库形）。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE positions (
            id INTEGER PRIMARY KEY,
            symbol VARCHAR(30) NOT NULL,
            market VARCHAR(20),
            type VARCHAR(20),
            quantity INTEGER DEFAULT 0,
            avg_price INTEGER DEFAULT 0,
            current_price INTEGER DEFAULT 0
        );
        INSERT INTO positions(symbol, market, type, quantity, avg_price, current_price)
        VALUES ('023887', 'CN_FUND', 'fund', 1000000, 8300, 8567);
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

    result = migrate_positions_price_columns(engine)
    assert result.startswith('[OK]')

    cols = [c['name'] for c in inspect(engine).get_columns('positions')]
    assert 'prev_close' in cols
    assert 'price_date' in cols

    with engine.connect() as conn:
        rows = conn.execute(text('SELECT symbol, prev_close, price_date FROM positions')).fetchall()
    # 关键：不回填。历史行没有可信的「上一确认价」，留 NULL 让前端降级「—」，
    # 而不是凭 current_price 反推一个看起来合理的数（那会被当成当日涨跌读）
    assert rows == [('023887', None, None)]


def test_idempotent(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    assert migrate_positions_price_columns(engine).startswith('[OK]')
    second = migrate_positions_price_columns(engine)
    assert second.startswith('[SKIP]')

    cols = [c['name'] for c in inspect(engine).get_columns('positions')]
    assert cols.count('prev_close') == 1
    assert cols.count('price_date') == 1


def test_missing_table_skipped(tmp_path):
    """空库：表还不存在 → skip（由 create_all 按新模型建表），不得抛错阻断启动。"""
    engine = _engine_for(tmp_path / 'empty.db')
    assert migrate_positions_price_columns(engine).startswith('[SKIP]')


class _FakeEngine:
    """只需 url 属性的假引擎：非 SQLite 分支在读 url 后即返回，不会真正连库。"""

    def __init__(self, url: str):
        self.url = url


def test_non_sqlite_skipped():
    assert migrate_positions_price_columns(_FakeEngine('postgresql://u:p@host/db')).startswith('[SKIP]')
    assert migrate_positions_price_columns(_FakeEngine('mysql+pymysql://u:p@host/db')).startswith('[SKIP]')
