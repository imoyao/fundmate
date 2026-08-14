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

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


def compute_record_hash(source: str, record: 'StandardTransactionRecord') -> str:
    """为单条交易记录生成去重哈希（平台无关，供所有导入/识别路径共用）。

    规则（与原 BaseImportParser.compute_import_hash 一致）：
        - 有平台交易流水号时：f"{source}|{transaction_id}"
        - 无流水号时：f"{source}|{confirm_date}|{symbol}|{business_type}|{shares}|{nav}"

    注意：不包含 amount，因为不同平台对金额的四舍五入处理不同。
    AI 识别导入（source='ai_txn'）同样复用本函数，保证去重口径统一。
    """
    if record.transaction_id:
        raw = f'{source}|{record.transaction_id}'
    else:
        shares_str = f'{float(record.shares):.4f}' if record.shares else '0'
        nav_str = f'{float(record.nav):.4f}' if record.nav else '0'
        raw = (
            f'{source}|{record.confirm_date.isoformat()}|{record.symbol}|{record.business_type}|{shares_str}|{nav_str}'
        )
    return hashlib.md5(raw.encode()).hexdigest()


def compute_position_hash(
    source: str,
    ledger_id: int,
    symbol: str,
    snapshot_date: Optional[date] = None,
) -> str:
    """为单条持仓记录生成去重哈希（issue #928，与交易去重口径对齐）。

    规则（规范 §3.3）：
        f"{source}|{ledger_id}|{symbol}|{snapshot_date}"

    - snapshot_date 优先取持仓快照日（confirm_date）；缺失时由调用方降级为
      created_at 的日期部分（或落库当日），保证「同一天、同一产品、同一来源」
      的持仓不会重复，即便手动录入未提供 snapshot_date。
    - 不含 quantity / avg_price：持仓是汇总结果，同一天同一产品只保留一条汇总
      记录（撞 key 时由 service 层转 upsert 更新数量/成本，而非拒绝）。

    与交易侧区别：交易依赖 transaction_id 区分真实多笔；持仓无流水号概念，
    故以 source|ledger|symbol|日期 作为内容指纹即可满足去重需求。
    """
    snap = snapshot_date.isoformat() if snapshot_date else 'unknown'
    raw = f'{source}|{ledger_id}|{symbol}|{snap}'
    return hashlib.md5(raw.encode()).hexdigest()


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
