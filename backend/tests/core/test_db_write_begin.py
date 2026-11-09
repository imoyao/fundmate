# -*- coding: utf-8 -*-
"""本地 SQLite 写事务以 ``BEGIN IMMEDIATE`` 开始（``db_factory._apply_sqlite_write_begin``）。

回归对象（2026-11-09 实测日志）：WAL 下「事务已读过 → 别的连接提交 → 本事务再写」时，
SQLite 无法把读快照升级成写锁，**立即**返回 ``database is locked``
（``SQLITE_BUSY_SNAPSHOT``，busy handler 不被调用，``timeout=30`` 不生效）。
导入确认的逐条 ``begin_nested()``（SAVEPOINT → SELECT 去重 → 首次写）正好踩这条，
于是整批导入随机失败。

判据分三层，缺一不可：
1. 连接确实带 ``isolation_level='IMMEDIATE'``（配置没被方言覆盖掉）；
2. SAVEPOINT 事务一开始就持有写锁（对端连写都写不进来）；
3. 先读后写不再瞬间失败，而是「本事务写成功 + 对端排队等锁」。
另加一条反向守卫：PRAGMA / DDL 不得被裹进事务（否则 ``migrations.py`` 的
``PRAGMA foreign_keys=OFF`` 会静默失效，重建表流程会被毁掉）。
"""

import sqlite3
import threading
import time

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.db_factory import DOMAIN_APP, DatabaseFactory


@pytest.fixture()
def engine(monkeypatch, tmp_path):
    db_path = tmp_path / 'write_begin.db'
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('DEV_DATABASE_URL', f'sqlite:///{db_path.as_posix()}')
    DatabaseFactory.reset()
    eng = DatabaseFactory.build(DOMAIN_APP, 'development')
    with eng.begin() as conn:
        conn.execute(text('CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)'))
        conn.execute(text('INSERT INTO t (v) VALUES (0)'))
    try:
        yield eng
    finally:
        eng.dispose()
        DatabaseFactory.reset()


def _dbapi(conn_or_session):
    """取底层 sqlite3 连接（SQLAlchemy 2.0 的公开路径：connection.connection.dbapi_connection）。"""
    conn = conn_or_session.connection() if isinstance(conn_or_session, Session) else conn_or_session
    return conn.connection.dbapi_connection


def test_connection_uses_immediate_isolation(engine):
    """连接级配置生效：隐式 BEGIN 走 IMMEDIATE，而不是 DEFERRED。"""
    with engine.connect() as conn:
        assert _dbapi(conn).isolation_level == 'IMMEDIATE'


def test_savepoint_starts_immediate_transaction(engine):
    """``begin_nested()`` 之后 DBAPI 已有事务，且该事务持写锁（对端 0.05s 就撞 locked）。"""
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        session.begin_nested()
        assert _dbapi(session).in_transaction is True

        other = sqlite3.connect(engine.url.database, timeout=0.05)
        try:
            with pytest.raises(sqlite3.OperationalError, match='database is locked'):
                other.execute('INSERT INTO t (v) VALUES (99)')
        finally:
            other.close()
    finally:
        session.rollback()
        session.close()


def test_write_after_read_waits_instead_of_immediate_busy(engine):
    """回归主判据：SAVEPOINT 事务先读、对端并发写，本事务的写仍成功（排队而非撞快照）。"""
    session = sessionmaker(bind=engine, autoflush=False)()
    errors = []
    started = threading.Event()
    finished = threading.Event()

    def concurrent_writer():
        conn = sqlite3.connect(engine.url.database, timeout=10)
        try:
            started.set()
            conn.execute('INSERT INTO t (v) VALUES (1)')
            conn.commit()
        except Exception as exc:  # noqa: BLE001 - 收集给主线程断言
            errors.append(exc)
        finally:
            conn.close()
            finished.set()

    try:
        session.begin_nested()
        session.execute(text('SELECT COUNT(*) FROM t')).fetchone()  # 建立读快照

        worker = threading.Thread(target=concurrent_writer)
        worker.start()
        assert started.wait(2), '并发写线程未能启动'
        time.sleep(0.3)  # 足够让对端撞上写锁；修复前本事务此刻已不可写
        assert not finished.is_set(), '对端写应当被本事务的写锁挡住'

        session.execute(text('DELETE FROM t WHERE v = 0'))  # 修复前：立即 database is locked
        session.commit()  # 释放写锁
        worker.join(10)

        assert finished.is_set(), '对端写在线程超时后仍未结束'
        assert errors == [], f'对端写失败: {errors!r}'
    finally:
        session.close()


def test_pragma_and_ddl_stay_outside_transaction(engine):
    """反向守卫：PRAGMA / DDL 不进事务，迁移里的 ``PRAGMA foreign_keys=OFF`` 仍生效。"""
    with engine.connect() as conn:
        conn.execute(text('PRAGMA foreign_keys=OFF'))
        assert conn.execute(text('PRAGMA foreign_keys')).scalar() == 0
        assert _dbapi(conn).in_transaction is False
        conn.execute(text('CREATE TABLE ddl_probe (id INTEGER)'))
        assert _dbapi(conn).in_transaction is False
