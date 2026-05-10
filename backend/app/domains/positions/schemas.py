# backend/app/schemas/models.py
# -*- coding: utf-8 -*-
"""持仓相关的 Pydantic Schema 定义."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class PositionCreate(BaseModel):
    """创建持仓时的请求体."""

    symbol: str = Field(..., max_length=50)
    name: Optional[str] = Field(None, max_length=100)
    market: str
    type: str
    account_name: str = Field(..., max_length=50)
    quantity: float = Field(..., gt=0)
    avg_price: float = Field(..., gt=0)
    currency: str = 'CNY'
    purchase_date: date
    # ↓ 新增可选字段
    fee: Optional[float] = Field(0.0, ge=0)
    confirm_date: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=300)
    # 🆕 操作相关
    op_type: Optional[str] = 'buy'
    position_id: Optional[int] = None
    # 🆕 其他元数据
    isAfter15: Optional[bool] = False
    interestRate: Optional[float] = 0.0
    allocation: Optional[str] = 'longterm'


class PositionUpdate(BaseModel):
    """更新持仓时的请求体，所有字段均为可选，只更新用户明确提供的字段."""

    name: Optional[str] = Field(None, max_length=100)
    account_name: Optional[str] = Field(None, max_length=50)
    quantity: Optional[float] = Field(None, gt=0)
    avg_price: Optional[float] = Field(None, gt=0)
    current_price: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = None
    purchase_date: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=300)


class PositionOut(PositionCreate):
    """返回给前端的持仓数据，包含数据库生成的字段."""

    id: int
    current_price: float
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    allocation: Optional[str] = 'longterm'  # 确保有这一行

    class Config:
        from_attributes = True


PositionOut.model_rebuild()
