# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/31 23:30
# File : records.py
# -*- coding: utf-8 -*-
"""
导入系统的标准化数据模型。

StandardTransactionRecord 是所有解析器的输出格式，
ImportError 是标准化错误记录。
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class StandardTransactionRecord:
    """所有导入解析器的统一输出格式"""

    # ── 必填字段 ──
    confirm_date: date  # 确认日期
    asset_type: str  # 'stock' 或 'fund'
    symbol: str  # 标准化代码
    name: str  # 标的名称
    business_type: str  # 标准化交易类型枚举
    amount: Decimal  # 确认金额
    account_name: str  # 资金账户名称
    ledger_id: Optional[int] = None  # 资金账户名称

    # ── 可选字段 ──
    trade_date: Optional[date] = None  # 交易申请日期（下单日，用于持有天数计算）
    shares: Optional[Decimal] = None  # 确认份额
    nav: Optional[Decimal] = None  # 确认净值
    fee: Decimal = Decimal('0')  # 手续费
    transaction_id: Optional[str] = None  # 平台交易流水号（去重核心）

    trade_amount: float = 0.0  # 原始成交金额（同花顺专用）
    net_amount: float = 0.0  # 净发生金额绝对值（同花顺专用）

    # ── 系统字段 ──
    import_hash: Optional[str] = None  # 交易级哈希（用于去重和幂等性）
    batch_id: Optional[str] = None  # 导入批次ID
    raw_text: Optional[str] = None  # 原始行文本，便于问题追溯
    source: str = ''  # 数据来源标识
    link_group_id: Optional[str] = None  # 关联交易组ID
    display_type: str = ''  # 产品细分类型，如“混合型”、“货币型”，前端展示用
    error: str = ''  # 解析失败时存放错误信息
    raw_op_type: str = ''  # 新增：原始中文操作类型，用于关联交易配对
    is_calculated: bool = False  # 份额和净值是否为系统自动推算


@dataclass
class SBImportError:
    """解析过程中的错误记录"""

    line_number: int
    field_name: Optional[str]
    message: str
    raw_value: Optional[str] = None
