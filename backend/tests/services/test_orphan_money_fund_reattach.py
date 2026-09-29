# -*- coding: utf-8 -*-
"""#1657 回归测试：货基持仓与孤儿流水互斥（#863 口径 A）。

覆盖：
- upsert_from_holding（导入快照路径）建货基持仓时，同 (ledger,symbol) 孤儿货基流水被挂回；
- 即便快照 is_money_fund 判定不一致（为 False，本机 pos[445]/pos[26] 同类问题），
  仍应挂回孤儿流水，避免资金双计（#1657 堵源核心）；
- process_buy_or_deposit（写路径, force_create_position=True 手动建仓）建货基持仓时同样挂回；
- 挂回后同 (ledger,symbol) 不再存在「既有持仓、又有 position_id IS NULL 货基流水」的双计态。

注意：_reattach_orphan_flows 只改内存、由调用方提交；测试内断言前需 db.flush() 再重新查询，
否则 db.refresh 会从库里读回未 flush 的旧值。
"""

from datetime import date

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.transactions.models import Transaction
from app.services.position_service import PositionService


@pytest.fixture
def fund_ledger(db):
    ledger = Ledger(name='基金E账户', ledger_type='e_account', family_id=1)
    db.add(ledger)
    db.flush()
    return ledger


def _orphan_money_fund_txn(db, ledger, symbol='001821', amount_yuan=3973.61):
    """造一条孤儿货基流水（position_id IS NULL，非收益），模拟 #1657 的双计源。"""
    txn = Transaction(
        position_id=None,
        ledger_id=ledger.id,
        family_id=1,
        txn_type='buy',
        symbol=symbol,
        asset_type='money_fund',
        amount=Money.yuan_to_cents(amount_yuan),
        price=Money.yuan_to_price_units(1.0),
        quantity=Money.shares_to_min_unit(amount_yuan),
        status='success',
        is_income=False,
    )
    db.add(txn)
    db.flush()
    return txn


def _holding_data(ledger, symbol='001821', **overrides):
    data = {
        'symbol': symbol,
        'name': '示例货币B',
        'asset_type': 'money_fund',
        'ledger_id': ledger.id,
        'account_name': '基金E账户',
        'quantity': 3973.61,
        'avg_price': 1.0,
        'current_price': 1.0,
        'snapshot_date': date(2026, 8, 14),
        'currency': 'CNY',
        'source': 'e_account_holding',
        'family_id': 1,
    }
    data.update(overrides)
    return data


def test_upsert_reattaches_orphan_money_fund_flow(db, fund_ledger):
    """导入快照建货基持仓 → 同 (ledger,symbol) 孤儿货基流水被挂回。"""
    txn = _orphan_money_fund_txn(db, fund_ledger)
    assert txn.position_id is None

    pos = PositionService.upsert_from_holding(db, _holding_data(fund_ledger))
    db.flush()

    reattached = db.query(Transaction).filter_by(id=txn.id).first()
    assert reattached.position_id == pos.id  # 已挂回，不再孤儿
    # 不再双计：无 position_id IS NULL 的同 symbol 货基流水
    leftover = (
        db.query(Transaction)
        .filter(
            Transaction.position_id.is_(None),
            Transaction.asset_type == 'money_fund',
            Transaction.symbol == '001821',
            Transaction.ledger_id == fund_ledger.id,
        )
        .count()
    )
    assert leftover == 0


def test_upsert_reattaches_even_when_is_money_fund_flag_false(db, fund_ledger):
    """#1657 堵源：快照 is_money_fund 判定为 False 时（本机 pos[445]/pos[26] 同类），
    仍应挂回孤儿货基流水，不能因判定不一致而漏挂回导致双计。"""
    txn = _orphan_money_fund_txn(db, fund_ledger)
    pos = PositionService.upsert_from_holding(db, _holding_data(fund_ledger, is_money_fund=False))
    assert pos.is_money_fund is False  # 模拟快照判定不一致

    db.flush()
    reattached = db.query(Transaction).filter_by(id=txn.id).first()
    assert reattached.position_id == pos.id  # 仍被挂回


def test_process_buy_reattaches_orphan_money_fund_flow(db, fund_ledger):
    """写路径手动建仓（process_buy_or_deposit, force_create_position=True）→ 孤儿货基流水被挂回。"""
    txn = _orphan_money_fund_txn(db, fund_ledger)

    pos = PositionService.process_buy_or_deposit(
        db,
        {
            'symbol': '001821',
            'asset_type': 'money_fund',
            'ledger_id': fund_ledger.id,
            'quantity': 3973.61,
            'avg_price': 1.0,
            'current_price': 1.0,
            'txn_type': 'buy',
            'family_id': 1,
        },
        force_create_position=True,
    )
    db.flush()

    reattached = db.query(Transaction).filter_by(id=txn.id).first()
    assert reattached.position_id == pos.id


def test_no_double_count_after_reattach(db, fund_ledger):
    """综合断言：挂回后同 (ledger,symbol) 既无孤儿货基流水、也无双计态。"""
    _orphan_money_fund_txn(db, fund_ledger, symbol='001821', amount_yuan=3973.61)
    _orphan_money_fund_txn(db, fund_ledger, symbol='001937', amount_yuan=10.88)
    PositionService.upsert_from_holding(db, _holding_data(fund_ledger, symbol='001821'))
    PositionService.upsert_from_holding(db, _holding_data(fund_ledger, symbol='001937'))
    db.flush()

    double_count = (
        db.query(Transaction)
        .filter(
            Transaction.position_id.is_(None),
            Transaction.asset_type == 'money_fund',
            Transaction.ledger_id == fund_ledger.id,
        )
        .count()
    )
    assert double_count == 0


def test_upsert_reattaches_across_symbol_forms(db, fund_ledger):
    """#1657 复审：孤儿流水带交易所前缀（`SZ001937`）、持仓是裸码（`001937`）时也必须挂回。

    一次性修复脚本最初用 `symbol` **精确相等**匹配，这类跨形态组合被静默漏挂；本机 3 个
    成功案例恰好都是裸码对裸码，把缺陷掩盖了。运行时（归一化匹配）本就正确，此处钉死防漂移。
    """
    txn = _orphan_money_fund_txn(db, fund_ledger, symbol='SZ001937', amount_yuan=10.88)

    pos = PositionService.upsert_from_holding(db, _holding_data(fund_ledger, symbol='001937'))
    db.flush()

    assert db.query(Transaction).filter_by(id=txn.id).first().position_id == pos.id


def test_find_orphan_cash_flows_fallback_for_unparsable_symbol(db, fund_ledger):
    """非标准代码（归一化不出 6 位数字）退回**精确相等**匹配。

    原实现在此时把候选集退化为 `{''}`，于是 `MF001` 与 `ABCDEF` 会互相命中；既有用例
    `test_summary_money_fund.py::TestOrphanFlowReattach` 用 `MF001` 造数，正是靠这条退化行为
    「碰巧通过」。但直接把它短路成空又会破坏该用例，故正解是退回精确相等。
    """
    from app.services.position_service import find_orphan_cash_flows

    nonstandard = _orphan_money_fund_txn(db, fund_ledger, symbol='MF001')
    other = _orphan_money_fund_txn(db, fund_ledger, symbol='ABCDEF')

    matched = [t.id for t in find_orphan_cash_flows(db, fund_ledger.id, 'MF001', 1)]
    assert matched == [nonstandard.id]
    assert other.id not in matched
    assert find_orphan_cash_flows(db, fund_ledger.id, '', 1) == []
