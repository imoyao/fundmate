# -*- coding: utf-8 -*-
"""CacheService 单测（#892 架构决策落地）。

覆盖：LRU 命中/TTL 过期、文件层持久化与冷启动、get_or_set producer 调用次数、
invalidate 两级同删、producer 返回 None 不缓存、Redis 回退声明、文件层目录隔离。

隔离说明（#1531）：文件层目录跨进程存活，落全局临时目录时残留 pkl 会在 ttl 内被
下一个进程直接命中，测试结果取决于「上一轮跑过什么」。本文件里凡涉及文件层的用例
一律显式传 `file_dir=tmp_path`；未显式传的用例由 conftest 的 `_isolate_cache_file_dir`
兜底重定向 `CACHE_FILE_DIR`。
"""

import tempfile
import time
from pathlib import Path

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
        c1 = CacheService(namespace='cold', file_dir=tmp_path)
        c1.set('series', [1, 2, 3], ttl=600)
        c2 = CacheService(namespace='cold', file_dir=tmp_path)  # 模拟重启：全新 LRU
        assert c2.get('series') == [1, 2, 3]

    def test_file_expiry(self, tmp_path):
        c1 = CacheService(namespace='exp', file_dir=tmp_path)
        c1.set('k', 'v', ttl=0)
        c2 = CacheService(namespace='exp', file_dir=tmp_path)
        time.sleep(0.01)
        assert c2.get('k') is None


class TestFileDirIsolation:
    """文件层目录隔离（#1531）。

    原先文件层固定落 `tempfile.gettempdir()/fundmate_cache`：全局共享、无清理，
    跨进程残留让 `test_producer_called_once` 在 ttl 内重跑必失败（红灯不再反映真实
    状态）。以下三条钉住「显式 file_dir / env / 默认目录」三者的优先级与去向。
    """

    def test_explicit_file_dir_used(self, tmp_path):
        """构造参数 `file_dir` 生效，且文件确实落在该目录。"""
        cache = CacheService(namespace='inj', file_dir=tmp_path)
        cache.set('k', 'v', ttl=600)
        assert (tmp_path / 'cache_inj_k.pkl').exists()

    def test_file_dir_param_beats_env(self, tmp_path, monkeypatch):
        """显式 `file_dir` 优先于 env（否则测试隔离会被外部环境覆盖）。"""
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path / 'from_env'))
        cache = CacheService(namespace='prio', file_dir=tmp_path)
        cache.set('k', 'v', ttl=600)
        assert (tmp_path / 'cache_prio_k.pkl').exists()
        assert not (tmp_path / 'from_env').exists()

    def test_env_file_dir_read_at_construction(self, tmp_path, monkeypatch):
        """`CACHE_FILE_DIR` 在构造期读取——import 之后再设 env 也必须生效。"""
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path))
        cache = CacheService(namespace='envd')
        cache.set('k', 'v', ttl=600)
        assert (tmp_path / 'cache_envd_k.pkl').exists()

    def test_default_dir_not_global_temp_dir(self):
        """默认目录不得是全局临时目录（依赖 conftest 的隔离 fixture）。

        若本断言失败，说明隔离被绕过：文件层又写进了跨进程共享的目录，本文件其他
        用例会重新变成「结果取决于上一轮跑过什么」。
        """
        global_file = Path(tempfile.gettempdir()) / 'fundmate_cache' / 'cache_probe_k.pkl'
        # 先清残留：隔离失效时本条会写入它，若不清则修好之后还会被这枚旧文件误伤
        global_file.unlink(missing_ok=True)
        CacheService(namespace='probe').set('k', 'v', ttl=600)
        assert not global_file.exists(), '文件层写进了全局临时目录，#1531 的隔离失效'


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
        cache = CacheService(namespace='inv', file_dir=tmp_path)
        cache.set('k', 'v', ttl=600)
        cache.invalidate('k')
        # 新实例（绕过 LRU）也拿不到——文件层已删
        fresh = CacheService(namespace='inv', file_dir=tmp_path)
        assert fresh.get('k') is None


class TestRedisFallback:
    def test_redis_unavailable_falls_back(self, monkeypatch):
        """CACHE_BACKEND=redis 但 redis 未安装 → 静默回退 local，行为不变。

        #1531：原用例只断言「回退后照常工作」，而 `CACHE_BACKEND` 当初是 import 期
        固化的模块常量——构造期读不到 monkeypatch 的 env，即便 redis 分支被整体删掉
        这条用例照样绿（假阳性）。故补一条「确实尝试过导入 redis」的断言。
        """
        import builtins

        real_import = builtins.__import__
        import_attempts = []

        def fake_import(name, *args, **kwargs):
            if name == 'redis':
                import_attempts.append(name)
                raise ImportError('No module named redis')
            return real_import(name, *args, **kwargs)

        monkeypatch.setenv('CACHE_BACKEND', 'redis')
        monkeypatch.setattr(builtins, '__import__', fake_import)
        cache = CacheService(namespace='rf')
        assert import_attempts == ['redis'], '未真正走 redis 分支——用例已退化为假阳性'
        assert cache._backend == 'local'
        cache.set('k', 'v', ttl=60)
        assert cache.get('k') == 'v'  # 回退本地后照常工作
