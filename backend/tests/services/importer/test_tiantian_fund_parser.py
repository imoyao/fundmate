# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/7 15:05
# File : test_tiantian_fund_parser.py
# tests/services/importer/test_tiantian_fund_parser.py
"""天天基金解析器测试"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.importer.parsers.tiantian_fund import TiantianFundParser


class TestTiantianFundParser:
    @pytest.fixture
    def parser(self):
        return TiantianFundParser()

    def test_parse_normal_buy(self, parser):
        """正常申购记录"""
        csv_content = (
            '确认日期,基金代码,基金简称,业务类型,确认状态,确认份额,确认金额,手续费,确认净值,关联银行卡\n'
            '2023-02-17,003474,南方天天利货币B,买基金,成功,10.00,10.00,0.00,1.0000,浦发银行 | 7239\n'
        )
        records, errors = parser.parse(csv_content.encode('utf-8'))
        assert len(records) == 1
        assert len(errors) == 0
        r = records[0]
        assert r.symbol == '003474'
        assert r.name == '南方天天利货币B'
        assert r.business_type == 'buy'
        assert r.amount == Decimal('10.00')
        assert r.shares == Decimal('10.00')
        assert r.fee == Decimal('0.00')
        assert r.nav == Decimal('1.0000')
        assert r.confirm_date == date(2023, 2, 17)
        assert r.account_name == '浦发银行'  # 银行卡名提取
        assert r.source == 'tiantian_fund'

    def test_parse_activity_grant_as_deposit(self, parser):
        """活动发放映射为存入"""
        csv_content = (
            '确认日期,基金代码,基金简称,业务类型,确认状态,确认份额,确认金额,手续费,确认净值,关联银行卡\n'
            '2023-02-15,000638,富国富钱包货币A,活动发放,成功,10.00,10.00,0.00,1.0000,浦发银行 | 7239\n'
        )
        records, _ = parser.parse(csv_content.encode('utf-8'))
        assert len(records) == 1
        assert records[0].business_type == 'deposit'

    def test_parse_super_convert_in(self, parser):
        """超级转换-转入映射为买入"""
        csv_content = (
            '确认日期,基金代码,基金简称,业务类型,确认状态,确认份额,确认金额,手续费,确认净值,关联银行卡\n'
            '2023-02-16,012841,华泰柏瑞交易货币C,超级转换-转入,成功,10.00,10.00,0.00,1.0000,浦发银行 | 7239\n'
        )
        records, _ = parser.parse(csv_content.encode('utf-8'))
        assert records[0].business_type == 'buy'

    def test_parse_super_convert_out_as_sell(self, parser):
        """超级转换-转出映射为卖出"""
        csv_content = (
            '确认日期,基金代码,基金简称,业务类型,确认状态,确认份额,确认金额,手续费,确认净值,关联银行卡\n'
            '2023-02-16,162206,宏利货币A,超级转换-转出,成功,10.00,10.00,0.00,1.0000,浦发银行 | 7239\n'
        )
        records, _ = parser.parse(csv_content.encode('utf-8'))
        assert records[0].business_type == 'sell'

    def test_parse_normal_withdrawal_as_sell(self, parser):
        """普通取现映射为卖出"""
        csv_content = (
            '确认日期,基金代码,基金简称,业务类型,确认状态,确认份额,确认金额,手续费,确认净值,关联银行卡\n'
            '2023-02-07,000638,富国富钱包货币A,普通取现,成功,2.64,2.64,0.00,1.0000,浦发银行 | 7239\n'
        )
        records, _ = parser.parse(csv_content.encode('utf-8'))
        assert records[0].business_type == 'sell'

    def test_skip_failed_status(self, parser):
        """确认状态非成功时应被跳过"""
        csv_content = (
            '确认日期,基金代码,基金简称,业务类型,确认状态,确认份额,确认金额,手续费,确认净值,关联银行卡\n'
            '2023-02-01,001234,某基金,买基金,失败,10.00,10.00,0.00,1.0000,银行 | 1234\n'
            '2023-02-02,003474,南方天天利货币B,买基金,成功,10.00,10.00,0.00,1.0000,浦发银行 | 7239\n'
        )
        records, errors = parser.parse(csv_content.encode('utf-8'))
        assert len(records) == 1
        assert records[0].symbol == '003474'

    def test_skip_header_rows_when_pasted_multiple_times(self, parser):
        """用户多次复制时混入的表头行应被跳过"""
        csv_content = (
            '确认日期,基金代码,基金简称,业务类型,确认状态,确认份额,确认金额,手续费,确认净值,关联银行卡\n'
            '2023-02-17,003474,南方天天利货币B,买基金,成功,10.00,10.00,0.00,1.0000,浦发银行 | 7239\n'
            '确认日期,基金代码,基金简称,业务类型,确认状态,确认份额,确认金额,手续费,确认净值,关联银行卡\n'
            '2023-02-18,012841,华泰柏瑞交易货币C,买基金,成功,20.00,20.00,0.00,1.0000,银行 | 1111\n'
        )
        records, errors = parser.parse(csv_content.encode('utf-8'))
        assert len(records) == 2

    def test_missing_required_columns(self, parser):
        """缺少必填列时应返回错误"""
        csv_content = (
            '确认日期,基金代码,基金简称,确认状态,确认份额,确认金额\n'  # 缺少业务类型
            '2023-02-17,003474,南方天天利货币B,成功,10.00,10.00\n'
        )
        records, errors = parser.parse(csv_content.encode('utf-8'))
        assert len(records) == 0
        assert len(errors) == 1
        assert '缺少必填列' in errors[0].message

    def test_invalid_fund_code(self, parser):
        """无效基金代码应抛出ValueError并记录为错误"""
        csv_content = (
            '确认日期,基金代码,基金简称,业务类型,确认状态,确认份额,确认金额,手续费,确认净值,关联银行卡\n'
            '2023-02-17,abc,某基金,买基金,成功,10.00,10.00,0.00,1.0000,银行 | 1234\n'
        )
        records, errors = parser.parse(csv_content.encode('utf-8'))
        assert len(records) == 0
        assert len(errors) == 1
        assert '无法识别基金代码' in errors[0].message

    def test_empty_bank_info(self, parser):
        """关联银行卡为空时，账户名称应为空"""
        csv_content = (
            '确认日期,基金代码,基金简称,业务类型,确认状态,确认份额,确认金额,手续费,确认净值,关联银行卡\n'
            '2023-02-17,003474,南方天天利货币B,买基金,成功,10.00,10.00,0.00,1.0000,\n'
        )
        records, _ = parser.parse(csv_content.encode('utf-8'))
        assert records[0].account_name == ''

    def test_validate_all_valid(self, parser):
        """校验全部通过"""
        csv_content = (
            '确认日期,基金代码,基金简称,业务类型,确认状态,确认份额,确认金额,手续费,确认净值,关联银行卡\n'
            '2023-02-17,003474,南方天天利货币B,买基金,成功,10.00,10.00,0.00,1.0000,浦发银行 | 7239\n'
        )
        records, _ = parser.parse(csv_content.encode('utf-8'))
        valid, errors = parser.validate(records)
        assert len(valid) == 1
        assert len(errors) == 0

    def test_validate_future_date_rejected(self, parser):
        """未来日期校验不通过"""
        csv_content = (
            '确认日期,基金代码,基金简称,业务类型,确认状态,确认份额,确认金额,手续费,确认净值,关联银行卡\n'
            '2099-01-01,003474,南方天天利货币B,买基金,成功,10.00,10.00,0.00,1.0000,浦发银行 | 7239\n'
        )
        records, _ = parser.parse(csv_content.encode('utf-8'))
        valid, errors = parser.validate(records)
        assert len(valid) == 0
        assert len(errors) == 1
        assert '确认日期不能晚于今天' in errors[0].message
