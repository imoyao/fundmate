# tests/services/importer/test_standard_parser.py
# -*- coding: utf-8 -*-
"""测试标准模板解析器"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.importer.parsers.standard import FundStandardParser, StockStandardParser


class TestStandardFundParser:
    """基金标准模板测试"""

    @pytest.fixture
    def parser(self):
        return FundStandardParser()

    def test_parse_normal_fund_record(self, parser):
        """正常基金申购记录"""
        csv_content = (
            '确认日期,交易日期,基金代码,基金名称,业务类型,份额,金额,手续费,净值,账户名称,交易流水号\n'
            '2023-06-01,2023-05-31,014330,国联优势产业混合C,申购,11.14,10.00,0.00,0.8976,我的基金账户,\n'
        )
        records, errors = parser.parse(csv_content.encode('utf-8'))
        assert len(records) == 1
        assert len(errors) == 0

        r = records[0]
        assert r.symbol == '014330'
        assert r.name == '国联优势产业混合C'
        assert r.business_type == 'buy'
        assert r.amount == Decimal('10.00')
        assert r.shares == Decimal('11.14')
        assert r.nav == Decimal('0.8976')
        assert r.account_name == '我的基金账户'
        assert r.confirm_date == date(2023, 6, 1)
        assert r.trade_date == date(2023, 5, 31)

    def test_parse_minimal_required_fields(self, parser):
        """只填必填字段，名称和账户为空"""
        csv_content = '确认日期,基金代码,业务类型,金额\n2023-06-01,014330,申购,10.00\n'
        records, errors = parser.parse(csv_content.encode('utf-8'))
        assert len(records) == 1
        assert len(errors) == 0

        r = records[0]
        assert r.symbol == '014330'
        assert r.name == ''
        assert r.account_name == ''
        assert r.amount == Decimal('10.00')

    def test_parse_missing_required_column(self, parser):
        """缺少必填列"""
        csv_content = '确认日期,基金代码,业务类型\n2023-06-01,014330,申购\n'
        records, errors = parser.parse(csv_content.encode('utf-8'))
        assert len(records) == 0
        assert len(errors) == 1
        assert '缺少必填列' in errors[0].message

    def test_parse_code_normalization(self, parser):
        """基金代码标准化：去空格、补零"""
        csv_content = '确认日期,基金代码,业务类型,金额\n2023-06-01, 14330 ,申购,10.00\n'
        records, _ = parser.parse(csv_content.encode('utf-8'))
        assert records[0].symbol == '014330'

    def test_parse_invalid_code(self, parser):
        """无效基金代码应返回一条错误记录"""
        csv_content = '确认日期,基金代码,业务类型,金额\n2023-06-01,abc,申购,10.00\n'
        records, errors = parser.parse(csv_content.encode('utf-8'))
        # 应有一条记录，但带有错误信息
        assert len(records) == 1
        assert records[0].error is not None
        assert '无法识别基金代码' in records[0].error
        # 没有解析层面的致命错误
        assert len(errors) == 0

    def test_validate_normal(self, parser):
        """校验通过"""
        csv_content = '确认日期,基金代码,业务类型,金额\n2023-06-01,014330,申购,10.00\n'
        records, _ = parser.parse(csv_content.encode('utf-8'))
        valid, errors = parser.validate(records)
        assert len(valid) == 1
        assert len(errors) == 0

    def test_validate_invalid_business_type(self, parser):
        """不支持的业务类型"""
        csv_content = '确认日期,基金代码,业务类型,金额\n2023-06-01,014330,未知类型,10.00\n'
        records, _ = parser.parse(csv_content.encode('utf-8'))
        valid, errors = parser.validate(records)
        assert len(valid) == 0
        assert len(errors) > 0

    def test_validate_future_date(self, parser):
        """日期不能晚于今天"""
        csv_content = '确认日期,基金代码,业务类型,金额\n2099-01-01,014330,申购,10.00\n'
        records, _ = parser.parse(csv_content.encode('utf-8'))
        valid, errors = parser.validate(records)
        assert len(valid) == 0
        assert len(errors) > 0


class TestStandardStockParser:
    """股票标准模板测试"""

    @pytest.fixture
    def parser(self):
        return StockStandardParser()

    def test_parse_normal_stock_record(self, parser):
        """正常股票买入记录"""
        csv_content = (
            '确认日期,交易日期,股票代码,股票名称,业务类型,数量(股),成交均价,成交金额,手续费,账户名称,合同编号\n'
            '2023-06-01,2023-06-01,SH600519,贵州茅台,买入,100,1650.00,165000.00,12.50,我的股票账户,\n'
        )
        records, errors = parser.parse(csv_content.encode('utf-8'))
        assert len(records) == 1
        assert len(errors) == 0

        r = records[0]
        assert r.symbol == 'SH600519'
        assert r.name == '贵州茅台'
        assert r.business_type == 'buy'
        assert r.amount == Decimal('165000.00')
        assert r.shares == Decimal('100')
        assert r.nav == Decimal('1650.00')
