# -*- coding: utf-8 -*-
"""ETF 东财 K 线熔断器（`_EmKlineBreaker` 接入 `_fetch_etf_frame`）的单元测试。

背景：2026-10-14 实测 push2his.eastmoney.com 对本机 IP 级拒绝期间，每只 ETF
白烧 2×3 次重试才回退新浪；熔断后连续连接级失败达阈值即跳过东财。
"""

import time
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
import requests

from app.services.adapters.akshare_adapter import (
    AkshareAdapter,
    _em_kline_breaker,
)

START = date(2026, 10, 13)
END = date(2026, 10, 14)


def _sina_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                'date': '2026-10-13',
                'open': 0.527,
                'high': 0.530,
                'low': 0.522,
                'close': 0.524,
                'volume': 200877044,
            }
        ]
    )


@pytest.fixture(autouse=True)
def _reset_breaker():
    _em_kline_breaker.reset()
    yield
    _em_kline_breaker.reset()


@pytest.fixture
def adapter():
    return AkshareAdapter()


def _em_raising_ak() -> SimpleNamespace:
    return SimpleNamespace(
        fund_etf_hist_em=MagicMock(side_effect=requests.exceptions.ConnectionError('boom')),
        fund_etf_hist_sina=MagicMock(return_value=_sina_df()),
    )


def _fetch(adapter, ak, code='159865', adjust=''):
    return adapter._fetch_etf_frame(ak, 'sz', code, START, END, adjust)


class TestCircuitOpens:
    def test_two_failures_open_breaker_third_symbol_skips_em(self, adapter):
        ak = _em_raising_ak()

        # 前两个 symbol：各走一次东财（失败）后回退新浪
        for code in ('159865', '159262'):
            df = _fetch(adapter, ak, code=code)
            assert df is not None and not df.empty
        assert ak.fund_etf_hist_em.call_count == 2
        assert ak.fund_etf_hist_sina.call_count == 2

        # 第三个 symbol：熔断已开，未复权直切新浪，东财不再被调用
        df = _fetch(adapter, ak, code='513130')
        assert df is not None and not df.empty
        assert ak.fund_etf_hist_em.call_count == 2  # 未增加
        assert ak.fund_etf_hist_sina.call_count == 3

    def test_breaker_open_qfq_returns_none_without_em_call(self, adapter):
        ak = _em_raising_ak()
        _fetch(adapter, ak, code='159865')
        _fetch(adapter, ak, code='159262')  # 打开熔断

        assert _fetch(adapter, ak, code='513130', adjust='qfq') is None
        assert ak.fund_etf_hist_em.call_count == 2  # 未增加
        assert ak.fund_etf_hist_sina.call_count == 2  # 复权路径不走新浪


class TestBreakerLifecycle:
    def test_success_resets_consecutive_count(self, adapter):
        ak = _em_raising_ak()
        _fetch(adapter, ak, code='159865')  # 1 次失败，未达阈值
        assert not _em_kline_breaker.should_skip(time.time())

        # 一次成功即复位
        ok_ak = SimpleNamespace(
            fund_etf_hist_em=MagicMock(return_value=_sina_df()),
            fund_etf_hist_sina=MagicMock(return_value=_sina_df()),
        )
        _fetch(adapter, ok_ak, code='159262', adjust='qfq')

        # 再失败 1 次：因计数已复位，熔断不得打开
        _fetch(adapter, ak, code='513130')
        assert not _em_kline_breaker.should_skip(time.time())

    def test_cooldown_expiry_half_open(self, adapter):
        ak = _em_raising_ak()
        _fetch(adapter, ak, code='159865')
        _fetch(adapter, ak, code='159262')  # 打开熔断
        assert _em_kline_breaker.should_skip(time.time())

        open_until = _em_kline_breaker._open_until
        assert not _em_kline_breaker.should_skip(open_until + 1)

    def test_non_connection_error_does_not_count(self, adapter):
        ak = SimpleNamespace(
            fund_etf_hist_em=MagicMock(side_effect=ValueError('parse')),
            fund_etf_hist_sina=MagicMock(return_value=_sina_df()),
        )
        for code in ('159865', '159262', '513130'):
            df = _fetch(adapter, ak, code=code)
            assert df is not None and not df.empty  # 仍回退新浪
        assert not _em_kline_breaker.should_skip(time.time())
        assert ak.fund_etf_hist_em.call_count == 3  # 从未跳过东财
