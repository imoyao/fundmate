# -*- coding: utf-8 -*-
"""项目核心业务枚举定义，继承自旧版 settings.py 精华."""

from enum import Enum


# ──────────────────────────────────────────────
# 1. 市场与币种
# ──────────────────────────────────────────────
class MarketEnum(str, Enum):
    """资产所属市场."""

    SH = 'SH'
    SZ = 'SZ'
    HK = 'HK'
    US = 'US'


class CurrencyEnum(str, Enum):
    """支持的本币种."""

    CNY = 'CNY'
    USD = 'USD'
    HKD = 'HKD'


# ──────────────────────────────────────────────
# 2. 资产类型
# ──────────────────────────────────────────────
class AssetTypeEnum(str, Enum):
    """大类资产类型."""

    STOCK = 'stock'
    FUND = 'fund'
    ETF = 'etf'
    BOND = 'bond'
    CASH = 'cash'


# ──────────────────────────────────────────────
# 3. 风险等级 (继承旧 RiskTypeEnum)
# ──────────────────────────────────────────────
class RiskLevelEnum(int, Enum):
    """风险等级（四笔钱）."""

    undefined = 0
    plain = 1  # 灵活取用
    low = 2  # 稳健增值
    balance = 3  # 平衡增长
    advance = 4  # 进阶成长
    high = 5  # 积极进取


# ──────────────────────────────────────────────
# 4. 交易操作类型 (继承旧 FundOpTypeEnum)
# ──────────────────────────────────────────────
class OpTypeEnum(int, Enum):
    """交易操作类型."""

    purchase = 1  # 买入
    redeem = 2  # 卖出
    deposit = 10  # 存入
    draw_out = 11  # 取出
    dividend = 5  # 现金分红


TYPE_LABELS = {
    'stock': '股票',
    'fund': '基金',
    'bond': '可转债',
    'crypto': '虚拟货币',
    'saving': '银行存款',
    'cash': '现金',
    'static': '其他',
}
MARKET_LABELS = {'CN_A': 'A股', 'CN_HK': '港股', 'US': '美股', 'CRYPTO': '虚拟币'}
ALLOCATION_LABELS = {
    'liquid': '活钱',
    'stable': '稳健底仓',
    'longterm': '长期增值',
    'speculative': '高风险博弈',
    'security': '保险保障',
}
