# -*- coding: utf-8 -*-
"""测试数据源适配器"""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.adapters.akshare_adapter import AkshareAdapter
from app.services.adapters.xalpha_adapter import XalphaAdapter, validate_redemption_schedule


class TestXalphaAdapter:
    @pytest.fixture
    def adapter(self):
        return XalphaAdapter()

    def test_get_name(self, adapter):
        assert adapter.get_name() == 'xalpha'

    def test_fetch_fund_list_raises(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.fetch_fund_list()

    @patch('app.services.adapters.xalpha_adapter.requests.get')
    def test_fetch_fund_nav_returns_records(self, mock_get, adapter):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(
                return_value={
                    'Data': {
                        'TotalCount': 2,
                        'LSJZList': [
                            {'FSRQ': '2025-01-02', 'DWJZ': '1.6000', 'LJJZ': '2.1000'},
                            {'FSRQ': '2025-01-01', 'DWJZ': '1.5000', 'LJJZ': '2.0000'},
                        ],
                    }
                }
            ),
        )

        records = adapter.fetch_fund_nav('000001', start_date=date(2025, 1, 1))
        assert len(records) == 2
        assert records[0]['unit_nav'] == 1.6
        assert records[0]['acc_nav'] == 2.1
        assert records[0]['fund_code'] == '000001'
        assert records[0]['is_money_fund'] is False

    @patch('app.services.adapters.xalpha_adapter.requests.get')
    def test_fetch_fund_nav_empty(self, mock_get, adapter):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={'Data': {'TotalCount': 0, 'LSJZList': []}}),
        )
        records = adapter.fetch_fund_nav('000001', start_date=date(2025, 1, 1))
        assert records == []

    @patch('app.services.adapters.xalpha_adapter.requests.get')
    def test_fetch_fund_nav_money_fund_uses_pingzhong(self, mock_get, adapter):
        """货币基金：lsjz 增量返回每万份收益（SYType），应回退 pingzhongdata 解析"""
        pz_text = 'var Data_millionCopiesIncome = [[1735689600000, 0.5], [1735776000000, 0.4]];'
        mock_get.side_effect = [
            MagicMock(
                status_code=200,
                json=MagicMock(return_value={'Data': {'SYType': '每万份收益', 'TotalCount': 2, 'LSJZList': []}}),
            ),
            MagicMock(status_code=200, text=pz_text),
        ]

        records = adapter.fetch_fund_nav('000198', start_date=date(2025, 1, 1))
        assert len(records) == 2
        assert records[0]['is_money_fund'] is True
        assert records[0]['unit_nav'] == 0.5
        assert records[0]['fund_code'] == '000198'

    def test_fetch_fund_nav_by_date(self, adapter):
        with patch('app.services.adapters.xalpha_adapter.requests.get') as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=MagicMock(return_value={'Data': {'LSJZList': [{'FSRQ': '2025-01-01', 'DWJZ': '1.5000'}]}}),
            )
            nav = adapter.fetch_fund_nav_by_date('000001', date(2025, 1, 1))
            assert nav == 1.5

    def test_fetch_fund_nav_by_date_money_fund(self, adapter):
        """货币基金净值恒为 1.0，lsjz 返回的 DWJZ 是万份收益而非单位净值"""
        with patch('app.services.adapters.xalpha_adapter.requests.get') as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=MagicMock(
                    return_value={
                        'Data': {'SYType': '每万份收益', 'LSJZList': [{'FSRQ': '2025-01-01', 'DWJZ': '0.2251'}]}
                    }
                ),
            )
            nav = adapter.fetch_fund_nav_by_date('000198', date(2025, 1, 1))
            assert nav == 1.0

    def test_fetch_fund_nav_by_date_no_data(self, adapter):
        with patch('app.services.adapters.xalpha_adapter.requests.get') as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=MagicMock(return_value={'Data': {'LSJZList': []}}),
            )
            assert adapter.fetch_fund_nav_by_date('000001', date(2025, 1, 1)) is None

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

    def test_parse_holding_range_units_and_forms(self, adapter):
        """「年」不能当「天」，且「大于X，小于等于Y」不能被吃成从 0 天起

        旧实现只认「大于等于X，小于Y」，于是天天基金现在的写法
        「大于7天，小于等于30天」落进 ``elif '小于'`` 分支被写成 ``(0, 30)``，
        「大于30天，小于等于2年」被写成 ``(0, 2)``——2 年变 2 天。
        """
        assert adapter._parse_holding_range('小于等于7天') == (0, 8)
        assert adapter._parse_holding_range('小于7天') == (0, 7)
        assert adapter._parse_holding_range('大于7天，小于等于30天') == (8, 31)
        assert adapter._parse_holding_range('大于等于7天，小于30天') == (7, 30)
        assert adapter._parse_holding_range('大于等于7天') == (7, None)
        # 年 → 天：1年 = 365 天；「小于等于2年」= ≤730 天，而 end_day 是不含上界 → 731
        assert adapter._parse_holding_range('大于30天，小于等于2年') == (31, 731)
        assert adapter._parse_holding_range('大于2年，小于等于3年') == (731, 1096)
        assert adapter._parse_holding_range('大于3年') == (1096, None)
        assert adapter._parse_holding_range('小于等于1年') == (0, 366)
        assert adapter._parse_holding_range('大于等于2年') == (730, None)
        assert adapter._parse_holding_range('不满7天') == (0, 7)
        assert adapter._parse_holding_range('持有期限') is None

    def test_parse_redemption_schedule_real_page_with_year_tiers(self, adapter):
        """000513 费率页原文（2026-10-18 实测抓取）→ 每档唯一且阶梯可用"""
        feeinfo = [
            '小于等于7天',
            '1.50%',
            '大于7天，小于等于30天',
            '0.75%',
            '大于30天，小于等于2年',
            '0.60%',
            '大于2年，小于等于3年',
            '0.30%',
            '大于3年',
            '0.00%',
        ]
        schedule = adapter._parse_redemption_schedule(feeinfo)
        assert schedule == [
            {'start_day': 0, 'end_day': 8, 'rate': 1.5},
            {'start_day': 8, 'end_day': 31, 'rate': 0.75},
            {'start_day': 31, 'end_day': 731, 'rate': 0.6},
            {'start_day': 731, 'end_day': 1096, 'rate': 0.3},
            {'start_day': 1096, 'end_day': None, 'rate': 0.0},
        ]
        assert validate_redemption_schedule(schedule) == []

    def test_parse_first_tier_starting_at_one_day_is_normalized(self, adapter):
        """首档写「大于等于1天」的页面必须归一到 0 天起（001678 实测页面）

        否则持有 0 天的份额匹配不到任何档 → 赎回费被算成 0；校验器也会判「未覆盖
        0 天起」而拒写（2026-10-18 实测：这批 29 只曾因此全部被拒）。
        """
        feeinfo = [
            '大于等于1天，小于7天',
            '1.50%',
            '大于等于7天，小于30天',
            '0.75%',
            '大于等于30天，小于365天',
            '0.50%',
            '大于等于730天',
            '0.00%',
        ]
        schedule = adapter._parse_redemption_schedule(feeinfo)
        assert schedule == [
            {'start_day': 0, 'end_day': 7, 'rate': 1.5},
            {'start_day': 7, 'end_day': 30, 'rate': 0.75},
            {'start_day': 30, 'end_day': 365, 'rate': 0.5},
            {'start_day': 730, 'end_day': None, 'rate': 0.0},
        ]
        assert validate_redemption_schedule(schedule) == []

    def test_first_tier_starting_beyond_one_day_is_left_alone(self, adapter):
        """首档下界 ≥2（定开型等）不做归一：那是产品规则，交给校验器拒写"""
        schedule = adapter._parse_redemption_schedule(['大于等于30天', '0.00%'])
        assert schedule == [{'start_day': 30, 'end_day': None, 'rate': 0.0}]
        assert any('未覆盖 0 天' in p for p in validate_redemption_schedule(schedule))

    def test_validate_rejects_broken_schedules(self, adapter):
        """四类坏阶梯都必须判为不可用（写侧据此拒写）"""
        dup = [{'start_day': 0, 'end_day': 7, 'rate': 1.5}, {'start_day': 0, 'end_day': 7, 'rate': 0.75}]
        assert any('区间重复' in p for p in validate_redemption_schedule(dup))

        inverted = [{'start_day': 0, 'end_day': 7, 'rate': 1.5}, {'start_day': 7, 'end_day': 1, 'rate': 0.1}]
        assert any('区间非法' in p for p in validate_redemption_schedule(inverted))

        no_zero = [{'start_day': 30, 'end_day': None, 'rate': 0.0}]
        assert any('未覆盖 0 天' in p for p in validate_redemption_schedule(no_zero))

        overlapping = [{'start_day': 0, 'end_day': 90, 'rate': 0.1}, {'start_day': 30, 'end_day': None, 'rate': 0.0}]
        assert any('重叠' in p for p in validate_redemption_schedule(overlapping))

        # 空阶梯 = 上游没给，不算错误（调用方直接跳过写入）
        assert validate_redemption_schedule([]) == []

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

    @patch('app.core.akshare_lazy._AKSHARE')
    def test_fetch_fund_list(self, mock_ak, adapter):
        df = pd.DataFrame(
            {'基金代码': ['000001', '000002'], '基金简称': ['基金A', '基金B'], '基金类型': ['混合型', '股票型']}
        )
        mock_ak.fund_name_em.return_value = df
        records = adapter.fetch_fund_list()
        assert len(records) == 2
        assert records[0]['fund_code'] == '000001'

    @patch('app.core.akshare_lazy._AKSHARE')
    @patch('app.services.adapters.akshare_adapter.get_normalizer')
    def test_fetch_stock_list(self, mock_norm, mock_ak, adapter):
        df = pd.DataFrame({'code': ['600519', '000001'], 'name': ['茅台', '平安']})
        mock_ak.stock_info_a_code_name.return_value = df
        normalizer_mock = MagicMock()
        normalizer_mock.normalize.side_effect = lambda c: (
            (f'SH{c}', 'SH', None) if c == '600519' else (f'SZ{c}', 'SZ', None)
        )
        mock_norm.return_value = normalizer_mock

        records = adapter.fetch_stock_list()
        assert len(records) == 2
        assert records[0]['symbol'] == 'SH600519'

    @patch('app.core.akshare_lazy._AKSHARE')
    @patch('app.services.adapters.akshare_adapter.get_normalizer')
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
