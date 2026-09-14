# -*- coding: utf-8 -*-
"""申万行业行情改走申万宏源官网（非东财）—— #1431。"""

import pandas as pd

from app.services.bias.direct_feeds import fetch_close_sw_industry


def test_sw_industry_non_si_returns_none():
    """非申万后缀不走申万源（短路；不会触网）。"""
    assert fetch_close_sw_industry('000300.SH', 60) is None
    assert fetch_close_sw_industry('510300.SH', 60) is None


def test_sw_industry_parses_akshare_frame(monkeypatch):
    """给定 akshare 返回帧时，正确取「收盘」序列与最后交易日。"""
    dates = pd.date_range('2024-01-01', periods=80, freq='B')
    df = pd.DataFrame(
        {
            '代码': '801010',
            '日期': [d.strftime('%Y-%m-%d') for d in dates],
            '收盘': [float(i) for i in range(80)],
        }
    )

    class _FakeAk:
        @staticmethod
        def index_hist_sw(symbol, period='day'):
            return df

    import app.core.akshare_lazy as al

    monkeypatch.setattr(al, 'get_akshare', lambda: _FakeAk())

    res = fetch_close_sw_industry('801010.SI', days=60)

    assert res is not None
    vals, last = res
    assert len(vals) == 60
    assert vals[-1] == 79.0
    assert last == dates[-1].strftime('%Y-%m-%d')


def test_sw_industry_empty_frame_returns_none(monkeypatch):
    """akshare 返回空帧时降级为 None，不抛异常。"""

    class _FakeAk:
        @staticmethod
        def index_hist_sw(symbol, period='day'):
            return pd.DataFrame()

    import app.core.akshare_lazy as al

    monkeypatch.setattr(al, 'get_akshare', lambda: _FakeAk())

    assert fetch_close_sw_industry('801010.SI', 60) is None
