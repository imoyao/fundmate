# -*- coding: utf-8 -*-
"""测试数据源适配器"""

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

    @patch('app.services.sync.adapters.xalpha_adapter.xa')
    def test_fetch_fund_nav_returns_records(self, mock_xa, adapter):
        mock_fund = MagicMock()
        mock_fund.price = pd.DataFrame(
            {'netvalue': [1.5, 1.6], 'totvalue': [2.0, 2.1]}, index=pd.to_datetime(['2025-01-01', '2025-01-02'])
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
        mock_fund.price = pd.DataFrame()
        mock_xa.fundinfo.return_value = mock_fund
        records = adapter.fetch_fund_nav('000001')
        assert records == []

    def test_parse_redemption_schedule_normal(self, adapter):
        feeinfo = ['小于7天', '1.50%', '大于等于7天，小于30天', '0.75%', '大于等于30天', '0.00%']
        schedule = adapter._parse_redemption_schedule(feeinfo)
        assert len(schedule) == 3
        assert schedule[0] == {'start_day': 0, 'end_day': 7, 'rate': 1.5}
        assert schedule[1] == {'start_day': 7, 'end_day': 30, 'rate': 0.75}
        assert schedule[2] == {'start_day': 30, 'end_day': None, 'rate': 0.0}

    def test_parse_redemption_schedule_none(self, adapter):
        assert adapter._parse_redemption_schedule(None) == []
        assert adapter._parse_redemption_schedule([]) == []

    def test_parse_redemption_schedule_short_list(self, adapter):
        assert adapter._parse_redemption_schedule(['小于7天']) == []

    def test_fetch_fund_manager_raises(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.fetch_fund_manager('000001')

    def test_stock_methods_raise(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.fetch_stock_list()
        with pytest.raises(NotImplementedError):
            adapter.fetch_stock_price('SH600519')


class TestAkshareAdapter:
    @pytest.fixture
    def adapter(self):
        return AkshareAdapter()

    def test_get_name(self, adapter):
        assert adapter.get_name() == 'akshare'

    @patch('app.services.sync.adapters.akshare_adapter.ak')
    def test_fetch_fund_list(self, mock_ak, adapter):
        df = pd.DataFrame(
            {'基金代码': ['000001', '000002'], '基金简称': ['基金A', '基金B'], '基金类型': ['混合型', '股票型']}
        )
        mock_ak.fund_name_em.return_value = df
        records = adapter.fetch_fund_list()
        assert len(records) == 2
        assert records[0]['fund_code'] == '000001'

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

    @patch('app.services.sync.adapters.akshare_adapter.ak')
    @patch('app.services.sync.adapters.akshare_adapter.get_normalizer')
    def test_fetch_stock_price(self, mock_norm, mock_ak, adapter):
        normalizer_mock = MagicMock()
        normalizer_mock.to_sina_code.return_value = 'sh600519'
        mock_norm.return_value = normalizer_mock

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

    def test_parse_fund_info_dataframe(self, adapter):
        df = pd.DataFrame(
            {
                '字段': ['投资类型', '基金管理人', '基金全称', '成立日期', '业绩比较基准', '基金经理'],
                '值': ['混合型', '华夏基金', '华夏成长混合', '2001-12-18', '沪深300', '张三,李四'],
            }
        )
        result = adapter._parse_fund_info_dataframe(df, '000001')
        assert result['fund_type_raw'] == '混合型'
        assert result['company_name'] == '华夏基金'
        assert result['fund_full_name'] == '华夏成长混合'
        assert result['create_time'] == date(2001, 12, 18)
        assert result['benchmark'] == '沪深300'
        assert result['manager_names'] == ['张三', '李四']

    def test_parse_fund_info_dataframe_empty(self, adapter):
        assert adapter._parse_fund_info_dataframe(None, '000001') == {}
        assert adapter._parse_fund_info_dataframe(pd.DataFrame(), '000001') == {}

    def test_fund_nav_raises(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.fetch_fund_nav('000001')
