# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/12 19:29
# File : schemas.py
# app/domains/performance/schemas.py
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class XirrRequest(BaseModel):
    """年化收益率查询参数"""

    scope: str = Field(..., description='查询范围: position / portfolio')
    position_id: Optional[int] = Field(None, description='持仓ID（scope=position时必填）')
    portfolio_id: Optional[int] = Field(None, description='投资组合ID（scope=portfolio时用于指定组合）')
    include_cash_equivalents: bool = Field(
        False, description='是否将货币基金/逆回购/现金等现金等价物纳入年化收益分母；默认 False=仅主动投资'
    )


class MoneyFundIncomeRequest(BaseModel):
    """货币基金每日收益查询参数"""

    scope: Optional[str] = Field(None, description='查询范围: ledger / family')
    ledger_id: Optional[int] = Field(None, description='账户ID（scope=ledger时必填）')
    start_date: Optional[date] = Field(None, description='起始日期(YYYY-MM-DD)，默认近30天')
    end_date: Optional[date] = Field(None, description='结束日期(YYYY-MM-DD)，默认今天')


class XirrResponse(BaseModel):
    xirr: float = Field(..., description='年化收益率，如 0.1234 表示 12.34%')
    total_invested: float = Field(..., description='总投入金额')
    current_value: float = Field(..., description='当前市值')
    total_return: float = Field(..., description='总收益')
    cashflow_count: int = Field(..., description='参与计算的现金流笔数')
