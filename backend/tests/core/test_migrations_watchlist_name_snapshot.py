# -*- coding: utf-8 -*-
"""#1508 回归：watchlist.name 名称快照列迁移。

验证 `migrate_watchlist_name_snapshot`：
- 旧库（加列之前）执行后补列成功，且**存量行保持 NULL**（读取端据此落回反查链，不倒退）；
- 幂等：重复执行不报错、不重复加列；
- 空库（表不存在）安全 skip，交给 create_all 建表；
- 非 SQLite 引擎（Supabase Postgres）安全 skip，避免误跑 SQLite 专属 SQL。
"""

import sqlite3

from sqlalchemy import create_engine, inspect, text

from app.core.migrations import migrate_watchlist_name_snapshot


def _make_old_db(path) -> None:
    """造一个「加 name 列之前」的 watchlist 表（保留 NOT NULL market/venue 以贴近真实）。"""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE watchlist (
            id INTEGER PRIMARY KEY,
            symbol VARCHAR(50) NOT NULL,
            market VARCHAR(10) NOT NULL DEFAULT '',
            asset_type VARCHAR(20),
            venue VARCHAR(10) NOT NULL DEFAULT ''
        );
        INSERT INTO watchlist(symbol, market, asset_type, venue)
        VALUES ('SZ159857', 'CN_A', 'etf', 'EXCHANGE');
        """
    )
    conn.commit()
    conn.close()


def _engine_for(path):
    # Windows 上 as_posix() 才与 SQLAlchemy 的 sqlite URL 约定一致（反斜杠会解析异常）
    return create_engine(f'sqlite:///{path.as_posix()}')


def test_adds_name_column_and_preserves_rows(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    result = migrate_watchlist_name_snapshot(engine)
    assert result.startswith('[OK]')

    cols = {c['name'] for c in inspect(engine).get_columns('watchlist')}
    assert 'name' in cols

    with engine.connect() as conn:
        rows = conn.execute(text('SELECT symbol, name FROM watchlist')).fetchall()
    # 存量行 name 为 NULL → 读取端落回反查链，行为与迁移前一致
    assert rows == [('SZ159857', None)]


def test_idempotent(tmp_path):
    db = tmp_path / 'invest.db'
    _make_old_db(db)
    engine = _engine_for(db)

    assert migrate_watchlist_name_snapshot(engine).startswith('[OK]')
    second = migrate_watchlist_name_snapshot(engine)
    assert second.startswith('[SKIP]')

    cols = [c['name'] for c in inspect(engine).get_columns('watchlist')]
    assert cols.count('name') == 1  # 未重复加列


def test_missing_table_skipped(tmp_path):
    """空库：表还不存在 → skip（由 create_all 按新模型建表），不得抛错阻断启动。"""
    engine = _engine_for(tmp_path / 'empty.db')
    assert migrate_watchlist_name_snapshot(engine).startswith('[SKIP]')


class _FakeEngine:
    """只需 url 属性的假引擎：非 SQLite 分支在读 url 后即返回，不会真正连库。"""

    def __init__(self, url: str):
        self.url = url


def test_non_sqlite_skipped():
    assert migrate_watchlist_name_snapshot(_FakeEngine('postgresql://u:p@host/db')).startswith('[SKIP]')
    assert migrate_watchlist_name_snapshot(_FakeEngine('mysql+pymysql://u:p@host/db')).startswith('[SKIP]')
