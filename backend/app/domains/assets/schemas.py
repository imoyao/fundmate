# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/10 17:21
# File : schemas.py
# -*- coding: utf-8 -*-
"""通用资产的 Pydantic Schema."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class AssetCreate(BaseModel):
    """创建通用资产."""

    major_category: str = Field(..., max_length=20)
    minor_category: Optional[str] = Field(None, max_length=50)
    name: str = Field(..., max_length=200)
    amount: float = Field(..., description='资产金额，正数表示资产，负数表示负债')
    currency: str = 'CNY'
    account_name: Optional[str] = Field(None, max_length=50)
    allocation: Optional[str] = 'longterm'
    status: str = 'active'
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=500)
    extra: Optional[dict] = None


class AssetUpdate(BaseModel):
    """更新通用资产（PATCH，所有字段可选）."""

    major_category: Optional[str] = None
    minor_category: Optional[str] = None
    name: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    account_name: Optional[str] = None
    allocation: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None
    extra: Optional[dict] = None


class AssetOut(AssetCreate):
    """返回给前端的通用资产数据."""

    id: int
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# 强制 Pydantic 重新解析继承链中的 datetime 类型
AssetOut.model_rebuild()
