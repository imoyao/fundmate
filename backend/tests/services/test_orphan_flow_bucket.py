# -*- coding: utf-8 -*-
"""#2844 回归：孤儿现金等价物流水的「本金 / 收益」分桶。

现场：货基的现金分红（`txn_type='dividend'`、`position_id IS NULL`）落在
`orphan_*` 三个聚合函数的 `else: continue` 里，被整笔丢掉；而它的买入
（`buy`）照收进本金桶。于是总资产里**单边排除**：本金进了、收益没进，
「累计收益 = 期末资产 − 净投入」被系统性压低（真库实证：12 笔货基分红
81.74 元一分钱没进过任何桶，`income_map` 恒为空 `{}`）。

修法：把「逐笔怎么分桶」收成一个函数 `orphan_flow_delta`，三处消费方共用。
本文件钉住那个函数本身，以及汇总函数真的把它用上了。
"""

from app.core.money import Money
from app.services.summary_service import (
    ORPHAN_BUCKET_INCOME,
    ORPHAN_BUCKET_NET,
    orphan_flow_delta,
    orphan_money_fund_totals_by_ledger,
)

# ── 纯函数：逐笔分桶 ────────────────────────────────────────────────────


def test_cash_dividend_goes_to_income_bucket():
    """现金分红是「钱到账」，进收益桶（正），不进本金。"""
    assert orphan_flow_delta('dividend', 210, None) == (ORPHAN_BUCKET_INCOME, 210)
    assert orphan_flow_delta('dividend_cash', 210, None) == (ORPHAN_BUCKET_INCOME, 210)


def test_dividend_tax_subtracts_from_income_bucket():
    """代扣税从收益里扣，不进本金桶——否则「我一共投了多少」被税啃掉。"""
    assert orphan_flow_delta('dividend_tax', 42, None) == (ORPHAN_BUCKET_INCOME, -42)


def test_buy_and_sell_stay_in_principal_bucket():
    """买入 / 卖出是本金变动（方向由符号表达）。"""
    assert orphan_flow_delta('buy', 10000, None) == (ORPHAN_BUCKET_NET, 10000)
    assert orphan_flow_delta('sell', 4000, None) == (ORPHAN_BUCKET_NET, -4000)
    assert orphan_flow_delta('deposit', 500, None) == (ORPHAN_BUCKET_NET, 500)
    assert orphan_flow_delta('withdraw', 500, None) == (ORPHAN_BUCKET_NET, -500)


def test_is_income_flag_still_moves_principal_to_income_bucket():
    """#863 D1 的语义不变：渠道发放的收益行不能当本金再滚收益。"""
    assert orphan_flow_delta('buy', 300, True) == (ORPHAN_BUCKET_INCOME, 300)


def test_unrelated_types_do_not_enter_any_bucket():
    """split / 未知类型不动钱；返回 None 是为了让调用方 continue，而不是记 0 笔。"""
    assert orphan_flow_delta('split', 300, None) is None
    assert orphan_flow_delta(None, 300, None) is None


# ── 集成：汇总真的把它算进去了 ──────────────────────────────────────────


def test_totals_include_orphan_dividend(db, make_transaction):
    """一瓶一账：货基分红现在出现在收益桶里，本金桶不受影响。"""
    from app.domains.ledgers.models import Ledger

    ledger = Ledger(name='华泰证券', ledger_type='fund')
    db.add(ledger)
    db.commit()

    make_transaction(
        None,
        ledger.id,
        txn_type='buy',
        amount=100.00,
        asset_type='money_fund',
        symbol='',
        entry_status='orphan',
    )
    make_transaction(
        None,
        ledger.id,
        txn_type='dividend',
        amount=2.10,
        asset_type='money_fund',
        symbol='',
        entry_status='orphan',
    )
    db.commit()

    net_map, income_map = orphan_money_fund_totals_by_ledger(db, 1)

    # 分单位（`make_transaction` 按元入参、落库为分）
    assert net_map[ledger.id] == Money.yuan_to_cents(100.00)  # 本金桶只有买入
    assert income_map[ledger.id] == Money.yuan_to_cents(2.10)  # 收益桶不再恒空
