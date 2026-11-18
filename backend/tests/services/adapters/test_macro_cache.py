# -*- coding: utf-8 -*-
"""宏观序列复用缓冲层的判据（成本红线，不是性能优化）。

这里的每条用例都对应一次真实成本：缓存判错（该命中没命中）= 白扣一次积分；
缓存判宽（不该命中却命中）= 把旧口径的数讲给用户。所以两边都要钉。
"""

import time
from datetime import date, timedelta

import pytest

from app.services.adapters import macro_cache

_DAY = 86400


def _row(name='中国:CPI:当月同比', freq='月', points=None):
    return {
        'name': name,
        'freq': freq,
        'unit': '%',
        'points': points if points is not None else {date(2026, 9, 30): 0.4, date(2026, 10, 31): 0.7},
    }


@pytest.fixture(autouse=True)
def _isolated_dir(monkeypatch, tmp_path):
    """每个用例独立缓存目录：缓存是跨调用状态，共享目录会让用例互相喂数据。"""
    monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path))


# ── 频率 → TTL ───────────────────────────────────────────────────────────
def test_ttl_follows_release_cadence_not_wall_clock():
    """月频给 3 天、季频给 7 天：宏观有固定发布日历，按小时重取纯属烧积分。"""
    assert macro_cache.ttl_seconds('月') == 3 * _DAY
    assert macro_cache.ttl_seconds('季') == 7 * _DAY
    assert macro_cache.ttl_seconds('日') == 6 * 3600
    assert macro_cache.ttl_seconds('年') == 30 * _DAY
    assert macro_cache.ttl_seconds(None) == _DAY, '认不出频率时按最保守的 1 天'


def test_freq_class_accepts_cn_and_abbr():
    """上游 ``freq`` 中英文都出现过，两种都要认（否则一律落到 unknown）。"""
    for raw, want in (
        ('月', 'month'),
        ('M', 'month'),
        ('季', 'quarter'),
        ('Q', 'quarter'),
        ('日', 'day'),
        ('', 'unknown'),
    ):
        assert macro_cache.freq_class(raw) == want


def test_period_days_matches_window_estimate():
    assert macro_cache.period_days('月') == 31
    assert macro_cache.period_days('季') == 92
    assert macro_cache.period_days('???') == 92, '认不出按季，窗口偏大只多取不会取空'


# ── 频率反推（零调用） ────────────────────────────────────────────────────
def test_infer_freq_from_point_gaps():
    """不额外调接口就能判断更新频率：点间隔中位数就是答案。"""
    month = {date(2026, m, 28): 1.0 for m in (1, 2, 3, 4)}
    quarter = {d: 1.0 for d in (date(2026, 3, 31), date(2026, 6, 30), date(2026, 9, 30))}
    daily = {date(2026, 11, d): 1.0 for d in range(1, 8)}
    assert macro_cache.infer_freq(month) == '月'
    assert macro_cache.infer_freq(quarter) == '季'
    assert macro_cache.infer_freq(daily) == '日'
    assert macro_cache.infer_freq({date(2026, 1, 1): 1.0}) is None, '单点无法判断'


def test_infer_uses_median_not_mean():
    """停更造成的超长间隔不能把结论带偏：一两个洞不该把月频判成年频。"""
    points = {date(2026, m, 28): 1.0 for m in (1, 2, 3, 4, 5)}
    points[date(2031, 12, 31)] = 1.0  # 一个 5 年的洞
    assert macro_cache.infer_freq(points) == '月'


# ── 读写与裁剪 ───────────────────────────────────────────────────────────
def test_write_then_read_clips_to_window():
    """缓存存全量窗口，返回按请求窗口裁——同一份缓存服务多个问法。"""
    macro_cache.write_series('CPI', [_row()], date(2026, 1, 1), date(2026, 11, 16))

    got = macro_cache.read_series('CPI', date(2026, 10, 1), date(2026, 11, 16))

    assert got is not None
    assert got[0]['points'] == {date(2026, 10, 31): 0.7}, '窗口外的点必须裁掉'
    assert got[0]['cache'] == 'hit'
    assert got[0]['fetched_at'], '必须带采集时间，叙事要如实交代'


def test_read_misses_when_window_not_covered():
    """请求窗口起点早于缓存 → 不能拿半截数据充数。"""
    macro_cache.write_series('CPI', [_row()], date(2026, 6, 1), date(2026, 11, 16))

    assert macro_cache.read_series('CPI', date(2026, 1, 1), date(2026, 11, 16)) is None


def test_read_misses_when_entry_is_stale():
    """过期后正常读必须 miss（否则永远不更新）；但 stale 读要还能拿到。"""
    macro_cache.write_series('CPI', [_row()], date(2026, 1, 1), date(2026, 11, 16))
    later = time.time() + 4 * _DAY  # 月频 TTL 3 天，越过即过期

    assert macro_cache.read_series('CPI', date(2026, 1, 1), date(2026, 11, 16), now=later) is None
    stale = macro_cache.read_series_stale('CPI', date(2026, 1, 1), date(2026, 11, 16))
    assert stale is not None and stale[0]['cache'] == 'stale'


def test_cache_key_is_exact_name_not_normalized():
    """两个口径只差「现价 / 不变价」，归一化会把它们压成同一个键——那是串数据。"""
    macro_cache.write_series(
        '中国:GDP:现价:当季值',
        [_row('中国:GDP:现价:当季值', points={date(2026, 9, 30): 334193.0})],
        date(2026, 1, 1),
        date(2026, 11, 16),
    )

    assert macro_cache.read_series('中国:GDP:不变价:当季同比', date(2026, 1, 1), date(2026, 11, 16)) is None


def test_empty_rows_are_not_cached():
    """「没取到数」不能进缓存：否则一次上游抖动会把该指标锁到 TTL 结束。"""
    macro_cache.write_series('CPI', [], date(2026, 1, 1), date(2026, 11, 16))

    assert macro_cache.read_series('CPI', date(2026, 1, 1), date(2026, 11, 16)) is None


def test_write_strips_source_tags():
    """写缓存时要剥掉来源标记，否则命中一次之后 ``cache='hit'`` 会被当成原始数据落盘。"""
    macro_cache.write_series('CPI', [dict(_row(), cache='stale', fetched_at='x')], date(2026, 1, 1), date(2026, 11, 16))

    got = macro_cache.read_series('CPI', date(2026, 1, 1), date(2026, 11, 16))
    assert got is not None and got[0]['cache'] == 'hit'


def test_search_cache_roundtrip():
    macro_cache.write_search('中国GDP同比', [{'name': '中国:GDP:不变价:当季同比', 'code': 'X', 'freq': '季'}])

    got = macro_cache.read_search('中国GDP同比')

    assert got is not None and got[0]['cache'] == 'hit'
    assert macro_cache.read_search('另一个问法') is None, '不同问法不共享检索缓存'


def test_window_tolerance_is_one_ttl_not_unlimited():
    """终点落后一个 TTL 内可复用（发布日历未到），落后更多必须重取。"""
    old_end = date(2026, 1, 1)
    macro_cache.write_series('CPI', [_row(points={date(2026, 1, 1): 0.4})], date(2025, 1, 1), old_end)

    assert macro_cache.read_series('CPI', date(2026, 1, 1), old_end + timedelta(days=1)) is not None
    assert macro_cache.read_series('CPI', date(2026, 1, 1), old_end + timedelta(days=30)) is None
