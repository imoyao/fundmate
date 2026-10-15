# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/9
# File : schemas.py
# app/domains/products/schemas.py
"""产品域请求契约。"""

from __future__ import annotations

import datetime as dt
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
    start: Optional[dt.date] = Field(
        None,
        description=(
            '显式起始日（YYYY-MM-DD）——「建仓期」区间用（#2171）：首笔买入日至今，'
            '区间长度因人而异，档位表达不了。给定时忽略 range 档位；'
            '晚于今天按今天算（空序列由前端降级）。'
        ),
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


class IndexProfileRequest(BaseModel):
    """`GET /api/products/index-profile/` 的查询参数（#2028 · 详情页指数区块）。

    只要资料 + 估值 + 分位，不需要 market / venue 消歧——品类已由详情页 resolver
    判定，指数代码在 ``index_catalog`` 是全局唯一的裸 6 位码。
    """

    symbol: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description='指数代码（裸 6 位码或带交易所前/后缀形态，service 内归一）',
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


class AdvisorProfileRequest(BaseModel):
    """`GET /api/products/advisor-profile/` 的查询参数（#1975 · 详情页投顾组合区块）。

    入参是 **``code`` 而非组合名**：``code`` 是 ``advisor_portfolios`` 的表级唯一键
    （本机实测 105/105 唯一），而 ``name`` 没有唯一约束 —— 当前 105 个组合恰好不重名，
    但那不是约束保证的（多平台接入后「稳健」「进取」这类通用名很容易撞）。
    详情页路由 ``/portfolio/<symbol>`` 传下来的就是它。

    与 ``ManagerProfileRequest`` 同族：档案类入参一律用**业务唯一键**，不用展示名 ——
    展示名是给用户看的，不该同时承担寻址职责。
    """

    code: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description='平台组合码（如 ZH012926 / XCOVSEX / LONG_WIN）',
    )


class RelatedSymbolsRequest(BaseModel):
    """`GET /api/products/related-symbols/` 的查询参数（#1976 · 详情页关联标的区块）。

    只需 symbol：关系表 ``channel_links`` 统一存**裸代码**，入参带不带市场前缀都能命中
    （service 内抽取数字部分），故不需要 `market` / `venue` 消歧——这与
    `StockProfileRequest` 不同，后者要按市场过滤证券记录。
    """

    symbol: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description='产品代码（带前缀形态如 SH510300 或裸代码 510300 均可）',
    )


class FundRiskTypesRequest(BaseModel):
    """`GET /api/products/fund-risk-types/` 的查询参数（#167 · 榜单页类型选择器）。

    只声明可选的口径版本，其余无参——本端点回答的是「哪些类型现在有榜可看」，
    不由客户端决定范围（客户端能改范围的话，选择器与榜单就会对不上）。
    """

    caliber_version: Optional[int] = Field(None, ge=1, description='口径版本；不给用当前版本')


class FundRiskRankingRequest(BaseModel):
    """`GET /api/products/fund-risk-ranking/` 的查询参数（#167 · 按风险指标筛同类）。

    ``fund_type_id`` **必填**：风险比跨类别不可比（债基波动天生小 ⇒ 夏普系统性偏高），
    所以榜单必须限定在同一类内。**不提供「不传就全市场」的默认**——那种默认一定会被
    误用成跨类榜，而那正是用户担心的事。
    """

    fund_type_id: int = Field(..., ge=1, description='基金类型 ID（同类分组键，必填）')
    metric: str = Field(..., min_length=1, max_length=40, description='排序指标（白名单见后端 SORTABLE_METRICS）')
    limit: Optional[int] = Field(None, ge=1, description='条数上限（默认 20，硬上限 200）')
    order: Optional[str] = Field(None, description='asc / desc；不给则用指标默认方向')
    include_distorted: bool = Field(False, description='是否纳入口径可疑（净值跳变/样本不足）的行')
