# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/1 22:55
# File : mappings.py
# -*- coding: utf-8 -*-
"""
导入系统业务类型映射。

所有业务类型的定义集中在此枚举中管理。
新增类型只需添加一行枚举成员，所有映射字典自动派生。
"""

from enum import Enum


class BusinessType(Enum):
    """
    业务类型枚举。

    每个成员定义：
        - code: 内部编码
        - label: 通用中文标签
        - fund_names: 基金模板下的中文别名
        - stock_names: 股票模板下的中文别名
    """

    BUY = (
        'buy',
        '买入',
        ('申购',),
        ('买入',),
        (
            '证券买入',
            '基金申购拨出',
            '上证LOF申购',
            '开放基金申购',
            '通用回购逆回',
            '资管计划实时',
            '新股入账',
            '配售缴款',
        ),
    )
    SELL = ('sell', '卖出', ('赎回',), ('卖出',), ('证券卖出', '基金赎回拨入', '资管T0取现拨', '债券转股回售'))
    DIVIDEND_CASH = (
        'dividend_cash',
        '现金分红',
        ('现金分红',),
        ('现金分红',),
        ('基金红利拨入', '债券兑息', '红利入账', '利息归本', '配股退款退息', '转股零款'),
    )
    DIVIDEND_REINVEST = ('dividend_reinvest', '红利再投资', ('红利再投资',), (), ())
    DEPOSIT = ('deposit', '存入', ('转入', '其他收入'), ('其他收入',), ('股份转入',))
    WITHDRAW = ('withdraw', '取出', ('转出', '其他支出'), ('其他支出',), ('股份转出',))
    SPLIT = ('split', '拆分', (), ('送股',), ('转股入账',))
    BOND_REDEEM = ('bond_redeem', '债券兑付', (), (), ('债券兑付',))
    TAX = ('tax', '扣税', (), (), ('股息红利差异', '股息红利差异扣税', '债券兑息兑付'))
    OTHER = ('other', '其他', (), (), ('证券蓝补',))

    def __init__(self, code, label, fund_names, stock_names, ths_names):
        self.code = code
        self.label = label
        self.fund_names = fund_names
        self.stock_names = stock_names
        self.ths_names = ths_names

    @classmethod
    def get_service_code(cls, import_code: str) -> str:
        """根据导入系统的精细编码，获取旧服务层所需的统一编码"""
        # 只有新旧编码不一致的类型才需要列出来
        legacy_map = {
            'dividend_cash': 'dividend',
            'dividend_reinvest': 'dividend',
        }
        return legacy_map.get(import_code, import_code)


# 自动派生所有映射字典
OP_TYPE_LABEL = {bt.code: bt.label for bt in BusinessType}
FUND_OP_MAP = {name: bt.code for bt in BusinessType for name in bt.fund_names}
STOCK_OP_MAP = {name: bt.code for bt in BusinessType for name in bt.stock_names}
THS_OP_MAP = {name: bt.code for bt in BusinessType for name in bt.ths_names}
VALID_OP_TYPES = set(OP_TYPE_LABEL.keys())
