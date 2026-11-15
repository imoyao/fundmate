# -*- coding: utf-8 -*-
"""交易编辑的审计留痕（`transaction_edit` 动作）。

## 背景（2026-11-15 实测）

排查「补录日志记 115 份 @30 元、落库行是 30 份 @115 元」时，唯一线索是
`transactions.updated_at` 比 `created_at` 晚 3 分钟——**改的人、改前改后都查不到**。
补录/回补/重建/删除都写 `adjustment_logs`，唯独最常走的「编辑交易」不写。

本文件锁住三件事：
1. 改了哪几个字段，日志里就只有哪几个（不塞整行，避免「改了什么」被噪声淹没）；
2. 值没变化时不写日志（重复提交同一份表单不该留痕）；
3. `import_hash` 被清空是编辑的**后果**，不进日志字段（记录它会误导排查）。
"""

import json
from datetime import date

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.reconciliation.models import AdjustmentLog
from app.domains.transactions.models import Transaction
from app.services.ledger_write_service import update_ledger_transaction


@pytest.fixture
def ledger(db):
    lg = Ledger(name='同花顺（银河证券）', ledger_type='stock', family_id=1)
    db.add(lg)
    db.flush()
    return lg


def _txn(db, ledger, **overrides):
    txn = Transaction(
        family_id=1,
        ledger_id=ledger.id,
        symbol='SH600027',
        txn_type='buy',
        confirm_date=date(2026, 1, 5),
        quantity=Money.shares_to_min_unit(1000),
        price=Money.yuan_to_price_units(5.49),
        amount=Money.yuan_to_cents(5490),
        position_name='华电国际',
        account_name=ledger.name,
        asset_type='stock',
        status='success',
    )
    for key, value in overrides.items():
        setattr(txn, key, value)
    db.add(txn)
    db.flush()
    return txn


def _log(db) -> AdjustmentLog:
    logs = db.query(AdjustmentLog).filter(AdjustmentLog.action == 'transaction_edit').all()
    assert len(logs) == 1, f'应当只写一条审计，实际 {len(logs)} 条'
    return logs[0]


def test_edit_quantity_records_only_that_field(db, ledger):
    txn = _txn(db, ledger)

    update_ledger_transaction(db, ledger, txn, {'quantity': 1200})

    log = _log(db)
    before = json.loads(log.before_json)
    after = json.loads(log.after_json)
    assert before['transaction_id'] == txn.id
    assert before['fields']['quantity'] == Money.shares_to_min_unit(1000)
    # 改数量会按「价格×数量」重算金额，故 amount 也是**真的变了**，必须一并留痕；
    # 但除这两个字段外不许出现别的（否则「改了什么」被噪声淹没）。
    assert set(after['changed']) == {'quantity', 'amount'}
    assert after['fields']['quantity'] == Money.shares_to_min_unit(1200)


def test_edit_multiple_fields_lists_each_change(db, ledger):
    txn = _txn(db, ledger)

    update_ledger_transaction(db, ledger, txn, {'price': 6.1, 'notes': '按对账单更正'})

    after = json.loads(_log(db).after_json)
    assert set(after['changed']) == {'price', 'amount', 'notes'}
    assert after['fields']['notes'] == '按对账单更正'


def test_no_change_writes_no_audit(db, ledger):
    """重复提交同一份表单（值没变）不该留痕——否则日志会被空转动作淹没。"""
    txn = _txn(db, ledger)

    update_ledger_transaction(db, ledger, txn, {'quantity': 1000, 'price': 5.49})

    assert db.query(AdjustmentLog).count() == 0


def test_import_hash_clearing_is_not_audited_as_user_field(db, ledger):
    """`import_hash` 被清空是编辑的后果，不是用户输入：记进日志只会误导排查。"""
    txn = _txn(db, ledger, import_hash='deadbeef')

    update_ledger_transaction(db, ledger, txn, {'notes': '手工更正'})

    after = json.loads(_log(db).after_json)
    assert 'import_hash' not in after['fields']
    assert txn.import_hash is None
