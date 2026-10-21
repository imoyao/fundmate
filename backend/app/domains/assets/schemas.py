# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 17:21
# File : schemas.py
# -*- coding: utf-8 -*-
"""通用资产的 Pydantic Schema."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.asset_types import MAJOR_CATEGORY_VALUES


def _validate_major_category(value: str | None) -> str | None:
    """大类取值必须在权威词表内（#2136）。

    此前写入侧完全不校验，于是任何字符串都能落库；而读侧按词表过滤
    ⇒ 词表外的值（如历史上误用的 'current'）会变成**谁都读不到**的隐形行——
    账户现金恒为 0 就是这么来的。这里早失败，把错误挡在入库之前。
    """
    if value is None:
        return None
    if value not in MAJOR_CATEGORY_VALUES:
        raise ValueError(f'major_category 非法：{value!r}；合法取值见 /api/utils/enums/ 的 asset_category')
    return value


class AssetCreate(BaseModel):
    """创建通用资产."""

    major_category: str = Field(..., max_length=20)
    minor_category: Optional[str] = Field(None, max_length=50)
    name: str = Field(..., max_length=200)
    amount: float = Field(..., gt=0, description='资产金额，必须大于0')
    currency: str = 'CNY'
    ledger_id: Optional[int] = None  # 新增：关联账户 ID
    account_name: Optional[str] = Field(None, max_length=50)
    allocation: Optional[str] = 'longterm'
    status: str = 'active'
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=500)
    extra: Optional[dict] = None

    _check_major_category = field_validator('major_category')(_validate_major_category)


class AssetUpdate(BaseModel):
    """更新通用资产（PATCH，所有字段可选）."""

    major_category: Optional[str] = None
    minor_category: Optional[str] = None
    name: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    ledger_id: Optional[int] = None  # 新增
    account_name: Optional[str] = None
    allocation: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None
    extra: Optional[dict] = None

    _check_major_category = field_validator('major_category')(_validate_major_category)


class AssetOut(BaseModel):
    id: int
    user_id: int
    major_category: str
    minor_category: Optional[str] = None
    name: str
    amount: float  # 没有 gt 限制
    signed_amount: float  # 负债为负，资产为正
    currency: str = 'CNY'
    ledger_id: Optional[int] = None  # 新增：前端列表/详情需要
    account_name: Optional[str] = None
    allocation: Optional[str] = None
    allocation_label: Optional[str] = None
    type_label: Optional[str] = None  # 新增
    status: str = 'active'
    notes: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    extra: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# 强制 Pydantic 重新解析继承链中的 datetime 类型
AssetOut.model_rebuild()
