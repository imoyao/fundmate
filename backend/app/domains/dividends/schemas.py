# -*- coding: utf-8 -*-
"""分红与股息 Schema（#872）。"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DividendTargetUpdate(BaseModel):
    """设置 / 更新家庭股息目标。"""

    target_yield_pct: float = Field(
        ...,
        gt=0,
        le=100,
        description='目标年化股息率(%)，如 4 表示"年化股息率 ≥ 4%"',
    )
    notes: Optional[str] = Field(None, max_length=200, description='目标备注')


class DividendTargetOut(BaseModel):
    """股息目标达成度（与 `dividend_service._target_block` 输出同构）。"""

    model_config = ConfigDict(from_attributes=True)

    configured: bool = Field(..., description='是否已设置目标')
    target_yield_pct: Optional[float] = Field(None, description='目标年化股息率(%)')
    notes: Optional[str] = None
    progress_pct: Optional[float] = Field(None, description='实际股息率 / 目标 × 100（达成度）')
    gap_pct: Optional[float] = Field(None, description='实际 − 目标（百分点），负数=未达标')
    met: Optional[bool] = Field(None, description='是否已达标')
