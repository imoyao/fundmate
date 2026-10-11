# -*- coding: utf-8 -*-
"""#2007 回归：持仓展示层的「当日盈亏」口径。

`enrich_position_dict` 是 positions / ledgers 两域共用的**唯一**展示出口，
所以口径钉在这里最省事，也不用起库（`Position` 是纯 ORM 对象，本文件全为纯函数断言）。

覆盖四条红线：

1. **单位**：`day_pnl` 是**元**（与 `pnl` 同），`day_pnl_rate` 是**百分数**（与
   `ledger_service.pnl_rate` 同），两个不同单位必须各自正确；
2. **缺失即 None，绝不 0**：没有上一确认价时给 `None`（前端降级「—」）；
   给 0 会被读成「今天一分没涨没跌」——那是编造一个用户会信的结论；
3. **`prev_close = 0` 也走 None**：除零要拦住，不能让 `ratio` 变成 inf；
4. **货基**（按面值计价、基准留 NULL）同样落 None，不因「价格恒为 1」而显示 0 涨跌。
"""

from datetime import date

from app.core.money import Money
from app.domains.positions.models import Position
from app.services.position_presenter import enrich_position_dict


def _pos(**overrides) -> Position:
    """一条持仓（1.0000 元成本 / 1.1000 元现价、1 份），字段值刻意取成好算的数。

    `source` / `symbol_norm` / `allocation` 这些**列默认值**必须显式给：ORM 的
    `default=` 只在 INSERT 时生效，这里是纯对象（不过库），拿不到默认值，
    直接传下去会被 `PositionOut` 的必填校验拦下。
    """
    base = dict(
        id=1,
        symbol='000001',
        symbol_norm='CN_A:000001',
        name='测试标的',
        market='CN_A',
        asset_type='fund',
        quantity=10000,  # 1 份（内部单位 0.0001 份）
        avg_price=10000,  # 1.0000 元
        current_price=11000,  # 1.1000 元
        currency='CNY',
        valuation_mode='nav',
        allocation='longterm',
        source='manual',
        ownership_status='active',
        family_id=1,
    )
    base.update(overrides)
    return Position(**base)


def test_day_pnl_and_rate_units():
    """`day_pnl` 元 + `day_pnl_rate` 百分数：两者单位不同，必须各自正确。"""
    p = _pos(prev_close=10000, price_date=date(2026, 10, 9))  # 上一确认价 1.0000 元

    d = enrich_position_dict(p)

    # (1.1000 − 1.0000) 元 × 1 份 = 0.1 元
    assert d['day_pnl'] == 0.1
    # 涨幅 10% → 百分数 10.0（前端不再 ×100，直接带 % 展示）
    assert d['day_pnl_rate'] == 10.0
    assert d['prev_close'] == 1.0
    assert d['price_date'] == '2026-10-09'


def test_day_pnl_matches_multiply_helper():
    """金额走 `Money.multiply_price_quantity`（不得裸乘 float），与实际口径逐分一致。"""
    p = _pos(quantity=123456, prev_close=9876, current_price=10234)

    d = enrich_position_dict(p)

    expected_cents = Money.multiply_price_quantity(p.current_price - p.prev_close, p.quantity)
    assert d['day_pnl'] == Money.cents_to_yuan(expected_cents)


def test_missing_prev_close_yields_none_not_zero():
    """无基准 → None（不是 0）。这条是整张卡的语义核心。"""
    p = _pos(prev_close=None, price_date=None)

    d = enrich_position_dict(p)

    assert d['day_pnl'] is None
    assert d['day_pnl_rate'] is None
    assert d['prev_close'] is None
    assert d['price_date'] is None


def test_zero_prev_close_does_not_explode():
    """`prev_close = 0` 走同一条 None 分支：不能让 ratio 变成 inf / 被 JSON 序列化炸掉。"""
    p = _pos(prev_close=0)

    d = enrich_position_dict(p)

    assert d['day_pnl'] is None
    assert d['day_pnl_rate'] is None


def test_money_fund_baseline_stays_none():
    """货基按面值计价（价格恒 1.0000），没有「上一日价差」→ 基准 NULL → 显示「—」。"""
    p = _pos(
        asset_type='money_fund',
        is_money_fund=True,
        quantity=10000000,
        avg_price=10000,
        current_price=10000,
        prev_close=None,
        price_date=None,
    )

    d = enrich_position_dict(p)

    assert d['day_pnl'] is None
    assert d['day_pnl_rate'] is None


def test_existing_pnl_caliber_unchanged():
    """`pnl`（持有盈亏）口径不因本卡受影响：仍是 (现价 − 成本) × 数量，且不含已实现。"""
    p = _pos(prev_close=9000)

    d = enrich_position_dict(p)

    assert d['pnl'] == 0.1  # (1.1000 − 1.0000) × 1 份
