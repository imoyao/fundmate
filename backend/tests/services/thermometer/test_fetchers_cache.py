# -*- coding: utf-8 -*-
"""温度计抓取的缓存目录与 TTL 语义（#1537）。

背景：`fetchers.py` 原先自带一套 `_cached()` 文件缓存，目录**硬编码**全局临时目录，
与 `app/core/cache.py` 的 `CacheService` 共用 `fundmate_cache` 却不认 `CACHE_FILE_DIR`
——按环境指定缓存目录时只生效一半，测试隔离也漏掉了这条路径（#1531 那类「上一轮跑过
什么决定本轮结果」的隐患在 fetchers 上没封住）。

本文件钉住修复后的三条契约（对应 issue 的三条验收标准）：

1. 落盘目录与 `CacheService` **同源**（同经 `resolve_cache_file_dir()`）；
2. conftest 的 autouse 隔离夹具**覆盖** fetchers 的落盘路径，且不污染全局目录；
3. TTL 窗口语义不变（写盘后 12h 内复用、过期重跑），producer 返回 None 不写盘。
"""

import tempfile
from pathlib import Path

from app.core.cache import CacheService
from app.services.thermometer import fetchers
from app.services.thermometer.constants import SELF_CALC_CACHE_KEY, SELF_CALC_CACHE_TTL


class _FakeAk:
    """最小 akshare 替身：`_producer` 第一步取 PE 即返回 None，短路掉后续重活。"""

    def __init__(self):
        self.calls = []

    def stock_index_pe_lg(self, symbol):  # noqa: ARG002 - 签名对齐被替换的真实接口
        self.calls.append(symbol)
        return None


def _isolated_dir(tmp_path: Path) -> Path:
    """conftest 的 `_isolate_cache_file_dir` 写入的用例私有目录。"""
    return tmp_path / 'fundmate_cache'


class TestSharedCacheDir:
    def test_same_dir_as_cache_service(self, tmp_path, monkeypatch):
        """两套实现目录同源：改 `CACHE_FILE_DIR` 对双方一起生效（验收 1）。"""
        target = tmp_path / 'custom'
        monkeypatch.setenv('CACHE_FILE_DIR', str(target))
        assert fetchers._cache()._file_dir == CacheService(namespace='probe')._file_dir == target

    def test_write_lands_in_isolated_dir(self, tmp_path):
        """隔离夹具覆盖 fetchers 落盘路径，且不污染全局临时目录（验收 2）。"""
        fetchers._cache().set(SELF_CALC_CACHE_KEY, {'v': 1}, ttl=SELF_CALC_CACHE_TTL)
        filename = f'cache_thermometer_{SELF_CALC_CACHE_KEY}.pkl'

        assert (_isolated_dir(tmp_path) / filename).exists(), 'fetchers 落盘未被 conftest 隔离夹具覆盖'
        global_dir = Path(tempfile.gettempdir()) / 'fundmate_cache'
        assert not (global_dir / filename).exists(), 'fetchers 仍写进跨进程共享的全局临时目录，#1537 未生效'


class TestSelfCalcCacheSemantics:
    """TTL 语义（验收 3）：与替换前一致——写盘后 12h 内复用，过期后重跑。"""

    def test_hit_skips_producer(self, monkeypatch):
        """命中缓存直接返回，不再触发 akshare（12h 复用的核心承诺）。"""
        cached = {'data': {'percent': 42.0, 'level': '适中'}, 'stale': False}
        fetchers._cache().set(SELF_CALC_CACHE_KEY, cached, ttl=SELF_CALC_CACHE_TTL)

        def boom():
            raise AssertionError('命中缓存却仍调用了 akshare')

        monkeypatch.setattr('app.core.akshare_lazy.get_akshare', boom)
        assert fetchers.SelfCalcFetcher().fetch() == cached

    def test_expired_entry_reruns_producer(self, monkeypatch):
        """过期条目不再返回，重跑 producer。"""
        fetchers._cache().set(SELF_CALC_CACHE_KEY, {'data': {'percent': 1.0}}, ttl=0)
        ak = _FakeAk()
        monkeypatch.setattr('app.core.akshare_lazy.get_akshare', lambda: ak)

        assert fetchers.SelfCalcFetcher().fetch() is None  # producer 短路返回 None
        assert ak.calls == ['沪深300'], '过期后没有重跑 producer'

    def test_producer_none_not_cached(self, monkeypatch):
        """producer 返回 None 不写盘、下次重试（#1537 起的 CacheService 语义）。

        替换前的 `_cached()` 会把 None 也缓存 12 小时：一次 akshare 抖动就让「自算估值
        分位」连续标灰且不重试。生产侧每天只跑一次、12h TTL 跨不到次日，故此为纯改进。
        """
        ak = _FakeAk()
        monkeypatch.setattr('app.core.akshare_lazy.get_akshare', lambda: ak)
        fetcher = fetchers.SelfCalcFetcher()

        assert fetcher.fetch() is None
        assert fetcher.fetch() is None
        assert len(ak.calls) == 2, 'None 结果被缓存了，第二次调用没有重试'
