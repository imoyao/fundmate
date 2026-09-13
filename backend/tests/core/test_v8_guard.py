# -*- coding: utf-8 -*-
"""V8 并发守卫（app/core/v8_guard.py）单测。

背景（2026-09-13 真机实测）：akshare 有 40 个模块用 `py_mini_racer` 解密新浪/巨潮系 JS
数据，且**每次调用都新建一个 `MiniRacer()`**（新 V8 isolate）；V8 的 configurable pool
只能初始化一次，多线程并发首次创建会触发
`FATAL: Check failed: !IsConfigurablePoolInitialized()` —— **那是 C++ abort 而非 Python
异常，抓不住、直接杀掉整个进程**。

单测**无法**复现真实 V8 崩溃（会连 pytest 一起杀掉），故这里钉住「防线」的行为契约：
预热全进程只创建一次 isolate、并发调用被串行化、失败结果被缓存、收口点自动触发预热。
"""

import sys
import threading
import types

import pytest

from app.core import akshare_lazy, v8_guard


@pytest.fixture(autouse=True)
def _reset_guard():
    """每个用例前复位预热状态，避免上一用例的缓存短路被测逻辑。"""
    v8_guard.reset_for_test()
    yield
    v8_guard.reset_for_test()


def _fake_mini_racer(monkeypatch, boom: bool = False):
    """把 py_mini_racer 换成可计数的假模块，返回「被创建次数」列表。"""
    calls = []

    class _FakeRacer:
        def __init__(self):
            calls.append(1)
            if boom:
                raise RuntimeError('模拟 V8 初始化失败')

        def eval(self, _code):
            return 2

    fake = types.ModuleType('py_mini_racer')
    fake.MiniRacer = _FakeRacer
    monkeypatch.setitem(sys.modules, 'py_mini_racer', fake)
    return calls


class TestEnsureV8Ready:
    def test_creates_isolate_once_and_caches_result(self, monkeypatch):
        calls = _fake_mini_racer(monkeypatch)

        assert v8_guard.ensure_v8_ready() is True
        assert v8_guard.ensure_v8_ready() is True
        assert v8_guard.ensure_v8_ready() is True

        assert len(calls) == 1, '预热必须全进程只创建一次 V8 isolate'

    def test_failure_is_cached_and_reported(self, monkeypatch):
        calls = _fake_mini_racer(monkeypatch, boom=True)

        assert v8_guard.ensure_v8_ready() is False
        assert v8_guard.ensure_v8_ready() is False

        assert len(calls) == 1, '失败的预热也要缓存，避免反复触发危险创建'

    def test_concurrent_calls_are_serialized(self, monkeypatch):
        """并发调用只能有一个线程真正创建 isolate——否则又会踩同一个 abort。

        真机已验证：锁保护下的首次创建即便发生在**工作线程**也与主线程预热等价
        （lock_prewarm_parallel6 → exit_code=0）。
        """
        calls = _fake_mini_racer(monkeypatch)
        barrier = threading.Barrier(8)
        results = []
        lock = threading.Lock()

        def _run():
            barrier.wait()
            r = v8_guard.ensure_v8_ready()
            with lock:
                results.append(r)

        threads = [threading.Thread(target=_run) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results == [True] * 8
        assert len(calls) == 1, '并发预热必须串行化，否则会再次触发 V8 abort'

    def test_reset_for_test_clears_cache(self, monkeypatch):
        calls = _fake_mini_racer(monkeypatch)

        assert v8_guard.ensure_v8_ready() is True
        v8_guard.reset_for_test()
        assert v8_guard.ensure_v8_ready() is True

        assert len(calls) == 2


class TestAkshareChokePointTriggersGuard:
    """`get_akshare()` 是全仓 akshare 唯一收口点，预热必须挂在这里才算结构免疫。"""

    @staticmethod
    def _reset_akshare(monkeypatch):
        """注入假 akshare 模块 + 复位缓存，避免真导入 akshare（约 3s）。"""
        monkeypatch.setitem(sys.modules, 'akshare', types.ModuleType('akshare'))
        monkeypatch.setattr(akshare_lazy, '_AKSHARE', None)

    def test_get_akshare_calls_ensure_v8_ready(self, monkeypatch):
        called = []
        monkeypatch.setattr(v8_guard, 'ensure_v8_ready', lambda: called.append(1) or True)
        self._reset_akshare(monkeypatch)

        akshare_lazy.get_akshare()

        assert called == [1], 'get_akshare() 必须触发 V8 预热，否则其它并发取数路径仍会 abort'

    def test_second_call_does_not_repeat_prewarm(self, monkeypatch):
        called = []
        monkeypatch.setattr(v8_guard, 'ensure_v8_ready', lambda: called.append(1) or True)
        self._reset_akshare(monkeypatch)

        akshare_lazy.get_akshare()
        akshare_lazy.get_akshare()

        assert len(called) == 1, '预热只在首次导入 akshare 时做一次'
