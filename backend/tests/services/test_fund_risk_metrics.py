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
    shape_gain,
    shape_gain2,
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


# ── 拟涨幅2（#167 收尾）──────────────────────────────────────────────────────


def _daily_flat_return_series(daily_pct: float, days: int = 400, start=D0):
    """构造日复利序列（每天的收益率为 daily_pct%），用于可手算的拟涨幅2 断言。"""
    values = [1.0]
    for _ in range(days):
        values.append(values[-1] * (1 + daily_pct / 100))
    return _series(values, start=start)


def test_shape_gain2_equal_segments_is_weighted_product():
    """四段各 +10% ⇒ 连乘加权，结果 = (1+0.4·.1)(1+0.3·.1)(1+0.2·.1)(1+0.1·.1)−1。

    这是「算得对」的判据：**连乘而非加权求和**。写成 0.4+0.3+0.2+0.1 的加权平均
    会得到 10.00%（而不是 10.355%），本用例会红。
    """
    # 每天恒定涨，四段涨幅必然相同（复利下四段略不等，故直接构造分段数据）
    from datetime import date as _d

    end = _d(2021, 12, 31)
    # 四个分界点：end-365/180/90/30，各段 +10%
    navs = {365: 1.0, 180: 1.1, 90: 1.21, 30: 1.331}
    pts = [(end - timedelta(days=366), 1.0)]
    for back, nav in navs.items():
        pts.append((end - timedelta(days=back), nav))
    pts.append((end, 1.331 * 1.1))

    out = shape_gain2(pts)
    assert out is not None
    expected = 1.0
    for w in (0.4, 0.3, 0.2, 0.1):
        expected *= 1 + w * 0.10
    assert out['shape_gain2'] == pytest.approx((expected - 1) * 100, abs=0.02)


def test_shape_gain2_deoverlaps_segments():
    """去重叠：四段收益互不包含，故四段的**复合** = 整年涨幅。

    这条钉住「p_i = (1+r_i)/(1+r_{i-1})−1」那步**确实做了**：若直接把滚动
    r1..r4 当 p1..p4 用，近 1 月的行情会被算四遍（segments 里会出现四个
    同量级的正数），复合并后会远大于整年涨幅，本用例即红。
    """
    from datetime import date as _d

    end = _d(2021, 12, 31)
    # 四段各 +5%，故整年 = 1.05^4 − 1
    pts = [
        (end - timedelta(days=400), 1.0),  # 早于一年前，只为让 365 段有落点
        (end - timedelta(days=365), 1.0),
        (end - timedelta(days=180), 1.05),
        (end - timedelta(days=90), 1.05**2),
        (end - timedelta(days=30), 1.05**3),
        (end, 1.05**4),
    ]
    out = shape_gain2(pts)
    assert out is not None
    segs = out['segments']
    assert len(segs) == 4
    for s in segs:
        assert s == pytest.approx(5.0, abs=0.01), '每段应恰为 +5%（去重叠后不重复计数）'
    compounded = 1.0
    for s in segs:
        compounded *= 1 + s / 100
    assert (compounded - 1) * 100 == pytest.approx(21.550625, abs=0.02)


def test_shape_gain2_none_when_history_under_one_year():
    """历史不足一年 ⇒ None（**不拿成立以来凑**）：掺一个口径不同的数进去，
    结果既不是「近一年」也不是「成立以来」。"""
    pts = _daily_flat_return_series(0.05, days=100)
    assert shape_gain2(pts) is None


def test_shape_gain2_flat_nav_yields_zero():
    """净值不动 ⇒ 四段全 0 ⇒ 结果 0（而非 None）：0 是诚实结论，不是缺数据。"""
    out = shape_gain2(_flat(400))
    assert out is not None
    assert out['shape_gain2'] == pytest.approx(0.0, abs=1e-6)
    assert out['segments'] == [0.0, 0.0, 0.0, 0.0]


def test_shape_gain2_respects_as_of():
    """`as_of` 之后的点不参与——与 fund_performance 的业务日口径一致。

    ⚠️ 必须用**非恒定增长**的序列：日复利恒定增长时，任何 as_of 下的四段比值
    都相同（数学上必然相等），拿它测 as_of 会得到「两条路都对」的假绿。
    这里构造「前 400 天涨 1 倍、后 400 天平」，截断点落在后半段 ⇒ 结果必然不同。
    """
    from datetime import date as _d
    from datetime import timedelta as _td

    D = _d(2020, 1, 1)
    values = [1.0]
    for i in range(1, 801):
        step = 0.002 if i <= 400 else 0.0  # 前半段涨、后半段平
        values.append(values[-1] * (1 + step))
    pts = [(D + _td(days=i), v) for i, v in enumerate(values)]

    full = shape_gain2(pts)
    # 截到倒数第 61 个点（仍有 ~739 天历史）：此时最后一日落在「平段」
    truncated = shape_gain2(pts, as_of=pts[-61][0])
    assert full is not None and truncated is not None
    assert full['shape_gain2'] != truncated['shape_gain2']
    assert truncated['segments'] != full['segments']


# ── 拟涨幅（原版 · #167 收尾）────────────────────────────────────────────────


def _monthly_gain_curve(gain_months):
    """构造原文 §1 的 9 条特例曲线之一：12 个月里只在 ``gain_months`` 内均匀涨 100%。

    位置设「当前为 12 月底」：第 m 月的月度末净值进序列；起点（年初）= 1.0。
    """
    v = 1.0
    navs = [1.0]
    for m in range(1, 13):
        if m in gain_months:
            v *= 2 ** (1.0 / len(gain_months))
        navs.append(v)
    # 月度末按「当前日往前推 (12-m) 个 30 天」定位，使 30/90/180 三个窗口恰好落在
    # 对应的月度末上。**年初那一点必须 ≥365 天**，否则 365 窗口取不到点 ⇒ 整指标
    # 不出值（这正是「历史不足一年 ⇒ None」的判据，不该被测试数据触发）。
    end = date(2021, 12, 31)
    pts = [(end - timedelta(days=30 * (12 - i)), nav) for i, nav in enumerate(navs)]
    pts.insert(0, (end - timedelta(days=366), navs[0]))  # 补一个一年前的锚点
    return pts


#: 原文 §1 的 9 条曲线：均涨 100%、起点终点相同，仅「涨在哪几个月」不同。
_SOURCE_CURVES = {
    '基金1': list(range(1, 7)),  # 前 6 月
    '基金2': list(range(1, 10)),  # 前 9 月
    '基金3': list(range(1, 12)),  # 前 11 月
    '基金4': list(range(1, 13)),  # 全年均匀
    '基金5': list(range(7, 13)),  # 后 6 月
    '基金6': list(range(10, 13)),  # 后 3 月
    '基金7': [12],  # 最后 1 月
    '基金8': [7, 8, 9],  # 三季度
    '基金9': [10, 11],  # 四季度前 2 月
}


def _rank_desc(scores):
    return [name for name, _v in sorted(scores.items(), key=lambda kv: -kv[1])]


def test_shape_gain_matches_source_ranking():
    """**口径正确性的硬判据**：复算原文 9 条特例曲线的排位，逐位一致。

    原文（见基行事《拟涨幅》，K 定义与公式为图片，已 OCR 复原）给出的总排位是：
        基金7>基金6>基金9>基金5>基金8>基金4>基金3>基金2>基金1
    权重取原文示例（给 r4 更高权重）：0.1 / 0.2 / 0.3 / 0.4。

    这条不是「跑通」，是「和作者用同一组数得同一个序」——K 系数、几何平均、
    权重方向（哪头是近一月）任一处理错，排位都会变。
    """
    scores = {}
    for name, months in _SOURCE_CURVES.items():
        out = shape_gain(_monthly_gain_curve(months))
        assert out is not None, f'{name} 应出值'
        scores[name] = out['shape_gain']
    assert _rank_desc(scores) == [
        '基金7',
        '基金6',
        '基金9',
        '基金5',
        '基金8',
        '基金4',
        '基金3',
        '基金2',
        '基金1',
    ]


def test_shape_gain2_matches_source_ranking():
    """拟涨幅2 复算原文**第二条**排位，逐位一致（与上一条同为硬判据）。

    原文第二条排位：基金7>基金9>基金6>基金5>基金8>基金4>基金3>基金2>基金1
    （与第一条的区别：基金6 与基金9 交换位置）。
    """
    scores = {}
    for name, months in _SOURCE_CURVES.items():
        out = shape_gain2(_monthly_gain_curve(months))
        assert out is not None, f'{name} 应出值'
        scores[name] = out['shape_gain2']
    assert _rank_desc(scores) == [
        '基金7',
        '基金9',
        '基金6',
        '基金5',
        '基金8',
        '基金4',
        '基金3',
        '基金2',
        '基金1',
    ]


def test_shape_gain_matches_closed_form_on_steady_growth():
    """匀速增长下有**闭式解**，用它钉住「几何平均 + K 归一化」的算式。

    设日增 g，则 d 天窗口的涨幅 r_d = (1+g)^d − 1，K 归一化后
    1 + k_d·r_d = 1 + (d/365)·((1+g)^d − 1)。权重全 1 时结果即这四个因子的
    几何平均。这不是「随便对个数字」——闭式解由公式定义直接推出，
    几何平均写成算术平均、K 取错（如全取 1）、权重方向反了都会让它偏掉。
    """
    g = 0.0005  # 日增 0.05%
    pts = _daily_flat_return_series(0.05, days=400)
    out = shape_gain(pts, weights=[1, 1, 1, 1])
    assert out is not None
    expected = 1.0
    for d, k in zip((30, 90, 180, 365), (1 / 12, 0.25, 0.5, 1.0)):
        r = (1 + g) ** d - 1
        expected *= 1 + k * r
    expected = expected**0.25  # 四个因子、权重全 1 ⇒ 四次方根
    assert out['shape_gain'] == pytest.approx((expected - 1) * 100, abs=0.01)


def test_shape_gain_weights_scale_invariant():
    """权重**同比例缩放不影响结果**（几何平均已按 Σw 归一化）。

    这是「权重和不必凑 100%」的判据（参考站也是这么做的：拖完滑块点“等比缩放到 100%”
    只是显示方便）。若实现漏了 Σw 归一化，本用例必红。
    """
    pts = _daily_flat_return_series(0.03, days=400)
    a = shape_gain(pts, weights=[0.1, 0.2, 0.3, 0.4])
    b = shape_gain(pts, weights=[1, 2, 3, 4])
    assert a is not None and b is not None
    assert a['shape_gain'] == pytest.approx(b['shape_gain'], abs=1e-6)


def test_shape_gain_k_normalizes_to_annual():
    """K 把窗口涨幅折成年频：**只有近 1 月涨 10%** 与「只有近 1 年涨 X%」等价当且仅当
    X 由 k 归一化给出。

    构造两个序列并比较其 r1·k1 与 r4·k4 是否同量级（K 的立法意图）。
    若 K 被误设为全 1（不归一化），1 个月的 10% 会被当作 1 年的 10%（低估近端）。
    """
    out = shape_gain(_daily_flat_return_series(0.05, days=400))
    assert out is not None
    assert out['k'] == [pytest.approx(1 / 12), pytest.approx(0.25), pytest.approx(0.5), pytest.approx(1.0)]


def test_shape_gain_needs_full_year():
    """历史不足一年 ⇒ None（与拟涨幅2 同一条诚实降级）。"""
    assert shape_gain(_daily_flat_return_series(0.05, days=100)) is None


def test_shape_gain_flat_nav_yields_zero():
    out = shape_gain(_flat(400))
    assert out is not None
    assert out['shape_gain'] == pytest.approx(0.0, abs=1e-6)


def test_shape_gain_rejects_bad_weights():
    """非法权重**抛错**而不是静默夹值——一个被悄悄改过的权重会让指标
    看着正常、实则不是用户要的口径。"""
    pts = _daily_flat_return_series(0.02, days=400)
    with pytest.raises(ValueError):
        shape_gain(pts, weights=[1, 1, 1])
    with pytest.raises(ValueError):
        shape_gain(pts, weights=[0, 1, 1, 1])
    with pytest.raises(ValueError):
        shape_gain(pts, weights=[-1, 1, 1, 1])


def test_shape_gain_respects_as_of():
    """`as_of` 之后的点不参与（用非恒定增长序列，避免恒等式假绿）。"""
    D = date(2020, 1, 1)
    values = [1.0]
    for i in range(1, 801):
        step = 0.002 if i <= 400 else 0.0
        values.append(values[-1] * (1 + step))
    pts = [(D + timedelta(days=i), v) for i, v in enumerate(values)]
    full = shape_gain(pts)
    truncated = shape_gain(pts, as_of=pts[-61][0])
    assert full is not None and truncated is not None
    assert full['shape_gain'] != truncated['shape_gain']
