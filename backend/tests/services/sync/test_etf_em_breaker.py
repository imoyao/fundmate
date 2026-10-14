# -*- coding: utf-8 -*-
"""ETF 日线多源链路（腾讯主源 → 东财备源 → 新浪保底）与东财熔断器的单元测试。

背景：2026-10-14 东财 push2his IP 级封锁后拍板主源切腾讯（stock_zh_a_hist_tx，
交叉验证与东财零差异、社区 3 年 0 封禁投诉），东财降为备源并保留熔断；
新浪仅在未复权路径做保底。本文件钉住链路顺序、source 打标、东财 volume
单位换算（手→股）与熔断语义。
"""

import time
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

from app.services.adapters.akshare_adapter import (
    AkshareAdapter,
    _em_kline_breaker,
)

# 熔断计数只认 requests 的连接级异常（内建 ConnectionError 不算，见 _fetch_etf_frame）
_CONN_ERR = requests.exceptions.ConnectionError

START = date(2026, 10, 13)
END = date(2026, 10, 14)


def _df() -> pd.DataFrame:
    """腾讯/新浪同构的英文列样例（下游只读 date/open/high/low/close/volume）。"""
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


def _em_df() -> pd.DataFrame:
    """东财样例：中文列 + volume 单位「手」（入库前须 ×100 归一成「股」）。"""
    return pd.DataFrame(
        [
            {
                '日期': '2026-10-13',
                '开盘': 0.527,
                '最高': 0.530,
                '最低': 0.522,
                '收盘': 0.524,
                '成交量': 2008770,
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


def _ak(tx=None, em=None, sina=None) -> SimpleNamespace:
    """组装 mock ak：默认腾讯/东财均连接级失败、新浪可用。"""
    return SimpleNamespace(
        stock_zh_a_hist_tx=tx if tx is not None else MagicMock(side_effect=_CONN_ERR('tx down')),
        fund_etf_hist_em=em if em is not None else MagicMock(side_effect=_CONN_ERR('em down')),
        fund_etf_hist_sina=sina if sina is not None else MagicMock(return_value=_df()),
    )


def _fetch(adapter, ak, code='159865', adjust=''):
    return adapter._fetch_etf_frame(ak, 'sz', code, START, END, adjust)


class TestSourceChain:
    def test_tx_success_short_circuits(self, adapter):
        """腾讯成功即返回，东财/新浪不得被调用。"""
        ak = _ak(tx=MagicMock(return_value=_df()))
        df, source = _fetch(adapter, ak)
        assert source == 'akshare_tx'
        assert df is not None and not df.empty
        assert ak.fund_etf_hist_em.call_count == 0
        assert ak.fund_etf_hist_sina.call_count == 0

    def test_tx_fail_em_success(self, adapter):
        """腾讯失败回退东财；东财成功须复位熔断计数并标 akshare_em。"""
        ak = _ak(tx=MagicMock(side_effect=_CONN_ERR('tx down')), em=MagicMock(return_value=_em_df()))
        df, source = _fetch(adapter, ak, adjust='qfq')
        assert source == 'akshare_em'
        assert df is not None and not df.empty
        assert ak.fund_etf_hist_sina.call_count == 0  # 复权路径无新浪
        assert not _em_kline_breaker.should_skip(time.time())

    def test_all_fail_unadjusted_falls_to_sina(self, adapter):
        df, source = _fetch(adapter, _ak())
        assert source == 'akshare_sina'
        assert df is not None and not df.empty

    def test_all_fail_qfq_returns_none(self, adapter):
        """腾讯与东财都失败时，qfq 返回 (None, '')——adj_close 由上层回退 close。"""
        df, source = _fetch(adapter, _ak(), adjust='qfq')
        assert df is None
        assert source == ''


class TestCircuitOpens:
    def test_two_em_failures_open_breaker_third_symbol_skips_em(self, adapter):
        ak = _ak()

        # 前两个 symbol：腾讯失败 → 东财尝试（连接级失败计数）→ 新浪保底
        for code in ('159865', '159262'):
            df, source = _fetch(adapter, ak, code=code)
            assert source == 'akshare_sina'
            assert df is not None and not df.empty
        assert ak.fund_etf_hist_em.call_count == 2
        assert ak.fund_etf_hist_sina.call_count == 2

        # 第三个 symbol：熔断已开，未复权跳过东财直切新浪（腾讯仍每次尝试）
        df, source = _fetch(adapter, ak, code='513130')
        assert source == 'akshare_sina'
        assert df is not None and not df.empty
        assert ak.stock_zh_a_hist_tx.call_count == 3  # 主源每次都先试
        assert ak.fund_etf_hist_em.call_count == 2  # 未增加
        assert ak.fund_etf_hist_sina.call_count == 3

    def test_breaker_open_qfq_returns_none_without_em_call(self, adapter):
        ak = _ak()
        _fetch(adapter, ak, code='159865')
        _fetch(adapter, ak, code='159262')  # 打开熔断

        df, source = _fetch(adapter, ak, code='513130', adjust='qfq')
        assert df is None and source == ''
        assert ak.fund_etf_hist_em.call_count == 2  # 未增加
        assert ak.fund_etf_hist_sina.call_count == 2  # 复权路径不走新浪


class TestBreakerLifecycle:
    def test_success_resets_consecutive_count(self, adapter):
        ak = _ak()
        _fetch(adapter, ak, code='159865')  # 东财 1 次失败，未达阈值
        assert not _em_kline_breaker.should_skip(time.time())

        # 一次东财成功即复位（腾讯失败才会尝试东财）
        ok_ak = _ak(em=MagicMock(return_value=_em_df()))
        df, source = _fetch(adapter, ok_ak, code='159262', adjust='qfq')
        assert source == 'akshare_em'

        # 再失败 1 次：因计数已复位，熔断不得打开
        _fetch(adapter, ak, code='513130')
        assert not _em_kline_breaker.should_skip(time.time())

    def test_cooldown_expiry_half_open(self, adapter):
        ak = _ak()
        _fetch(adapter, ak, code='159865')
        _fetch(adapter, ak, code='159262')  # 打开熔断
        assert _em_kline_breaker.should_skip(time.time())

        open_until = _em_kline_breaker._open_until
        assert not _em_kline_breaker.should_skip(open_until + 1)

    def test_non_connection_error_does_not_count(self, adapter):
        """解析错等业务异常不计入熔断：东财始终被尝试，熔断始终不开。"""
        ak = _ak(tx=MagicMock(side_effect=ValueError('tx parse')), em=MagicMock(side_effect=ValueError('parse')))
        for code in ('159865', '159262', '513130'):
            df, source = _fetch(adapter, ak, code=code)
            assert source == 'akshare_sina'
            assert df is not None and not df.empty  # 仍回退新浪
        assert not _em_kline_breaker.should_skip(time.time())
        assert ak.fund_etf_hist_em.call_count == 3  # 从未跳过东财


class TestStockPriceWiring:
    """fetch_stock_price 层：source 按实际命中源打标 + 东财 volume 手→股换算。"""

    def test_tx_primary_source_label(self, adapter):
        ak = _ak(tx=MagicMock(return_value=_df()))
        with patch('app.core.akshare_lazy.get_akshare', return_value=ak):
            records = adapter.fetch_stock_price('SZ159865', start_date=START, end_date=END)
        assert len(records) == 1
        assert records[0]['source'] == 'akshare_tx'
        assert records[0]['volume'] == 200877044  # 腾讯原生即「股」，不换算

    def test_em_backup_volume_normalized_to_shares(self, adapter):
        """东财备源命中时 source 标 akshare_em，volume 由「手」×100 归一为「股」。"""
        ak = _ak(tx=MagicMock(side_effect=_CONN_ERR('tx down')), em=MagicMock(return_value=_em_df()))
        with patch('app.core.akshare_lazy.get_akshare', return_value=ak):
            records = adapter.fetch_stock_price('SZ159865', start_date=START, end_date=END)
        assert len(records) == 1
        assert records[0]['source'] == 'akshare_em'
        assert records[0]['volume'] == 200877000  # 2,008,770 手 × 100

    def test_sina_fallback_source_label(self, adapter):
        """三源全挂后的新浪保底不再被错标成 akshare_em（#2029 脚注指源教训）。"""
        ak = _ak()
        with patch('app.core.akshare_lazy.get_akshare', return_value=ak):
            records = adapter.fetch_stock_price('SZ159865', start_date=START, end_date=END)
        assert len(records) == 1
        assert records[0]['source'] == 'akshare_sina'
        assert records[0]['volume'] == 200877044
