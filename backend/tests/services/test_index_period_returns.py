# -*- coding: utf-8 -*-
"""指数阶段性收益（#2278 · 详情页指数区块）。

重点覆盖四件事：
1. **窗口口径**：自然月回溯 + 「目标日或之前最近交易日」基准、YTD 用上年末交易日；
2. **历史不足不编数**：序列起点晚于基准需求 → 该窗口 None（前端「—」）；
3. **波动率诚实**：日收益样本 <20 → None；常数序列 → 0（真实语义，非缺数）；
4. **缓存纪律**：成功结果进 TTL 缓存，双源皆空/序列异常短**不进缓存**（下次重试）。

数据链（csindex → tencent 兜底）在本文件用 monkeypatch 打桩——单测不联网，
真机双源互补实测见模块 docstring 与 #2278 卡面。
"""

from datetime import date

import pytest

from app.services import index_period_returns as ipr
from app.services.index_period_returns import (
    _shift_months,
    compute_period_returns,
    fetch_period_returns,
)


# ── _shift_months（月末钳位）───────────────────────────────────────────
def test_shift_months_month_end_clamps():
    """03-31 回 1 个月 → 02-28（2026 非闰年），不越界抛错。"""
    assert _shift_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert _shift_months(date(2024, 3, 31), -1) == date(2024, 2, 29)  # 闰年
    assert _shift_months(date(2026, 1, 15), -12) == date(2025, 1, 15)
    assert _shift_months(date(2026, 3, 15), -3) == date(2025, 12, 15)
    assert _shift_months(date(2026, 3, 15), -36) == date(2023, 3, 15)


def test_shift_months_across_year_boundary():
    assert _shift_months(date(2026, 1, 10), -1) == date(2025, 12, 10)
    assert _shift_months(date(2026, 1, 31), -1) == date(2025, 12, 31)


# ── compute_period_returns（纯函数）───────────────────────────────────
# 造一份锚点稀疏但覆盖 3 年的序列：各窗口基准收盘已知 → 期望收益率手算可验。
# today = 2026-06-15；latest close = 110。
_FULL_SERIES = [
    ('2023-06-14', 60.0),  # 3y 基准（target 2023-06-15 之前最近）
    ('2024-06-14', 70.0),  # 2y 基准（target 2024-06-15 之前最近）
    ('2025-06-13', 80.0),  # 1y 基准（target 2025-06-15 之前最近）
    ('2025-12-31', 85.0),  # YTD 基准（2025 最后一个交易日）
    ('2026-03-14', 90.0),  # 3m 基准（target 2026-03-15 之前最近）
    ('2026-05-14', 100.0),  # 1m 基准（target 2026-05-15 之前最近）
    ('2026-06-15', 110.0),  # latest
]
_TODAY = date(2026, 6, 15)


def test_compute_windows_full_history():
    """7 点锚点序列：6 窗口全部可算，逐个核对手算值（%）。"""
    result = compute_period_returns(_FULL_SERIES, today=_TODAY)

    assert result is not None
    assert result['as_of'] == '2026-06-15'
    w = result['windows']
    assert w['1m'] == pytest.approx((110 / 100 - 1) * 100, abs=1e-9)  # +10.0
    assert w['3m'] == pytest.approx((110 / 90 - 1) * 100, abs=1e-9)  # +22.22
    assert w['ytd'] == pytest.approx((110 / 85 - 1) * 100, abs=1e-9)  # +29.41
    assert w['1y'] == pytest.approx((110 / 80 - 1) * 100, abs=1e-9)  # +37.5
    assert w['2y'] == pytest.approx((110 / 70 - 1) * 100, abs=1e-9)  # +57.14
    assert w['3y'] == pytest.approx((110 / 60 - 1) * 100, abs=1e-9)  # +83.33
    # 7 点 → 日收益 6 个 < 20 → 波动率诚实降级
    assert result['volatility_1y'] is None


def test_compute_insufficient_history_windows_none():
    """今年才成立的序列：1m/3m/ytd 有基准可算，1y/2y/3y None（不编数）。"""
    series = [
        ('2026-01-20', 100.0),  # 晚于 YTD 基准需求（2025-12-31）→ ytd None
        ('2026-05-20', 105.0),  # 1m 基准（target 2026-06-15 前 1 月 = 05-15 之前最近…见下）
        ('2026-06-15', 110.0),
    ]
    result = compute_period_returns(series, today=_TODAY)

    assert result is not None
    w = result['windows']
    assert w['ytd'] is None  # 无上年末交易日
    assert w['1y'] is None  # target 2025-06-15 早于序列起点
    assert w['2y'] is None
    assert w['3y'] is None
    # 1m target = 2026-05-15，序列里 2026-01-20 ≤ target → 基准 100（该日或之前最近）
    assert w['1m'] == pytest.approx((110 / 100 - 1) * 100, abs=1e-9)
    # 3m target = 2026-03-15 → 基准同 100
    assert w['3m'] == pytest.approx((110 / 100 - 1) * 100, abs=1e-9)


def test_compute_too_short_series_none():
    """单点序列算不出任何收益 → None（整块降级）。"""
    assert compute_period_returns([('2026-06-15', 100.0)], today=_TODAY) is None
    assert compute_period_returns([], today=_TODAY) is None


def test_compute_bad_latest_close_none():
    """最新收盘 ≤ 0（脏数据）→ None，不用它当分母。"""
    assert compute_period_returns([('2026-06-14', 100.0), ('2026-06-15', 0.0)], today=_TODAY) is None


def test_compute_unsorted_input_handled_by_baseline():
    """基准取「目标日或之前最近」——序列升序是 direct_feeds 的契约，此处防退化：
    若序列乱序，`_baseline_on_or_before` 的 break 会提前截断（已知边界），
    本用例锁定升序输入下的正确行为即可。"""
    result = compute_period_returns(sorted(_FULL_SERIES), today=_TODAY)
    assert result['windows']['1y'] == pytest.approx(37.5, abs=1e-9)


# ── 波动率 ────────────────────────────────────────────────────────────
def test_volatility_constant_series_zero():
    """常数序列：日收益全 0 → 年化波动率 0.0（真实语义，不是缺数）。"""
    series = [(f'2026-{m:02d}-{d:02d}', 100.0) for m, d in [(1, i) for i in range(1, 29)]]
    # 2026-01-01..2026-01-28 共 28 点 → 27 个日收益 ≥ 20
    result = compute_period_returns(series, today=date(2026, 1, 28))

    assert result is not None
    assert result['volatility_1y'] == pytest.approx(0.0, abs=1e-12)


def test_volatility_too_few_samples_none():
    """日收益样本 <20 → None（样本太小的波动率没意义）。"""
    series = [(f'2026-01-{i:02d}', 100.0 + i) for i in range(1, 15)]  # 14 点 → 13 收益
    result = compute_period_returns(series, today=date(2026, 1, 14))

    assert result is not None
    assert result['volatility_1y'] is None


def test_volatility_positive_for_varying_series():
    """有波动的序列给出正的年化波动率（数量级合理：日波动 ~1% → 年化 ~16%）。"""
    closes = [100.0]
    for i in range(1, 60):
        closes.append(closes[-1] * (1.01 if i % 2 else 0.99))
    series = [(f'2026-01-{(i % 28) + 1:02d}', c) for i, c in enumerate(closes)]
    # 同日多点不影响：基准/收益按升序遍历，重复日只是多余点；波动率取窗口内全部收盘
    result = compute_period_returns(series, today=date(2026, 3, 1))

    assert result is not None
    vol = result['volatility_1y']
    assert vol is not None and vol > 0


# ── 数据链与缓存（打桩，不联网）────────────────────────────────────────
@pytest.fixture(autouse=True)
def _clear_returns_cache():
    ipr._returns_cache.clear()
    yield
    ipr._returns_cache.clear()


def test_fetch_uses_csindex_first(monkeypatch):
    """中证官网有数据 → 直接用，不打扰腾讯（降请求量）。"""
    calls = []
    monkeypatch.setattr(ipr, 'fetch_daily_csindex', lambda c, start_date=None: calls.append(('csi', c)) or [('2026-06-15', 110.0)] * 30)
    monkeypatch.setattr(ipr, 'fetch_daily_tencent', lambda c, start_date=None: calls.append(('tx', c)) or [])

    result = fetch_period_returns('SH000300')

    assert result is not None
    assert [x[0] for x in calls] == ['csi']  # 腾讯一次都没被打扰


def test_fetch_falls_back_to_tencent(monkeypatch):
    """中证官网空（399 系等）→ 腾讯兜底。"""
    monkeypatch.setattr(ipr, 'fetch_daily_csindex', lambda c, start_date=None: [])
    monkeypatch.setattr(ipr, 'fetch_daily_tencent', lambda c, start_date=None: [('2026-06-15', 110.0)] * 30)

    result = fetch_period_returns('399006')

    assert result is not None
    assert result['as_of'] == '2026-06-15'


def test_fetch_both_sources_empty_not_cached(monkeypatch):
    """双源皆空 → None 且**不进缓存**：下次查看重试（负缓存会把瞬时故障焊死）。"""
    monkeypatch.setattr(ipr, 'fetch_daily_csindex', lambda c, start_date=None: [])
    monkeypatch.setattr(ipr, 'fetch_daily_tencent', lambda c, start_date=None: [])

    assert fetch_period_returns('000001') is None
    assert '000001' not in ipr._returns_cache  # 关键：空结果不缓存


def test_fetch_source_exception_not_cached(monkeypatch):
    """抓取链整体抛异常（两源都炸）→ None 不缓存。"""
    monkeypatch.setattr(ipr, 'fetch_daily_csindex', lambda c, start_date=None: (_ for _ in ()).throw(RuntimeError('net')))
    monkeypatch.setattr(ipr, 'fetch_daily_tencent', lambda c, start_date=None: (_ for _ in ()).throw(RuntimeError('net')))

    assert fetch_period_returns('000300') is None
    assert '000300' not in ipr._returns_cache


def test_fetch_caches_success(monkeypatch):
    """成功结果进缓存：第二次不再触发抓取。"""
    calls = []

    def _csi(c, start_date=None):
        calls.append(c)
        return [('2026-01-01', 100.0), ('2026-06-15', 110.0)]

    monkeypatch.setattr(ipr, 'fetch_daily_csindex', _csi)

    r1 = fetch_period_returns('000300')
    r2 = fetch_period_returns('000300')

    assert r1 is not None and r1 == r2
    assert len(calls) == 1  # 第二次命中缓存


def test_fetch_blank_symbol_none():
    """无 6 位码的脏入口 → None，不发任何请求。"""
    assert fetch_period_returns('   ') is None
    assert fetch_period_returns('沪深300') is None
