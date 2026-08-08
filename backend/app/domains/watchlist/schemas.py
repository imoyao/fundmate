# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/13 21:58
# File : schemas.py
# 自选模块 Schema
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ── 自选资产 ──
class WatchlistItemCreate(BaseModel):
    symbol: str = Field(..., max_length=50, description='标准化代码')
    market: Optional[str] = Field(None, max_length=10, description='市场代码')
    asset_type: Optional[str] = Field(None, max_length=20, description='资产类型')
    venue: Optional[str] = Field(None, max_length=10, description='交易场所')
    add_reason: Optional[str] = Field(None, max_length=500, description='关注理由')
    is_pinned: Optional[bool] = Field(False, description='置顶自选')
    cost_price: Optional[float] = Field(None, description='观察参考成本价（探市迁移透传）')
    quantity: Optional[float] = Field(None, description='观察参考份额（探市迁移透传）')


class WatchlistItemUpdate(BaseModel):
    is_pinned: Optional[bool] = Field(None, description='是否置顶')
    status: Optional[str] = Field(None, max_length=20, description='持仓状态')
    venue: Optional[str] = Field(None, max_length=10, description='交易场所')
    favorite: Optional[bool] = Field(None, description='特别关注标记')
    notes: Optional[str] = Field(None, max_length=2000, description='投资笔记')
    add_reason: Optional[str] = Field(None, max_length=500, description='关注理由')


class WatchlistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    market: Optional[str] = None
    asset_type: Optional[str] = None
    venue: Optional[str] = None
    status: Optional[str] = None
    favorite: Optional[bool] = None  # 新增
    favorite_at: Optional[date] = None  # 新增
    is_pinned: Optional[bool] = None
    pinned_at: Optional[datetime] = None
    add_reason: Optional[str] = None
    notes: Optional[str] = None
    cost_price: Optional[float] = None  # 观察参考成本价（探市迁移透传）
    quantity: Optional[float] = None  # 观察参考份额（探市迁移透传）
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # 前端展示用字段（非数据库列）
    display_name: Optional[str] = None
    group_ids: list[int] = []
    tag_ids: list[int] = []


# ── 分组 ──
class WatchlistGroupCreate(BaseModel):
    name: str = Field(..., max_length=50, description='分组名称')
    color: Optional[str] = Field(None, max_length=7, description='颜色')
    entity_type: Optional[str] = Field('ASSET', max_length=20, description='实体类型')


class WatchlistGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50, description='分组名称')
    color: Optional[str] = Field(None, max_length=7, description='颜色')
    sort_order: Optional[int] = Field(None, description='排序')
    is_visible: Optional[bool] = Field(None, description='是否显示')


class WatchlistGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: Optional[str] = None
    sort_order: Optional[int] = None
    is_system: Optional[bool] = None
    is_visible: Optional[bool] = None
    entity_type: Optional[str] = None


# ── 标签定义 ──
class WatchlistTagDefCreate(BaseModel):
    name: str = Field(..., max_length=50, description='标签名称')
    color: Optional[str] = Field(None, max_length=7, description='颜色')


class WatchlistTagDefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: Optional[str] = None


class WatchlistTagDefUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=7)
