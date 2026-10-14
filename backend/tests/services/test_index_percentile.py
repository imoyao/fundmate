# -*- coding: utf-8 -*-
"""测试指数估值分位计算（#1407 拍板：方向参数硬约束 + 并列口径，#2028 消费）。"""

from datetime import timedelta

import pytest

from app.services.index_percentile import (
    MIN_BASELINE_POINTS,
    PERCENTILE_WINDOW_DAYS,
    compute_percentile,
    window_cutoff,
)


class TestComputePercentile:
    def test_asc_direction(self):
        """PE 正向：当前值越大、分位越高（越高越贵）。"""
        series = [10.0, 11.0, 12.0, 13.0, 14.0]
        # 当前 13（在序列内）：3 严格小于 + 1 并列×0.5 → 3.5/5 = 70%
        assert compute_percentile(13.0, series, direction='asc') == 70.0
        # 当前 10：0 严格小于 + 1 并列×0.5 → 10%
        assert compute_percentile(10.0, series, direction='asc') == 10.0
        # 当前 9（低于全序列）：0 严格小于 → 0%（最便宜）
        assert compute_percentile(9.0, series, direction='asc') == 0.0
        # 当前 15（高于全序列）：5 严格小于 → 100%（最贵）
        assert compute_percentile(15.0, series, direction='asc') == 100.0

    def test_desc_direction(self):
        """股息率反向：当前值越大、分位越低（越高越便宜）。"""
        series = [2.0, 3.0, 4.0, 5.0, 6.0]
        # 当前 5（在序列内）：1 严格大于 + 1 并列×0.5 → 1.5/5 = 30%（高股息率 = 便宜 = 低分位）
        assert compute_percentile(5.0, series, direction='desc') == 30.0
        # 当前 2（在序列内）：4 严格大于 + 1 并列×0.5 → 4.5/5 = 90%
        assert compute_percentile(2.0, series, direction='desc') == 90.0

    def test_direction_required_no_default(self):
        """方向必须显式传入——漏传是 TypeError 而非静默按 asc 处理。"""
        with pytest.raises(TypeError):
            compute_percentile(13.0, [10.0, 11.0, 12.0])  # type: ignore[call-arg]

    def test_invalid_direction_rejected(self):
        with pytest.raises(ValueError):
            compute_percentile(13.0, [10.0, 11.0], direction='higher')

    def test_ties_counted_half(self):
        """并列记半个，避免死序列给出 0/100 极端误导。"""
        series = [10.0, 10.0, 10.0]
        # current=10：0 严格小于 + 3 并列 × 0.5 → 1.5/3 = 50%
        assert compute_percentile(10.0, series, direction='asc') == 50.0

    def test_empty_series_returns_none(self):
        assert compute_percentile(10.0, [], direction='asc') is None

    def test_none_values_filtered(self):
        series = [10.0, None, 12.0]  # type: ignore[list-item]
        # 过滤后剩 2 个点，当前 12（在序列内）：1 严格小于 + 1 并列×0.5 → 75%
        assert compute_percentile(12.0, series, direction='asc') == 75.0

    def test_regression_high_dividend_not_overvalued(self):
        """#1436 同类事故锁定：高股息率若按 asc 算会得出「高估」错误结论。

        场景：股息率 6% 处于历史高位——真实语义是「便宜」，desc 分位应接近 0；
        若误用 asc 会得到接近 100 的「高估」。本测试钉死两个方向的差异。
        """
        series = [1.0, 2.0, 3.0, 4.0, 5.0]
        desc = compute_percentile(6.0, series, direction='desc')
        asc_wrong = compute_percentile(6.0, series, direction='asc')
        assert desc == 0.0  # 高股息率 → 便宜 → 低分位
        assert asc_wrong == 100.0  # 若方向用错，会得到完全相反的「高估」


class TestWindow:
    def test_window_days_is_five_years(self):
        assert PERCENTILE_WINDOW_DAYS == 5 * 366

    def test_cutoff(self):
        from datetime import date

        # 5*366 = 1830 天（含闰年修正，比 5*365 多一个基线点的容差）
        assert window_cutoff(date(2026, 10, 11)) == date(2026, 10, 11) - timedelta(days=5 * 366)

    def test_min_points_reasonable(self):
        # 月频基线 1 年 ≈ 12 点；低于一年不给分位
        assert MIN_BASELINE_POINTS == 12
