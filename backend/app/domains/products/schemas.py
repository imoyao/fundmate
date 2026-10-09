# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/9
# File : schemas.py
# app/domains/products/schemas.py
"""产品域请求契约。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.asset_types import normalize_asset_type


class ProductResolveRequest(BaseModel):
    """`GET /api/products/resolve/` 的查询参数。

    ``asset_type`` 是**入口提示**（前端 URL 路径段传来的品类），后端只拿它做
    「无自选/无持仓可依时」的兜底；与后端判定不一致时**以后端返回为准**
    （设计 §3.3：路径可被手输 / 收藏夹可能过期，不可信任）。
    """

    symbol: str = Field(..., min_length=1, max_length=50, description='产品代码（大小写不敏感）')
    market: Optional[str] = Field(None, max_length=20, description='市场消歧（同品类跨市场同码，如 000001）')
    venue: Optional[str] = Field(
        None, max_length=10, description='交易场所消歧（EXCHANGE 场内 / OTC 场外；空串=无场所实体）'
    )
    asset_type: Optional[str] = Field(None, max_length=20, description='入口提示品类；后端判定优先于此')

    @field_validator('asset_type')
    @classmethod
    def _normalize_asset_type(cls, v: Optional[str]) -> Optional[str]:
        """归一为小写；非法值由 normalize_asset_type 抛 ValueError → 400。"""
        return normalize_asset_type(v) if v else v
