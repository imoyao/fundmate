# -*- coding: utf-8 -*-
"""#2135 区间收益归因测试。

锁定四件事：
1. **Σ ≡ 引擎月合计**——同窗 `build_daily_pnl_series` 的 `month_total` 与
   `compute_range_attribution` 的 `total_pnl` 逐位相等（构造保证，不是对账）；
2. **建仓日剔除**——期中建仓的水平值不算当日贡献（与 opening_pnl 门控同口径）；
3. **已实现进水平值**——区间内部分清仓的品种不丢失已实现贡献；
4. **诚实降级**——无价持仓进 unpriced_positions 不进合计、无持仓 total=None。
"""

import datetime as dt

import pytest

from app.core.money import Money
from app.domains.funds.models import DailyWorth
from app.services.pnl_calendar import build_daily_pnl_series, compute_range_attribution


def _add_nav(db, fund_code, date, unit_nav):
    db.add(DailyWorth(fund_code=fund_code, date=date, unit_nav=unit_nav))
    db.commit()


def _pnl_by_symbol(attr):
    return {r['symbol']: r['pnl'] for r in attr['positions']}


def test_双品种贡献_与引擎月合计自洽(db, make_position, make_transaction):
    """一涨一跌：各自贡献等于经济真相，且 Σ ≡ 引擎 month_total。"""
    d1, d2 = dt.date(2026, 1, 5), dt.date(2026, 1, 6)

    # A：净值 1.0→1.2，1000 份 ⇒ +200
    pos_a = make_position(symbol='000101', name='上涨基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos_a.id,
        ledger_id=pos_a.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000101',
    )
    _add_nav(db, '000101', d1, 1.0)
    _add_nav(db, '000101', d2, 1.2)
    # B：净值 1.0→0.9，2000 份 ⇒ −200
    pos_b = make_position(symbol='000102', name='下跌基金', quantity=2000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos_b.id,
        ledger_id=pos_b.ledger_id,
        txn_type='buy',
        quantity=2000,
        price=1.0,
        confirm_date=d1,
        symbol='000102',
    )
    _add_nav(db, '000102', d1, 1.0)
    _add_nav(db, '000102', d2, 0.9)

    attr = compute_range_attribution(db, family_id=1, start_date='2026-01-05', end_date='2026-01-06')
    engine = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-06')

    assert attr['has_any_computable'] is True
    # Σ ≡ 引擎月合计（核心自洽验收）
    assert attr['total_pnl'] == pytest.approx(engine['month_total'], abs=0.001)
    assert attr['total_pnl'] == pytest.approx(0.0, abs=0.001)
    assert _pnl_by_symbol(attr) == pytest.approx({'000101': 200.0, '000102': -200.0})
    # 合计为 0（没赚没赔）⇒ 占比无意义，None 而不是 0%
    assert all(r['pct'] is None for r in attr['positions'])
    # 同为 fund 大类 ⇒ 一个聚合桶
    assert len(attr['categories']) == 1
    assert attr['categories'][0]['asset_type'] == 'fund'
    assert attr['categories'][0]['positions_count'] == 2


def test_建仓日剔除_期中建仓不虚增贡献(db, make_position, make_transaction):
    """期中建仓：建仓日的水平值是「今天新出现的」，不是「今天赚的」。

    变异探针：删掉折叠里的 `- day_opening_level` 剔除 ⇒ B 在建仓日虚增
    +200，本用例两处断言（B 的贡献、Σ ≡ 引擎）同时转红。
    """
    d1, d2, d3 = dt.date(2026, 1, 5), dt.date(2026, 1, 6), dt.date(2026, 1, 7)

    # A 于 d1 建仓，净值恒 1.0 ⇒ 贡献 0
    pos_a = make_position(symbol='000103', name='平盘基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos_a.id,
        ledger_id=pos_a.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000103',
    )
    _add_nav(db, '000103', d1, 1.0)
    _add_nav(db, '000103', d2, 1.0)
    _add_nav(db, '000103', d3, 1.0)
    # B 于 d2 期中建仓：买价 1.0 而当日净值已 1.2（建仓瞬间浮盈 200，
    # 属「新出现的」而非「今天赚的」）；d3 净值 1.5 ⇒ 真实贡献 +300
    pos_b = make_position(symbol='000104', name='期中建仓基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos_b.id,
        ledger_id=pos_b.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d2,
        symbol='000104',
    )
    _add_nav(db, '000104', d2, 1.2)
    _add_nav(db, '000104', d3, 1.5)

    attr = compute_range_attribution(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')
    engine = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')

    assert attr['total_pnl'] == pytest.approx(engine['month_total'], abs=0.001)
    assert attr['total_pnl'] == pytest.approx(300.0, abs=0.001)
    assert _pnl_by_symbol(attr) == pytest.approx({'000103': 0.0, '000104': 300.0})


def test_已实现盈亏进品种贡献(db, make_position, make_transaction):
    """部分清仓 + 暴跌：已实现 250 留在水平值里，品种贡献=经济真相 +200。

    场景：1000 份 @1.0 建仓 → 净值 1.5（浮盈 +500）→ 半仓 @1.5 落袋
    （已实现 +250）→ 净值跌到 0.9（剩余浮亏 −50）⇒ 净贡献 +200。

    变异探针：折叠里不记 prev 基准（`diff = level − opening`）⇒ d3 把
    水平值 200 整个当增量，本用例转红。
    """
    d1, d2, d3 = dt.date(2026, 1, 5), dt.date(2026, 1, 6), dt.date(2026, 1, 7)

    pos = make_position(symbol='000105', name='清仓基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000105',
    )
    _add_nav(db, '000105', d1, 1.0)
    _add_nav(db, '000105', d2, 1.5)
    # d3 卖出一半 @1.5：已实现 (1.5−1.0)×500 = 250 元；夹具不换算 realized_pnl ⇒ 传分
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='sell',
        quantity=500,
        price=1.5,
        confirm_date=d3,
        symbol='000105',
        realized_pnl=Money.yuan_to_cents(250),
    )
    _add_nav(db, '000105', d3, 0.9)

    attr = compute_range_attribution(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')
    engine = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')

    assert attr['total_pnl'] == pytest.approx(engine['month_total'], abs=0.001)
    assert attr['total_pnl'] == pytest.approx(200.0, abs=0.001)
    assert _pnl_by_symbol(attr) == pytest.approx({'000105': 200.0})


def test_无价持仓诚实降级不进合计(db, make_position, make_transaction):
    """持有但整窗无价：进 unpriced_positions、不进 positions、不进合计。

    变异探针：把无价品种并进 positions（0.0 明细）⇒ 本用例品种集合断言转红。
    """
    d1, d2 = dt.date(2026, 1, 5), dt.date(2026, 1, 6)

    pos_a = make_position(symbol='000106', name='有价基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos_a.id,
        ledger_id=pos_a.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000106',
    )
    _add_nav(db, '000106', d1, 1.0)
    _add_nav(db, '000106', d2, 1.2)
    # B：整窗无任何净值 / 行情行
    pos_b = make_position(symbol='000107', name='无价基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos_b.id,
        ledger_id=pos_b.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000107',
    )

    attr = compute_range_attribution(db, family_id=1, start_date='2026-01-05', end_date='2026-01-06')
    engine = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-06')

    assert attr['total_pnl'] == pytest.approx(engine['month_total'], abs=0.001)
    assert attr['total_pnl'] == pytest.approx(200.0, abs=0.001)
    assert set(_pnl_by_symbol(attr)) == {'000106'}
    assert [r['symbol'] for r in attr['unpriced_positions']] == ['000107']


def test_组合口径_显式归属与继承归属都算(db, make_position, make_transaction):
    """组合 = 成员账本继承 + 持仓显式归属；组合外账户持仓不出现。"""
    from app.domains.ledgers.models import Ledger
    from app.domains.portfolios.models import Portfolio

    d1, d2 = dt.date(2026, 1, 5), dt.date(2026, 1, 6)

    pf = Portfolio(family_id=1, name='测试组合', is_deleted=False)
    db.add(pf)
    db.commit()

    # A：账户甲（成员账本）⇒ 继承进组合，+200
    pos_a = make_position(
        symbol='000108', name='组合内继承', quantity=1000, avg_price=1.0, asset_type='fund', account_name='组合甲账户'
    )
    make_transaction(
        position_id=pos_a.id,
        ledger_id=pos_a.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000108',
    )
    db.query(Ledger).filter(Ledger.id == pos_a.ledger_id).update({'portfolio_id': pf.id})
    db.commit()
    _add_nav(db, '000108', d1, 1.0)
    _add_nav(db, '000108', d2, 1.2)
    # B：账户乙（非成员、未显式指定）⇒ 组合外，+300 不该出现
    pos_b = make_position(
        symbol='000109', name='组合外基金', quantity=1000, avg_price=1.0, asset_type='fund', account_name='组合乙账户'
    )
    make_transaction(
        position_id=pos_b.id,
        ledger_id=pos_b.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000109',
    )
    _add_nav(db, '000109', d1, 1.0)
    _add_nav(db, '000109', d2, 1.3)
    # C：账户乙但**显式归属本组合** ⇒ 显式覆盖继承，+100 要出现
    pos_c = make_position(
        symbol='000110',
        name='显式归属基金',
        quantity=1000,
        avg_price=1.0,
        asset_type='fund',
        account_name='组合乙账户',
        portfolio_id=pf.id,
    )
    make_transaction(
        position_id=pos_c.id,
        ledger_id=pos_c.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000110',
    )
    _add_nav(db, '000110', d1, 1.0)
    _add_nav(db, '000110', d2, 1.1)

    attr = compute_range_attribution(
        db, family_id=1, start_date='2026-01-05', end_date='2026-01-06', portfolio_id=pf.id
    )

    assert attr['scope'] == 'portfolio'
    assert attr['portfolio_id'] == pf.id
    assert _pnl_by_symbol(attr) == pytest.approx({'000108': 200.0, '000110': 100.0})
    assert attr['total_pnl'] == pytest.approx(300.0, abs=0.001)


def test_账户口径_Σ账户等于家庭且对齐账户日历(db, make_position, make_transaction):
    """账户级：Σ品种 ≡ 账户级日历 month_total；家庭 = Σ账户（#1916 可加性）。"""
    d1, d2 = dt.date(2026, 1, 5), dt.date(2026, 1, 6)

    pos_a = make_position(
        symbol='000111', name='甲账户基金', quantity=1000, avg_price=1.0, asset_type='fund', account_name='可加甲账户'
    )
    make_transaction(
        position_id=pos_a.id,
        ledger_id=pos_a.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000111',
    )
    _add_nav(db, '000111', d1, 1.0)
    _add_nav(db, '000111', d2, 1.2)
    pos_b = make_position(
        symbol='000112', name='乙账户基金', quantity=1000, avg_price=1.0, asset_type='fund', account_name='可加乙账户'
    )
    make_transaction(
        position_id=pos_b.id,
        ledger_id=pos_b.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000112',
    )
    _add_nav(db, '000112', d1, 1.0)
    _add_nav(db, '000112', d2, 1.1)

    attr_f = compute_range_attribution(db, family_id=1, start_date='2026-01-05', end_date='2026-01-06')
    attr_a = compute_range_attribution(
        db, family_id=1, start_date='2026-01-05', end_date='2026-01-06', ledger_id=pos_a.ledger_id
    )
    attr_b = compute_range_attribution(
        db, family_id=1, start_date='2026-01-05', end_date='2026-01-06', ledger_id=pos_b.ledger_id
    )
    engine_a = build_daily_pnl_series(
        db, family_id=1, start_date='2026-01-05', end_date='2026-01-06', ledger_id=pos_a.ledger_id
    )

    assert attr_a['scope'] == 'ledger'
    assert attr_a['total_pnl'] == pytest.approx(engine_a['month_total'], abs=0.001)
    assert attr_a['total_pnl'] == pytest.approx(200.0, abs=0.001)
    assert attr_b['total_pnl'] == pytest.approx(100.0, abs=0.001)
    # 家庭可加：家庭归因 = Σ 各账户归因
    assert attr_f['total_pnl'] == pytest.approx(attr_a['total_pnl'] + attr_b['total_pnl'], abs=0.001)


def test_无持仓诚实降级_total为None(db):
    """区间内无任何持仓：total_pnl=None（不是 0.0——0.0 会被读成「没赚没赔」）。"""
    attr = compute_range_attribution(db, family_id=1, start_date='2026-01-05', end_date='2026-01-06')

    assert attr['total_pnl'] is None
    assert attr['has_any_computable'] is False
    assert attr['positions'] == []
    assert attr['categories'] == []


def test_参数校验_互斥与组合不存在(db):
    with pytest.raises(ValueError, match='互斥'):
        compute_range_attribution(
            db, family_id=1, start_date='2026-01-05', end_date='2026-01-06', ledger_id=1, portfolio_id=1
        )
    with pytest.raises(ValueError, match='投资组合不存在'):
        compute_range_attribution(db, family_id=1, start_date='2026-01-05', end_date='2026-01-06', portfolio_id=999999)
