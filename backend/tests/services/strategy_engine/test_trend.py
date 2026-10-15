# -*- coding: utf-8 -*-
"""趋势跟踪策略 + 契约/注册表的基础测试（#2224）。

全部为纯计算用例，不连数据库——策略层本就不该依赖 DB。
"""

from datetime import date, timedelta

import pytest

from app.services.strategy_engine import strategies  # noqa: F401  触发注册
from app.services.strategy_engine.contracts import (
    PositionState,
    SeriesPoint,
    SignalAction,
    StrategyContext,
    StrategyFamily,
    simple_moving_average,
)
from app.services.strategy_engine.registry import registry
from app.services.strategy_engine.strategies.trend import TrendFollowingStrategy

BASE_DAY = date(2026, 1, 1)


def _series(values, start: date = BASE_DAY) -> tuple[SeriesPoint, ...]:
    return tuple(SeriesPoint(date=start + timedelta(days=i), value=v) for i, v in enumerate(values))


def _ctx(values, **params) -> StrategyContext:
    return StrategyContext(symbol='000001', name='测试标的', series=_series(values), params=params)


def test_sma_prefix_is_none_not_zero():
    """长度不足返回 None——不能补 0，否则信号会假装自己有效。"""
    ma = simple_moving_average([1.0, 2.0, 3.0], window=5)
    assert ma == [None, None, None]


def test_sma_value():
    assert simple_moving_average([1.0, 2.0, 3.0], window=2)[-1] == pytest.approx(2.5)


def test_registry_registers_trend():
    assert registry.get('trend_following') is not None
    assert 'trend_following' in registry.codes()
    assert registry.by_family(StrategyFamily.TIMING)


def test_registry_satisfiable_filters_by_data():
    """数据不足（无 nav）时趋势策略不该出现在可运行列表里。"""
    assert registry.satisfiable(['nav'])
    assert not registry.satisfiable([])


def test_insufficient_history_returns_watch():
    """样本不足 → WATCH + WATCHING，而不是硬算出个方向。"""
    signal = TrendFollowingStrategy().evaluate(_ctx([1.0] * 10))
    assert signal.action is SignalAction.WATCH
    assert signal.state is PositionState.WATCHING
    assert '不足' in signal.reason


def test_uptrend_signals_buy():
    rising = [100.0 + i * 0.5 for i in range(80)]
    signal = TrendFollowingStrategy().evaluate(_ctx(rising))
    assert signal.action is SignalAction.BUY
    assert signal.state is PositionState.HOLDING
    assert signal.metrics['nav'] > signal.metrics['ma20'] > signal.metrics['ma60']


def test_downtrend_signals_sell():
    falling = [200.0 - i * 0.6 for i in range(80)]
    signal = TrendFollowingStrategy().evaluate(_ctx(falling))
    assert signal.action is SignalAction.SELL
    assert signal.state is PositionState.CLEARED


def test_watch_has_no_action_word_in_reason():
    """合规：任何信号的文案都不得出现「建议」字样。"""
    for values in ([1.0] * 10, [100.0 + i for i in range(80)], [200.0 - i for i in range(80)]):
        signal = TrendFollowingStrategy().evaluate(_ctx(values))
        assert '建议' not in signal.reason


def test_invalid_windows_raise():
    with pytest.raises(ValueError):
        TrendFollowingStrategy().evaluate(_ctx([1.0] * 80, fast_window=60, slow_window=20))
