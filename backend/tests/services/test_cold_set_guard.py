# -*- coding: utf-8 -*-
"""#2123 P2 回归测试：冷集膨胀守卫的判定逻辑。

重点不是「能算对数字」，而是**判定逻辑本身**：
- 首次巡检（无基线）绝不判膨胀——否则一上线就误报；
- 超阈值才判膨胀，且阈值是「单次增量」而非绝对值；
- 阈值边界值不判（`>` 而非 `>=`）；
- stats 坏掉时按首次巡检处理，不能抛异常把巡检自己搞死。
"""

import json

from app.services.cold_set_guard import (
    DEFAULT_MAX_GROWTH,
    GUARD_JOB_NAME,
    GuardReport,
    TableSnapshot,
    compare_with_last,
)


def _report(total_stale):
    return GuardReport(cutoff='2025-10-13', total_stale=total_stale)


class TestCompareWithLast:
    def test_first_run_never_bloated(self):
        """无基线时不判定——没有上次数据就说不出「增长过快」。"""
        r = compare_with_last(_report(100), None)
        assert r.prev_stale is None
        assert r.growth is None
        assert r.bloated is False

    def test_empty_stats_treated_as_first_run(self):
        r = compare_with_last(_report(100), {})
        assert r.bloated is False
        assert r.growth is None

    def test_stats_without_total_stale_is_first_run(self):
        r = compare_with_last(_report(100), {'cutoff': 'x'})
        assert r.prev_stale is None
        assert r.bloated is False

    def test_growth_within_threshold_is_ok(self):
        last = {'total_stale': 100}
        r = compare_with_last(_report(100 + DEFAULT_MAX_GROWTH), last)
        assert r.growth == DEFAULT_MAX_GROWTH
        assert r.bloated is False, '等于阈值不算超（用 > 而非 >=）'

    def test_growth_over_threshold_is_bloated(self):
        last = {'total_stale': 100}
        r = compare_with_last(_report(100 + DEFAULT_MAX_GROWTH + 1), last)
        assert r.bloated is True

    def test_shrinkage_is_not_bloat(self):
        """清理让过期行下降同样不是膨胀（增量为负）。"""
        r = compare_with_last(_report(10), {'total_stale': 5000})
        assert r.growth == -4990
        assert r.bloated is False

    def test_custom_threshold_respected(self):
        r = compare_with_last(_report(600), {'total_stale': 100})
        r.max_growth = 100
        r = compare_with_last(r, {'total_stale': 100})
        assert r.bloated is True


class TestComparableBaseline:
    """判定必须用「按上次 cutoff 重算」的值（#3076）。

    cutoff = 今天 - 保留天数，它自己会随时间前移，把窗口推过老行。直接拿本次值比上次值，
    时间流逝就被算成增长：真库实测本次 93,375 行、同口径 14,762 行、上次 28 行——前者差
    9.3 万（其中 7.9 万纯漂移），后者差 1.47 万，才是真正写进来的老行。
    """

    def test_same_cutoff_value_overrides_current(self):
        r = _report(93375)
        r.max_growth = 21429
        out = compare_with_last(r, {'total_stale': 28, 'cutoff': '2025-10-13'}, comparable_stale=14762)
        assert out.growth == 14734
        assert out.bloated is False

    def test_displayed_and_recorded_values_untouched(self):
        """展示的仍是上次记录值，本次值不被改写——落库要用它当下一次的基线。"""
        r = _report(93375)
        out = compare_with_last(r, {'total_stale': 28, 'cutoff': '2025-10-13'}, comparable_stale=14762)
        assert out.prev_stale == 28
        assert out.total_stale == 93375

    def test_real_growth_still_detected(self):
        """同口径值超出阈值仍要判膨胀——防「改成同口径后永远绿」。"""
        r = _report(93375)
        r.max_growth = 5000
        out = compare_with_last(r, {'total_stale': 28}, comparable_stale=90000)
        assert out.growth == 89972
        assert out.bloated is True

    def test_default_path_is_old_behavior(self):
        """不传同口径值时退化为旧口径（既有调用与历史 stats 不受影响）。"""
        out = compare_with_last(_report(600), {'total_stale': 100})
        assert out.growth == 500
        assert out.bloated is False


class TestReportSerialization:
    def test_stats_round_trip(self):
        """stats 必须能 JSON 往返——它是唯一的时序载体。"""
        r = _report(28)
        r.tables.append(
            TableSnapshot(
                table='daily_worth',
                total_rows=662602,
                cold_rows=479832,
                stale_rows=18,
                cold_funds=3305,
            )
        )
        r.prev_stale = 20
        r.growth = 8
        r.bloated = False
        raw = json.dumps(r.to_stats(), ensure_ascii=False)
        back = json.loads(raw)
        assert back['total_stale'] == 28
        assert back['prev_stale'] == 20
        assert back['growth'] == 8
        assert back['bloated'] is False
        assert back['tables'][0]['table'] == 'daily_worth'
        assert back['tables'][0]['stale_rows'] == 18

    def test_first_run_stats_are_json_safe(self):
        """首轮字段为 None 也必须能序列化（不能炸在 json.dumps）。"""
        raw = json.dumps(_report(0).to_stats(), ensure_ascii=False)
        assert json.loads(raw)['prev_stale'] is None


class TestConstants:
    def test_guard_job_name_is_distinct(self):
        """守卫的 job 名不能与真实同步 job 撞名，否则污染增量基准。"""
        assert GUARD_JOB_NAME == 'cold_set_bloat_guard'
        assert GUARD_JOB_NAME not in {'fund_nav', 'price_history', 'fund_list'}

    def test_threshold_is_sane(self):
        """阈值必须显著大于正常按需取、显著小于误跑全量。"""
        assert 100 <= DEFAULT_MAX_GROWTH <= 100_000
