# -*- coding: utf-8 -*-
"""目标配比 Schema（#2237）。"""

from typing import Optional

from pydantic import BaseModel, Field


class AllocationItem(BaseModel):
    """单个标的的目标占比。"""

    symbol: str = Field(..., max_length=30, description='标的代码（与 positions.symbol 同字面量）')
    target_weight: float = Field(..., ge=0, le=100, description='目标占比（百分点，0~100）')
    notes: Optional[str] = Field(None, max_length=200, description='备注')


class AllocationUpdate(BaseModel):
    """整体覆盖式保存：提交什么就是什么，未提交的旧目标视为移除。

    刻意不做「逐条 PATCH」——配比是一组相互制衡的约定，逐条改容易在改完一只后
    整体早已失衡却看不见；整体提交配合 GET 的偏离预览，用户在保存前就看得见全局。
    """

    items: list[AllocationItem] = Field(default_factory=list, description='目标配比列表（空列表 = 清空）')
