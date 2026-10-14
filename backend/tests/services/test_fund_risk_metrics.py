# -*- coding: utf-8 -*-
"""基金风险收益指标（#167 P0 纯计算骨架）单元测试。

覆盖重点：
- 每个指标的公式方向正确（不是「跑起来」而是「算得对」）；
- 口径纪律：样本不足一律 None、rf 随值可改、跳变标记、胜率周期与窗口是两个轴；
- 边界：无波动（分母 0）、单调上涨、基准对齐（取交集）。
"""

from datetime import date, timedelta

import pytest

from app.services.fund_risk_metrics import (
    RISK_FREE_RATE_ANNUAL,
    benchmark_diagnostics,
    compute_risk_metrics,
    current_drawdown,
    detect_jumps,
    drawdown_series,
    ulcer_index,
    win_rate,
)

D0 = date(2020, 1, 1)


def _series(values, start=D0, step=1):
    return [(start + timedelta(days=i * step), v) for i, v in enumerate(values)]


def _flat(n, value=1.0):
    return _series([value] * n)


# ── 跳变检测 ─────────────────────────────────────────────────────────────────


def test_detect_jumps_hits_large_move():
    # 1.0 → 1.5 是 +50%，超阈值
    hits = detect_jumps(_series([1.0, 1.0, 1.5, 1.5]))
    assert hits == [D0 + timedelta(days=2)]


def test_detect_jumps_ignores_normal_moves():
    assert detect_jumps(_series([1.0, 1.02, 0.99, 1.01])) == []


def test_jump_marks_basis_distorted():
    r = compute_risk_metrics(_series([1.0, 1.1, 1.7, 1.75, 1.8]))
    assert r.basis == 'distorted'
    assert any('跳变' in c for c in r.caveats)


# ── 溃疡指数 ─────────────────────────────────────────────────────────────────


def test_ulcer_zero_when_monotonic_up():
    assert ulcer_index(_series([1.0, 1.1, 1.2, 1.3])) == 0.0


def test_ulcer_penalises_only_downside():
    # 全程上涨后一次性回落，看只罚下行：UI 只由回撤段贡献
    up = ulcer_index(_series([1.0, 1.2, 1.4]))
    down = ulcer_index(_series([1.0, 1.2, 0.9]))
    assert up == 0.0
    assert down is not None and down > 0


# ── 主入口：年化收益 / 波动率 / 回撤 ─────────────────────────────────────────


def test_annual_return_endpoint_geometric():
    # 一年（365 天）翻倍 → 年化 ≈ 100%
    # 至少 3 个点：少于 3 点时只有 1 个日收益，年化会被外推成天文数字 ⇒ 早退不出现值
    s = [(date(2020, 1, 1), 1.0), (date(2020, 7, 1), 1.5), (date(2020, 12, 31), 2.0)]
    r = compute_risk_metrics(s)
    assert r.annual_return == pytest.approx(100.0, abs=0.01)


def test_max_drawdown_negative_sign_kept():
    r = compute_risk_metrics(_series([1.0, 1.2, 0.9, 1.1]))
    # 与既有 max_drawdown 字段同号（负数），避免两个域符号打架
    assert r.max_drawdown is not None and r.max_drawdown < 0


def test_zero_volatility_sharpe_none_but_sortino_defined():
    # 净值恒定 → 波动率 0（**合法值**，不是 None）
    r = compute_risk_metrics(_flat(300))
    assert r.annual_volatility == 0.0
    # 夏普是 (0−rf)/0 型 0/0，无定义 ⇒ None（不能返回 inf）
    assert r.sharpe is None
    # 索提诺的分母是「低于 MAR(=rf) 的偏离」，恒定 0 收益每一天都低于 rf ⇒ 分母非 0，
    # 故它**有定义且为负** —— 这正是诚实表达「这只基金从未跑赢现金」。
    assert r.sortino is not None and r.sortino < 0


def test_flat_series_with_zero_rf_has_no_sortino():
    # rf=0 时恒定收益的偏离全为 0 ⇒ 索提诺分母 0 ⇒ 同样不出值
    r = compute_risk_metrics(_flat(300), rf_annual=0.0)
    assert r.sortino is None


def test_calmar_divides_by_abs_drawdown():
    # 年化收益为正、回撤为负 → 卡玛为正（不能因符号搞成负数）
    r = compute_risk_metrics(_series([1.0, 1.2, 0.9, 1.1, 1.3]))
    assert r.calmar is not None
    assert r.calmar > 0


def test_return_drawdown_ratio_positive_when_return_positive():
    r = compute_risk_metrics(_series([1.0, 1.2, 0.9, 1.1, 1.3]))
    assert r.return_drawdown_ratio is not None
    assert r.return_drawdown_ratio > 0


# ── rf 口径 ──────────────────────────────────────────────────────────────────


def test_rf_is_shipped_in_caveats():
    r = compute_risk_metrics(_series([1.0 + i * 0.001 for i in range(300)]))
    assert any('rf=' in c for c in r.caveats), 'rf 必须随值下发，否则夏普不可复核'


def test_higher_rf_lowers_sharpe_but_keeps_order():
    # rf 的核心性质：**同窗口内所有基金同减一个数 ⇒ 排序不变**（这才是取常量的理由）。
    # 不预设谁高谁低（取决于各自的收益/波动比），只钉「次序不变」+「绝对水平同步下降」。
    a = _series([1.0 + i * 0.002 for i in range(300)])
    b = _series([1.0 + i * 0.001 for i in range(300)])
    r_low = [compute_risk_metrics(x, rf_annual=0.0).sharpe for x in (a, b)]
    r_high = [compute_risk_metrics(x, rf_annual=0.05).sharpe for x in (a, b)]
    assert r_low[0] != r_low[1]  # 两者本就不同，才有「次序」可谈
    assert (r_high[0] > r_high[1]) == (r_low[0] > r_low[1])  # 次序不变
    assert r_high[0] < r_low[0] and r_high[1] < r_low[1]  # 绝对水平同步下降


def test_default_rf_matches_constant():
    assert RISK_FREE_RATE_ANNUAL == 0.015


# ── 胜率：周期与窗口是两个正交的轴 ───────────────────────────────────────────


def test_win_rate_day_vs_month_differ():
    # 锯齿形：日频胜率约 50%，月频抽样后不同 —— 证明两者不是「同一指标的精度差异」
    vals = []
    v = 1.0
    for i in range(300):
        v *= 1.01 if i % 2 == 0 else 0.995
        vals.append(v)
    day = win_rate(_series(vals), period='day')
    month = win_rate(_series(vals), period='month')
    assert day is not None and month is not None
    assert day != month


def test_win_rate_rejects_unknown_period():
    with pytest.raises(ValueError):
        win_rate(_series([1.0, 1.1]), period='quarter')


def test_win_rate_marked_overlap():
    r = compute_risk_metrics(_series([1.0 + i * 0.001 for i in range(300)]))
    assert r.overlap is True, '滚动窗口重叠，须标 overlap（体验指标而非概率）'


def test_win_rate_insufficient_samples_is_none():
    assert win_rate(_series([1.0]), period='month') is None


# ── 样本不足：诚实降级 ───────────────────────────────────────────────────────


def test_insufficient_points_returns_none_fields():
    # 2 个点只有 1 个日收益 ⇒ 不足以支撑任何指标（年化会被外推成天文数字），全为 None
    r = compute_risk_metrics(_series([1.0, 1.1]))
    assert r.sample_points == 2
    assert r.annual_return is None
    assert r.annual_volatility is None
    assert r.sharpe is None


def test_empty_series_is_none():
    r = compute_risk_metrics([])
    assert r.sample_points == 0
    assert r.as_of is None
    assert r.sharpe is None


# ── 基准相对指标 ─────────────────────────────────────────────────────────────


def test_benchmark_aligns_by_common_dates():
    fund = _series([1.0, 1.1, 1.2, 1.3])
    bench = _series([1.0, 1.05, 1.1])  # 少一天
    out = benchmark_diagnostics(fund, bench)
    assert out['basis'] == 'ok'
    assert out['sample_points'] == 3  # 取交集，不能错配


def test_benchmark_insufficient():
    out = benchmark_diagnostics(_series([1.0, 1.1]), _series([1.0]))
    assert out['basis'] == 'insufficient'


def test_benchmark_excess_return_sign():
    # 基金涨得比基准快 → 超额为正
    fund = _series([1.0, 1.2, 1.5, 1.8, 2.0])
    bench = _series([1.0, 1.05, 1.1, 1.15, 1.2])
    out = benchmark_diagnostics(fund, bench)
    assert out['excess_return'] is not None and out['excess_return'] > 0


def test_upside_capture_above_100_when_outperforming_up_days():
    # 基准上涨日基金涨得更多 → 上行捕获 > 100
    fund = _series([1.0, 1.10, 1.22, 1.36])
    bench = _series([1.0, 1.05, 1.10, 1.15])
    out = benchmark_diagnostics(fund, bench)
    assert out['upside_capture'] is not None
    assert out['upside_capture'] > 100


def test_downside_capture_below_100_when_falling_less():
    # 基准下跌日基金跌得更少 → 下行捕获 < 100（好）
    fund = _series([1.0, 0.995, 0.99, 0.985])
    bench = _series([1.0, 0.95, 0.90, 0.85])
    out = benchmark_diagnostics(fund, bench)
    assert out['downside_capture'] is not None
    assert out['downside_capture'] < 100


def test_benchmark_none_when_not_provided():
    r = compute_risk_metrics(_series([1.0, 1.1, 1.2]))
    assert r.benchmark is None


def test_benchmark_attached_when_provided():
    r = compute_risk_metrics(_series([1.0, 1.1, 1.2, 1.3]), benchmark_points=_series([1.0, 1.05, 1.1, 1.15]))
    assert r.benchmark is not None and r.benchmark['basis'] == 'ok'


# ── 本轮回撤（#167：与「最大回撤」是两个不同问题） ─────────────────────────


def test_drawdown_series_shape_and_bounds():
    # 1.0 → 1.2（新高）→ 0.9（-25%）→ 1.1（仍低于新高，DD = -8.33%）
    series = drawdown_series(_series([1.0, 1.2, 0.9, 1.1]))
    assert series[0][1] == 0.0  # 首日即高点
    assert series[1][1] == 0.0  # 创新高 → DD 归 0
    assert series[2][1] == pytest.approx(-25.0)
    assert series[3][1] == pytest.approx(-8.3333, abs=1e-3)
    assert all(dd <= 0 for _d, dd in series), '回撤恒 ≤ 0'


def test_current_drawdown_zero_when_at_new_high():
    """已爬出坑 → 本轮回撤 0.0（**不是 None**：在最高点是事实，不是缺数据）。"""
    st = current_drawdown(_series([1.0, 1.2, 0.9, 1.5]))
    assert st is not None
    assert st.current_drawdown == 0.0
    assert st.days == 0
    assert st.peak_date == D0 + timedelta(days=3)  # 高点就是最后一天


def test_current_drawdown_differs_from_max_drawdown():
    """核心判据：跌 30% 但已修复 → 最大回撤仍是 -30%，本轮回撤归 0。

    只给最大回撤会把「已修复」和「仍在水下」显示成同一个数——这正是本轮回撤存在的理由。
    """
    s = _series([1.0, 1.3, 0.91, 1.35])
    r = compute_risk_metrics(s)
    assert r.max_drawdown is not None and r.max_drawdown < -25
    assert r.current_drawdown == 0.0  # 1.35 > 1.3，最新一日即新高


def test_current_drawdown_when_still_underwater():
    """仍在坑里 → 本轮回撤是「最近一次新高 → 最新一日」，并给出熬了多少天。"""
    s = _series([1.0, 1.5, 1.2])
    st = current_drawdown(s)
    assert st is not None
    assert st.current_drawdown == pytest.approx(-20.0)
    assert st.peak_date == D0 + timedelta(days=1)
    assert st.days == 1  # 高点到最新一日 = 1 个自然日


def test_current_drawdown_uses_latest_peak_not_deepest():
    """本轮起点是**最近一次**新高，不是历史上最高的那次。"""
    # 1.0 → 1.5（新高）→ 1.2（回落）→ 1.6（又新高，本轮起点）→ 1.4
    st = current_drawdown(_series([1.0, 1.5, 1.2, 1.6, 1.4]))
    assert st is not None
    assert st.peak_date == D0 + timedelta(days=3)  # 1.6 那天才是「本轮」起点
    assert st.current_drawdown == pytest.approx(-12.5)  # 1.4/1.6 − 1


def test_current_drawdown_peak_is_running_max_not_global_max():
    """历史最高点之后又出现新高时，起点必须跟着推进 —— 否则跌幅会被算大。

    1.0 → 2.0（历史最高）→ 1.0 → 3.0（又创新高）→ 2.7：本轮从 3.0 算，跌 10%，不是从 2.0 算跌…%
    """
    st = current_drawdown(_series([1.0, 2.0, 1.0, 3.0, 2.7]))
    assert st is not None
    assert st.peak_date == D0 + timedelta(days=3)
    assert st.current_drawdown == pytest.approx(-10.0)


def test_current_drawdown_monotonic_up_is_zero():
    st = current_drawdown(_series([1.0, 1.1, 1.2]))
    assert st is not None and st.current_drawdown == 0.0


def test_current_drawdown_single_point_is_zero():
    st = current_drawdown(_series([1.0]))
    assert st is not None
    assert st.current_drawdown == 0.0
    assert st.days == 0


def test_current_drawdown_empty_is_none():
    assert current_drawdown([]) is None


def test_compute_risk_metrics_ships_drawdown_caliber():
    """口径元数据必须随值下发：光给一个 -20% 不知道「哪天掉下来的、熬了多久」。"""
    r = compute_risk_metrics(_series([1.0, 1.5, 1.2]))
    assert r.current_drawdown == pytest.approx(-20.0)
    assert r.drawdown_peak_date == D0 + timedelta(days=1)
    assert r.drawdown_days == 1
    assert r.max_drawdown_peak_date is not None
    assert r.max_drawdown_trough_date is not None
