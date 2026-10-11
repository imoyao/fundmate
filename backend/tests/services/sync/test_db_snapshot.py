# -*- coding: utf-8 -*-
"""DB 下载导入层测试（#1776 ⑤）。

覆盖三段：
- 导出：市场域表白名单 + meta（format_version / counts / missing_tables）；
- 导入：同名列剔除 rowid 主键列、按本地唯一约束幂等去重（不覆盖本地记录）、
  无唯一约束的表在目标非空时跳过；
- 校验：非 SQLite / 缺 meta / 含白名单外表 / 版本不符 → 明确拒绝。

刻意**不依赖 app fixtures**：导出/导入都支持显式传源/目标路径，
测试用最小 schema 的临时 SQLite 文件即可（不拉起整个应用）。
"""

import json
import sqlite3
from pathlib import Path

import pytest

from app.services.sync import snapshot as snapshot_service


def _make_market_db(path: Path, *, with_rows: bool = True) -> None:
    """构造最小市场域库：funds（UNIQUE fund_code）+ daily_worth（UNIQUE code+date）。"""
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            CREATE TABLE funds (
                id INTEGER PRIMARY KEY,
                fund_code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL
            );
            CREATE TABLE daily_worth (
                id INTEGER PRIMARY KEY,
                fund_code TEXT NOT NULL,
                date TEXT NOT NULL,
                unit_nav REAL,
                UNIQUE (fund_code, date)
            );
            """
        )
        if with_rows:
            conn.execute("INSERT INTO funds (fund_code, name) VALUES ('000001', '华夏成长')")
            conn.executemany(
                'INSERT INTO daily_worth (fund_code, date, unit_nav) VALUES (?, ?, ?)',
                [('000001', f'2026-09-{d:02d}', 1.0 + d / 100) for d in range(1, 6)],
            )
        conn.commit()
    finally:
        conn.close()


def _query(path: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


# ── 导出 ──────────────────────────────────────────────────────────────────


def test_export_copies_market_tables_and_meta(tmp_path):
    src = tmp_path / 'invest.db'
    snapshot = tmp_path / 'snapshot.db'
    _make_market_db(src)

    meta = snapshot_service.export_snapshot(snapshot, source_path=src)

    assert Path(meta['path']) == snapshot
    assert meta['format_version'] == snapshot_service.FORMAT_VERSION

    tables = _query(snapshot, "SELECT name FROM sqlite_master WHERE type='table'")
    names = {r[0] for r in tables}
    # 只含市场域表 + meta；sync_logs / 用户域表一律不出现
    assert {'funds', 'daily_worth', snapshot_service.SNAPSHOT_META_TABLE} <= names
    assert 'sync_logs' not in names
    assert 'positions' not in names

    # 行数如实记录
    counts = json.loads(meta['counts'])
    assert counts['funds'] == 1
    assert counts['daily_worth'] == 5
    # 行数据真实落进快照
    assert len(_query(snapshot, 'SELECT 1 FROM daily_worth')) == 5


def test_export_records_tables_missing_in_source(tmp_path):
    """源库缺某张市场域表（模型领先于存量库）→ 记入 missing，而不是炸掉导出"""
    src = tmp_path / 'invest.db'
    conn = sqlite3.connect(str(src))
    conn.execute('CREATE TABLE funds (id INTEGER PRIMARY KEY, fund_code TEXT UNIQUE, name TEXT)')
    conn.commit()
    conn.close()

    meta = snapshot_service.export_snapshot(tmp_path / 'snapshot.db', source_path=src)

    assert 'securities' in json.loads(meta['missing_tables'])
    assert 'funds' in json.loads(meta['tables'])


def test_export_is_atomic_no_tmp_left(tmp_path):
    src = tmp_path / 'invest.db'
    _make_market_db(src)
    snapshot = tmp_path / 'snapshot.db'

    snapshot_service.export_snapshot(snapshot, source_path=src)

    assert snapshot.exists()
    assert not (tmp_path / 'snapshot.db.tmp').exists()


# ── 校验 ──────────────────────────────────────────────────────────────────


def test_import_rejects_non_sqlite_file(tmp_path):
    fake = tmp_path / 'snapshot.db'
    fake.write_text('这不是 SQLite 文件', encoding='utf-8')

    with pytest.raises(ValueError, match='不是 SQLite 数据库文件'):
        snapshot_service.import_snapshot(fake, db_path=tmp_path / 'target.db')


def test_import_rejects_db_without_meta(tmp_path):
    """没有 snapshot_meta 的库（比如随手拷来的别的库）必须拒绝，防止灌入未知数据"""
    src = tmp_path / 'invest.db'
    _make_market_db(src)
    snapshot = tmp_path / 'snapshot.db'
    snapshot_service.export_snapshot(snapshot, source_path=src)

    # 抹掉 meta 表 → 不再是本仓的快照
    conn = sqlite3.connect(str(snapshot))
    conn.execute('DROP TABLE snapshot_meta')
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match='snapshot_meta'):
        snapshot_service.import_snapshot(snapshot, db_path=tmp_path / 'target.db')


def test_import_rejects_snapshot_containing_user_tables(tmp_path):
    """快照的表清单被篡改、混入用户私有表 → 拒绝导入，这是最重要的安全校验"""
    src = tmp_path / 'invest.db'
    _make_market_db(src)

    snapshot = tmp_path / 'snapshot.db'
    snapshot_service.export_snapshot(snapshot, source_path=src)

    # 篡改快照 meta：把用户私有表 positions 塞进表清单（模拟「来历不明的快照」）
    conn = sqlite3.connect(str(snapshot))
    tables = json.loads(conn.execute("SELECT value FROM snapshot_meta WHERE key='tables'").fetchone()[0])
    tables.append('positions')
    conn.execute(
        "UPDATE snapshot_meta SET value = ? WHERE key = 'tables'",
        (json.dumps(tables),),
    )
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match='白名单之外的表'):
        snapshot_service.import_snapshot(snapshot, db_path=tmp_path / 'target.db')


def test_import_rejects_unknown_format_version(tmp_path):
    src = tmp_path / 'invest.db'
    _make_market_db(src)
    snapshot = tmp_path / 'snapshot.db'
    snapshot_service.export_snapshot(snapshot, source_path=src)

    conn = sqlite3.connect(str(snapshot))
    conn.execute("UPDATE snapshot_meta SET value='999' WHERE key='format_version'")
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match='格式版本不兼容'):
        snapshot_service.import_snapshot(snapshot, db_path=tmp_path / 'target.db')


# ── 导入 ──────────────────────────────────────────────────────────────────


def test_import_fills_missing_rows_without_overwriting_local(tmp_path):
    """核心语义：按业务唯一键幂等补齐——本地已有的记录**不被覆盖**，缺的补上"""
    src = tmp_path / 'invest.db'
    _make_market_db(src)
    snapshot = tmp_path / 'snapshot.db'
    snapshot_service.export_snapshot(snapshot, source_path=src)

    target = tmp_path / 'target.db'
    conn = sqlite3.connect(str(target))
    conn.executescript(
        """
        CREATE TABLE funds (
            id INTEGER PRIMARY KEY,
            fund_code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL
        );
        CREATE TABLE daily_worth (
            id INTEGER PRIMARY KEY,
            fund_code TEXT NOT NULL,
            date TEXT NOT NULL,
            unit_nav REAL,
            UNIQUE (fund_code, date)
        );
        """
    )
    # 本地已有：同 fund 的另一条净值（值不同，验证「不覆盖」）；以及同名基金（id 不同）
    conn.execute("INSERT INTO funds (fund_code, name) VALUES ('000001', '本地已有名称')")
    conn.execute("INSERT INTO daily_worth (fund_code, date, unit_nav) VALUES ('000001', '2026-09-01', 9.99)")
    conn.commit()
    conn.close()

    result = snapshot_service.import_snapshot(snapshot, db_path=target)

    # 5 天净值里 4 天是新的；2026-09-01 本地已有 → 不覆盖（保持 9.99）
    assert result['inserted']['daily_worth'] == 4
    assert result['inserted']['funds'] == 0

    rows = dict(_query(target, "SELECT date, unit_nav FROM daily_worth WHERE fund_code='000001'"))
    assert len(rows) == 5
    assert rows['2026-09-01'] == 9.99  # 本地值原样保留
    assert rows['2026-09-05'] == pytest.approx(1.05)

    # 基金只有一条（业务键去重），名称仍是本地值
    assert _query(target, 'SELECT COUNT(*), name FROM funds GROUP BY fund_code') == [(1, '本地已有名称')]


def test_import_reassigns_rowid_primary_key(tmp_path):
    """快照里的 rowid 主键（id）不导入：另一套库的 id 无意义，交给本地重新分配。

    实证：本地已有一条 id=1 的记录，快照里 000001 的 id 恰好也是 1——
    若 id 被照搬，INSERT OR IGNORE 会因主键冲突把整行丢掉。
    """
    src = tmp_path / 'invest.db'
    _make_market_db(src)
    snapshot = tmp_path / 'snapshot.db'
    snapshot_service.export_snapshot(snapshot, source_path=src)

    target = tmp_path / 'target.db'
    conn = sqlite3.connect(str(target))
    conn.executescript(
        """
        CREATE TABLE funds (
            id INTEGER PRIMARY KEY,
            fund_code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL
        );
        CREATE TABLE daily_worth (
            id INTEGER PRIMARY KEY,
            fund_code TEXT NOT NULL,
            date TEXT NOT NULL,
            unit_nav REAL,
            UNIQUE (fund_code, date)
        );
        """
    )
    conn.execute("INSERT INTO funds (fund_code, name) VALUES ('000099', '本地已有基金')")
    conn.commit()
    conn.close()

    result = snapshot_service.import_snapshot(snapshot, db_path=target)

    assert result['inserted']['funds'] == 1
    rows = _query(target, 'SELECT id, fund_code FROM funds ORDER BY id')
    # 快照里 000001 的 id=1，本地重新分配为 2（1 已被本地首条占用）
    assert rows == [(1, '000099'), (2, '000001')]


def test_import_skips_keyless_table_when_target_non_empty(tmp_path, monkeypatch):
    """无唯一约束的表没有幂等抓手：目标非空 → 跳过（避免重复行堆积）

    keyless 表刻意**不带任何主键 / 唯一约束**（否则 id 主键本身就构成去重抓手）。
    """
    monkeypatch.setattr(snapshot_service, 'snapshot_tables', lambda: ('daily_worth', 'keyless_market'))
    src = tmp_path / 'invest.db'
    conn = sqlite3.connect(str(src))
    conn.executescript(
        """
        CREATE TABLE daily_worth (id INTEGER PRIMARY KEY, fund_code TEXT, date TEXT, unit_nav REAL);
        CREATE TABLE keyless_market (note TEXT);
        """
    )
    conn.execute("INSERT INTO keyless_market (note) VALUES ('快照里的行')")
    conn.commit()
    conn.close()

    snapshot = tmp_path / 'snapshot.db'
    snapshot_service.export_snapshot(snapshot, source_path=src)

    target = tmp_path / 'target.db'
    conn = sqlite3.connect(str(target))
    conn.executescript(
        """
        CREATE TABLE daily_worth (id INTEGER PRIMARY KEY, fund_code TEXT, date TEXT, unit_nav REAL);
        CREATE TABLE keyless_market (note TEXT);
        """
    )
    conn.execute("INSERT INTO keyless_market (note) VALUES ('本地已有行')")
    conn.commit()
    conn.close()

    result = snapshot_service.import_snapshot(snapshot, db_path=target)

    assert 'keyless_market' in result['skipped']
    assert _query(target, 'SELECT COUNT(*) FROM keyless_market') == [(1,)]


def test_import_reports_locally_missing_tables(tmp_path):
    """本地缺表（代码落后于快照）→ 跳过并报告，而不是把表 DDL 也搬进来"""
    src = tmp_path / 'invest.db'
    _make_market_db(src)
    snapshot = tmp_path / 'snapshot.db'
    snapshot_service.export_snapshot(snapshot, source_path=src)

    target = tmp_path / 'target.db'
    conn = sqlite3.connect(str(target))
    # 目标只有 daily_worth（funds 表还没有）
    conn.execute('CREATE TABLE daily_worth (id INTEGER PRIMARY KEY, fund_code TEXT, date TEXT, unit_nav REAL)')
    conn.commit()
    conn.close()

    result = snapshot_service.import_snapshot(snapshot, db_path=target)

    assert 'funds' in result['skipped']
    assert result['inserted']['daily_worth'] == 5


def test_resolve_market_db_path_rejects_non_sqlite_engine(monkeypatch):
    """市场域是远端库（Turso/Postgres）时显式报错：远端快照由部署侧打包，不走本命令"""

    class _FakeUrl:
        @staticmethod
        def get_backend_name():
            return 'postgresql'

        database = None

    class _FakeEngine:
        url = _FakeUrl()

    monkeypatch.setattr('app.core.database.get_engine', lambda domain: _FakeEngine())

    with pytest.raises(RuntimeError, match='仅支持本地 SQLite'):
        snapshot_service.resolve_market_db_path()
