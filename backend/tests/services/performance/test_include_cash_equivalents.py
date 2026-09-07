# -*- coding: utf-8 -*-
"""#1354：calculate_portfolio_xirr 的 include_cash_equivalents 口径切换（聚合层端到端）。

默认（剔除现金等价物）只统计主动投资交易；开关打开后货币基金/逆回购/现金
也并入分母，得到被货基低收益拖拽的「账户总收益」口径。
"""

from datetime import date

from app.services.performance.calculators import calculate_portfolio_xirr


def test_portfolio_xirr_excludes_cash_like_by_default(db, make_position, make_transaction):
    # 零持仓的占位 position 仅用于满足 Transaction 外键
    pos = make_position(
        symbol='DUMMY',
        name='占位',
        account_name='测试账户',
        asset_type='fund',
        quantity=0,
    )
    ledger_id = pos.ledger_id

    # 主动投资基金：买 1000 → 卖 1100（+10%）
    make_transaction(
        pos.id,
        ledger_id,
        txn_type='buy',
        asset_type='fund',
        amount=1000,
        confirm_date=date(2024, 1, 1),
        account_name='测试账户',
    )
    make_transaction(
        pos.id,
        ledger_id,
        txn_type='sell',
        asset_type='fund',
        amount=1100,
        confirm_date=date(2025, 1, 1),
        account_name='测试账户',
    )
    # 货币基金：买 1000 → 卖 1020（+2%）
    make_transaction(
        pos.id,
        ledger_id,
        txn_type='buy',
        asset_type='money_fund',
        amount=1000,
        confirm_date=date(2024, 1, 1),
        account_name='测试账户',
    )
    make_transaction(
        pos.id,
        ledger_id,
        txn_type='sell',
        asset_type='money_fund',
        amount=1020,
        confirm_date=date(2025, 1, 1),
        account_name='测试账户',
    )

    r_excl = calculate_portfolio_xirr(db, family_id=1, include_cash_equivalents=False)
    r_incl = calculate_portfolio_xirr(db, family_id=1, include_cash_equivalents=True)

    # 剔除口径：仅主动投资，2 笔现金流、年化≈10%
    assert r_excl['cashflow_count'] == 2
    assert abs(r_excl['xirr'] - 0.10) < 0.01

    # 含现金等价物口径：4 笔现金流、年化被货基拖拽至≈6%，低于剔除口径
    assert r_incl['cashflow_count'] == 4
    assert r_incl['xirr'] < r_excl['xirr']
