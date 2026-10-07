# -*- coding: utf-8 -*-
"""卖出/取出关联持仓的兜底与盈亏写入（#1920）。

背景：真实库 2051 笔导入流水中 1348 笔 `symbol` 为空（券商交割单常见「有名称、无代码」），
而 `process_orphan_sell_or_withdraw` 此前只按 `symbol` 匹配持仓 ⇒ 必然查不到
⇒ 卖出退化成孤儿流水 ⇒ `realized_pnl` 无从计算而**静默写 0**（649 笔卖出如此）。

本组用例锁定两件事：
1. `symbol` 缺失时能按**名称 + 账户**兜底关联到持仓，从而走上写 `realized_pnl` 的路径；
2. 关联成功时 `realized_pnl` 真的被写入（对齐 `compute_sell_realized_cents` 公式）。
"""

import datetime as dt

import pytest

from app.core.money import Money
from app.domains.transactions.models import Transaction
from app.services.position_service import PositionService


def _make(db, make_position, name='兴业成长动力混合C', account='天天基金', qty=1000, avg=1.0):
    return make_position(
        symbol='020106', name=name, account_name=account, quantity=qty, avg_price=avg, asset_type='fund'
    )


def test_卖出时symbol缺失应按名称兜底关联并写入realized(db, make_position):
    """核心回归：无 symbol 的卖出也要能关联到持仓并算出已实现盈亏。"""
    pos = _make(db, make_position, qty=1000, avg=2.0)  # 成本均价 2.0

    PositionService.process_orphan_sell_or_withdraw(
        db,
        {
            'symbol': '',  # ← 券商交割单没给代码
            'name': '兴业成长动力混合C',  # 只给了名称
            'account_name': '天天基金',
            'quantity': 1000,
            'avg_price': 3.0,  # 卖价 3.0 ⇒ 每股赚 1.0 ⇒ 共赚 1000 元
            'trade_date': dt.datetime(2026, 1, 13),
            'confirm_date': dt.date(2026, 1, 13),
            'family_id': 1,
        },
    )

    txn = db.query(Transaction).filter(Transaction.txn_type == 'sell').order_by(Transaction.id.desc()).first()
    assert txn is not None, '应创建卖出流水'
    assert txn.position_id == pos.id, (
        f'应按名称兜底关联到 position_id={pos.id}，实际 {txn.position_id}（未关联 ⇒ realized 无从计算 ⇒ 静默丢 0）'
    )
    # (3.0 - 2.0) × 1000 = 1000 元
    assert txn.realized_pnl == Money.yuan_to_cents(1000), (
        f'realized 应为 100000 分（赚 1000 元），实际 {txn.realized_pnl}'
    )


def test_名称也匹配不到时仍退化为孤儿但不崩(db, make_position):
    """兜底不命中时保持原有降级行为（孤儿流水），不抛异常。"""
    make_position(symbol='020106', name='别的基金', account_name='天天基金', quantity=1000, avg_price=1.0)

    PositionService.process_orphan_sell_or_withdraw(
        db,
        {
            'symbol': '',
            'name': '查无此基金',
            'account_name': '天天基金',
            'quantity': 1000,
            'avg_price': 3.0,
            'trade_date': dt.datetime(2026, 1, 13),
            'family_id': 1,
        },
    )

    txn = db.query(Transaction).filter(Transaction.txn_type == 'sell').order_by(Transaction.id.desc()).first()
    assert txn is not None
    assert txn.position_id is None, '确实关联不上时才作为孤儿'


def test_有symbol时优先按symbol匹配而非名称(db, make_position):
    """symbol 可用时不应被名称兜底抢走匹配（避免串户）。"""
    pos = _make(db, make_position, name='同名不同户', account='天天基金', qty=1000, avg=2.0)
    # 另一个账户下有同名的持仓，symbol 不同
    make_position(symbol='999999', name='兴业成长动力混合C', account_name='天天基金', quantity=1000, avg_price=9.0)

    PositionService.process_orphan_sell_or_withdraw(
        db,
        {
            'symbol': '020106',
            'name': '兴业成长动力混合C',
            'account_name': '天天基金',
            'quantity': 1000,
            'avg_price': 3.0,
            'trade_date': dt.datetime(2026, 1, 13),
            'family_id': 1,
        },
    )

    txn = db.query(Transaction).filter(Transaction.txn_type == 'sell').order_by(Transaction.id.desc()).first()
    assert txn.position_id == pos.id, '有 symbol 时必须按 symbol 匹配'
    assert txn.realized_pnl == Money.yuan_to_cents(1000)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
