# -*- coding: utf-8 -*-
"""PriceFetcher 持久化缓存单测：命中/失效/降级/透传 stale + 默认缓存目录解析（#1540）。

隔离方式（#1540 起）：用例**不再**逐个传 `cache_dir=tmp_path`，而是统一由
`tests/conftest.py::_isolate_cache_file_dir`（autouse，设 env `CACHE_FILE_DIR`）覆盖——
需要落盘路径时用 `PriceFetcher().cache_dir` 取真实解析结果。这样既完成隔离，
也顺带守住「env 真被认」这条回归线（退回模块级常量则本文件相关用例随即写进源码树）。
"""

import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from app.services.bias import calculator
from app.services.bias.calculator import BIAS_PERIOD, BiasCalculator, PriceFetcher
from app.services.bias.constants import ITEM_TYPE_INDEX


def _make_df(n: int = 30, end: str = None):
    end = end or datetime.now().strftime('%Y-%m-%d')
    dates = pd.date_range(end=end, periods=n, freq='D').strftime('%Y-%m-%d')
    closes = [float(i) + 10.0 for i in range(n)]
    return pd.DataFrame({'日期': dates, '收盘': closes})


def _write_stale_cache(cache_dir, symbol='000300', item_type='index', n=30):
    payload = {
        'symbol': symbol,
        'item_type': item_type,
        'values': [float(i) + 10.0 for i in range(n)],
        'data_last_date': '2000-01-01',
        'fetched_at': '2000-01-01T00:00:00',
    }
    p = cache_dir / f'{item_type}__{symbol.replace(".", "_")}.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding='utf-8')


@contextmanager
def _live_index_akshare(result=None, exc=None):
    """把 PriceFetcher 的实时抓取锁定到 akshare 兜底路径（屏蔽腾讯/东财直连，避免测试触网），
    并让 get_akshare() 返回可编程的假 ak；yield 该假 ak 供断言调用次数。"""
    fake_ak = MagicMock()
    if exc is not None:
        fake_ak.index_zh_a_hist.side_effect = exc
    else:
        fake_ak.index_zh_a_hist.return_value = result
    with (
        patch('app.core.akshare_lazy.get_akshare', return_value=fake_ak),
        patch.object(PriceFetcher, '_fetch_direct', return_value=(None, None)),
        patch('app.services.bias.calculator.time.sleep'),
    ):
        yield fake_ak


def test_process_cache_hit_avoids_live():
    """同进程内第二次 fetch 直接命中 _cache，不请求实时源。"""
    fetcher = PriceFetcher(days=60)
    df = _make_df()
    with _live_index_akshare(result=df) as fake_ak:
        r1 = fetcher.fetch('000300', ITEM_TYPE_INDEX)
        assert r1 is not None
        assert fake_ak.index_zh_a_hist.call_count == 1
        r2 = fetcher.fetch('000300', ITEM_TYPE_INDEX)
        assert r2 == r1
        assert fake_ak.index_zh_a_hist.call_count == 1
        assert fetcher._stale[('000300', ITEM_TYPE_INDEX)] is False


def test_file_cache_survives_restart():
    """新实例（模拟进程重启）从文件缓存加载，不请求实时源。"""
    df = _make_df()
    with _live_index_akshare(result=df) as fake_ak1:
        f1 = PriceFetcher()
        f1.fetch('000300', ITEM_TYPE_INDEX)
        assert fake_ak1.index_zh_a_hist.call_count == 1
    with _live_index_akshare(result=df) as fake_ak2:
        f2 = PriceFetcher()
        r = f2.fetch('000300', ITEM_TYPE_INDEX)
        assert r is not None
        assert fake_ak2.index_zh_a_hist.call_count == 0  # 文件命中，未请求实时源
        assert f2._stale[('000300', ITEM_TYPE_INDEX)] is False


def test_stale_fallback_on_live_failure():
    """实时抓取失败但有旧缓存 → 回退旧数据并标 stale=True。"""
    fetcher = PriceFetcher()
    _write_stale_cache(fetcher.cache_dir)
    with _live_index_akshare(exc=Exception('boom')):
        r = fetcher.fetch('000300', ITEM_TYPE_INDEX)
    assert r is not None
    assert len(r) >= BIAS_PERIOD
    assert fetcher._stale[('000300', ITEM_TYPE_INDEX)] is True


def test_no_cache_returns_none():
    """无缓存且实时失败 → 返回 None。"""
    fetcher = PriceFetcher()
    with _live_index_akshare(exc=Exception('boom')):
        r = fetcher.fetch('000300', ITEM_TYPE_INDEX)
    assert r is None


def test_is_fresh():
    assert PriceFetcher._is_fresh(datetime.now().strftime('%Y-%m-%d')) is True
    assert PriceFetcher._is_fresh('2000-01-01') is False
    assert PriceFetcher._is_fresh('') is False


def test_calculate_item_propagates_stale():
    """stale 状态透传到 BiasResult。"""
    fetcher = PriceFetcher()
    _write_stale_cache(fetcher.cache_dir)
    with _live_index_akshare(exc=Exception('boom')):
        calc = BiasCalculator(fetcher=fetcher)
        res = calc.calculate_item('000300', ITEM_TYPE_INDEX, '沪深300')
    assert res is not None
    assert res.stale is True


class TestDefaultCacheDir:
    """#1540：默认缓存目录改由 `resolve_cache_subdir()` 调用期解析。"""

    def test_default_under_cache_file_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path / 'custom'))
        assert PriceFetcher().cache_dir == tmp_path / 'custom' / 'bias_price_cache'

    def test_default_follows_env_change_at_call_time(self, tmp_path, monkeypatch):
        """**核心回归守卫**：import 之后再改 env，默认目录随之移动（退回常量即失败）。"""
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path / 'a'))
        before = PriceFetcher().cache_dir
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path / 'b'))
        after = PriceFetcher().cache_dir

        assert before != after, '默认目录未随 CACHE_FILE_DIR 变化，疑似被固化成 import 期常量'
        assert after == tmp_path / 'b' / 'bias_price_cache'

    def test_explicit_cache_dir_wins(self, tmp_path, monkeypatch):
        """显式 `cache_dir=` 仍优先于 env——该构造参数的语义不变。"""
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path / 'env'))
        assert PriceFetcher(cache_dir=tmp_path / 'explicit').cache_dir == tmp_path / 'explicit'

    def test_not_in_source_tree(self, tmp_path, monkeypatch):
        """默认目录不再落在源码树内的 `backend/data/bias_price_cache`。"""
        monkeypatch.setenv('CACHE_FILE_DIR', str(tmp_path))
        resolved = PriceFetcher().cache_dir.resolve()
        legacy = Path(calculator.__file__).resolve().parents[3] / 'data' / 'bias_price_cache'
        assert resolved != legacy, f'默认目录仍指向源码树内的 {legacy}'
        assert resolved == tmp_path / 'bias_price_cache'

    def test_isolated_by_conftest_fixture(self, tmp_path):
        """不传 `cache_dir` 时由 conftest 的 autouse 夹具隔离，落盘进用例私有目录。"""
        assert PriceFetcher().cache_dir == tmp_path / 'fundmate_cache' / 'bias_price_cache'
