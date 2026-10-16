# -*- coding: utf-8 -*-
"""行为反推测试（#2225）——纯数据输入，不连库。"""

from datetime import date, timedelta

import pytest

from app.services.strategy_engine.behavior_profile import TradeRecord, build_behavior_profile
from app.services.strategy_engine.contracts import SeriesPoint

D0 = date(2025, 1, 1)


def _series(values, start: date = D0) -> tuple[SeriesPoint, ...]:
    return tuple(SeriesPoint(date=start + timedelta(days=i), value=v) for i, v in enumerate(values))


def _trade(day_offset: int, side: str, qty: float, price: float) -> TradeRecord:
    return TradeRecord(
        symbol='000001', trade_date=D0 + timedelta(days=day_offset), side=side, quantity=qty, price=price
    )


def test_empty_trades_returns_unknown():
    profile = build_behavior_profile('000001', [], _series([1.0, 1.1]))
    assert profile.trade_count == 0
    assert profile.classified_as == 'unknown'


def test_long_hold_classification():
    """买入持有 400 天未卖 → 长期持有。"""
    trades = [_trade(0, 'buy', 1000.0, 1.0)]
    series = _series([1.0 + i * 0.001 for i in range(500)])
    profile = build_behavior_profile('000001', trades, series, today=D0 + timedelta(days=400))
    assert profile.avg_hold_days == 400
    assert profile.classified_as == 'long_hold'


def test_short_hold_classification():
    """买入 10 天后卖出 → 短线频繁交易。"""
    trades = [_trade(0, 'buy', 1000.0, 1.0), _trade(10, 'sell', 1000.0, 1.05)]
    series = _series([1.0 + i * 0.001 for i in range(60)])
    profile = build_behavior_profile('000001', trades, series)
    assert profile.avg_hold_days == 10
    assert profile.classified_as == 'frequent'


def test_early_exit_cost_positive_when_price_kept_rising():
    """卖在 1.05、后来涨到 1.20 → 提前卖出少赚 (1.20-1.05)*1000 = 150。"""
    trades = [_trade(0, 'buy', 1000.0, 1.0), _trade(30, 'sell', 1000.0, 1.05)]
    series = _series([1.0 + i * 0.004 for i in range(60)])  # 末值 ≈ 1.236
    profile = build_behavior_profile('000001', trades, series)
    assert profile.early_exit_cost is not None
    assert profile.early_exit_cost > 0


def test_early_exit_cost_can_be_negative():
    """卖在 1.20、后来跌到 1.10 → 提前卖出反而躲过了下跌，代价为负（如实呈现）。"""
    trades = [_trade(0, 'buy', 1000.0, 1.0), _trade(30, 'sell', 1000.0, 1.20)]
    series = _series([1.0] * 30 + [1.10])
    profile = build_behavior_profile('000001', trades, series)
    assert profile.early_exit_cost == pytest.approx(-100.0)


def test_profitable_sell_ratio():
    """两卖一赚一亏 → 50%。"""
    trades = [
        _trade(0, 'buy', 1000.0, 1.0),
        _trade(10, 'buy', 1000.0, 1.0),
        _trade(20, 'sell', 1000.0, 1.20),  # 盈利
        _trade(30, 'sell', 1000.0, 0.90),  # 亏损
    ]
    series = _series([1.0] * 40)
    profile = build_behavior_profile('000001', trades, series)
    assert profile.profitable_sell_ratio == pytest.approx(50.0)
    assert profile.evidence['closed_pairs'] == 2


def test_fifo_partial_fill():
    """一笔买 1000，分两次各卖 400 → 第二笔卖只能配到剩余 200 份的那部分。"""
    trades = [
        _trade(0, 'buy', 1000.0, 1.0),
        _trade(10, 'sell', 400.0, 1.10),
        _trade(20, 'sell', 400.0, 1.10),
    ]
    series = _series([1.0] * 40)
    profile = build_behavior_profile('000001', trades, series)
    assert profile.evidence['closed_pairs'] == 2
    assert profile.profitable_sell_ratio == pytest.approx(100.0)


def test_no_side_effect_on_input():
    """行为反推不得修改传入的交易列表。"""
    trades = [_trade(0, 'buy', 1000.0, 1.0)]
    snapshot = list(trades)
    build_behavior_profile('000001', trades, _series([1.0] * 10))
    assert trades == snapshot
