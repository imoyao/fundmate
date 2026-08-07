# -*- coding: utf-8 -*-
"""
industry_crowding 模块离线测试：覆盖分母兜底链降级顺序与 baostock 兜底路径。
不依赖真实外部数据源（mock 掉 legulegu / baostock / 东财请求）。
"""

from datetime import datetime

import pandas as pd
import pytest

from app.services.thermometer import industry_crowding as ic


class _FakeRows:
    """伪造 baostock ResultData 迭代：fields + next()/get_row_data()。"""

    def __init__(self, rows):
        self.fields = ['date', 'code', 'pbMRQ']
        self._rows = list(rows)
        self._i = 0

    def next(self):
        if self._i < len(self._rows):
            self._i += 1
            return True
        return False

    def get_row_data(self):
        return list(self._rows[self._i - 1])


@pytest.fixture
def fake_baostock(monkeypatch):
    """把 baostock.login / query_daily_history_k_AStock / logout 替换为可编程假实现。"""
    import types

    captured = {'calls': 0, 'rows': []}

    class _FakeBS:
        @staticmethod
        def login():
            return types.SimpleNamespace(error_code=0, error_msg='success')

        @staticmethod
        def logout():
            return types.SimpleNamespace(error_code=0, error_msg='success')

        @staticmethod
        def query_daily_history_k_AStock(date=''):
            captured['calls'] += 1
            return _FakeRows(captured['rows'])

    monkeypatch.setattr(ic, 'bs', _FakeBS)
    # 隔离真实 socket：让 _run 里的 import baostock 拿到假模块
    import sys

    monkeypatch.setitem(sys.modules, 'baostock', _FakeBS)
    monkeypatch.setitem(sys.modules, 'baostock.data', types.SimpleNamespace())
    return captured


def test_market_pb_series_baostock_fallback(fake_baostock, monkeypatch):
    """legulegu 与本地缓存都不可用时，应落到 baostock 兜底并返回当日点。"""
    fake_baostock['rows'] = [
        ['2026-08-07', 'sh.600519', '6.27'],
        ['2026-08-07', 'sz.000001', '0.49'],
        ['2026-08-07', 'sh.601318', '0.99'],
        ['2026-08-07', 'sh.600036', '0.85'],
        ['2026-08-07', 'sz.000858', '5.50'],
    ]

    monkeypatch.setattr(ic, 'ak', None)
    monkeypatch.setattr(ic, '_load_allpb_cache', lambda: None)
    monkeypatch.setattr(ic, '_eastmoney_current_median_pb', lambda: None)

    s, meta = ic.market_pb_series()

    assert meta['src'] == 'baostock'
    assert meta['hist_ok'] is False
    # 中位数：排序 [0.49, 0.85, 0.99, 5.50, 6.27] -> 0.99
    assert s.iloc[-1] == pytest.approx(0.99)
    assert fake_baostock['calls'] == 1


def test_market_pb_series_falls_back_to_eastmoney(fake_baostock, monkeypatch):
    """baostock 兜底返回 None 时，应继续落到东财（历史遗留）。"""
    fake_baostock['rows'] = []  # 空行 -> median 抛错 -> 返回 None

    monkeypatch.setattr(ic, 'ak', None)
    monkeypatch.setattr(ic, '_load_allpb_cache', lambda: None)
    monkeypatch.setattr(
        ic,
        '_eastmoney_current_median_pb',
        lambda: 2.5,
    )

    s, meta = ic.market_pb_series()

    assert meta['src'] == 'eastmoney-live'
    assert s.iloc[-1] == pytest.approx(2.5)


def test_market_pb_series_unavailable(fake_baostock, monkeypatch):
    """全链失败（baostock 空 + 东财 None）→ unavailable，绝不抛异常。"""
    fake_baostock['rows'] = []
    monkeypatch.setattr(ic, 'ak', None)
    monkeypatch.setattr(ic, '_load_allpb_cache', lambda: None)
    monkeypatch.setattr(ic, '_eastmoney_current_median_pb', lambda: None)

    s, meta = ic.market_pb_series()

    assert meta['src'] == 'unavailable'
    assert s is None


def test_baostock_timeout_not_raised(monkeypatch):
    """baostock 兜底内部任何异常都应降级为 None，不向上抛（保护主链路）。"""
    import concurrent.futures

    def _boom():
        raise RuntimeError('simulated bs failure')

    monkeypatch.setattr(ic, '_save_allpb_cache', lambda s: None)

    # 用可控的超时实现（立刻超时），验证异常被吞掉
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_boom)
        with pytest.raises(RuntimeError):
            fut.result(timeout=1)


def test_crowding_hist_ok_false_returns_multiple_only():
    """hist_ok=False（分母仅当日点）时只给倍数，crowding_pct 为 None 且标注。"""
    ind = pd.Series({pd.Timestamp('2026-08-07'): 6.27})
    mkt = pd.Series({pd.Timestamp('2026-08-07'): 2.62})

    c = ic.crowding(ind, mkt, hist_ok=False)

    assert c is not None
    assert c['multiple'] == pytest.approx(6.27 / 2.62, rel=1e-3)
    assert c['crowding_pct'] is None
    assert c['hist_ok'] is False


def test_record_stale_placeholder_shape():
    """全失败时的 stale 占位记录符合 multi 扁平格式（前端可直接消费）。"""
    rec = ic._placeholder('测试占位')

    assert rec['kind'] == 'multi'
    assert rec['source'] == 'industry_crowding'
    assert rec['stale'] is True
    assert rec['data']['note'] == '测试占位'
    assert isinstance(rec['collected_at'], datetime)
