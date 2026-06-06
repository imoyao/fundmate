# tests/services/importer/test_ths_stock_parser.py
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from app.services.importer.parsers.ths_stock import THSStockParser

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


# 真实样本暂不使用，因为集成测试依赖旧解析器生成 CSV，此处跳过
# FIXTURE_PATH = BASE_DIR / "tests" / "fixtures" / "ths_sample.csv"


class TestTHSStockParserRowLogic:
    """测试 _parse_row 核心解析逻辑"""

    @pytest.fixture
    def parser(self):
        return THSStockParser()

    def _make_series(self, **kwargs):
        """构造同花顺格式的 Series，列名用中文（原始列名），值按需覆盖"""
        defaults = {
            '证券代码': '600519',
            '证券名称': '测试股票',
            '操作': '证券买入',
            '成交数量': '100',
            '成交均价': '1650.00',
            '成交金额': '165000.00',
            '发生金额': '-165015.00',
            '佣金': '5.00',
            '印花税': '8.50',
            '过户费': '1.00',
            '其他杂费': '0.50',
            '币种': 'CNY',
            '交收日期': '20220101',
            '合同编号': '123',
            'fee': '15.00',  # 模拟 parse() 合并后的总费用
        }
        defaults.update(kwargs)
        return pd.Series(defaults)

    def test_parse_buy(self, parser):
        """买入：金额应为发生金额绝对值（已含费）"""
        row = self._make_series()
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.business_type == 'buy'
        assert record.symbol == 'SH600519'
        assert record.shares == Decimal('100')
        assert record.nav == Decimal('1650.00')
        assert record.fee == Decimal('15.00')
        # 买入金额 = abs(发生金额) = 165015
        assert record.amount == Decimal('165015.00')

    def test_parse_sell(self, parser):
        """卖出：金额应为发生金额本身（到账金额）"""
        row = self._make_series(
            操作='证券卖出',
            成交金额='80000.00',
            发生金额='79985.00',
            佣金='3.00',
            印花税='10.00',
            过户费='1.00',
            其他杂费='1.00',
            fee='15.00',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.business_type == 'sell'
        # 卖出金额 = 发生金额 = 79985
        assert record.amount == Decimal('79985.00')

    def test_parse_dividend(self, parser):
        """分红：发生金额直接取绝对值"""
        row = self._make_series(
            操作='红利入账',
            成交数量='0',
            成交均价='0',
            成交金额='0',
            发生金额='500.00',
            佣金='0',
            印花税='0',
            过户费='0',
            其他杂费='0',
            fee='0',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.business_type == 'dividend_cash'
        assert record.amount == Decimal('500.00')

    def test_contract_id_format(self, parser):
        assert parser._format_contract_id('123') == '0000000123'
        assert parser._format_contract_id(None) == ''
        assert parser._format_contract_id('') == ''

    def test_parse_money_fund(self, parser):
        """银河水星现金添利应被识别为 money_fund"""
        row = self._make_series(
            证券代码='970164',
            证券名称='银河水星现金添利',
            操作='基金申购拨出',
            成交数量='0',
            成交均价='0',
            成交金额='0',
            发生金额='-10000',
            佣金='0',
            印花税='0',
            过户费='0',
            其他杂费='0',
            fee='0',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.asset_type == 'money_fund', f'期望 money_fund，实际 {record.asset_type}'
        assert record.symbol == 'SH970164'

    def test_parse_reverse_repo(self, parser):
        """GC007 应被识别为 reverse_repo"""
        row = self._make_series(
            证券代码='204001',
            证券名称='GC007',
            操作='通用回购逆回',
            成交数量='10',
            成交均价='2.5',
            成交金额='10000',
            发生金额='-10000',
            佣金='0',
            印花税='0',
            过户费='0',
            其他杂费='0',
            fee='0',
        )
        record = parser._parse_row(row, line_num=2)
        assert record is not None
        assert record.asset_type == 'reverse_repo', f'期望 reverse_repo，实际 {record.asset_type}'
        assert record.symbol == 'SH204001'


class TestTHSStockParserIntegration:
    """集成测试：完整 parse 流程"""

    @pytest.fixture
    def parser(self):
        return THSStockParser()

    def test_parse_cash_transfer_integration(self, parser):
        """资金划转集成测试"""
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t发生金额\t'
            '佣金\t印花税\t过户费\t其他杂费\t币种\t交收日期\t合同编号\n'
            '\t\t银行转证券\t0\t0\t0\t100000\t0\t0\t0\t0\tCNY\t20220101\t\n'
        )
        records, _ = parser.parse(csv_content.encode('gbk'))
        assert len(records) == 1
        assert records[0].asset_type == 'cash'
        assert records[0].business_type == 'deposit'

    def test_parse_empty_file(self, parser):
        records, errors = parser.parse(b'')
        assert len(records) == 0
        assert len(errors) == 1

    def test_parse_real_csv_sample(self, parser):
        """使用 Tab 分隔的 UTF-8 样本进行集成测试"""
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t发生金额\t佣金\t印花税\t过户费\t其他杂费\t合同编号\t交收日期\n'
            '600519\t测试股票\t证券买入\t100\t1650.00\t165000.00\t-165015.00\t5.00\t8.50\t1.00\t0.50\t123\t20220101\n'
        )
        records, _ = parser.parse(csv_content.encode('utf-8'))
        assert len(records) == 1
        assert records[0].fee == Decimal('15.00')
        assert records[0].transaction_id == '0000000123'
