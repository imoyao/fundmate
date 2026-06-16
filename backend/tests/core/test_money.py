# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/15 20:01
# File : test_money.py
# -*- coding: utf-8 -*-
"""Money 工具类单元测试"""

from decimal import Decimal

from app.core.money import Money


class TestMoneyYuanCents:
    """金额：元 ↔ 分"""

    def test_basic_float(self):
        assert Money.yuan_to_cents(123.45) == 12345

    def test_basic_int(self):
        assert Money.yuan_to_cents(100) == 10000

    def test_basic_decimal(self):
        assert Money.yuan_to_cents(Decimal('99.99')) == 9999

    def test_none_input(self):
        assert Money.yuan_to_cents(None) == 0

    def test_rounding_down(self):
        """四舍五入：0.004 元 -> 舍去"""
        assert Money.yuan_to_cents(0.004) == 0

    def test_rounding_up(self):
        """四舍五入：0.005 元 -> 进位为 1 分"""
        assert Money.yuan_to_cents(0.005) == 1

    def test_rounding_boundary(self):
        """临界值：0.995 元 -> 进位为 100 分"""
        assert Money.yuan_to_cents(0.995) == 100

    def test_negative_amount(self):
        """负数金额（如退款）"""
        assert Money.yuan_to_cents(-50.00) == -5000

    def test_large_amount(self):
        """大额金额"""
        assert Money.yuan_to_cents(1234567.89) == 123456789

    def test_cents_to_yuan_basic(self):
        assert Money.cents_to_yuan(12345) == 123.45

    def test_cents_to_yuan_zero(self):
        assert Money.cents_to_yuan(0) == 0.0

    def test_cents_to_yuan_none(self):
        assert Money.cents_to_yuan(None) == 0.0

    def test_cents_to_yuan_negative(self):
        assert Money.cents_to_yuan(-5000) == -50.0

    def test_roundtrip(self):
        """往返转换：元 → 分 → 元，应保持一致"""
        original = 123.45
        assert Money.cents_to_yuan(Money.yuan_to_cents(original)) == original


class TestMoneyShares:
    """份额：份 ↔ 最小单位"""

    def test_basic_float(self):
        assert Money.shares_to_min_unit(100.1234) == 1001234

    def test_basic_int(self):
        assert Money.shares_to_min_unit(100) == 1000000

    def test_basic_decimal(self):
        assert Money.shares_to_min_unit(Decimal('50.5678')) == 505678

    def test_none_input(self):
        assert Money.shares_to_min_unit(None) == 0

    def test_four_decimal_places(self):
        """支持4位小数"""
        assert Money.shares_to_min_unit(0.0001) == 1

    def test_rounding_up_shares(self):
        """第5位小数四舍五入：0.00005 -> 进位"""
        assert Money.shares_to_min_unit(0.00005) == 1

    def test_rounding_down_shares(self):
        """第5位小数四舍五入：0.00004 -> 舍去"""
        assert Money.shares_to_min_unit(0.00004) == 0

    def test_large_shares(self):
        assert Money.shares_to_min_unit(9999999.9999) == 99999999999

    def test_min_unit_to_shares_basic(self):
        assert Money.min_unit_to_shares(1001234) == 100.1234

    def test_min_unit_to_shares_int(self):
        assert Money.min_unit_to_shares(1000000) == 100.0

    def test_min_unit_to_shares_zero(self):
        assert Money.min_unit_to_shares(0) == 0.0

    def test_min_unit_to_shares_none(self):
        assert Money.min_unit_to_shares(None) == 0.0

    def test_shares_roundtrip(self):
        """往返转换：份 → 最小单位 → 份"""
        original = 100.1234
        assert Money.min_unit_to_shares(Money.shares_to_min_unit(original)) == original


class TestMoneyParseNav:
    """净值解析：字符串 → Decimal"""

    def test_basic_string(self):
        assert Money.parse_nav('1.5030') == Decimal('1.5030')

    def test_high_precision(self):
        assert Money.parse_nav('1.00005') == Decimal('1.00005')

    def test_none_input(self):
        assert Money.parse_nav(None) == Decimal('0')

    def test_float_input(self):
        """float 输入时也应正确转换"""
        result = Money.parse_nav(1.5030)
        assert isinstance(result, Decimal)

    def test_no_trailing_zeros_loss(self):
        """确保不会丢失末尾的0（1.5030 ≠ 1.503）"""
        assert Money.parse_nav('1.5030') == Decimal('1.5030')
        assert str(Money.parse_nav('1.5030')) == '1.5030'


class TestMoneyMultiply:
    """安全计算：价格 × 数量"""

    def test_basic(self):
        """10.50元 × 100.1234份 = 1051.2957元 ≈ 105130分"""
        # price=1050分, quantity=1001234最小单位
        assert Money.multiply_price_quantity(1050, 1001234) == 105130

    def test_rounding_up(self):
        """舍入进位"""
        # 0.015元 × 1.0001份 = 0.0150015元 ≈ 2分
        assert Money.multiply_price_quantity(2, 10001) == 2

    def test_zero_price(self):
        assert Money.multiply_price_quantity(0, 1001234) == 0

    def test_zero_quantity(self):
        assert Money.multiply_price_quantity(1050, 0) == 0

    def test_large_values(self):
        """大值不溢出"""
        result = Money.multiply_price_quantity(99999999, 99999999)
        assert result > 0
