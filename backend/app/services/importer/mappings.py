# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/1 22:55
# File : mappings.py
# -*- coding: utf-8 -*-
"""
导入系统业务类型映射。

BusinessType 枚举只定义业务类型的代码和标签。
各平台的操作类型中文别名作为独立的映射字典存在，新增平台只需添加一个字典即可。
"""

from enum import Enum


class BusinessType(Enum):
    """
    业务类型枚举。

    只定义平台无关的核心属性：
        - code: 内部编码
        - label: 通用中文标签
    """

    BUY = ('buy', '买入')
    SELL = ('sell', '卖出')
    DIVIDEND_CASH = ('dividend_cash', '现金分红')
    DIVIDEND_REINVEST = ('dividend_reinvest', '红利再投资')
    DEPOSIT = ('deposit', '存入')
    WITHDRAW = ('withdraw', '取出')
    SPLIT = ('split', '拆分/送股')
    BOND_REDEEM = ('bond_redeem', '债券兑付')
    TAX = ('tax', '扣税')
    OTHER = ('other', '其他')

    def __init__(self, code: str, label: str):
        self.code = code
        self.label = label

    @classmethod
    def get_label(cls, code: str) -> str:
        """根据内部编码获取中文标签"""
        return cls[code.upper()].label


# 通用标签字典（所有平台共用）
OP_TYPE_LABEL = {bt.code: bt.label for bt in BusinessType}

# 所有有效的操作类型编码
VALID_OP_TYPES = set(OP_TYPE_LABEL.keys())

# ── 标准模板别名映射 ──
# 用户在标准模板 CSV 中填写的中文 → 内部编码

FUND_OP_MAP = {
    '申购': BusinessType.BUY.code,
    '赎回': BusinessType.SELL.code,
    '现金分红': BusinessType.DIVIDEND_CASH.code,
    '红利再投资': BusinessType.DIVIDEND_REINVEST.code,
    '转入': BusinessType.DEPOSIT.code,
    '转出': BusinessType.WITHDRAW.code,
    '其他收入': BusinessType.DEPOSIT.code,
    '其他支出': BusinessType.WITHDRAW.code,
}

STOCK_OP_MAP = {
    '买入': BusinessType.BUY.code,
    '卖出': BusinessType.SELL.code,
    '现金分红': BusinessType.DIVIDEND_CASH.code,
    '送股': BusinessType.SPLIT.code,
    '其他收入': BusinessType.DEPOSIT.code,
    '其他支出': BusinessType.WITHDRAW.code,
}

# ── 同花顺平台映射 ──
THS_OP_MAP = {
    '证券买入': BusinessType.BUY.code,
    '证券卖出': BusinessType.SELL.code,
    '基金申购拨出': BusinessType.BUY.code,
    '基金赎回拨入': BusinessType.SELL.code,
    '上证LOF申购': BusinessType.BUY.code,
    '开放基金申购': BusinessType.BUY.code,
    '通用回购逆回': BusinessType.BUY.code,
    '资管计划实时': BusinessType.BUY.code,
    '新股入账': BusinessType.BUY.code,
    '配售缴款': BusinessType.BUY.code,
    '资管T0取现拨': BusinessType.SELL.code,
    '债券转股回售': BusinessType.SELL.code,
    '基金红利拨入': BusinessType.DIVIDEND_CASH.code,
    '债券兑息': BusinessType.DIVIDEND_CASH.code,
    '红利入账': BusinessType.DIVIDEND_CASH.code,
    '利息归本': BusinessType.DIVIDEND_CASH.code,
    '配股退款退息': BusinessType.DIVIDEND_CASH.code,
    '转股零款': BusinessType.DIVIDEND_CASH.code,
    '股份转入': BusinessType.DEPOSIT.code,
    '股份转出': BusinessType.WITHDRAW.code,
    '转股入账': BusinessType.SPLIT.code,
    '债券兑付': BusinessType.BOND_REDEEM.code,
    '股息红利差异': BusinessType.TAX.code,
    '股息红利差异扣税': BusinessType.TAX.code,
    '债券兑息兑付': BusinessType.TAX.code,
    '证券蓝补': BusinessType.OTHER.code,
}

# ── 天天基金平台映射 ──
TIANTIAN_OP_MAP = {
    '买基金': BusinessType.BUY.code,
    '超级转换-转入': BusinessType.BUY.code,
    '普通转入': BusinessType.BUY.code,
    '充值': BusinessType.BUY.code,
    '活期宝即充即用': BusinessType.BUY.code,
    '超级转换份额调增': BusinessType.BUY.code,
    '卖基金': BusinessType.SELL.code,
    '强赎': BusinessType.SELL.code,
    '超级转换份额调减': BusinessType.SELL.code,
    '超级转换-转出': BusinessType.SELL.code,
    '普通取现': BusinessType.SELL.code,
    '普通转出': BusinessType.SELL.code,
    '现金分红': BusinessType.DIVIDEND_CASH.code,
    '红利再投资': BusinessType.DIVIDEND_REINVEST.code,
    '活动发放': BusinessType.DEPOSIT.code,
    '其他收入': BusinessType.DEPOSIT.code,
    '其他支出': BusinessType.WITHDRAW.code,
}
