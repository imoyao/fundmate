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
    name: str = Field(..., description='组合名称')
    description: Optional[str] = Field(None, description='组合描述')
    purpose: Optional[str] = Field(None, description='投资目的（如"养老金"）')
    target_return: Optional[float] = Field(None, description='年化目标收益率（%）')
    target_amount: Optional[float] = Field(None, description='目标金额')
    target_date: Optional[date] = Field(None, description='目标日期')
    benchmark: Optional[str] = Field(None, description='基准指数（如 CSI300）')


class PortfolioUpdate(BaseModel):
    name: Optional[str] = Field(None, description='组合名称')
    description: Optional[str] = Field(None, description='组合描述')
    purpose: Optional[str] = Field(None, description='投资目的（如"养老金"）')
    target_return: Optional[float] = Field(None, description='年化目标收益率（%）')
    target_amount: Optional[float] = Field(None, description='目标金额')
    target_date: Optional[date] = Field(None, description='目标日期')
    benchmark: Optional[str] = Field(None, description='基准指数（如 CSI300）')


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
