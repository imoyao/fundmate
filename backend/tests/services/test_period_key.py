# -*- coding: utf-8 -*-
"""定期复盘报告周期键纯函数单测（#875）。

钉死以下口径（owner 逐条拍板，见方案文档 §0）：
- week = 严格 ISO 周序（跨年周归 ISO 年）；
- quarter = 自然季度（Q1~Q4），键 `YYYY-Qn` 与月键 `YYYY-MM` 同长但靠正则区分；
- 翻页跨年/跨季正确。
"""

import datetime as dt

import pytest

from app.services.analytics.period_key import (
    PERIOD_KINDS,
    next_period_key,
    period_bounds,
    period_key_of,
    prev_period_key,
    resolve_last_trading_day,
)


class TestPeriodKeyOf:
    def test_week_iso_order(self):
        # 周一与周日同属一个 ISO 周
        assert period_key_of(dt.date(2026, 11, 23), 'week') == '2026-W48'  # 周一
        assert period_key_of(dt.date(2026, 11, 29), 'week') == '2026-W48'  # 周日

    def test_week_cross_year_belongs_to_iso_year(self):
        # 2026-12-28（周一）~ 2027-01-03（周日）是跨年周，ISO 归 2026-W53
        assert period_key_of(dt.date(2026, 12, 31), 'week') == '2026-W53'
        assert period_key_of(dt.date(2027, 1, 1), 'week') == '2026-W53'  # 仍属上一 ISO 年
        assert period_key_of(dt.date(2027, 1, 4), 'week') == '2027-W01'  # 周一才翻到新 ISO 年

    def test_month_quarter_year(self):
        d = dt.date(2026, 7, 15)
        assert period_key_of(d, 'month') == '2026-07'
        assert period_key_of(d, 'quarter') == '2026-Q3'
        assert period_key_of(d, 'year') == '2026'

    def test_invalid_kind_raises(self):
        with pytest.raises(ValueError):
            period_key_of(dt.date(2026, 1, 1), 'hour')


class TestPeriodBounds:
    def test_week_bounds(self):
        assert period_bounds('2026-W48', 'week') == (dt.date(2026, 11, 23), dt.date(2026, 11, 29))

    def test_cross_year_week_bounds(self):
        assert period_bounds('2026-W53', 'week') == (dt.date(2026, 12, 28), dt.date(2027, 1, 3))

    def test_week01_monday_in_previous_year(self):
        # ISO 2026-W01 的周一落在 2025-12-29
        assert period_bounds('2026-W01', 'week') == (dt.date(2025, 12, 29), dt.date(2026, 1, 4))

    def test_month_bounds_leap_and_common(self):
        assert period_bounds('2026-02', 'month') == (dt.date(2026, 2, 1), dt.date(2026, 2, 28))  # 平年
        assert period_bounds('2028-02', 'month') == (dt.date(2028, 2, 1), dt.date(2028, 2, 29))  # 闰年

    def test_quarter_bounds(self):
        assert period_bounds('2026-Q1', 'quarter') == (dt.date(2026, 1, 1), dt.date(2026, 3, 31))
        assert period_bounds('2026-Q4', 'quarter') == (dt.date(2026, 10, 1), dt.date(2026, 12, 31))

    def test_year_bounds(self):
        assert period_bounds('2026', 'year') == (dt.date(2026, 1, 1), dt.date(2026, 12, 31))

    def test_invalid_key_raises(self):
        with pytest.raises(ValueError):
            period_bounds('2026-13', 'month')
        with pytest.raises(ValueError):
            period_bounds('2026-Q5', 'quarter')
        with pytest.raises(ValueError):
            period_bounds('abc-Wxx', 'week')


class TestPagination:
    def test_next_prev_week_cross_year(self):
        assert next_period_key('2026-W52', 'week') == '2026-W53'
        assert next_period_key('2026-W53', 'week') == '2027-W01'  # 跨年
        assert prev_period_key('2027-W01', 'week') == '2026-W53'

    def test_next_prev_quarter_cross_year(self):
        assert next_period_key('2026-Q4', 'quarter') == '2027-Q1'
        assert prev_period_key('2026-Q1', 'quarter') == '2025-Q4'

    def test_next_prev_month_cross_year(self):
        assert next_period_key('2026-12', 'month') == '2027-01'
        assert prev_period_key('2026-01', 'month') == '2025-12'


class TestResolveLastTradingDay:
    def test_weekend_backs_off_to_friday(self):
        # 2026-11-29 是周日，最后交易日 = 11-27（周五）
        weekdays_only = lambda d: d.weekday() < 5  # noqa: E731
        assert resolve_last_trading_day(dt.date(2026, 11, 29), weekdays_only) == dt.date(2026, 11, 27)

    def test_trading_day_itself(self):
        weekdays_only = lambda d: d.weekday() < 5  # noqa: E731
        assert resolve_last_trading_day(dt.date(2026, 11, 27), weekdays_only) == dt.date(2026, 11, 27)

    def test_long_holiday_returns_none(self):
        # 连续 8 天都非交易日 → 回退超过 max_lookback=7 → None
        always_rest = lambda d: False  # noqa: E731
        assert resolve_last_trading_day(dt.date(2026, 11, 29), always_rest) is None


class TestPeriodKinds:
    def test_kinds_set(self):
        assert set(PERIOD_KINDS) == {'week', 'month', 'quarter', 'year'}
