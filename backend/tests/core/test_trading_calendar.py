# -*- coding: utf-8 -*-
"""A 股交易日历唯一出口单测（#1217）。

核心是锁定「开盘日 ≠ 法定工作日」这一差异：调休补班的周末打工人要上班，
但沪深交易所休市，必须判为**非开盘日**。
"""

from datetime import date

import pytest
from chinese_calendar import is_workday

from app.core.trading_calendar import is_trading_day, next_trading_day
from app.core.utils import get_confirm_date


class TestTradingDayVsWorkday:
    def test_adjusted_weekend_is_not_trading_day(self):
        """调休补班的周六：是法定工作日，但交易所休市 → 不是开盘日。"""
        # 前提：确认 2026-10-10 确实是调休工作日（否则本用例失去意义）
        assert is_workday(date(2026, 10, 10)) is True
        assert is_trading_day(date(2026, 10, 10)) is False

    def test_all_2026_adjusted_weekends_are_closed(self):
        """2026 年 6 个调休补班周末，一律判休市。"""
        adjusted = [
            date(2026, 1, 4),
            date(2026, 2, 14),
            date(2026, 2, 28),
            date(2026, 5, 9),
            date(2026, 9, 20),
            date(2026, 10, 10),
        ]
        for d in adjusted:
            assert d.weekday() >= 5, f'{d} 应为一个周末'
            assert is_workday(d) is True, f'{d} 应为调休工作日'
            assert is_trading_day(d) is False, f'{d} 交易所休市，不应判为开盘日'

    def test_normal_weekday_is_trading_day(self):
        assert is_trading_day(date(2026, 8, 31)) is True  # 周一

    def test_holiday_weekday_is_not_trading_day(self):
        """法定节假日落在工作日 → 休市。"""
        assert is_trading_day(date(2026, 10, 1)) is False

    def test_normal_weekend_is_not_trading_day(self):
        assert is_trading_day(date(2026, 8, 30)) is False  # 周日


class TestNextTradingDay:
    def test_skips_adjusted_weekend(self):
        """2026-10-09(周五) 之后：跳过调休周六 10-10 与周日 10-11，落到 10-12(周一)。"""
        nxt = next_trading_day(date(2026, 10, 9))
        assert nxt == date(2026, 10, 12)
        assert nxt.weekday() < 5
        assert is_trading_day(nxt) is True

    def test_delta_two_for_qdii(self):
        """QDII T+2：连续推进两个开盘日。"""
        start = date(2026, 8, 31)  # 周一
        first = next_trading_day(start, delta_days=1)
        second = next_trading_day(start, delta_days=2)
        assert is_trading_day(first) is True
        assert is_trading_day(second) is True
        assert first < second

    def test_invalid_delta_raises(self):
        with pytest.raises(ValueError):
            next_trading_day(date(2026, 8, 31), delta_days=0)


class TestConfirmDateUsesTradingDay:
    def test_after_15_shifts_to_trading_day_not_workday(self):
        """15:00 后下单顺延：不能落到调休补班的周末。"""
        confirm = get_confirm_date(date(2026, 10, 9), fund_type='domestic', is_after_15=True)
        assert confirm.weekday() < 5, f'确认日 {confirm} 不应是周末'
        assert confirm != date(2026, 10, 10), '不应把调休补班的周六当作确认日'
        assert is_trading_day(confirm) is True

    def test_qdii_confirm_is_two_trading_days(self):
        confirm = get_confirm_date(date(2026, 8, 31), fund_type='qdii', is_after_15=False)
        assert is_trading_day(confirm) is True
        assert confirm == next_trading_day(date(2026, 8, 31), delta_days=2)
