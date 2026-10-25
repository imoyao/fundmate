# -*- coding: utf-8 -*-
"""组合级收益口径回归：金额单位 + 净投入 / 累计收益 + method 透传。

## 修的 bug（线上表现）

组合详情「组合收益」卡显示：当前市值 ¥400,860、总投入 ¥168,579,480、
总收益 -¥18,864,539.86，年化 0.00%，标题还写着「组合收益（[object Object]）」。

两个独立成因：

1. **单位错**：`transactions.amount` 存的是**分**，`generate_portfolio_cashflows`
   直接 `float(amount)` 当元用；而虚拟卖出（当前市值）是元。同一张现金流表里
   混了两种单位 ⇒ 现金流比市值大 100 倍，`total_return` 变成 -1886 万、XIRR 求解
   退化到 0（`generate_cashflows` 走的持仓/产品级一直是对的，故只有组合级中招）。
2. **展示口径**：`total_invested` 是**累计买入毛额**（每笔买入都累加，再投入重复计），
   拿它当「总投入本金」展示会越交易越大；用户会读成「我投了 1.68 亿」。
   故新增 `net_invested = 累计买入 − 累计卖出/分红`，`total_return = 当前市值 − 净投入`。

## 覆盖

- `generate_portfolio_cashflows` 输出必须是**元**（-1000.0 而不是 -100000.0）；
- `net_invested` / `total_return` 的算术关系（赚的钱要算进来，不能只算亏的）；
- `method=dietz` 在组合级必须真的走 Dietz（此前 `calculate_portfolio_xirr_by_id`
  漏传 method，切「区间」仍回 xirr 字段 → 页面恒 0.00%）。
"""

import datetime as dt
from datetime import date, timedelta

import pytest

from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.services.performance.calculators import calculate_portfolio_xirr_by_id
from app.services.performance.xirr_engine import generate_portfolio_cashflows

# 「持有一整年」：相对今天倒推，避免写死年份让 XIRR 期望随真实日期漂移
ONE_YEAR_AGO = date.today() - timedelta(days=365)


def _seed(db, make_position, make_transaction, *, sell_amount: float | None = None):
    """一个组合 + 一个成员账户 + 一条持仓；买入 1000 元，可选卖出一笔。

    市值口径用 `asset_type='bond'`（走 `current_price`，不依赖 NAV / 行情表），
    与 `test_position_xirr.py` 同一约定。期末市值 = 1000 份 × 1.2 = 1200 元。
    """
    pf = Portfolio(name='口径回归组合', family_id=1)
    db.add(pf)
    db.flush()
    ledger = Ledger(name='口径回归账户', ledger_type='fund', family_id=1, portfolio_id=pf.id)
    db.add(ledger)
    db.flush()

    pos = make_position(
        symbol='AAA',
        name='测试标的',
        ledger_id=ledger.id,
        asset_type='bond',
        quantity=1000,
        current_price=1.2,
    )
    make_transaction(
        pos.id,
        ledger.id,
        txn_type='buy',
        asset_type='bond',
        amount=1000,
        confirm_date=ONE_YEAR_AGO,
        account_name='口径回归账户',
        symbol='AAA',
    )
    if sell_amount is not None:
        make_transaction(
            pos.id,
            ledger.id,
            txn_type='sell',
            asset_type='bond',
            amount=sell_amount,
            confirm_date=date.today(),
            account_name='口径回归账户',
            symbol='AAA',
        )
    db.commit()
    return pf, ledger, pos


def test_portfolio_cashflows_are_in_yuan(db, make_position, make_transaction):
    """现金流必须是元：`amount` 存的是分，漏换算会大 100 倍（本轮线上 bug 的根因）。"""
    pf, _ledger, _pos = _seed(db, make_position, make_transaction)

    cashflows = generate_portfolio_cashflows(db, pf.id, current_value=1200.0)

    assert cashflows[0] == (ONE_YEAR_AGO, -1000.0), f'买入金额单位错了：{cashflows[0]}'
    assert cashflows[-1] == (date.today(), 1200.0)


def test_net_invested_and_total_return(db, make_position, make_transaction):
    """净投入 = 累计买入 − 累计卖出；累计收益 = 当前市值 − 净投入（赚亏都算）。"""
    pf, _ledger, _pos = _seed(db, make_position, make_transaction, sell_amount=200)

    r = calculate_portfolio_xirr_by_id(db, pf.id, family_id=1)

    assert r['total_invested'] == 1000.0  # 毛额仍是累计买入
    assert r['total_withdrawn'] == 200.0
    assert r['net_invested'] == 800.0
    assert r['current_value'] == 1200.0
    # 1200 + 200 - 1000 = 400：盈利必须体现为正数，而不是仅统计亏损
    assert r['total_return'] == 400.0
    assert r['cashflow_count'] == 3


def test_profit_is_not_reported_as_loss(db, make_position, make_transaction):
    """复现原 bug 的算术形态：现金流漏换算时 total_return 会是 -118000 而不是 +400。"""
    pf, _ledger, _pos = _seed(db, make_position, make_transaction, sell_amount=200)

    r = calculate_portfolio_xirr_by_id(db, pf.id, family_id=1)

    assert r['total_return'] > 0, '盈利账户被算成了亏损（单位换算回归）'
    # 现金流：t0 -1000，t1（今天）+200 卖出 +1200 虚拟卖出 = +1400 ⇒ 一年 40%
    assert abs(r['xirr'] - 0.4) < 0.01, f'年化应约为 40%，实际 {r["xirr"]}'


@pytest.mark.parametrize('method', ['xirr', 'dietz'])
def test_portfolio_method_is_passed_through(db, make_position, make_transaction, method):
    """组合级必须真的按 method 分派：漏传会让「区间」标签下回 xirr 字段（页面恒 0.00%）。"""
    pf, _ledger, _pos = _seed(db, make_position, make_transaction, sell_amount=200)

    r = calculate_portfolio_xirr_by_id(db, pf.id, family_id=1, method=method)

    assert r['method'] == method
    if method == 'dietz':
        assert 'dietz' in r and 'xirr' not in r
    else:
        assert 'xirr' in r and 'dietz' not in r


def test_internal_transfer_amounts_still_pair(db, make_position, make_transaction):
    """内部划转配对按「分」比较：换算成元后仍必须能配对并剔除。"""
    pf = Portfolio(name='划转组合', family_id=1)
    db.add(pf)
    db.flush()
    la = Ledger(name='划转账户A', ledger_type='fund', family_id=1, portfolio_id=pf.id)
    lb = Ledger(name='划转账户B', ledger_type='fund', family_id=1, portfolio_id=pf.id)
    db.add_all([la, lb])
    db.flush()

    day = dt.date.today() - dt.timedelta(days=10)
    pos_a = make_position(symbol='AAA', name='A', ledger_id=la.id, asset_type='bond', quantity=0, current_price=1.0)
    pos_b = make_position(symbol='BBB', name='B', ledger_id=lb.id, asset_type='bond', quantity=0, current_price=1.0)
    make_transaction(pos_a.id, la.id, txn_type='withdraw', amount=500, confirm_date=day, symbol='AAA')
    make_transaction(pos_b.id, lb.id, txn_type='deposit', amount=500, confirm_date=day, symbol='BBB')
    # 一笔真实买入留在现金流里，避免「全被剔掉」时误判为通过
    make_transaction(pos_a.id, la.id, txn_type='buy', asset_type='bond', amount=100, confirm_date=day, symbol='AAA')
    db.commit()

    cashflows = generate_portfolio_cashflows(db, pf.id, current_value=0.0)

    assert cashflows == [(day, -100.0)], '内部划转未被剔除，或金额单位错'
