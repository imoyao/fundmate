# -*- coding: utf-8 -*-
"""持仓抽屉的流水分录：孤儿流水必须并进来。

## 为什么单独立文件

「持仓份额没被扣」与「抽屉里只有买入」是同一个 bug 的两张脸：卖出在导入时找不到持仓
（导出文件时间倒序）会被落成孤儿流水（``position_id IS NULL``），份额不扣；而抽屉旧实现
是「``position_id`` 有任意命中就只返回这一批」，孤儿行因此**一笔都看不见**。

落库侧的顺序修正见 ``tests/services/importer/test_orchestrator.py``（``sort_records_for_replay``）；
本文件只钉**读侧**：孤儿要能被看见，但**不能**把别的标的、别的账户的孤儿也卷进来。
"""

from app.services.position_txn_read import list_position_transactions


def test_position_transactions_include_orphan_sell(make_position, make_transaction, db):
    """孤儿卖出（position_id=NULL）必须出现在持仓抽屉里。"""
    pos = make_position(
        symbol='SH113053',
        name='隆22转债',
        asset_type='bond',
        account_name='测试账户',
        quantity=100,
        avg_price=100,
    )
    buy = make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        symbol='SH113053',
        asset_type='bond',
    )
    orphan_sell = make_transaction(
        position_id=None,
        ledger_id=pos.ledger_id,
        txn_type='sell',
        symbol='SH113053',
        asset_type='bond',
        entry_status='orphan',
        position_name='隆22转债',
    )

    rows = list_position_transactions(db, pos)

    assert {r.id for r in rows} == {buy.id, orphan_sell.id}
    assert {r.txn_type for r in rows} == {'buy', 'sell'}


def test_position_transactions_exclude_other_symbol_orphans(make_position, make_transaction, db):
    """反证：别的标的的孤儿不能被卷进来（那会把「漏算」换成「多算」）。"""
    pos = make_position(
        symbol='SH113053',
        name='隆22转债',
        asset_type='bond',
        account_name='测试账户',
        quantity=100,
        avg_price=100,
    )
    make_transaction(position_id=pos.id, ledger_id=pos.ledger_id, symbol='SH113053', asset_type='bond')
    make_transaction(
        position_id=None,
        ledger_id=pos.ledger_id,
        txn_type='sell',
        symbol='SZ128022',
        asset_type='bond',
        entry_status='orphan',
    )

    rows = list_position_transactions(db, pos)

    assert [r.symbol for r in rows] == ['SH113053']


def test_position_transactions_exclude_other_ledger_orphans(make_position, make_transaction, db):
    """反证：同一标的在别的账户的孤儿不并进来（身份键含 ledger_id，见 #2372）。"""
    pos = make_position(
        symbol='SH113053',
        name='隆22转债',
        asset_type='bond',
        account_name='测试账户',
        quantity=100,
        avg_price=100,
    )
    make_transaction(position_id=pos.id, ledger_id=pos.ledger_id, symbol='SH113053', asset_type='bond')
    make_transaction(
        position_id=None,
        ledger_id=pos.ledger_id + 1000,
        txn_type='sell',
        symbol='SH113053',
        asset_type='bond',
        entry_status='orphan',
    )

    rows = list_position_transactions(db, pos)

    assert [r.txn_type for r in rows] == ['buy']


def test_position_transactions_without_own_rows_keeps_identity_fallback(make_position, make_transaction, db):
    """仍保留 #2372 的旧兜底：持仓自身一条 position_id 都没有时，按身份键全量取。"""
    pos = make_position(
        symbol='SH113053',
        name='隆22转债',
        asset_type='bond',
        account_name='测试账户',
        quantity=100,
        avg_price=100,
    )
    orphan_sell = make_transaction(
        position_id=None,
        ledger_id=pos.ledger_id,
        txn_type='sell',
        symbol='SH113053',
        asset_type='bond',
        entry_status='orphan',
    )

    rows = list_position_transactions(db, pos)

    assert [r.id for r in rows] == [orphan_sell.id]
