# -*- coding: utf-8 -*-
"""流水写入汇点的账本引用校验回归（#2875 之后的补漏）。

#2875 撤销了「``ledger_id`` 为空即报错」的硬拦——手工建仓 / 探市不带账本是
合法形态。但校验全下放给导入路径后，预览行回传的 id、红利税继承的历史 id
都只判「非空」，不判账本是否还存在、是否属于本家庭；SQLite 在
``PRAGMA foreign_keys=OFF`` 下 FK 形同虚设，于是留下悬空引用。

本文件钉住：NULL 合法、非空必须有效、跨 family 拒绝、继承来的 id 同样要验。
"""

from datetime import date

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.transactions.ledger_guard import (
    dividend_tax_source_fields,
    validate_ledger_ref,
)
from app.domains.transactions.models import Transaction
from app.services.trading import TransactionService


def _ledger(db, name, family_id=1):
    ledger = Ledger(name=name, ledger_type='fund', family_id=family_id)
    db.add(ledger)
    db.commit()
    return ledger


def _create(db, **kw):
    return TransactionService.create(
        db=db,
        txn_type='buy',
        symbol='510300',
        position_name='测试',
        account_name='',
        quantity=0,
        price=0,
        amount=Money.yuan_to_cents(1),
        status='success',
        family_id=1,
        **kw,
    )


def test_null_ledger_is_still_legal(db):
    """#2875 定案：手工建仓 / 探市不带账本是合法形态，不能被拦。"""
    txn = _create(db, ledger_id=None)
    db.commit()
    assert txn.ledger_id is None


def test_existing_ledger_passes(db):
    ledger = _ledger(db, '正常账户')
    txn = _create(db, ledger_id=ledger.id)
    db.commit()
    assert txn.ledger_id == ledger.id


def test_dangling_ledger_id_rejected(db):
    with pytest.raises(ValueError, match='不存在'):
        _create(db, ledger_id=999_999)


def test_cross_family_ledger_rejected(db):
    other = _ledger(db, '别家的账户', family_id=2)
    with pytest.raises(ValueError, match='不属于当前家庭'):
        _create(db, ledger_id=other.id)


def test_validate_ledger_ref_skips_null(db):
    assert validate_ledger_ref(db, None, 1) is None


def test_dividend_tax_inherited_dangling_ledger_rejected(db):
    """红利税继承最近一笔分红的 id：只判非空会把已删账本的 id 复制进新流水。"""
    db.add(
        Transaction(
            ledger_id=999_999,
            family_id=1,
            txn_type='dividend',
            symbol='510300',
            position_name='分红',
            account_name='',
            quantity=0,
            price=0,
            amount=Money.yuan_to_cents(10),
            status='success',
            trade_date=date.today(),
        )
    )
    db.commit()
    with pytest.raises(ValueError, match='不存在'):
        dividend_tax_source_fields(db, 1, '510300', None)
