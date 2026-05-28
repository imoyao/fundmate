# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 10:54
# File : templates.py
"""导入模板定义：标准模板 + 同花顺交割单模板"""

from dataclasses import dataclass, field


@dataclass
class ImportTemplate:
    """导入模板基类"""

    name: str
    description: str
    column_map: dict
    required_columns: list = field(default_factory=list)
    optional_columns: list = field(default_factory=list)
    core_columns: list = field(default_factory=list)  # 新增：核心特征列，用于模板自动检测

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
    core_columns=['证券代码', '操作', '成交数量', '成交均价', '交收日期'],  # 核心特征列
    required_columns=['证券代码', '操作', '成交数量', '成交均价', '交收日期'],
    optional_columns=['证券名称', '证券中文全称', '佣金', '手续费', '印花税', '过户费', '其他杂费', '币种', '合同编号'],
)
