# -*- coding: utf-8 -*-
"""PriceFetcher 持久化缓存单测：命中/失效/降级/透传 stale。"""

import json
from datetime import datetime
from unittest.mock import patch

import pandas as pd

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
    p.write_text(json.dumps(payload), encoding='utf-8')


def test_process_cache_hit_avoids_live(tmp_path):
    """同进程内第二次 fetch 直接命中 _cache，不请求东财。"""
    fetcher = PriceFetcher(cache_dir=tmp_path, days=60)
    df = _make_df()
    with patch('app.services.bias.calculator.ak.index_zh_a_hist', return_value=df) as m:
        r1 = fetcher.fetch('000300', ITEM_TYPE_INDEX)
        assert r1 is not None
        assert m.call_count == 1
        r2 = fetcher.fetch('000300', ITEM_TYPE_INDEX)
        assert r2 == r1
        assert m.call_count == 1
        assert fetcher._stale[('000300', ITEM_TYPE_INDEX)] is False


def test_file_cache_survives_restart(tmp_path):
    """新实例（模拟进程重启）从文件缓存加载，不请求东财。"""
    df = _make_df()
    with patch('app.services.bias.calculator.ak.index_zh_a_hist', return_value=df) as m1:
        f1 = PriceFetcher(cache_dir=tmp_path)
        f1.fetch('000300', ITEM_TYPE_INDEX)
        assert m1.call_count == 1
    with patch('app.services.bias.calculator.ak.index_zh_a_hist', return_value=df) as m2:
        f2 = PriceFetcher(cache_dir=tmp_path)
        r = f2.fetch('000300', ITEM_TYPE_INDEX)
        assert r is not None
        assert m2.call_count == 0  # 文件命中，未请求东财
        assert f2._stale[('000300', ITEM_TYPE_INDEX)] is False


def test_stale_fallback_on_live_failure(tmp_path):
    """实时抓取失败但有旧缓存 → 回退旧数据并标 stale=True。"""
    _write_stale_cache(tmp_path)
    fetcher = PriceFetcher(cache_dir=tmp_path)
    with patch('app.services.bias.calculator.ak.index_zh_a_hist', side_effect=Exception('boom')):
        r = fetcher.fetch('000300', ITEM_TYPE_INDEX)
    assert r is not None
    assert len(r) >= BIAS_PERIOD
    assert fetcher._stale[('000300', ITEM_TYPE_INDEX)] is True


def test_no_cache_returns_none(tmp_path):
    """无缓存且实时失败 → 返回 None。"""
    fetcher = PriceFetcher(cache_dir=tmp_path)
    with patch('app.services.bias.calculator.ak.index_zh_a_hist', side_effect=Exception('boom')):
        r = fetcher.fetch('000300', ITEM_TYPE_INDEX)
    assert r is None


def test_is_fresh():
    assert PriceFetcher._is_fresh(datetime.now().strftime('%Y-%m-%d')) is True
    assert PriceFetcher._is_fresh('2000-01-01') is False
    assert PriceFetcher._is_fresh('') is False


def test_calculate_item_propagates_stale(tmp_path):
    """stale 状态透传到 BiasResult。"""
    _write_stale_cache(tmp_path)
    fetcher = PriceFetcher(cache_dir=tmp_path)
    with patch('app.services.bias.calculator.ak.index_zh_a_hist', side_effect=Exception('boom')):
        calc = BiasCalculator(fetcher=fetcher)
        res = calc.calculate_item('000300', ITEM_TYPE_INDEX, '沪深300')
    assert res is not None
    assert res.stale is True
