# -*- coding: utf-8 -*-
"""测试数据源适配器（mock 第三方库）"""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.sync.adapters.akshare_adapter import AkshareAdapter
from app.services.sync.adapters.xalpha_adapter import XalphaAdapter


class TestXalphaAdapter:
    @pytest.fixture
    def adapter(self):
        return XalphaAdapter()

    def test_get_name(self, adapter):
        assert adapter.get_name() == 'xalpha'

    def test_fetch_fund_list_raises(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.fetch_fund_list()

    def test_fetch_stock_methods_raise(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.fetch_stock_list()
        with pytest.raises(NotImplementedError):
            adapter.fetch_stock_price('SH600519')

    def test_fetch_fund_manager_raises(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.fetch_fund_manager('000001')

    @patch('app.services.sync.adapters.xalpha_adapter.xa')
    def test_fetch_fund_nav_returns_records(self, mock_xa, adapter):
        # 模拟基金对象
        mock_fund = MagicMock()
        mock_fund.price = pd.DataFrame(
            {'date': pd.to_datetime(['2025-01-01', '2025-01-02']), 'netvalue': [1.5, 1.6], 'totvalue': [2.0, 2.1]}
        )
        mock_xa.fundinfo.return_value = mock_fund

        records = adapter.fetch_fund_nav('000001')
        assert len(records) == 2
        assert records[0]['unit_nav'] == 1.5
        assert records[0]['acc_nav'] == 2.0
        assert records[0]['fund_code'] == '000001'

    @patch('app.services.sync.adapters.xalpha_adapter.xa')
    def test_fetch_fund_nav_empty(self, mock_xa, adapter):
        mock_fund = MagicMock()
        mock_fund.price = pd.DataFrame()  # 空 DataFrame
        mock_xa.fundinfo.return_value = mock_fund
        records = adapter.fetch_fund_nav('000001')
        assert records == []


class TestAkshareAdapter:
    @pytest.fixture
    def adapter(self):
        return AkshareAdapter()

    def test_get_name(self, adapter):
        assert adapter.get_name() == 'akshare'

    # ── 基金列表 ──
    @patch('app.services.sync.adapters.akshare_adapter.ak')
    def test_fetch_fund_list(self, mock_ak, adapter):
        df = pd.DataFrame(
            {'基金代码': ['000001', '000002'], '基金简称': ['基金A', '基金B'], '基金类型': ['混合型', '股票型']}
        )
        mock_ak.fund_name_em.return_value = df  # 注意接口名
        records = adapter.fetch_fund_list()
        assert len(records) == 2
        assert records[0]['fund_code'] == '000001'
        assert records[0]['name'] == '基金A'

    # ── 股票列表 ──
    @patch('app.services.sync.adapters.akshare_adapter.ak')
    @patch('app.services.sync.adapters.akshare_adapter.get_normalizer')
    def test_fetch_stock_list(self, mock_norm, mock_ak, adapter):
        df = pd.DataFrame({'code': ['600519', '000001'], 'name': ['茅台', '平安']})
        mock_ak.stock_info_a_code_name.return_value = df
        normalizer_mock = MagicMock()
        normalizer_mock.normalize.side_effect = (
            lambda c: (f'SH{c}', 'SH', None) if c == '600519' else (f'SZ{c}', 'SZ', None)
        )
        mock_norm.return_value = normalizer_mock

        records = adapter.fetch_stock_list()
        assert len(records) == 2
        assert records[0]['symbol'] == 'SH600519'

    # ── 股票行情（使用东方财富 _em 接口） ──
    @patch('app.services.sync.adapters.akshare_adapter.ak')
    @patch('app.services.sync.adapters.akshare_adapter.get_normalizer')
    def test_fetch_stock_price(self, mock_norm, mock_ak, adapter):
        # 模拟标准化器返回新浪格式代码
        normalizer_mock = MagicMock()
        normalizer_mock.to_sina_code.return_value = 'sh600519'
        mock_norm.return_value = normalizer_mock

        # 构造新浪接口返回的 DataFrame（列名：date, open, high, low, close, volume）
        df = pd.DataFrame(
            {
                'date': ['2025-01-01'],
                'open': [100.0],
                'high': [105.0],
                'low': [99.0],
                'close': [102.0],
                'volume': [1000.0],
            }
        )
        mock_ak.stock_zh_a_daily.return_value = df

        records = adapter.fetch_stock_price('SH600519')
        assert len(records) == 1
        assert records[0]['close'] == 102
        assert records[0]['trade_date'] == date(2025, 1, 1)
        assert records[0]['source'] == 'akshare_sina'

    # ── 每日实时行情（增量用） ──
    @patch('app.services.sync.adapters.akshare_adapter.ak')
    @patch('app.services.sync.adapters.akshare_adapter.get_normalizer')
    def test_fetch_daily_spot_all(self, mock_norm, mock_ak, adapter):
        normalizer_mock = MagicMock()
        normalizer_mock.normalize.side_effect = (
            lambda c: (f'SH{c}', 'SH', None) if c == '600519' else (f'SZ{c}', 'SZ', None)
        )
        mock_norm.return_value = normalizer_mock

        df = pd.DataFrame(
            {
                '代码': ['600519', '000001'],
                '今开': [100, 12],
                '最高': [105, 13],
                '最低': [99, 11],
                '最新价': [102, 12.5],
                '成交量': [10000, 20000],
            }
        )
        mock_ak.stock_zh_a_spot_em.return_value = df

        records = adapter.fetch_daily_spot_all()
        assert len(records) == 2

    # ── 基金经理（使用 akshare 的 fund_manager_em） ──
    @patch('app.services.sync.adapters.akshare_adapter.ak')
    def test_fetch_fund_manager(self, mock_ak, adapter):
        # 清除可能被其他测试污染的缓存
        if hasattr(adapter, '_fund_manager_cache'):
            delattr(adapter, '_fund_manager_cache')

        df = pd.DataFrame(
            [
                {'序号': 1, '姓名': '张三', '所属公司': '易方达', '现任基金代码': '000001,000002'},
                {'序号': 2, '姓名': '李四', '所属公司': '华夏', '现任基金代码': '000002'},
            ]
        )
        mock_ak.fund_manager_em.return_value = df
        records = adapter.fetch_fund_manager('000001')
        assert len(records) == 1
        assert records[0]['name'] == '张三'
        # 验证 mgr_code 是哈希值
        assert len(records[0]['mgr_code']) == 12
        assert all(c in '0123456789abcdef' for c in records[0]['mgr_code'])

    def test_fund_nav_raises(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.fetch_fund_nav('000001')
