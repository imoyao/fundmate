# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/13
# File : schemas.py
"""AI 识别域候选行数据契约（各场景候选行 dataclass）。

识别器产出 + 类型反查后的候选行结构；对外（API）统一转 dict 传输。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WatchlistCandidate:
    """自选场景候选行（代码 + 名称 + 反查后的类型信息）。"""

    code: str  # 6 位数字代码
    name: str = ''
    symbol: Optional[str] = None  # 标准化代码（场内如 SH600519；场外基金为裸代码）
    type: Optional[str] = None  # stock / etf / bond / fund
    market: Optional[str] = None
    venue: Optional[str] = None


@dataclass
class TransactionCandidate:
    """持仓/交易场景候选行（比自选多买卖/日期/金额/份额等字段）。

    所有金额/份额/净值为「元 / 份」原始单位（与 importer 解析结果一致），
    入库时由 importer 管线统一换算（Money），本域不做精度换算。
    """

    code: str  # 6 位数字代码
    business_type: str  # 内部编码：buy / sell（由中文 买入/申购/卖出/赎回 归一）
    name: str = ''
    trade_date: str = ''  # 申请日 YYYY-MM-DD（截图通常只有该字段）
    confirm_date: str = ''  # 确认日 YYYY-MM-DD（可空，缺省入账用申请日）
    amount: Optional[float] = None  # 金额（元）
    shares: Optional[float] = None  # 份额/股数（份/股）
    nav: Optional[float] = None  # 净值/单价（元）
    fee: float = 0.0  # 手续费（元）
    # 反查后回填（catalog.enrich）
    symbol: Optional[str] = None
    type: Optional[str] = None
    market: Optional[str] = None
    venue: Optional[str] = None
    # 校验失败信息（预览表格展示用）
    warnings: list = field(default_factory=list)
