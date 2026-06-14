# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/13 19:57
# File : schemas.py
# -*- coding: utf-8 -*-
"""
策略标签 Schema 定义
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StrategyTagCreate(BaseModel):
    name: str = Field(..., description='标签名称（如"成长"）')


class StrategyTagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: Optional[datetime] = None


class PositionTagBind(BaseModel):
    position_id: int = Field(..., description='持仓ID')
    strategy_tag_id: int = Field(..., description='策略标签ID')
