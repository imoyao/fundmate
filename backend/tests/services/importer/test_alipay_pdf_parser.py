# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/11 20:50
# File : test_alipay_pdf_parser.py
# tests/services/importer/test_alipay_pdf_parser.py
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.services.importer.parsers.alipay_pdf import AlipayPDFParser


@pytest.fixture
def parser():
    return AlipayPDFParser()


def make_mock_page(table_data):
    """模拟 pdfplumber 页面，extract_table 返回指定表格"""
    page = MagicMock()
    page.extract_table.return_value = table_data
    return page


def mock_pdf_open(pages):
    """模拟 pdfplumber.open 返回指定页面列表"""
    mock = MagicMock()
    mock.__enter__.return_value.pages = pages
    return mock


# ── 基础解析流程 ──
class TestBasicParsing:
    def test_empty_pdf(self, parser):
        with patch('pdfplumber.open', return_value=mock_pdf_open([])):
            records, errors = parser.parse(b'dummy')
        assert records == []
        assert len(errors) == 1
        assert '未提取到交易数据' in errors[0].message

    def test_no_table_on_pages(self, parser):
        page = make_mock_page(None)
        with patch('pdfplumber.open', return_value=mock_pdf_open([page])):
            records, errors = parser.parse(b'dummy')
        assert records == []
        assert len(errors) == 1

    def test_skip_non_data_pages(self, parser):
        # 无表头关键词的说明页被跳过
        page = make_mock_page([['说明', ''], ['一些文字', '']])
        with patch('pdfplumber.open', return_value=mock_pdf_open([page])):
            records, errors = parser.parse(b'dummy')
        assert records == []
        assert len(errors) == 1


# ── 单页完整数据 ──
class TestSinglePage:
    @staticmethod
    def make_36col_table(rows):
        """构造36列表格，rows 为列表，每个元素是包含12个关键字段的列表"""
        header = [''] * 36
        header[0] = '订单号'
        header[3] = '交易时间'
        header[6] = '交易类型'
        header[9] = '基金名称'
        header[15] = '基金代码'
        header[18] = '申请金额'
        header[21] = '申请份额'
        header[24] = '确认金额'
        header[27] = '确认份额'
        header[30] = '手续费'
        header[33] = '确认日期'
        table = [header]
        for r in rows:
            row = [''] * 36
            row[0] = r[0]
            row[3] = r[1]
            row[6] = r[2]
            row[9] = r[3]
            # r[4] is empty string (组合基金名称)，我们跳过
            row[15] = r[5]
            row[18] = r[6]
            row[21] = r[7]
            row[24] = r[8]
            row[27] = r[9]
            row[30] = r[10]
            row[33] = r[11]
            table.append(row)
        return table

    def test_buy(self, parser):
        row = [
            '20260101001080010000000000000001',
            '2026/01/0114:30',
            '用户买入',
            '基金A',
            '',
            '001001',
            '1000.00',
            '/',
            '1000.00',
            '850.00',
            '1.50',
            '2026/01/0200:00',
        ]
        table = self.make_36col_table([row])
        with patch('pdfplumber.open', return_value=mock_pdf_open([make_mock_page(table)])):
            records, _ = parser.parse(b'dummy')
        assert len(records) == 1
        r = records[0]
        assert r.symbol == '001001'
        assert r.business_type == 'buy'
        assert r.amount == Decimal('1000.00')
        assert r.shares == Decimal('850.00')
        assert r.nav == Decimal('1.1765')
        assert r.confirm_date == date(2026, 1, 2)
        assert r.trade_date == date(2026, 1, 1)

    def test_sell(self, parser):
        row = [
            '20260102001080010000000000000002',
            '2026/01/0210:00',
            '用户卖出',
            '基金B',
            '',
            '002002',
            '0.00',
            '500.00',
            '2000.00',
            '500.00',
            '0.00',
            '2026/01/0300:00',
        ]
        table = self.make_36col_table([row])
        with patch('pdfplumber.open', return_value=mock_pdf_open([make_mock_page(table)])):
            records, _ = parser.parse(b'dummy')
        assert len(records) == 1
        r = records[0]
        assert r.business_type == 'sell'
        assert r.amount == Decimal('2000.00')
        assert r.nav == Decimal('4.0000')

    def test_dividend(self, parser):
        row = [
            '20260103001080010000000000000003',
            '2026/01/0314:00',
            '机构分红',
            '基金C',
            '',
            '003003',
            '0.00',
            '0',
            '500.00',
            '0',
            '0.00',
            '2026/01/0400:00',
        ]
        table = self.make_36col_table([row])
        with patch('pdfplumber.open', return_value=mock_pdf_open([make_mock_page(table)])):
            records, _ = parser.parse(b'dummy')
        assert len(records) == 1
        r = records[0]
        assert r.business_type == 'dividend_cash'
        assert r.amount == Decimal('500.00')
        assert r.nav is None


# ── 跨页断裂合并 ──
# ── 替换原有 TestCrossPageMerge 类 ──
class TestCrossPageMerge:
    @staticmethod
    def _header():
        """36列表头，只填充索引位置"""
        h = [''] * 36
        h[0] = '订单号'
        h[3] = '交易时间'
        h[6] = '交易类型'
        h[9] = '基金名称'
        h[15] = '基金代码'
        h[18] = '申请金额'
        h[21] = '申请份额'
        h[24] = '确认金额'
        h[27] = '确认份额'
        h[30] = '手续费'
        h[33] = '确认日期'
        return h

    @staticmethod
    def _partial_36(row_data: list):
        """创建36列不完整行，row_data 为12个关键字段的列表"""
        row = [''] * 36
        row[0] = row_data[0]  # 订单号（可能截断）
        row[3] = row_data[1]  # 交易时间
        row[6] = row_data[2]  # 交易类型
        row[9] = row_data[3]  # 基金名称
        # row_data[4] 为空字符串（组合基金名称）
        row[15] = row_data[5]  # 基金代码
        row[18] = row_data[6]  # 申请金额
        row[21] = row_data[7]  # 申请份额
        row[24] = row_data[8]  # 确认金额
        row[27] = row_data[9]  # 确认份额
        row[30] = row_data[10]  # 手续费
        row[33] = row_data[11]  # 确认日期（可能截断或为空）
        return row

    def test_basic_merge(self, parser):
        # 首页：表头 + 不完整行
        partial_data = [
            '20260104',  # 订单号截断
            '2026/01/0',  # 交易时间截断
            '用户买入',
            '基金D',
            '',
            '004004',
            '2000.00',
            '/',
            '2000.00',
            '1700.00',
            '2.00',
            '',  # 确认日期留空（将在续行补全）
        ]
        header = self._header()
        partial_row = self._partial_36(partial_data)
        page1 = make_mock_page([header, partial_row])

        # 续行（12列）：提取时已清洗，字符串形式
        cont = [
            '00108001000000000000000004',  # 订单号后半截
            '414:30',  # 时间后半截
            '',  # 交易类型（不变，留空）
            '',  # 基金名称（不变）
            '',  # 组合基金名称（无）
            '',  # 基金代码（不变）
            '',  # 申请金额（不变）
            '',  # 申请份额（不变）
            '',  # 确认金额（不变）
            '',  # 确认份额（不变）
            '',  # 手续费（不变）
            '2026/01/0500:00',  # 确认日期
        ]
        page2 = make_mock_page([cont])

        with patch('pdfplumber.open', return_value=mock_pdf_open([page1, page2])):
            records, _ = parser.parse(b'dummy')
        assert len(records) == 1
        r = records[0]
        assert r.transaction_id == '2026010400108001000000000000000004'
        assert r.trade_date == date(2026, 1, 4)
        assert r.symbol == '004004'
        assert r.shares == Decimal('1700.00')
        assert r.confirm_date == date(2026, 1, 5)

    def test_multiple_records_with_merge(self, parser):
        # 构造完整行（36列）
        def _full_36(row_data):
            row = [''] * 36
            row[0] = row_data[0]
            row[3] = row_data[1]
            row[6] = row_data[2]
            row[9] = row_data[3]
            row[15] = row_data[5]
            row[18] = row_data[6]
            row[21] = row_data[7]
            row[24] = row_data[8]
            row[27] = row_data[9]
            row[30] = row_data[10]
            row[33] = row_data[11]
            return row

        # 第一条完整记录
        full_data1 = [
            '20260105001080010000000000000005',  # 完整订单号
            '2026/01/0510:00',
            '用户卖出',
            '完整基金',
            '',
            '005005',
            '0.00',
            '300.00',
            '1500.00',
            '300.00',
            '0.00',
            '2026/01/0600:00',
        ]
        # 第二条不完整记录（断裂）
        partial_data = [
            '20260106',  # 截断的订单号
            '2026/01/0',  # 截断的交易时间
            '用户买入',
            '断裂基金',
            '',
            '006006',
            '3000.00',
            '/',
            '3000.00',
            '2700.00',
            '3.00',
            '',  # 确认日期留空，后续补充
        ]
        header = self._header()
        page1 = make_mock_page([header, _full_36(full_data1), self._partial_36(partial_data)])

        # 续行（12列）
        cont = [
            '00108001000000000000000006',  # 订单号后半截
            '614:00',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '2026/01/0700:00',
        ]
        page2 = make_mock_page([cont])

        with patch('pdfplumber.open', return_value=mock_pdf_open([page1, page2])):
            records, _ = parser.parse(b'dummy')
        assert len(records) == 2
        assert records[0].symbol == '005005'
        assert records[0].business_type == 'sell'
        assert records[1].symbol == '006006'
        assert records[1].transaction_id == '2026010600108001000000000000000006'
        assert records[1].trade_date == date(2026, 1, 6)
        assert records[1].confirm_date == date(2026, 1, 7)


# ── 错误与边界 ──
class TestEdgeCases:
    def test_missing_confirm_amount(self, parser):
        # 确认金额为空，行应被跳过
        header = [''] * 36
        header[0] = '订单号'
        header[3] = '交易时间'
        header[6] = '交易类型'
        header[9] = '基金名称'
        header[15] = '基金代码'
        header[18] = '申请金额'
        header[24] = '确认金额'
        header[27] = '确认份额'
        header[30] = '手续费'
        header[33] = '确认日期'
        row = [''] * 36
        row[0] = '20260107001080010000000000000007'
        row[3] = '2026/01/0710:00'
        row[6] = '用户买入'
        row[9] = '无金额基金'
        row[15] = '007007'
        row[18] = '1000.00'
        # 确认金额留空
        row[27] = '1000.00'
        row[30] = '0.00'
        row[33] = '2026/01/0800:00'
        page = make_mock_page([header, row])
        with patch('pdfplumber.open', return_value=mock_pdf_open([page])):
            records, errors = parser.parse(b'dummy')
        assert len(records) == 0

    def test_invalid_confirm_date(self, parser):
        header = [''] * 36
        header[0] = '订单号'
        header[3] = '交易时间'
        header[6] = '交易类型'
        header[9] = '基金名称'
        header[15] = '基金代码'
        header[18] = '申请金额'
        header[24] = '确认金额'
        header[27] = '确认份额'
        header[33] = '确认日期'
        row = [''] * 36
        row[0] = '20260108001080010000000000000008'
        row[3] = '2026/01/0810:00'
        row[6] = '用户买入'
        row[9] = '错误日期'
        row[15] = '008008'
        row[18] = '1000.00'
        row[24] = '1000.00'
        row[27] = '800.00'
        row[33] = '2026-13-08'  # 无效月份
        page = make_mock_page([header, row])
        with patch('pdfplumber.open', return_value=mock_pdf_open([page])):
            records, _ = parser.parse(b'dummy')
        assert len(records) == 0


# ── 内部方法单元测试 ──
class TestInternalHelpers:
    def test_clean_text(self):
        assert AlipayPDFParser._clean_text('  hello   world  ') == 'helloworld'
        assert AlipayPDFParser._clean_text(None) == ''
        assert AlipayPDFParser._clean_text('') == ''

    def test_parse_date(self, parser):
        assert parser._parse_date('2026/01/08') == date(2026, 1, 8)
        assert parser._parse_date('2026-01-08') == date(2026, 1, 8)
        assert parser._parse_date('') is None
        assert parser._parse_date('abc') is None

    def test_parse_decimal(self, parser):
        assert parser._parse_decimal('123.45') == Decimal('123.45')
        assert parser._parse_decimal('/') == Decimal('0')
        assert parser._parse_decimal('—') == Decimal('0')
        assert parser._parse_decimal('') == Decimal('0')

    def test_business_type_mapping(self, parser):
        row = ['20260109001', '2026/01/09', '用户买入', 'X', '', '009', '1000', '/', '1000', '900', '0', '2026/01/10']
        assert parser._row_to_record(row).business_type == 'buy'
        row[2] = '用户卖出'
        assert parser._row_to_record(row).business_type == 'sell'
        row[2] = '营销买入'
        assert parser._row_to_record(row).business_type == 'buy'
        row[2] = '用户跨TA转换'
        assert parser._row_to_record(row).business_type == 'buy'
