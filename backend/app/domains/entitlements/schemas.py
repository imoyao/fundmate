# -*- coding: utf-8 -*-
"""权益校验请求/响应 Schema。"""

from typing import Optional

from pydantic import BaseModel, Field


class EntitlementCheckRequest(BaseModel):
    feature: str = Field(..., description='功能键：pro-insight / pro-risk / pro-allocation / pro-status')
    family_id: Optional[int] = Field(None, description='可选，默认取当前家庭')


class EntitlementCheckResponse(BaseModel):
    feature: str
    granted: bool
    expires_at: Optional[str] = Field(None, description='ISO8601 或 null')
    reason: Optional[str] = Field(None, description='ok / not_granted / expired')
