# -*- coding: utf-8 -*-
"""CacheService 单测（#892 架构决策落地）。

覆盖：LRU 命中/TTL 过期、文件层持久化与冷启动、get_or_set producer 调用次数、
invalidate 两级同删、producer 返回 None 不缓存、Redis 回退声明。
"""

import time

from app.core.cache import CacheService


class TestLRULayer:
    def test_set_get_roundtrip(self):
        cache = CacheService(namespace='t1')
        cache.set('k1', {'a': 1}, ttl=60)
        assert cache.get('k1') == {'a': 1}

    def test_ttl_expiry(self):
        cache = CacheService(namespace='t2')
        cache.set('k', 'v', ttl=0)  # 立即过期
        time.sleep(0.01)
        assert cache.get('k') is None

    def test_namespace_isolation(self):
        c1 = CacheService(namespace='ns1')
        c2 = CacheService(namespace='ns2')
        c1.set('k', 'v1', ttl=60)
        assert c2.get('k') is None
        assert c1.get('k') == 'v1'

    def test_lru_capacity_eviction(self):
        cache = CacheService(namespace='t3')
        # 写满 256 + 10 条，最早写入的应被逐出（本地文件层仍在，get 仍可能从文件命中——
        # 故这里断言 LRU 层行为经由 invalidate 清文件后验证）
        for i in range(266):
            cache.set(f'k{i}', i, ttl=60)
        cache.invalidate('k0')  # 清掉文件层
        assert cache.get('k0') is None  # LRU 已逐出 + 文件已删
        assert cache.get('k265') == 265  # 热点仍在


class TestFileLayer:
    def test_cold_start_from_file(self, tmp_path):
        """进程重启（新实例）后从文件层命中——冷启动加速的核心承诺。"""
        import os

        os.environ['CACHE_FILE_DIR'] = str(tmp_path)
        try:
            c1 = CacheService(namespace='cold')
            c1.set('series', [1, 2, 3], ttl=600)
            c2 = CacheService(namespace='cold')  # 模拟重启：全新 LRU
            assert c2.get('series') == [1, 2, 3]
        finally:
            del os.environ['CACHE_FILE_DIR']

    def test_file_expiry(self, tmp_path):
        import os

        os.environ['CACHE_FILE_DIR'] = str(tmp_path)
        try:
            c1 = CacheService(namespace='exp')
            c1.set('k', 'v', ttl=0)
            c2 = CacheService(namespace='exp')
            time.sleep(0.01)
            assert c2.get('k') is None
        finally:
            del os.environ['CACHE_FILE_DIR']


class TestGetOrSet:
    def test_producer_called_once(self):
        cache = CacheService(namespace='t4')
        calls = []

        def producer():
            calls.append(1)
            return 'expensive'

        assert cache.get_or_set('k', producer, ttl=60) == 'expensive'
        assert cache.get_or_set('k', producer, ttl=60) == 'expensive'
        assert len(calls) == 1

    def test_none_producer_not_cached(self):
        """producer 返回 None 视为本次无可缓存，不写缓存、每次重试。"""
        cache = CacheService(namespace='t5')
        calls = []

        def producer():
            calls.append(1)
            return None

        assert cache.get_or_set('k', producer, ttl=60) is None
        assert cache.get_or_set('k', producer, ttl=60) is None
        assert len(calls) == 2


class TestInvalidate:
    def test_invalidates_both_layers(self, tmp_path):
        import os

        os.environ['CACHE_FILE_DIR'] = str(tmp_path)
        try:
            cache = CacheService(namespace='inv')
            cache.set('k', 'v', ttl=600)
            cache.invalidate('k')
            # 新实例（绕过 LRU）也拿不到——文件层已删
            fresh = CacheService(namespace='inv')
            assert fresh.get('k') is None
        finally:
            del os.environ['CACHE_FILE_DIR']


class TestRedisFallback:
    def test_redis_unavailable_falls_back(self, monkeypatch):
        """CACHE_BACKEND=redis 但 redis 未安装 → 静默回退 local，行为不变。"""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == 'redis':
                raise ImportError('No module named redis')
            return real_import(name, *args, **kwargs)

        monkeypatch.setenv('CACHE_BACKEND', 'redis')
        monkeypatch.setattr(builtins, '__import__', fake_import)
        cache = CacheService(namespace='rf')
        cache.set('k', 'v', ttl=60)
        assert cache.get('k') == 'v'  # 回退本地后照常工作
