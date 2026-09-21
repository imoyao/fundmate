# -*- coding: utf-8 -*-
"""#1609 / #1632 事务边界回归：请求级单会话 unit-of-work 与 BaseRepository 只 flush。

范式（conventions §2.13 方案 A，决策 D30）：事务由视图 / 用例层持有。
#1632 后 ``get_db()``（``with_db`` 亦经它）在**请求上下文**内是请求级单会话：
同一请求多次进入**复用同一 Session**，最外层提交（成功）/ 回滚（异常）；
非请求上下文（job / CLI）保持独立会话、不自动提交。

反向验证：去掉最外层 commit、或让每次 ``get_db()`` 新开 Session，下面用例必须转红。
"""

import pytest

from app.core.database import BaseRepository, get_db
from app.core.utils import with_db
from app.domains.ledgers.models import Ledger


def test_with_db_commits_on_success(app, db):
    """请求内 handler 未显式 commit，成功返回后写入必须持久（最外层边界代提交）。"""

    @with_db
    def handler(session):
        session.add(Ledger(name='边界账户', ledger_type='bank', family_id=1))
        return 'ok'

    with app.test_request_context('/api/'):
        assert handler() == 'ok'
    assert db.query(Ledger).filter_by(name='边界账户').count() == 1


def test_with_db_rolls_back_on_exception(app, db):
    """请求内 handler 抛异常 → 整体回滚：中途 flush 的写入不得残留。"""

    @with_db
    def handler(session):
        session.add(Ledger(name='半截账户', ledger_type='bank', family_id=1))
        session.flush()  # 模拟多步写：先落一半
        raise RuntimeError('boom')

    with pytest.raises(RuntimeError):
        with app.test_request_context('/api/'):
            handler()
    assert db.query(Ledger).filter_by(name='半截账户').count() == 0


def test_nested_get_db_reuses_same_request_session(app):
    """请求内嵌套 ``get_db()`` 必须复用同一 Session（#1632 核心契约）。"""
    with app.test_request_context('/api/'):
        with get_db() as outer:
            with get_db() as inner:
                assert outer is inner


def test_nested_get_db_shares_session_and_commits_at_request_end(app, db):
    """嵌套 ``get_db()`` 复用同一 Session；提交发生在请求结束（teardown）。"""
    with app.test_request_context('/api/'):
        with get_db() as outer:
            with get_db() as inner:
                inner.add(Ledger(name='嵌套账户', ledger_type='bank', family_id=1))
                inner.flush()
                assert outer is inner
    assert db.query(Ledger).filter_by(name='嵌套账户').count() == 1


def test_sequential_get_db_reuses_same_request_session(app):
    """同一请求内**先后**两个 ``with get_db()`` 块也必须复用同一 Session。

    回归 #1632：若在块退出时提交 / 关闭，第二个块会拿到新 Session，且首块对象
    detach + expire → 视图后续访问报 ``DetachedInstanceError``（strategy 视图实测）。
    """
    with app.test_request_context('/api/'):
        with get_db() as first:
            pass
        with get_db() as second:
            assert first is second


def test_get_db_outside_request_keeps_independent_sessions(app):
    """非请求上下文（job / CLI）：每次 ``get_db()`` 仍是独立会话，不自动提交。"""
    with get_db() as a:
        with get_db() as b:
            assert a is not b


def test_base_repository_save_only_flushes(app, db):
    """``BaseRepository.save()`` 只 flush：分配主键但不提交 → 回滚可撤销。"""
    led = Ledger(name='repo账户', ledger_type='bank', family_id=1)
    BaseRepository.save(led, db)

    assert led.id is not None  # flush 已分配主键（未提交）

    db.rollback()  # 若 save 内建 commit，回滚也删不掉 → 下一行断言转红
    assert db.query(Ledger).filter_by(name='repo账户').count() == 0


def test_base_repository_delete_only_flushes(app, db):
    """``BaseRepository.delete()`` 只 flush：会话内已删但不提交 → 回滚可恢复。"""
    led = Ledger(name='del账户', ledger_type='bank', family_id=1)
    db.add(led)
    db.commit()

    BaseRepository.delete(led, db)
    # flush 后当前会话内已不可见（若只 flush 未 commit，回滚应恢复）
    assert db.query(Ledger).filter_by(name='del账户').count() == 0

    db.rollback()
    assert db.query(Ledger).filter_by(name='del账户').count() == 1
