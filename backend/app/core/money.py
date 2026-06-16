# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/15 19:14
# File : money.py

"""
金融精度转换工具类。

核心原则：
- 金额/价格：内部存储为"分"（Integer），展示为"元"（除以100）
- 基金份额：内部存储为"最小单位"（Integer = 份 × 10000），展示为"份"（除以10000）
- 基金净值：使用 Decimal 直接存储，不做缩放

所有涉及金额、份额的读写操作，必须通过此工具类进行转换。
禁止在业务代码中直接进行乘除运算，杜绝单位混淆。

使用示例:
    # 写入
    position.avg_price = Money.yuan_to_cents(10.50)    # 10.50元 -> 1050分
    position.quantity = Money.shares_to_min_unit(100.1234) # 100.1234份 -> 1001234

    # 读取
    price_yuan = Money.cents_to_yuan(position.avg_price) # 1050分 -> 10.5元
    shares = Money.min_unit_to_shares(position.quantity)  # 1001234 -> 100.1234份
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Union


class Money:
    """金额和份额的精度转换工具"""

    # 金额转换因子（元 <-> 分）
    CENT_FACTOR = Decimal('100')

    # 份额转换因子（份 <-> 最小单位，支持 0.0001 份精度）
    SHARE_FACTOR = Decimal('10000')

    # ── 金额：元 ↔ 分 ──

    @staticmethod
    def yuan_to_cents(value: Union[int, float, Decimal, None]) -> int:
        """
        元 → 分 (用于写入数据库前)

        示例:
            Money.yuan_to_cents(123.45) -> 12345
            Money.yuan_to_cents(Decimal('99.99')) -> 9999
            Money.yuan_to_cents(None) -> 0
        """
        if value is None:
            return 0
        if isinstance(value, float):
            value = Decimal(str(value))
        elif not isinstance(value, Decimal):
            value = Decimal(str(value))
        return int((value * Money.CENT_FACTOR).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

    @staticmethod
    def cents_to_yuan(cents: Union[int, None]) -> float:
        """
        分 → 元 (用于返回给前端)

        示例:
            Money.cents_to_yuan(12345) -> 123.45
            Money.cents_to_yuan(None) -> 0.0
        """
        if cents is None:
            return 0.0
        return float(Decimal(str(cents)) / Money.CENT_FACTOR)

    # ── 份额：份 ↔ 最小单位 ──

    @staticmethod
    def shares_to_min_unit(value: Union[int, float, Decimal, None]) -> int:
        """
        份额 → 最小单位 (用于写入数据库前)

        示例:
            Money.shares_to_min_unit(100.1234) -> 1001234
            Money.shares_to_min_unit(100) -> 1000000
            Money.shares_to_min_unit(None) -> 0
        """
        if value is None:
            return 0
        if isinstance(value, float):
            value = Decimal(str(value))
        elif not isinstance(value, Decimal):
            value = Decimal(str(value))
        return int((value * Money.SHARE_FACTOR).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

    @staticmethod
    def min_unit_to_shares(units: Union[int, None]) -> float:
        """
        最小单位 → 份额 (用于返回给前端)

        示例:
            Money.min_unit_to_shares(1001234) -> 100.1234
            Money.min_unit_to_shares(1000000) -> 100.0
            Money.min_unit_to_shares(None) -> 0.0
        """
        if units is None:
            return 0.0
        return float(Decimal(str(units)) / Money.SHARE_FACTOR)

    # ── 净值：字符串 → Decimal（不缩放） ──

    @staticmethod
    def parse_nav(raw_value: Union[str, float, None]) -> Decimal:
        """
        解析净值字符串为 Decimal，禁止 float 中转

        示例:
            Money.parse_nav("1.5030") -> Decimal('1.5030')
            Money.parse_nav(None) -> Decimal('0')
        """
        if raw_value is None:
            return Decimal('0')
        if isinstance(raw_value, float):
            # 如果是 float，先转字符串避免二进制误差
            return Decimal(str(raw_value))
        return Decimal(str(raw_value))

    # ── 安全计算 ──

    @staticmethod
    def multiply_price_quantity(price_cents: int, quantity_units: int) -> int:
        """
        安全计算：价格(分) × 数量(最小单位) → 金额(分²)，再转回分

        因为数量和价格都放大了（数量×10000，价格×100），
        乘积需要除以数量因子才能得到正确的金额(分)。

        示例:
            # 10.50元 × 100.1234份 = 1051.2957元 = 105129.57分 → 105130分
            Money.multiply_price_quantity(1050, 1001234) -> 105130
        """
        # (price_cents) * (quantity_units) / SHARE_FACTOR
        result = Decimal(str(price_cents)) * Decimal(str(quantity_units)) / Money.SHARE_FACTOR
        return int(result.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
