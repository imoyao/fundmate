# -*- coding: utf-8 -*-
"""#1640 回归：user / market 域会话的请求级单会话（事务边界在请求 teardown）。

背景：``user_session()`` 原先只 ``yield`` + ``close()``、**既不提交也不回滚**，导致使用它的
视图必须逐个显式 ``commit()``，否则写入随连接关闭**静默丢失**（#1609 batch 3 实测：把
``domains/reconciliation/views.py`` 的 commit 改成 flush 后 `test_reconciliation.py` 6 个用例转红）。

本文件锁定 #1640 之后的契约（与 #1632 的 ``get_db()`` 规则一致）：

- 请求上下文内顺序 / 嵌套的 ``user_session()`` / ``market_session()`` 复用同一 Session，
  提交发生在请求结束（teardown）；异常时整体回滚；
- 三个槽位（应用会话 / user / market）彼此独立，互不提交、互不回滚；
- 非请求上下文（job / CLI）仍是每次独立会话、不自动提交。

反向验证：把 ``user_session()`` 改回「每次新建 + 只 close」，本文件用例必须转红。
"""

import pytest

from app.core.database import get_db, market_session, user_session
from app.domains.ledgers.models import Ledger


def _new_ledger(name: str) -> Ledger:
    return Ledger(name=name, ledger_type='bank', family_id=1)


def test_user_session_write_persists_without_explicit_commit(app, db):
    """#1640 核心：请求内经 ``user_session()`` 写入且**不显式 commit**，请求结束也必须落库。

    这条是防「静默丢数据」回潮的**对照用例**：一旦请求边界不再收尾 user 域会话
    （例如把 ``user_session()`` 改回只 ``close()``），断言即转红。
    """
    with app.test_request_context('/api/'):
        with user_session() as session:
            session.add(_new_ledger('user域无显式提交'))
            session.flush()
    assert db.query(Ledger).filter_by(name='user域无显式提交').count() == 1


def test_user_session_rolls_back_on_exception(app, db):
    """请求内 user 域多步写中途异常 → 整体回滚（中途 flush 的写入不得残留）。"""
    with pytest.raises(RuntimeError):
        with app.test_request_context('/api/'):
            with user_session() as session:
                session.add(_new_ledger('user域半截写入'))
                session.flush()
                raise RuntimeError('boom')
    assert db.query(Ledger).filter_by(name='user域半截写入').count() == 0


def test_nested_user_session_reuses_same_request_session(app):
    """请求内嵌套 ``user_session()`` 必须复用同一 Session。"""
    with app.test_request_context('/api/'):
        with user_session() as outer:
            with user_session() as inner:
                assert outer is inner


def test_sequential_user_session_reuses_same_request_session(app):
    """同一请求内**先后**两个 ``with user_session()`` 块也必须复用同一 Session。

    回归 #1640：若在块退出时提交 / 关闭，第二个块会拿到新 Session，且首块对象
    detach + expire → 视图后续访问报 ``DetachedInstanceError``。
    """
    with app.test_request_context('/api/'):
        with user_session() as first:
            pass
        with user_session() as second:
            assert first is second


def test_user_session_outside_request_keeps_independent_sessions(app):
    """非请求上下文（job / CLI / scheduler）：每次仍是独立会话，且不自动提交。"""
    with user_session() as a, user_session() as b:
        assert a is not b


def test_market_session_reuses_same_request_session(app):
    """market 域会话同样纳入请求级单会话（#1640）。"""
    with app.test_request_context('/api/'):
        with market_session() as outer:
            with market_session() as inner:
                assert outer is inner


def test_session_slots_are_independent(app):
    """同一请求内三个槽位彼此独立，且各自跨块复用（不会被对方的块退出提前提交 / 关闭）。"""
    with app.test_request_context('/api/'):
        with get_db() as app_db, user_session() as user_db, market_session() as market_db:
            assert len({id(app_db), id(user_db), id(market_db)}) == 3

        # 三个块都退出后再次进入：仍复用各自那一个 Session
        with get_db() as app_db2, user_session() as user_db2, market_session() as market_db2:
            assert (app_db2 is app_db, user_db2 is user_db, market_db2 is market_db) == (True, True, True)
