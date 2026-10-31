# -*- coding: utf-8 -*-
"""`app/core/ratelimit.py` 单测（#2764 遗留项）。

限流最怕的是「写了但没生效」和「生效了但误伤」。这里把窗口边界、分桶、重置都钉住；
`time.time` 用 monkeypatch 冻结，不依赖真实时钟（否则跨分钟边界必 flaky）。
"""

from app.core import ratelimit


class _Clock:
    def __init__(self, start=1_000_000):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _patch_clock(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(ratelimit.time, 'time', clock)
    ratelimit.reset_all()
    return clock


def test_allows_up_to_limit_then_blocks(monkeypatch):
    _patch_clock(monkeypatch)
    for _ in range(3):
        assert ratelimit.check('ip:a', limit=3) is True
    assert ratelimit.check('ip:a', limit=3) is False


def test_separate_keys_do_not_share_quota(monkeypatch):
    _patch_clock(monkeypatch)
    assert ratelimit.check('ip:a', limit=1) is True
    assert ratelimit.check('ip:b', limit=1) is True
    assert ratelimit.check('ip:a', limit=1) is False


def test_new_window_resets_counter(monkeypatch):
    clock = _patch_clock(monkeypatch)
    assert ratelimit.check('ip:a', limit=1, window_seconds=60) is True
    assert ratelimit.check('ip:a', limit=1, window_seconds=60) is False

    clock.advance(61)
    assert ratelimit.check('ip:a', limit=1, window_seconds=60) is True


def test_expired_buckets_are_pruned(monkeypatch):
    """清理是必需的：桶键含 IP，不清理会让字典随扫描流量无限膨胀。"""
    clock = _patch_clock(monkeypatch)
    ratelimit.check('ip:old', limit=5, window_seconds=60)
    assert len(ratelimit._BUCKETS) == 1

    clock.advance(600)
    ratelimit.check('ip:new', limit=5, window_seconds=60)
    assert 'ip:old' not in {k[0] for k in ratelimit._BUCKETS}


def test_non_positive_limit_means_unlimited(monkeypatch):
    """`limit <= 0` 视作关闭限流（便于本地/压测显式放行，不用改调用点）。"""
    _patch_clock(monkeypatch)
    for _ in range(50):
        assert ratelimit.check('ip:a', limit=0) is True


def test_reset_all_clears_state(monkeypatch):
    _patch_clock(monkeypatch)
    assert ratelimit.check('ip:a', limit=1) is True
    ratelimit.reset_all()
    assert ratelimit.check('ip:a', limit=1) is True
