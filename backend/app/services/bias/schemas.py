# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/31 23:32
# File : schemas.py
# -*- coding: utf-8 -*-
# backend/app/services/bias/schemas.py
"""
乖离率模块 Pydantic Schema（数据传输对象）
与 SQLAlchemy 表（MarketMultiItem）解耦
"""

from datetime import date, datetime
from typing import List

from pydantic import BaseModel, Field


class BiasResult(BaseModel):
    """单个品种的乖离率计算结果（Service 层内部使用）"""

    item_type: str = Field(..., description='品种类型: index/etf/fund/stock/industry')
    item_code: str = Field(..., description='品种代码')
    item_name: str = Field(..., description='品种名称')
    close: float = Field(..., description='最新收盘价/净值')
    bias: float = Field(..., description='乖离率值 (%)')
    ema20: float = Field(..., description='EMA20 对数值')
    label: str = Field(..., description='信号标签')
    position: float = Field(..., description='波段位置 (0-100)')
    position_label: str = Field(..., description='波段位置标签')
    data_date: date = Field(..., description='数据日期')
    calculated_at: datetime = Field(default_factory=datetime.now, description='计算时间')
    stale: bool = False

    def to_storage_dict(self) -> dict:
        """转换为 market_multi_items 表的存储格式"""
        return {
            'source': 'bias',
            'item_type': self.item_type,
            'item_code': self.item_code,
            'item_name': self.item_name,
            'data': {
                'bias': self.bias,
                'label': self.label,
                'position': self.position,
                'position_label': self.position_label,
                'close': self.close,
                'ema20': self.ema20,
                'data_date': self.data_date.isoformat(),
            },
            'collected_at': self.calculated_at,
            'stale': self.stale,
        }


class BiasBatchResult(BaseModel):
    """批量计算结果（Service 层内部使用）"""

    source: str = 'bias'
    calculated_at: datetime = Field(default_factory=datetime.now)
    items: List[BiasResult]

    def to_storage_records(self) -> List[dict]:
        """转换为数据库批量插入格式"""
        return [item.to_storage_dict() for item in self.items]
