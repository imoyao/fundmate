# -*- coding: utf-8 -*-
"""家庭财务规划 Schema。

金额对前端用「元」（float），存储层转「分」——与 assets/transactions 的 API 惯例一致。
两个字段都允许显式传 null 以清除配置；ge=0 拦住负数（年收入/支出不可能是负）。
"""
from typing import Optional

from pydantic import BaseModel, Field


class FinancialPlanUpdate(BaseModel):
    """设置 / 更新家庭财务规划。未传的字段保持不变（None=清除该项配置）。"""

    estimated_annual_expense: Optional[float] = Field(
        None, ge=0, le=1_000_000_000, description='预估年支出（元）；null=未配置'
    )
    estimated_annual_income: Optional[float] = Field(
        None, ge=0, le=1_000_000_000, description='预估年收入（元）；null=未配置'
    )


class FinancialPlanOut(BaseModel):
    """家庭财务规划配置读回。null = 未配置（不是 0）。"""

    estimated_annual_expense: Optional[float] = Field(
        None, description='预估年支出（元）'
    )
    estimated_annual_income: Optional[float] = Field(
        None, description='预估年收入（元）'
    )
