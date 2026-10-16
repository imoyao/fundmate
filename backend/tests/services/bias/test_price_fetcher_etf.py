# -*- coding: utf-8 -*-
"""PriceFetcher ETF akshare 兜底层的腾讯优先链路测试（GitHub #2173）。

钉住：ETF 兜底先调腾讯 stock_zh_a_hist_tx，成功不触东财；腾讯失败回退东财；
双源皆失败返回 (None, None)，由上层走本地缓存降级。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.bias.calculator import ITEM_TYPE_ETF, PriceFetcher

_N = 30  # ≥ BIAS_PERIOD(20)，否则被数据不足分支拦下


def _tx_df(n: int = _N) -> pd.DataFrame:
    dates = pd.date_range('2026-09-01', periods=n, freq='B').strftime('%Y-%m-%d')
    return pd.DataFrame({'date': list(dates), 'close': [1.0 + i * 0.01 for i in range(n)]})


def _em_df(n: int = _N) -> pd.DataFrame:
    dates = pd.date_range('2026-09-01', periods=n, freq='B').strftime('%Y-%m-%d')
    return pd.DataFrame(
        {
            '日期': list(dates),
            '开盘': [1.0] * n,
            '收盘': [2.0 + i * 0.01 for i in range(n)],
            '最高': [2.5] * n,
            '最低': [0.9] * n,
            '成交量': [1000] * n,
        }
    )


@pytest.fixture
def fetcher(tmp_path):
    # max_retries=1 / retry_backoff=0：测试内不重试、不睡眠
    return PriceFetcher(max_retries=1, retry_backoff=0, cache_dir=tmp_path)


def test_etf_prefers_tencent(fetcher):
    ak = SimpleNamespace(
        stock_zh_a_hist_tx=MagicMock(return_value=_tx_df()),
        fund_etf_hist_em=MagicMock(),
    )
    with patch('app.core.akshare_lazy.get_akshare', return_value=ak):
        values, last_date = fetcher._fetch_akshare('159865', ITEM_TYPE_ETF)
    assert ak.stock_zh_a_hist_tx.call_count == 1
    assert ak.fund_etf_hist_em.call_count == 0  # 腾讯成功不触东财
    assert values == pytest.approx([1.0 + i * 0.01 for i in range(_N)])
    assert last_date == str(_tx_df()['date'].iloc[-1])


def test_etf_falls_back_to_em(fetcher):
    ak = SimpleNamespace(
        stock_zh_a_hist_tx=MagicMock(side_effect=ConnectionError('tx down')),
        fund_etf_hist_em=MagicMock(return_value=_em_df()),
    )
    with patch('app.core.akshare_lazy.get_akshare', return_value=ak):
        values, last_date = fetcher._fetch_akshare('159865', ITEM_TYPE_ETF)
    assert ak.fund_etf_hist_em.call_count == 1
    assert values == pytest.approx([2.0 + i * 0.01 for i in range(_N)])
    assert last_date == str(_em_df()['日期'].iloc[-1])


def test_etf_both_sources_down_returns_none(fetcher):
    ak = SimpleNamespace(
        stock_zh_a_hist_tx=MagicMock(side_effect=ConnectionError('tx down')),
        fund_etf_hist_em=MagicMock(side_effect=ConnectionError('em down')),
    )
    with patch('app.core.akshare_lazy.get_akshare', return_value=ak):
        values, last_date = fetcher._fetch_akshare('159865', ITEM_TYPE_ETF)
    assert values is None
    assert last_date is None
