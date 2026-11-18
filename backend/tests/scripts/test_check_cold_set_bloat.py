# -*- coding: utf-8 -*-
"""冷集膨胀巡检的比较口径（#3076）。

两处「一眼看不出错」的时间算术，都用真库数字钉住：

1. **同口径重算**要用「今天 - 上次 cutoff」当 keep_days（实测 395），不是两次 cutoff 之差
   （30）——写成 30 会算成「近 30 天」的过期行（实测 591,234），比真实值大一个数量级。
2. **阈值按间隔折算**：`max_growth` 是 7 天的量，隔 30 天才跑一次不能拿周阈值去比，
   否则判定取决于跑得多勤，而不是灌得多快。

#3078 起这两个函数下沉到 `app.services.cold_set_check`（CLI 与调度器共用一份流程），
故 import 路径改这里；`scripts.check_cold_set_bloat` 仍再导出同名符号，按 CLI 路径
import 的旧写法不会静默失效。
"""

import math
from datetime import date, timedelta
from types import SimpleNamespace

from app.services import cold_set_guard

# 按 CLI 入口 import：这是下游实际会用的路径，走它才能守住「再导出」没被删。
from scripts.check_cold_set_bloat import WEEKLY_BASIS_DAYS, growth_limit, resolve_baseline


class _MeasureRecorder:
    """记录 measure 收到的 keep_days，并返回固定过期行。"""

    def __init__(self, total_stale=14762):
        self.calls = []
        self.total_stale = total_stale

    def __call__(self, db, keep_days):
        self.calls.append(keep_days)
        return SimpleNamespace(total_stale=self.total_stale)


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
    def _patch(self, monkeypatch, recorder):
        monkeypatch.setattr(cold_set_guard, 'measure', recorder)
        return recorder

    def test_no_last_stats(self, monkeypatch):
        rec = self._patch(monkeypatch, _MeasureRecorder())
        assert resolve_baseline(None, None, '2025-11-12') == (None, None)
        assert rec.calls == []

    def test_last_without_cutoff(self, monkeypatch):
        """旧记录只有 total_stale 没有 cutoff ⇒ 无法同口径，返回 None 走本次值。"""
        rec = self._patch(monkeypatch, _MeasureRecorder())
        assert resolve_baseline(None, {'total_stale': 28}, '2025-11-12') == (None, None)
        assert rec.calls == []

    def test_broken_cutoff_is_not_fatal(self, monkeypatch):
        rec = self._patch(monkeypatch, _MeasureRecorder())
        assert resolve_baseline(None, {'cutoff': 'x', 'total_stale': 28}, '2025-11-12') == (None, None)
        assert rec.calls == []

    def test_same_day_rerun_has_no_comparable(self, monkeypatch):
        """同一天重跑：间隔 0，没有可比增量，按本次值判定。"""
        today_cutoff = '2025-11-12'
        rec = self._patch(monkeypatch, _MeasureRecorder())
        val, days = resolve_baseline(None, {'cutoff': today_cutoff}, today_cutoff)
        assert (val, days) == (None, 0)
        assert rec.calls == []

    def test_recompute_uses_today_minus_prev_cutoff(self, monkeypatch):
        """**核心**：重现旧窗口的 keep_days = 今天 - 上次 cutoff（395），间隔另有 30 天。"""
        rec = self._patch(monkeypatch, _MeasureRecorder())
        today_cutoff = (date.today() - timedelta(days=365)).isoformat()
        prev_cutoff = (date.today() - timedelta(days=395)).isoformat()
        val, days = resolve_baseline(None, {'cutoff': prev_cutoff, 'total_stale': 28}, today_cutoff)
        assert val == 14762
        assert days == 30
        assert rec.calls == [395], '重算必须回到 395 天窗口，不是 30 天'
