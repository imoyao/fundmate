# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 10:54
# File : templates.py
"""导入模板定义：标准模板 + 同花顺交割单模板"""

from dataclasses import dataclass, field

# 同花顺操作类型 → 内部 op_type 映射
THS_OP_TYPE_MAP = {
    # 股票买卖
    '证券买入': 'buy',
    '证券卖出': 'sell',
    # 基金申赎
    '基金申购拨出': 'buy',
    '基金赎回拨入': 'sell',
    '上证LOF申购': 'buy',
    '开放基金申购': 'buy',
    # 分红与收益
    '基金红利拨入': 'dividend',
    '债券兑息兑付': 'dividend',
    '债券兑息': 'dividend',
    '红利入账': 'dividend',
    '股息红利差异': 'dividend',
    '利息归本': 'dividend',
    '债券兑付': 'dividend',  # 债券兑付通常是一次性还本，可能包含本金+利息，先按分红处理，后续可细化
    # 逆回购
    '通用回购逆回': 'buy',
    # 资管计划
    '资管计划实时': 'buy',
    '资管T0取现拨': 'sell',
    # 新股与配售
    '新股入账': 'buy',  # 新股中签缴款确认，视为买入
    '配售缴款': 'buy',  # 配股缴款，视为买入
    '配股退款退息': 'dividend',  # 退款退息，视为分红
    # 特殊处理（暂时归为其他，保留原始数据供用户手动处理）
    '债券转股回售': 'other',
    '转股零款': 'other',
    '转股入账': 'other',
    '股份转出': 'other',
    '股份转入': 'other',
    '证券蓝补': 'other',
    # 资金划转（由解析器内部特殊处理，不在此映射表中使用）
    '银行转证券': None,
    '证券转银行': None,
    'OTC资金划出': None,
    'OTC资金划入': None,
    'OTC现金宝交': None,
    'OTC资管转让': None,
    # 非交易记录（过滤）
    '指定交易': None,
    '指定登记': None,
}

# 新增other类型的标签
OP_TYPE_LABEL = {
    'buy': '买入',
    'sell': '卖出',
    'dividend': '分红',
    'deposit': '存入',
    'withdraw': '取出',
    'split': '拆分',
    'other': '其他',
}


@dataclass
class ImportTemplate:
    """导入模板基类"""

    name: str
    description: str
    column_map: dict  # 原始列名 → 内部字段名
    required_columns: list = field(default_factory=list)
    optional_columns: list = field(default_factory=list)

    def validate_columns(self, df_columns: set) -> tuple[bool, list]:
        missing = [col for col in self.required_columns if col not in df_columns]
        return len(missing) == 0, missing


# 标准模板（中文表头）
STANDARD_TEMPLATE = ImportTemplate(
    name='标准模板',
    description='ShowBuy 通用交易导入模板',
    column_map={
        '代码': 'symbol',
        '名称': 'name',
        '市场': 'market',
        '产品类型': 'type',
        '所属账户': 'account_name',
        '操作类型': 'op_type',
        '数量': 'quantity',
        '成交价格': 'avg_price',
        '币种': 'currency',
        '交易日期': 'purchase_date',
        '手续费': 'fee',
        '备注': 'notes',
    },
    required_columns=['代码', '操作类型', '数量', '成交价格', '交易日期'],
    optional_columns=['名称', '市场', '产品类型', '所属账户', '币种', '手续费', '备注'],
)

# 同花顺交割单模板
THS_TEMPLATE = ImportTemplate(
    name='同花顺交割单',
    description='同花顺导出的历史交割单',
    column_map={
        '证券代码': 'symbol',
        '证券名称': 'name',
        '证券中文全称': 'name',
        '操作': 'op_type',
        '成交数量': 'quantity',
        '成交均价': 'avg_price',
        '成交金额': 'amount',
        '发生金额': 'net_amount',
        '佣金': 'fee',
        '手续费': None,  # 不直接映射，汇总用
        '印花税': None,
        '过户费': None,
        '其他杂费': None,
        '币种': 'currency',
        '交收日期': 'purchase_date',
        '合同编号': 'contract_id',
    },
    required_columns=['证券代码', '操作', '成交数量', '成交均价', '交收日期'],
    optional_columns=['证券名称', '证券中文全称', '佣金', '手续费', '印花税', '过户费', '其他杂费', '币种', '合同编号'],
)
