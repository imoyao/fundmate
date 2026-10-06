# -*- coding: utf-8 -*-
"""每日收益日历派生口径测试（#1812）。

重点验证三件事：
1. **资金流免疫**——存取款当日不产生虚假日盈亏（这是选用 `total_pnl` 日差分
   而非 `net_worth` 日环比的根本理由）；
2. **四态可区分**——「无价格序列」不画成 0（balance 模式账户的关键诉求）；
3. **恒等式**——家庭级日盈亏 = Σ 各账户级日盈亏。
"""

import datetime as dt

import pytest

from app.core.money import Money
from app.domains.funds.models import DailyWorth
from app.services.pnl_calendar import (
    STATE_CLOSED,
    STATE_NO_PRICE,
    STATE_UPDOWN,
    STATE_ZERO,
    build_daily_pnl_series,
)


def _add_nav(db, fund_code, date, unit_nav):
    db.add(DailyWorth(fund_code=fund_code, date=date, unit_nav=unit_nav))
    db.commit()


def _state_of(result, day):
    return next((d['state'] for d in result['days'] if d['date'] == day.isoformat()), None)


def _pnl_of(result, day):
    return next((d['daily_pnl'] for d in result['days'] if d['date'] == day.isoformat()), None)


def test_资金流免疫_追加投入不产生虚假日盈亏(db, make_position, make_transaction):
    """追加买入当日：份额与成本同步增加 ⇒ 日盈亏应为 0，而非凭空跳增。

    这是本卡选用 `total_pnl` 日差分的核心依据。若误用 `net_worth` 日环比，
    追加投入当天会显示为「赚了一笔」，那就是假盈利。
    """
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)

    pos = make_position(symbol='000001', name='测试基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000001',
    )
    # d2 追加买入：份额 1000→2000，成本 1.0→1.0，市值不变 ⇒ 盈亏仍为 0
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d2,
        symbol='000001',
    )
    _add_nav(db, '000001', d1, 1.0)
    _add_nav(db, '000001', d2, 1.0)

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')

    # d2 当日：净值持平、份额翻倍但成本同步翻倍 ⇒ 盈亏必须为 0
    assert _pnl_of(result, d2) == 0, f'追加投入当日应盈亏 0，实际 {_pnl_of(result, d2)}'
    assert _state_of(result, d2) == STATE_ZERO


def test_净值下跌产生负收益(db, make_position, make_transaction):
    """净值从 1.2 跌到 1.1 ⇒ 当日负收益，且金额等于 (1.1-1.2)×份额。"""
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)

    pos = make_position(symbol='000002', name='下跌基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000002',
    )
    _add_nav(db, '000002', d1, 1.2)
    _add_nav(db, '000002', d2, 1.1)

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')

    # 份额 1000份，净值跌 0.1 元 ⇒ -100 元
    assert _pnl_of(result, d2) == pytest.approx(-100.0, abs=0.01)
    assert _state_of(result, d2) == STATE_UPDOWN


def test_无价格序列标记为no_price而非零收益(db, make_position, make_transaction):
    """balance 模式（银行理财等）无历史价格 ⇒ 整段 no_price，绝不能画成 0。"""
    d1 = dt.date(2026, 1, 5)
    pos = make_position(
        symbol='ZH0001',
        name='银行理财',
        quantity=0,
        avg_price=0,
        asset_type='portfolio',
        valuation_mode='balance',
        market_value_override=Money.yuan_to_cents(50000),
    )

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')

    assert result['has_any_price'] is False
    for day in (d1, dt.date(2026, 1, 6), dt.date(2026, 1, 7)):
        assert _state_of(result, day) == STATE_NO_PRICE, f'{day} 应为 no_price'
        assert _pnl_of(result, day) is None, f'{day} 无价格序列时盈亏须为 None（区别于 0）'


def test_零收益与无数据可区分(db, make_position, make_transaction):
    """净值持平 ⇒ zero 态且盈亏 0；无净值记录 ⇒ closed 态且盈亏 None。"""
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)
    d3 = dt.date(2026, 1, 7)

    pos = make_position(symbol='000003', name='持平基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000003',
    )
    _add_nav(db, '000003', d1, 1.0)
    _add_nav(db, '000003', d2, 1.0)
    # d3 故意不写净值 ⇒ 模拟未同步/休市

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')

    assert _state_of(result, d2) == STATE_ZERO
    assert _pnl_of(result, d2) == 0
    assert _state_of(result, d3) == STATE_CLOSED
    assert _pnl_of(result, d3) is None


def test_月合计等于区间内日序列求和(db, make_position, make_transaction):
    """验收项：月合计与区间内日盈亏求和一致（含边界日）。"""
    d1 = dt.date(2026, 1, 5)
    days = [dt.date(2026, 1, 5) + dt.timedelta(days=i) for i in range(4)]

    pos = make_position(symbol='000004', name='合计基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000004',
    )
    for i, day in enumerate(days):
        _add_nav(db, '000004', day, 1.0 + i * 0.01)

    result = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-08')

    s = sum(d['daily_pnl'] for d in result['days'] if d['daily_pnl'] is not None)
    assert result['month_total'] == pytest.approx(s, abs=0.02)


def test_家庭级等于各账户级之和(db, make_position, make_transaction):
    """恒等式：家庭级 daily_pnl = Σ 各账户级 daily_pnl。"""
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)

    p1 = make_position(
        symbol='000011', name='账户A基金', account_name='证券账户', quantity=1000, avg_price=1.0, asset_type='fund'
    )
    p2 = make_position(
        symbol='000012', name='账户B基金', account_name='银行账户', quantity=2000, avg_price=2.0, asset_type='fund'
    )
    for pos, qty in ((p1, 1000), (p2, 2000)):
        make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            txn_type='buy',
            quantity=qty,
            price=1.0,
            confirm_date=d1,
            symbol=pos.symbol,
        )
    _add_nav(db, '000011', d1, 1.0)
    _add_nav(db, '000011', d2, 1.05)
    _add_nav(db, '000012', d1, 2.0)
    _add_nav(db, '000012', d2, 2.10)

    family = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')
    led_a = build_daily_pnl_series(
        db, family_id=1, start_date='2026-01-05', end_date='2026-01-07', ledger_id=p1.ledger_id
    )
    led_b = build_daily_pnl_series(
        db, family_id=1, start_date='2026-01-05', end_date='2026-01-07', ledger_id=p2.ledger_id
    )

    assert family['scope'] == 'family'
    assert led_a['scope'] == 'ledger'
    assert family['month_total'] == pytest.approx(led_a['month_total'] + led_b['month_total'], abs=0.02)
    # 逐日对账。区间首日无前一日基准，三级都必须同为 None（都不可算），
    # 否则「账户级首日有值、家庭级首日无值」这种分叉会伪装成口径不一致。
    for day in (d1, d2):
        fam_v = _pnl_of(family, day)
        a_v = _pnl_of(led_a, day)
        b_v = _pnl_of(led_b, day)
        if fam_v is None:
            assert a_v is None and b_v is None, f'{day} 首日：三级应同为 None'
        else:
            assert fam_v == pytest.approx(a_v + b_v, abs=0.02)


def test_改持仓后历史自动重算(db, make_position, make_transaction):
    """本卡核心诉求：后补的建仓流水会改变 as-of 历史（快照方案做不到这点）。"""
    d1 = dt.date(2026, 1, 5)
    d2 = dt.date(2026, 1, 6)

    pos = make_position(symbol='000021', name='后补建仓', quantity=1000, avg_price=1.0, asset_type='fund')
    _add_nav(db, '000021', d1, 1.0)
    _add_nav(db, '000021', d2, 1.1)

    # 场景 A：起初没流水 ⇒ d2 无价格序列变化可算
    before = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')
    assert before['has_any_price'] is False

    # 场景 B：补录 d1 的建仓流水 ⇒ d2 立刻能算出 +100 元
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=d1,
        symbol='000021',
    )
    after = build_daily_pnl_series(db, family_id=1, start_date='2026-01-05', end_date='2026-01-07')

    assert after['has_any_price'] is True
    assert _pnl_of(after, d2) == pytest.approx(100.0, abs=0.01)
