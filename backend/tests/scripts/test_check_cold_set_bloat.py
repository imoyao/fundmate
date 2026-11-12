# -*- coding: utf-8 -*-
"""冷集膨胀巡检 CLI 的比较口径（#3076）。

`scripts/check_cold_set_bloat.py` 有两处「一眼看不出错」的时间算术，都用真库数字钉住：

1. **同口径重算**要用「今天 - 上次 cutoff」当 keep_days（实测 395），不是两次 cutoff 之差
   （30）——写成 30 会算成「近 30 天」的过期行（实测 591,234），比真实值大一个数量级。
2. **阈值按间隔折算**：`--max-growth` 是 7 天的量，隔 30 天才跑一次不能拿周阈值去比，
   否则判定取决于跑得多勤，而不是灌得多快。
"""

import math
from datetime import date, timedelta

from scripts.check_cold_set_bloat import WEEKLY_BASIS_DAYS, growth_limit, resolve_baseline


class _StubGuard:
    """记录 measure 收到的 keep_days，并返回固定过期行。"""

    calls = []

    def measure(self, db, keep_days):
        _StubGuard.calls.append(keep_days)

        class _R:
            total_stale = 14762

        return _R()


class TestGrowthLimit:
    def test_weekly_basis_is_unchanged(self):
        """7 天口径保持原值：换口径不能顺手放宽既有阈值。"""
        assert WEEKLY_BASIS_DAYS == 7
        assert growth_limit(5000, 7) == 5000

    def test_short_interval_is_not_discounted(self):
        """间隔短于基准周期时不折算——否则日跑能拿到 714 行的阈值，反而不设防。"""
        assert growth_limit(5000, 1) == 5000
        assert growth_limit(5000, 3) == 5000

    def test_missing_days_falls_back_to_raw(self):
        """没有间隔信息（首次巡检 / 旧 stats）时用原阈值。"""
        assert growth_limit(5000, None) == 5000

    def test_month_interval_is_scaled(self):
        """30 天折算到 21,429 —— 真库 14,734 行因此在阈值内（旧口径会判膨胀）。"""
        assert growth_limit(5000, 30) == math.ceil(5000 * 30 / 7) == 21429


class TestResolveBaseline:
    def setup_method(self):
        _StubGuard.calls = []

    def test_no_last_stats(self):
        assert resolve_baseline(_StubGuard(), None, None, '2025-11-12') == (None, None)
        assert _StubGuard.calls == []

    def test_last_without_cutoff(self):
        """旧记录只有 total_stale 没有 cutoff ⇒ 无法同口径，返回 None 走本次值。"""
        assert resolve_baseline(_StubGuard(), None, {'total_stale': 28}, '2025-11-12') == (None, None)
        assert _StubGuard.calls == []

    def test_broken_cutoff_is_not_fatal(self):
        assert resolve_baseline(_StubGuard(), None, {'cutoff': 'x', 'total_stale': 28}, '2025-11-12') == (None, None)

    def test_same_day_rerun_has_no_comparable(self):
        """同一天重跑：间隔 0，没有可比增量，按本次值判定。"""
        today_cutoff = '2025-11-12'
        val, days = resolve_baseline(_StubGuard(), None, {'cutoff': today_cutoff}, today_cutoff)
        assert (val, days) == (None, 0)
        assert _StubGuard.calls == []

    def test_recompute_uses_today_minus_prev_cutoff(self):
        """**核心**：重现旧窗口的 keep_days = 今天 - 上次 cutoff（395），间隔另有 30 天。"""
        today_cutoff = (date.today() - timedelta(days=365)).isoformat()
        prev_cutoff = (date.today() - timedelta(days=395)).isoformat()
        val, days = resolve_baseline(_StubGuard(), 'db', {'cutoff': prev_cutoff, 'total_stale': 28}, today_cutoff)
        assert val == 14762
        assert days == 30
        assert _StubGuard.calls == [395], '重算必须回到 395 天窗口，不是 30 天'
