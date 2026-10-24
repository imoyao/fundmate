# -*- coding: utf-8 -*-
# File : schemas.py
# app/domains/insight/schemas.py
"""静态诊断提示的响应契约（#1017）。

字段刻意不写死「有哪些规则」：`code` / `severity` 是字符串，规则增减不需要改契约——
这是卡面「规则可维护」的一半（另一半是 `services/insight/rules.py` 的注册表）。
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TipItem(BaseModel):
    """一条被触发的提示。"""

    code: str = Field(..., description='规则标识（稳定值，前端可用于埋点/去重）')
    severity: str = Field(..., description='严重度：risk / warn / info')
    title: str = Field(..., description='一句话标题')
    message: str = Field(..., description='面向用户的说明（含触发数值）')
    rationale: str = Field(..., description='为什么这条规则值得提醒（阈值与依据）')
    evidence: Dict[str, Any] = Field(default_factory=dict, description='触发时的原始数值，供复核')


class TipSnapshot(BaseModel):
    """快照摘要：解释「为什么一条提示都没有」。"""

    holding_count: int = Field(0, description='参与统计的投资持仓标的数')
    total_value_cents: int = Field(0, description='投资持仓总市值（分）')
    penetration_ratio: float = Field(0, description='行业穿透率（0~1），低穿透率时行业规则不触发')
    latest_day: Optional[Dict[str, Any]] = Field(None, description='最近有效交易日 {date, rate_pct}')


class TipListResponse(BaseModel):
    items: List[TipItem] = Field(default_factory=list)
    count: int = 0
    snapshot: TipSnapshot = Field(default_factory=TipSnapshot)
