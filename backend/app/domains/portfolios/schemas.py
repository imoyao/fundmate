# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/13 18:02
# File : schemas.py
"""
投资组合 Schema 定义
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PortfolioCreate(BaseModel):
    # max_length 与库列 portfolios.name 的 String(100) 对齐：此前没有长度约束，
    # SQLite 静默截断/接受、Postgres 直接 500——同一份输入两种结果。
    name: str = Field(..., min_length=1, max_length=100, description='组合名称（同家庭内唯一）')
    description: Optional[str] = Field(None, description='组合描述')
    purpose: Optional[str] = Field(None, description='投资目的（如"养老金"）')
    target_return: Optional[float] = Field(None, description='年化目标收益率（%）')
    target_amount: Optional[float] = Field(None, description='目标金额')
    target_date: Optional[date] = Field(None, description='目标日期')
    benchmark: Optional[str] = Field(None, description='基准指数（如 CSI300）')


class PortfolioUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description='组合名称（同家庭内唯一，排除自身）')
    description: Optional[str] = Field(None, description='组合描述')
    purpose: Optional[str] = Field(None, description='投资目的（如"养老金"）')
    target_return: Optional[float] = Field(None, description='年化目标收益率（%）')
    target_amount: Optional[float] = Field(None, description='目标金额')
    target_date: Optional[date] = Field(None, description='目标日期')
    benchmark: Optional[str] = Field(None, description='基准指数（如 CSI300）')
    # #981：关联账户完整 ID 集合——传入即在事务内原子替换（[] = 全部解绑），
    # 不传（None）= 本次不动关联。替代前端逐个 updateLedger 的非原子 diff。
    ledger_ids: Optional[list[int]] = Field(None, description='关联账户完整 ID 集合（传入即原子替换；[] 表示全部解绑）')


class PortfolioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    purpose: Optional[str] = None
    target_return: Optional[float] = None
    target_amount: Optional[float] = None
    target_date: Optional[date] = None
    benchmark: Optional[str] = None
    is_deleted: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
