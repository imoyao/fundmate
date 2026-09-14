# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/15 19:14
# File : money.py

"""
金融精度转换工具类。

 核心原则：
- 金额：内部存储为"分"（Integer，×100），展示为"元"（÷100）
- 价格（avg_price/current_price/txn.price）：内部存储为"0.0001元"（Integer，×10000，4 位小数精度），展示为"元"（÷10000），与份额精度对齐
- 基金份额：内部存储为"最小单位"（Integer = 份 × 10000），展示为"份"（除以10000）
- 基金净值：使用 Decimal 直接存储，不做缩放

所有涉及金额、价格、份额的读写操作，必须通过此工具类进行转换。
禁止在业务代码中直接进行乘除运算，杜绝单位混淆。

金融口径约定（#1375）：
- 服务层数据字典应保持 Decimal 直传，禁止 Decimal→float→Money 的冗余塌缩；
- float 仅允许出现在 JSON 边界（前端入参、展示层序列化）；
- 所有方法对 float 入参先做 Decimal(str(x)) 兜底（最短表示精确还原），int 域单位互转除外。

使用示例:
    # 写入
    position.avg_price = Money.yuan_to_price_units(10.50)  # 10.50元 -> 105000 (0.0001元)
    position.quantity = Money.shares_to_min_unit(100.1234) # 100.1234份 -> 1001234

    # 读取
    price_yuan = Money.price_units_to_yuan(position.avg_price) # 105000 -> 10.5元
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

    # 价格转换因子（元 <-> 0.0001元，4 位小数精度，与份额对齐）
    PRICE_FACTOR = Decimal('10000')

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

    # ── 价格：元 ↔ 0.0001元（4 位小数） ──

    @staticmethod
    def yuan_to_price_units(value: Union[int, float, Decimal, None]) -> int:
        """
        元 → 0.0001元（价格最小单位，4 位小数精度，与份额对齐）

        示例:
            Money.yuan_to_price_units(10.50) -> 105000
            Money.yuan_to_price_units(Decimal('1.5030')) -> 15030
            Money.yuan_to_price_units(None) -> 0
        """
        if value is None:
            return 0
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        return int((value * Money.PRICE_FACTOR).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

    @staticmethod
    def price_units_to_yuan(units: Union[int, None]) -> float:
        """
        0.0001元 → 元 (用于返回给前端)

        示例:
            Money.price_units_to_yuan(105000) -> 10.5
            Money.price_units_to_yuan(None) -> 0.0
        """
        if units is None:
            return 0.0
        return float(Decimal(str(units)) / Money.PRICE_FACTOR)

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
    def multiply_price_quantity(price_units: int, quantity_units: int) -> int:
        """
        安全计算：价格(0.0001元) × 数量(最小单位) → 金额(分)

        价格放大 ×10000，数量放大 ×10000，乘积为 元×份 ×1e8；
        金额以"分"(×100) 存储，故需 ÷1e6 还原为分。

        示例:
            # 10.50元 × 100.1234份 = 1051.2957元 = 105129.57分 → 105130分
            # 价格 10.50元 -> 105000 (0.0001元)，数量 100.1234份 -> 1001234
            Money.multiply_price_quantity(105000, 1001234) -> 105130
        """
        # (price_units) * (quantity_units) / 1e6
        result = Decimal(str(price_units)) * Decimal(str(quantity_units)) / Decimal('1000000')
        return int(result.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
