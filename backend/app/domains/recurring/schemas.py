# -*- coding: utf-8 -*-
"""定投计划入参校验（#2138）。

金额一律用**分**（与 ``transactions.amount`` 同口径），前端负责元⇄分换算；
不在后端做「有时是元、有时是分」的猜测——#2138 的初衷就是消掉心算。

``day_of_period`` 的语义按频率分叉：

- ``monthly``：每月第几日，限制 1~28（29~31 在 2 月会跳月，用户以为是「每月 31 号」，
  实际变成「2 月不投」，属于会让人漏投的静默行为，故直接不收）；
- ``weekly``：1~7（1=周一）；
- ``biweekly``：不接受该字段——14 天相位以 ``start_date`` 为锚，再对齐星期会破坏相位。
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domains.recurring.models import RECURRING_FREQUENCIES


class RecurringPlanCreate(BaseModel):
    """新建定投计划。"""

    ledger_id: Optional[int] = Field(None, description='关联账户 ID（须属于同一家庭）')
    account_name: Optional[str] = Field(None, max_length=100, description='账户名快照（服务端按 ledger_id 刷新）')
    symbol: str = Field(..., min_length=1, max_length=30, description='标的代码')
    position_name: Optional[str] = Field(None, max_length=100, description='标的名称快照')
    asset_type: Optional[str] = Field(None, max_length=20, description='资产类型快照')
    amount: int = Field(..., gt=0, description='每期投入金额（分）')
    frequency: str = Field('monthly', description='frequency: weekly / biweekly / monthly')
    day_of_period: Optional[int] = Field(None, description='每月第几日(1~28) 或 每周第几日(1=周一)')
    start_date: date = Field(..., description='首次扣款日')
    end_date: Optional[date] = Field(None, description='结束日期（不传=长期有效）')
    note: Optional[str] = Field(None, max_length=500, description='备注')

    @field_validator('frequency')
    @classmethod
    def _check_frequency(cls, value: str) -> str:
        if value not in RECURRING_FREQUENCIES:
            raise ValueError(f'frequency 必须是 {list(RECURRING_FREQUENCIES)} 之一，收到 {value!r}')
        return value

    @model_validator(mode='after')
    def _check_schedule(self):
        if self.day_of_period is not None:
            if self.frequency == 'weekly' and not 1 <= self.day_of_period <= 7:
                raise ValueError('weekly 的 day_of_period 必须是 1~7（1=周一）')
            if self.frequency == 'monthly' and not 1 <= self.day_of_period <= 28:
                raise ValueError('monthly 的 day_of_period 必须是 1~28（29~31 在 2 月会跳月）')
            if self.frequency == 'biweekly':
                raise ValueError('biweekly 不接受 day_of_period：14 天相位以 start_date 为锚')
        if self.end_date and self.end_date < self.start_date:
            raise ValueError('end_date 不能早于 start_date')
        return self


class RecurringPlanUpdate(BaseModel):
    """编辑计划。所有字段可选；视图会把它 merge 进现有计划后按 Create 的口径再校验一遍。"""

    ledger_id: Optional[int] = None
    account_name: Optional[str] = Field(None, max_length=100)
    symbol: Optional[str] = Field(None, min_length=1, max_length=30)
    position_name: Optional[str] = Field(None, max_length=100)
    asset_type: Optional[str] = Field(None, max_length=20)
    amount: Optional[int] = Field(None, gt=0)
    frequency: Optional[str] = None
    day_of_period: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    note: Optional[str] = Field(None, max_length=500)
