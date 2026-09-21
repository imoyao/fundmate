# -*- coding: utf-8 -*-
"""#1609 事务边界回归：请求级 unit-of-work（成功提交 / 异常回滚）与 BaseRepository 只 flush。

范式（conventions §2.13 方案 A，决策 D30）：事务由视图 / 用例层持有——
``with_db`` 是请求级 unit-of-work：正常返回 commit、抛异常 rollback 后原样抛出；
服务层与 ``BaseRepository`` 只 ``flush()`` 不 ``commit()``。

反向验证：若把 ``with_db`` 的 commit 去掉、或给 ``BaseRepository`` 加回内建 commit，
下面用例必须转红。
"""

import pytest

from app.core.database import BaseRepository
from app.core.utils import with_db
from app.domains.ledgers.models import Ledger


def test_with_db_commits_on_success(app, db):
    """handler 未显式 commit，成功返回后写入必须**持久**（边界代提交）。"""

    @with_db
    def handler(session):
        session.add(Ledger(name='边界账户', ledger_type='bank', family_id=1))
        return 'ok'

    assert handler() == 'ok'
    assert db.query(Ledger).filter_by(name='边界账户').count() == 1


def test_with_db_rolls_back_on_exception(app, db):
    """handler 抛异常 → 整体回滚：中途 flush 的写入不得残留。"""

    @with_db
    def handler(session):
        session.add(Ledger(name='半截账户', ledger_type='bank', family_id=1))
        session.flush()  # 模拟多步写：先落一半
        raise RuntimeError('boom')

    with pytest.raises(RuntimeError):
        handler()
    assert db.query(Ledger).filter_by(name='半截账户').count() == 0


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
