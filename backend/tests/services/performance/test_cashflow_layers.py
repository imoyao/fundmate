"""资金流水分层（#2615）回归：L1/L2/L3 分类、内部划转抵消、组合持仓口径。

本组用例钉的是**口径本身**，不是某个页面的数字：
- 入金/出金 与 买入/卖出 必须是两层（前者才是账户级外部现金流，后者只是账户内换形态）；
- 家庭内账户互转（同日同额反向）在账户资金流视图里净额为 0；
- **组合 XIRR 恒为持仓口径**（D20 二期）：买入 = 投入，卖出/分红 = 回收；
  入金/出金没有持仓归属，不进组合现金流。

口径变更史（读用例前先看这段）
    D67 / #2615 曾定「账户有真实入金 ⇒ 组合走账户口径（投入 = 入金）；无入金 ⇒ 降级持仓口径」，
    前提是「组合 = 账户集合」。D20 把组合成员改成持仓后该前提失效：同一账户下分属两个组合的
    持仓会各自认领整笔入金（本金翻倍）。故 2026-10-29 起组合口径统一为持仓口径，
    本文件中 `basis == 'account'` / `'mixed'` 的旧断言随需求变更改写，差异写在各自 docstring。
"""

import datetime as dt

from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.services.performance import cashflow_layers
from app.services.performance.xirr_engine import generate_portfolio_cashflows

ONE_YEAR_AGO = dt.date.today() - dt.timedelta(days=365)
TODAY = dt.date.today()
DAY = TODAY - dt.timedelta(days=10)


def _portfolio_with_ledger(db, name='分层组合', ledger_name='分层账户'):
    pf = Portfolio(name=name, family_id=1)
    db.add(pf)
    db.flush()
    ledger = Ledger(name=ledger_name, ledger_type='fund', family_id=1, portfolio_id=pf.id)
    db.add(ledger)
    db.flush()
    return pf, ledger


def test_layers_split_l1_l2_and_cash_residual(db, make_position, make_transaction):
    """入金 10 万 / 买入 8 万 / 卖出 9 万 / 出金 2 万：分层与现金残差。"""
    pf, ledger = _portfolio_with_ledger(db)
    pos = make_position(
        symbol='AAA', name='测试标的', ledger_id=ledger.id, asset_type='bond', quantity=0, current_price=1.0
    )
    for txn_type, amount in (
        ('deposit', 100000),
        ('buy', 80000),
        ('sell', 90000),
        ('withdraw', 20000),
    ):
        make_transaction(
            pos.id,
            ledger.id,
            txn_type=txn_type,
            asset_type='bond',
            amount=amount,
            confirm_date=DAY,
            symbol='AAA',
        )
    db.commit()

    layers = cashflow_layers.build_layers(db, [ledger.id])

    assert len(layers['l1']) == 2, '入金/出金必须落在 L1（外部资金流）'
    assert len(layers['l2']) == 2, '买入/卖出必须落在 L2（账户内换形态）'
    assert layers['l3'] == [], '本用例没有分红/税费'
    assert layers['unknown'] == [], '不该出现未分类交易'

    totals = layers['totals']
    # 单位是元（transactions.amount 存分，模块内已换算，消费方不再换算）
    assert totals['deposit'] == 100000.0
    assert totals['withdraw'] == 20000.0
    # 净投入 = 入金 − 出金。刻意不把已实现盈亏混进来：那是收益，不是投入。
    assert totals['net_invested'] == 80000.0
    # 现金残差 = 入金 − 出金 − 买入 + 卖出 = 10 - 2 - 8 + 9 = 9 万
    assert totals['cash_residual'] == 90000.0


def test_internal_transfer_pairs_are_net_zero_and_out_of_xirr(db, make_position, make_transaction):
    """家庭内账户互转：组合级净额为 0，两笔都不进 XIRR 现金流（修 `_ =` 空操作）。"""
    pf, la = _portfolio_with_ledger(db, name='划转组合', ledger_name='划转账户A')
    lb = Ledger(name='划转账户B', ledger_type='fund', family_id=1, portfolio_id=pf.id)
    db.add(lb)
    db.flush()

    pos_a = make_position(symbol='AAA', name='A', ledger_id=la.id, asset_type='bond', quantity=0, current_price=1.0)
    pos_b = make_position(symbol='BBB', name='B', ledger_id=lb.id, asset_type='bond', quantity=0, current_price=1.0)
    make_transaction(pos_a.id, la.id, txn_type='withdraw', amount=500, confirm_date=DAY, symbol='AAA')
    make_transaction(pos_b.id, lb.id, txn_type='deposit', amount=500, confirm_date=DAY, symbol='BBB')
    # 一笔真实买入留在现金流里，避免「全被剔掉」时误判为通过
    make_transaction(pos_a.id, la.id, txn_type='buy', asset_type='bond', amount=100, confirm_date=DAY, symbol='AAA')
    db.commit()

    layers = cashflow_layers.build_layers(db, [la.id, lb.id])
    assert len(layers['internal_transfer_indexes']) == 2, '同日同额反向的两笔必须被配对'
    assert layers['totals']['net_invested'] == 0.0, '组合级一进一出净额应为 0'

    cashflows = generate_portfolio_cashflows(db, pf.id, current_value=0.0)
    assert cashflows == [(DAY, -100.0)], '内部划转不应出现在组合现金流里'


def test_deposit_does_not_enter_position_portfolio_cashflow(db, make_position, make_transaction):
    """组合按持仓归因：账户入金（L1）不进组合现金流，买入才是本金。

    口径变更（D20 二期，2026-10-29）
        原用例名 `test_account_basis_uses_deposit_instead_of_buy`，断言「有入金 ⇒
        `basis='account'`，投入 = 入金 10 万，买入 8 万只是账户内换形态」。
        该口径的前提是「组合 = 账户集合」；组合成员改成持仓后，入金没有持仓归属，
        若仍按账户口径，同一账户下分属两个组合的持仓会各自认领整笔入金（本金翻倍）。
        故组合口径恒为持仓口径：`basis='position'`，买入才算投入。
    """
    pf, ledger = _portfolio_with_ledger(db, name='持仓口径组合', ledger_name='有入金的账户')
    pos = make_position(
        symbol='AAA', name='测试标的', ledger_id=ledger.id, asset_type='bond', quantity=1000, current_price=1.2
    )
    make_transaction(pos.id, ledger.id, txn_type='deposit', amount=100000, confirm_date=ONE_YEAR_AGO, symbol='AAA')
    make_transaction(
        pos.id, ledger.id, txn_type='buy', asset_type='bond', amount=80000, confirm_date=ONE_YEAR_AGO, symbol='AAA'
    )
    db.commit()

    sink: dict = {}
    cashflows = generate_portfolio_cashflows(db, pf.id, current_value=1200.0, basis_sink=sink)

    assert sink['basis'] == 'position', '组合口径只可能是持仓口径'
    assert sink['by_ledger'] == {}, '逐账户口径已不适用，不应再有 by_ledger 明细'
    assert cashflows == [(ONE_YEAR_AGO, -80000.0), (TODAY, 1200.0)], '入金不是组合本金，买入才是'


def test_basis_falls_back_to_position_without_deposit(db, make_position, make_transaction):
    """只导过交易的账户降级为持仓口径（否则会丢掉本金、年化变 0%）。"""
    pf, ledger = _portfolio_with_ledger(db, name='降级组合', ledger_name='只导过交易的账户')
    pos = make_position(
        symbol='AAA', name='测试标的', ledger_id=ledger.id, asset_type='bond', quantity=1000, current_price=1.2
    )
    make_transaction(
        pos.id, ledger.id, txn_type='buy', asset_type='bond', amount=1000, confirm_date=ONE_YEAR_AGO, symbol='AAA'
    )
    db.commit()

    sink: dict = {}
    cashflows = generate_portfolio_cashflows(db, pf.id, current_value=1200.0, basis_sink=sink)

    assert sink['basis'] == 'position'
    assert cashflows == [(ONE_YEAR_AGO, -1000.0), (TODAY, 1200.0)]


def test_multi_ledger_portfolio_uses_position_basis_uniformly(db, make_position, make_transaction):
    """多账户组合：每个账户的持仓统一按买入计本金，不再按账户分叉口径。

    口径变更（D20 二期，2026-10-29）
        原用例名 `test_mixed_basis_when_only_part_of_ledgers_have_deposit`，断言
        `basis='mixed'` + `by_ledger={A:'account', B:'position'}`（逐账户混算）。
        「组合 = 持仓集合」之后不再存在 account 分支，mixed 形态随之消失；
        本用例保留原意图——两种账户混在同一组合时**不得**出现两套算法——改为断言统一持仓口径。
    """
    pf, la = _portfolio_with_ledger(db, name='多账户组合', ledger_name='有入金的账户')
    lb = Ledger(name='只导交易的账户', ledger_type='fund', family_id=1, portfolio_id=pf.id)
    db.add(lb)
    db.flush()

    pos_a = make_position(symbol='AAA', name='A', ledger_id=la.id, asset_type='bond', quantity=1000, current_price=1.0)
    pos_b = make_position(symbol='BBB', name='B', ledger_id=lb.id, asset_type='bond', quantity=1000, current_price=1.0)
    make_transaction(pos_a.id, la.id, txn_type='deposit', amount=5000, confirm_date=ONE_YEAR_AGO, symbol='AAA')
    make_transaction(
        pos_a.id, la.id, txn_type='buy', asset_type='bond', amount=4000, confirm_date=ONE_YEAR_AGO, symbol='AAA'
    )
    make_transaction(
        pos_b.id, lb.id, txn_type='buy', asset_type='bond', amount=2000, confirm_date=ONE_YEAR_AGO, symbol='BBB'
    )
    db.commit()

    sink: dict = {}
    cashflows = generate_portfolio_cashflows(db, pf.id, current_value=2000.0, basis_sink=sink)

    assert sink['basis'] == 'position', '不再有 mixed / account 分支'
    assert sink['by_ledger'] == {}
    # 两笔买入都算投入（-4000 / -2000），入金 5000 不进来金；期末虚拟卖出 2000
    assert cashflows[-1] == (TODAY, 2000.0)
    assert sorted(cashflows[:-1]) == [(ONE_YEAR_AGO, -4000.0), (ONE_YEAR_AGO, -2000.0)]
