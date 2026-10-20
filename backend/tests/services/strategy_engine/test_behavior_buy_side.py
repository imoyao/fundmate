# -*- coding: utf-8 -*-
"""买入侧行为指标测试（#2382）——forward_return / buy_percentile / actual_vs_hold。

全部纯数据输入，不连库、不发起外部请求（末尾有网络探针测试钉住这一点）。
"""

import socket
from datetime import date, timedelta

import pytest

from app.services.strategy_engine.behavior_profile import (
    TradeRecord,
    account_actual_vs_hold,
    build_behavior_profile,
    forward_return_metrics,
    percentile_rank,
    year_return,
)
from app.services.strategy_engine.contracts import SeriesPoint

D0 = date(2025, 1, 1)


def _series(values, start: date = D0) -> tuple[SeriesPoint, ...]:
    return tuple(SeriesPoint(date=start + timedelta(days=i), value=v) for i, v in enumerate(values))


def _trade(day_offset: int, side: str, qty: float, price: float, symbol: str = '000001') -> TradeRecord:
    return TradeRecord(symbol=symbol, trade_date=D0 + timedelta(days=day_offset), side=side, quantity=qty, price=price)


# ── forward_return：买点质量 ──


def test_forward_return_basic_horizons():
    """买入 1.0，之后净值线性涨：h20/h60/h120 收益各可由序列手工复算。"""
    buys = [_trade(0, 'buy', 1000.0, 1.0)]
    series = _series([1.0 + i * 0.01 for i in range(200)])
    metrics = forward_return_metrics(buys, {p.date: p.value for p in series})
    # 买入日之后第 20 个净值日 = 下标 20 → 1.20 → +20%
    assert metrics['h20']['mean'] == pytest.approx(20.0)
    assert metrics['h20']['win_rate'] == pytest.approx(100.0)
    assert metrics['h20']['sample_count'] == 1
    assert metrics['h20']['missing_count'] == 0
    assert metrics['h60']['mean'] == pytest.approx(60.0)
    assert metrics['h120']['mean'] == pytest.approx(120.0)


def test_forward_return_uses_trade_price_not_nav():
    """成交价 1.05、当日净值 1.0：收益按用户真实付出的成交价算。"""
    buys = [_trade(0, 'buy', 1000.0, 1.05)]
    series = _series([1.0 + i * 0.01 for i in range(30)])
    metrics = forward_return_metrics(buys, {p.date: p.value for p in series})
    # 第 20 个净值日净值 1.20，相对成交价 1.05 → +14.29%
    assert metrics['h20']['mean'] == pytest.approx((1.20 - 1.05) / 1.05 * 100, rel=1e-3)


def test_forward_return_missing_when_window_too_short():
    """序列只有 10 天：所有窗口零样本 → 整体 None（调用方降级），不出现半空字典。"""
    buys = [_trade(0, 'buy', 1000.0, 1.0)]
    series = _series([1.0 + i * 0.01 for i in range(10)])
    metrics = forward_return_metrics(buys, {p.date: p.value for p in series})
    assert metrics is None


def test_forward_return_win_rate_and_median():
    """三笔不同成本的买入，同一净值路径：胜率/中位数可由逐笔收益手工复算。"""
    buys = [
        _trade(0, 'buy', 100.0, 1.0),  # day10 净值 1.10 → +10%
        _trade(0, 'buy', 100.0, 1.20),  # day10 净值 1.10 → -8.33%
        _trade(0, 'buy', 100.0, 0.90),  # day10 净值 1.10 → +22.22%
    ]
    values = [1.0] * 5 + [1.10] * 6  # 11 天：day0 买入 + 之后 10 个净值日
    series = _series(values)
    mapping = {p.date: p.value for p in series}
    metrics = forward_return_metrics(buys, mapping, horizons=(10,))
    assert metrics['h10']['sample_count'] == 3
    expected = sorted((1.10 - b.price) / b.price * 100 for b in buys)
    assert metrics['h10']['median'] == pytest.approx(expected[1], rel=1e-3)
    assert metrics['h10']['win_rate'] == pytest.approx(2 / 3 * 100, rel=1e-3)
    assert metrics['h10']['mean'] == pytest.approx(sum(expected) / 3, rel=1e-3)


def test_forward_return_no_buys_returns_none():
    assert forward_return_metrics([], {D0: 1.0}) is None


# ── percentile_rank：买入时点同类分位 ──


def test_percentile_rank_midrank():
    """20 个同类（含自身）：中位秩 = (严格小于 + 0.5×相等) / 20。"""
    peers = [float(i) for i in range(20)]  # 0..19
    assert percentile_rank(10.0, peers) == pytest.approx((10 + 0.5) / 20 * 100)  # 52.5
    assert percentile_rank(0.0, peers) == pytest.approx(0.5 / 20 * 100)  # 2.5
    assert percentile_rank(19.0, peers) == pytest.approx((19 + 0.5) / 20 * 100)  # 97.5


def test_percentile_rank_insufficient_peers_returns_none():
    """同类样本 < 20 → 伪精确，诚实降级 None（卡里验收第 2 条）。"""
    assert percentile_rank(50.0, [float(i) for i in range(19)]) is None


def test_percentile_rank_none_inputs():
    assert percentile_rank(None, [1.0] * 30) is None
    assert percentile_rank(1.0, None) is None


# ── year_return：近 1 年自身收益 ──


def test_year_return_basic():
    assert year_return(1.0, 1.2) == pytest.approx(20.0)
    assert year_return(0.0, 1.2) is None
    assert year_return(1.0, None) is None


# ── build_behavior_profile 接线 ──


def test_profile_includes_forward_return():
    trades = [_trade(0, 'buy', 1000.0, 1.0)]
    series = _series([1.0 + i * 0.01 for i in range(150)])
    profile = build_behavior_profile('000001', trades, series)
    assert profile.forward_return is not None
    assert profile.forward_return['h20']['mean'] == pytest.approx(20.0)
    assert profile.evidence['forward_missing_count'] == 0


def test_profile_forward_return_none_when_series_too_short():
    """序列短于最短窗口：forward_return 为 None，但画像其余字段仍正常。"""
    trades = [_trade(0, 'buy', 1000.0, 1.0)]
    series = _series([1.0] * 5)
    profile = build_behavior_profile('000001', trades, series)
    assert profile.forward_return is None
    assert profile.trade_count == 1


def test_profile_buy_percentile_via_peer_map():
    """peer map 按买入日给同类收益：逐笔算分位后取均值。"""
    trades = [_trade(0, 'buy', 1000.0, 1.0), _trade(30, 'buy', 500.0, 1.3)]
    series = _series([1.0 + i * 0.01 for i in range(150)])
    mapping = {p.date: p.value for p in series}
    # 两笔买入自身近 1 年收益：day0 窗口不足 365 天（序列只 150 天）→ 自身 None？
    # 序列 150 天 < 365 天窗口：_year_window_navs 取窗口内最早可得 → start=day0 净值 1.0
    own_d0 = (mapping[D0 + timedelta(days=149)] - 1.0) / 1.0 * 100
    own_d30 = (mapping[D0 + timedelta(days=149)] - 1.3) / 1.3 * 100
    peer_map = {
        D0: [own_d0] + [float(i) for i in range(19)],  # 自身 + 19 个同类 = 20
        D0 + timedelta(days=30): [own_d30] + [float(i) for i in range(19)],
    }
    profile = build_behavior_profile('000001', trades, series, peer_year_returns=peer_map)
    assert profile.buy_percentile is not None
    assert 0 <= profile.buy_percentile <= 100


def test_profile_buy_percentile_none_without_peer_map():
    """不传同类数据 → 分位 None（旧调用方零破坏）。"""
    trades = [_trade(0, 'buy', 1000.0, 1.0)]
    series = _series([1.0 + i * 0.01 for i in range(150)])
    profile = build_behavior_profile('000001', trades, series)
    assert profile.buy_percentile is None


# ── account_actual_vs_hold：账户层对照 ──


def test_actual_vs_hold_buy_only_matches_hold():
    """只买不卖、无早期交易：成本口径下实际收益与「持有到期末」同解。"""
    trades = [_trade(0, 'buy', 1000.0, 1.0)]
    series = _series([1.0 + i * 0.01 for i in range(30)])  # 末值 1.29
    result = account_actual_vs_hold(trades, {'000001': series})
    assert result is not None
    # 成交价=当日净值=1.0 → 两者都等于 (1.29-1.0)/1.0 = 29%
    assert result['actual_return_pct'] == pytest.approx(29.0, abs=0.01)
    assert result['hold_to_end_pct'] == pytest.approx(29.0, abs=0.01)
    assert result['diff_pct'] == pytest.approx(0.0, abs=0.01)


def test_actual_vs_hold_selling_early_loses():
    """买了涨了卖了、后来继续涨 → 实际操作跑输拿着，diff 为负。"""
    trades = [_trade(0, 'buy', 1000.0, 1.0), _trade(10, 'sell', 1000.0, 1.20)]
    series = _series([1.0] * 10 + [1.20] + [1.50] * 19)  # 之后一路 1.50
    result = account_actual_vs_hold(trades, {'000001': series})
    assert result is not None
    # 实际：期末 0 持仓 + 回款 1200 − 成本 1000 → 盈利 200 → 20%
    assert result['actual_return_pct'] == pytest.approx(20.0, abs=0.01)
    # 拿着：期末市值 1500 − 成本 1000 → 50%
    assert result['hold_to_end_pct'] == pytest.approx(50.0, abs=0.01)
    assert result['diff_pct'] == pytest.approx(-30.0, abs=0.01)


def test_actual_vs_hold_early_position_kept():
    """窗口前买入的份额参与期末市值，不丢早期交易。"""
    trades = [_trade(-10, 'buy', 1000.0, 1.0)]  # 早于序列起点
    series = _series([1.0 + i * 0.01 for i in range(30)], start=D0)
    result = account_actual_vs_hold(trades, {'000001': series})
    assert result is not None
    # 期末 1000×1.29，成本 1000 → +29%
    assert result['actual_return_pct'] == pytest.approx(29.0, abs=0.01)
    assert result['hold_to_end_pct'] == pytest.approx(29.0, abs=0.01)


def test_actual_vs_hold_none_without_trades():
    assert account_actual_vs_hold([], {'000001': _series([1.0, 1.1])}) is None


def test_actual_vs_hold_none_without_series():
    assert account_actual_vs_hold([_trade(0, 'buy', 100.0, 1.0)], {}) is None


def test_actual_vs_hold_multi_symbol_weighted():
    """两只基金：A 涨 10%、B 跌 10% 等额 → 账户收益 = 金额加权（成本口径）。"""
    trades = [
        _trade(0, 'buy', 1000.0, 1.0, symbol='A'),
        _trade(0, 'buy', 1000.0, 2.0, symbol='B'),
    ]
    series_a = _series([1.0 + i * 0.01 for i in range(11)], start=D0)  # 1.0 → 1.10
    series_b = _series([2.0 - i * 0.02 for i in range(11)], start=D0)  # 2.0 → 1.80
    result = account_actual_vs_hold(trades, {'A': series_a, 'B': series_b})
    assert result is not None
    # 成本 1000+2000=3000；期末市值 1100+1800=2900 → -100/3000 = -3.33%
    assert result['actual_return_pct'] == pytest.approx(-100 / 3000 * 100, abs=0.01)
    assert result['hold_to_end_pct'] == pytest.approx(-100 / 3000 * 100, abs=0.01)


# ── 零外部请求（卡里验收第 4 条） ──


def test_no_network_during_computation(monkeypatch):
    """行为指标计算期间任何 socket 连接尝试 → 测试失败（证明零外部请求）。"""

    def _boom(*args, **kwargs):
        raise AssertionError('行为指标计算不得发起网络请求')

    monkeypatch.setattr(socket.socket, 'connect', _boom)
    monkeypatch.setattr(socket, 'create_connection', _boom)

    trades = [_trade(0, 'buy', 1000.0, 1.0), _trade(5, 'sell', 500.0, 1.2)]
    series = _series([1.0 + i * 0.01 for i in range(150)])
    profile = build_behavior_profile(
        '000001',
        trades,
        series,
        peer_year_returns={D0: [float(i) for i in range(25)]},
    )
    assert profile.trade_count == 2
    result = account_actual_vs_hold(trades, {'000001': series})
    assert result is not None


# ── 合规措辞（卡里验收第 5 条） ──


def test_no_advice_wording_in_outputs():
    """输出措辞只陈述历史事实，不含买卖建议类表述。"""
    trades = [_trade(0, 'buy', 1000.0, 1.0), _trade(10, 'sell', 1000.0, 1.2)]
    series = _series([1.0] * 30)
    profile = build_behavior_profile('000001', trades, series)
    result = account_actual_vs_hold(trades, {'000001': series})
    banned = ('建议买入', '建议卖出', '应该买', '应该卖', '可以买入', '可以卖出', '推荐')
    texts = [profile.classified_label, str(profile.forward_return), str(profile.evidence)]
    if result:
        texts.extend(str(v) for v in result.values())
    for text in texts:
        for word in banned:
            assert word not in text
