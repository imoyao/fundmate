# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/9
# File : schemas.py
# app/domains/products/schemas.py
"""产品域请求契约。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class ProductTrendRequest(BaseModel):
    """`GET /api/products/trend/` 的查询参数（#1967 · 详情页走势区块）。

    与 `ProductResolveRequest` 分开而非合并：走势要的是**序列 + 区间**，解析要的是
    **身份**，两者生命周期也不同（走势按区间懒加载，解析进页面即取一次）。
    """

    symbol: str = Field(..., min_length=1, max_length=50, description='产品代码')
    range_: str = Field(
        '3M',
        alias='range',
        description='区间档位：1M / 3M / 6M / 1Y（默认 3M，设计 §12 ⑤）',
    )
    asset_type: Optional[str] = Field(
        None,
        max_length=20,
        description='品类；由 #1963 的 resolver 判定后回传，本服务据此选净值口径还是收盘价口径',
    )

    model_config = ConfigDict(populate_by_name=True)


class StockProfileRequest(BaseModel):
    """`GET /api/products/stock-profile/` 的查询参数（#1969 · 详情页股票区块）。

    与 `ProductResolveRequest` 分开而非合并：本端点只要**资料 + 区间行情**，不关心
    自选 / 持仓状态，故不需要 `venue` / `asset_type` —— 品类已由详情页 resolver 判定并
    分派到本区块，前端不重复推断。
    """

    symbol: str = Field(..., min_length=1, max_length=50, description='产品代码（带市场前缀形态，如 SZ000001）')
    market: Optional[str] = Field(
        None,
        max_length=20,
        description='市场消歧；同码跨市场时由 resolve 结果带下来，为空则不按市场过滤',
    )


class ManagerProfileRequest(BaseModel):
    """`GET /api/products/manager-profile/` 的查询参数（#1970 · 详情页经理区块）。

    入参是 **``mgr_code`` 而非姓名**：``managers`` 表实测有 119 组重名（最多「吴昊」
    6 位），姓名不是唯一键；``mgr_code`` 是 12 位哈希、100% 唯一。
    详情页路由 ``/manager/<symbol>`` 传下来的就是它（与 ``lookup_manager`` 同源）。

    任职基金条数上限默认 20 条（经理最多管 42 只，属极端值）：详情页是「看一眼」的
    定位而非列表页，不做分页，故给一个上限防止极端值把首屏撑爆。
    """

    mgr_code: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description='经理编码 mgr_code（12 位哈希；非姓名——库内存在重名）',
    )
    fund_limit: int = Field(
        20,
        ge=1,
        le=100,
        description='任职基金返回条数上限（默认 20；实测最多 42 只）',
    )
