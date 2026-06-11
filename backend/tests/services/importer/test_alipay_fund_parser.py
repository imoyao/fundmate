# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/8 20:02
# File : test_alipay_fund_parser.py
from decimal import Decimal

import pytest

from app.services.importer.parsers.alipay_fund import AlipayFundParser


class TestAlipayFundParser:
    @pytest.fixture
    def parser(self):
        return AlipayFundParser()

    def _make_csv(self, data_rows: str) -> bytes:
        """构造支付宝导出格式的 CSV 字节流（逗号分隔，含引号）"""
        header = (
            '交易号,商家订单号,交易创建时间,最近修改时间,交易来源地,'
            '类型,交易对方,商品名称,金额（元）,收/支,交易状态,'
            '服务费（元）,成功退款（元）,备注,资金状态\n'
        )
        return (header + data_rows).encode('utf-8')

    def test_parse_fund_buy(self, parser):
        """基金买入交易"""
        data = (
            '"TXN001","","2026/5/19 15:49","2026/5/19 15:49","支付宝网站",'
            '"即时到账交易","蚂蚁财富","蚂蚁财富-华泰柏瑞质量成长混合C-买入",'
            '"1000.00","不计收支","交易成功","0.50","0","","已收入"\n'
        )
        csv_bytes = self._make_csv(data)
        records, errors = parser.parse(csv_bytes)
        assert len(records) == 1
        assert len(errors) == 0
        r = records[0]
        assert r.asset_type == 'fund'
        assert r.business_type == 'buy'
        assert r.name == '华泰柏瑞质量成长混合C'
        assert r.amount == Decimal('1000.00')
        assert r.fee == Decimal('0.50')
        assert r.transaction_id == 'TXN001'
        assert r.symbol == ''

    def test_parse_fund_sell(self, parser):
        """基金卖出至余额宝"""
        data = (
            '"TXN002","","2026/6/1 10:00","2026/6/1 10:00","支付宝网站",'
            '"即时到账交易","蚂蚁财富","蚂蚁财富-某某基金-卖出至余额宝",'
            '"500.00","不计收支","交易成功","0","0","","已收入"\n'
        )
        csv_bytes = self._make_csv(data)
        records, _ = parser.parse(csv_bytes)
        assert len(records) == 1
        r = records[0]
        assert r.business_type == 'sell'
        assert r.name == '某某基金'

    def test_parse_dividend(self, parser):
        """基金现金分红"""
        data = (
            '"TXN003","","2026/5/20 8:30","2026/5/20 8:30","支付宝网站",'
            '"即时到账交易","蚂蚁财富","蚂蚁财富-红利基金-现金分红至余额宝",'
            '"50.00","不计收支","交易成功","0","0","","已收入"\n'
        )
        csv_bytes = self._make_csv(data)
        records, _ = parser.parse(csv_bytes)
        assert len(records) == 1
        r = records[0]
        assert r.business_type == 'dividend_cash'
        assert r.name == '红利基金'
        assert r.amount == Decimal('50.00')

    def test_parse_yuebao_income(self, parser):
        """余额宝收益发放"""
        data = (
            '"TXN004","","2026/5/19 3:37","2026/5/19 3:37","支付宝网站",'
            '"即时到账交易","易方达增金宝A","余额宝-2026.05.18-收益发放",'
            '"0.13","不计收支","交易成功","0","0","","已收入"\n'
        )
        csv_bytes = self._make_csv(data)
        records, _ = parser.parse(csv_bytes)
        assert len(records) == 1
        r = records[0]
        assert r.asset_type == 'cash'
        assert r.business_type == 'deposit'
        assert r.amount == Decimal('0.13')

    def test_parse_yuebao_withdraw(self, parser):
        """余额宝转出到银行卡"""
        data = (
            '"TXN005","","2026/5/18 9:00","2026/5/18 9:00","支付宝网站",'
            '"即时到账交易","浦发银行","余额宝-转出到银行卡",'
            '"4656.53","不计收支","交易成功","0","0","","资金转移"\n'
        )
        csv_bytes = self._make_csv(data)
        records, _ = parser.parse(csv_bytes)
        assert len(records) == 1
        r = records[0]
        assert r.asset_type == 'cash'
        assert r.business_type == 'withdraw'
        assert r.amount == Decimal('4656.53')

    def test_skip_failed_transaction(self, parser):
        """非成功状态的交易应被过滤"""
        data = (
            '"TXN006","","2026/5/15 12:00","2026/5/15 12:00","支付宝网站",'
            '"即时到账交易","蚂蚁财富","蚂蚁财富-某基金-买入",'
            '"100.00","不计收支","交易关闭","0","0","",""\n'
            '"TXN007","","2026/5/15 13:00","2026/5/15 13:00","支付宝网站",'
            '"即时到账交易","蚂蚁财富","蚂蚁财富-某基金-买入",'
            '"200.00","不计收支","交易成功","0","0","",""\n'
        )
        csv_bytes = self._make_csv(data)
        records, _ = parser.parse(csv_bytes)
        assert len(records) == 1
        assert records[0].amount == Decimal('200.00')

    def test_mixed_transactions(self, parser):
        """混合交易（含基金和余额宝）"""
        data = (
            '"TXN001","","2026/5/19 15:49","2026/5/19 15:49","支付宝网站",'
            '"即时到账交易","蚂蚁财富","蚂蚁财富-XX基金-买入",'
            '"100.00","不计收支","交易成功","0","0","","已收入"\n'
            '"TXN002","","2026/5/19 3:37","2026/5/19 3:37","支付宝网站",'
            '"即时到账交易","易方达增金宝A","余额宝-收益发放",'
            '"0.13","不计收支","交易成功","0","0","","已收入"\n'
        )
        csv_bytes = self._make_csv(data)
        records, _ = parser.parse(csv_bytes)
        assert len(records) == 2
        assert records[0].asset_type == 'fund'
        assert records[1].asset_type == 'cash'

    def test_skip_header_and_trailer(self, parser):
        """跳过文件头元数据和尾部统计行"""
        full_content = (
            '支付宝交易记录明细查询\n'
            '账号:[test@test.com]\n'
            '起始日期:[2026-01-01 00:00:00]    终止日期:[2026-06-08 19:13:15]\n'
            '---------------------------------交易记录明细列表------------------------------------\n'
            '交易号,商家订单号,交易创建时间,最近修改时间,交易来源地,'
            '类型,交易对方,商品名称,金额（元）,收/支,交易状态,'
            '服务费（元）,成功退款（元）,备注,资金状态\n'
            '"TXN008","","2026/6/1 10:00","2026/6/1 10:00","支付宝网站",'
            '"即时到账交易","蚂蚁财富","蚂蚁财富-测试基金-买入",'
            '"100.00","不计收支","交易成功","0","0","","已收入"\n'
            '------------------------------------------------------------------------------------\n'
            '共1笔记录\n'
            '已收入:0笔	0.00元\n'
        )
        records, errors = parser.parse(full_content.encode('utf-8'))
        assert len(records) == 1
        assert records[0].name == '测试基金'

    def test_amount_with_comma(self, parser):
        """金额包含千分位逗号"""
        data = (
            '"TXN009","","2026/5/1 10:00","2026/5/1 10:00","支付宝网站",'
            '"即时到账交易","蚂蚁财富","蚂蚁财富-大额基金-买入",'
            '"1,234,567.89","不计收支","交易成功","0","0","","已收入"\n'
        )
        csv_bytes = self._make_csv(data)
        records, _ = parser.parse(csv_bytes)
        assert records[0].amount == Decimal('1234567.89')
