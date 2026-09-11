# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/13 21:58
# File : schemas.py
# 自选模块 Schema
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ── 自选资产 ──
class WatchlistItemCreate(BaseModel):
    symbol: str = Field(..., max_length=50, description='标准化代码')
    market: Optional[str] = Field(None, max_length=10, description='市场代码')
    asset_type: Optional[str] = Field(None, max_length=20, description='资产类型')
    venue: Optional[str] = Field(None, max_length=10, description='交易场所')
    add_reason: Optional[str] = Field(None, max_length=500, description='关注理由')
    is_pinned: Optional[bool] = Field(False, description='置顶自选')
    cost_price: Optional[float] = Field(None, description='观察参考成本价（探市迁移透传）')
    quantity: Optional[float] = Field(None, description='观察参考份额（探市迁移透传）')


class WatchlistItemUpdate(BaseModel):
    is_pinned: Optional[bool] = Field(None, description='是否置顶')
    status: Optional[str] = Field(None, max_length=20, description='持仓状态')
    venue: Optional[str] = Field(None, max_length=10, description='交易场所')
    favorite: Optional[bool] = Field(None, description='特别关注标记')
    notes: Optional[str] = Field(None, max_length=2000, description='投资笔记')
    add_reason: Optional[str] = Field(None, max_length=500, description='关注理由')
    next_review_date: Optional[date] = Field(None, description='下次复盘提醒日期')


class WatchlistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    market: Optional[str] = None
    asset_type: Optional[str] = None
    venue: Optional[str] = None
    status: Optional[str] = None
    favorite: Optional[bool] = None  # 新增
    favorite_at: Optional[date] = None  # 新增
    next_review_date: Optional[date] = None  # 新增：复盘提醒（未竟之蹊卡片底部）
    is_pinned: Optional[bool] = None
    pinned_at: Optional[datetime] = None
    add_reason: Optional[str] = None
    notes: Optional[str] = None
    cost_price: Optional[float] = None  # 观察参考成本价（探市迁移透传）
    quantity: Optional[float] = None  # 观察参考份额（探市迁移透传）
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # 前端展示用字段（非数据库列）
    display_name: Optional[str] = None
    group_ids: list[int] = []
    tag_ids: list[int] = []
    # 真实持仓统计（views._enrich_item 动态补充；区别于上方迁移透传的 cost_price/quantity）
    holding_quantity: Optional[float] = None  # 真实持仓数量（份/股，positions 汇总）
    holding_cost_price: Optional[float] = None  # 加权成本均价（元）
    holding_pnl: Optional[float] = None  # 持仓收益（元）
    holding_pnl_percent: Optional[float] = None  # 持仓收益率（%）
    price_at_added: Optional[float] = None  # 添加自选日最近交易日收盘价（元，price_history 有回填时）
    # 投顾组合补充信息（#1167，仅 AdvisorPortfolio 命中时有值；非投顾一律 None，
    # 前端据此决定是否在产品列渲染第二行元信息，避免与代码/类型/标签挤一行）
    advisor_platform: Optional[str] = None  # QIEMAN/DANJUAN/TIANTIAN/YINGMI
    advisor_host: Optional[str] = None  # 主理人
    advisor_strategy_type: Optional[str] = None  # 策略类型（均衡/进取/稳健）
    advisor_org_name: Optional[str] = None  # 主理人所属机构/平台方
    # 投顾品类差异化指标（#1392，仅 asset_type=portfolio 且 AdvisorPortfolio 命中时有值；
    # 其余恒 null，前端「投顾组合」品类专属列据此渲染，未落库显示 `—`）。
    # 区间收益来自天天 SYL_* 实测映射；回撤/超额 API 不直接提供时为空。
    return_1w: Optional[float] = None  # 近1周收益(%)
    return_1m: Optional[float] = None  # 近1月收益(%)
    return_1y: Optional[float] = None  # 近1年收益(%)
    return_ytd: Optional[float] = None  # 今年以来收益(%)
    return_since_incep: Optional[float] = None  # 成立以来收益(%)
    max_drawdown: Optional[float] = None  # 最大回撤(%)
    excess_return: Optional[float] = None  # 相对基准超额收益(%)
    advisor_benchmark: Optional[str] = None  # 业绩比较基准
    advisor_holding_count: Optional[int] = None  # 持仓基金数
    advisor_concentration: Optional[float] = None  # 持仓集中度 HHI = Σ(占比%²)
    # 基金经理补充信息（#1286）：经理行没有对外有意义的交易代码，第二行元信息由公司承担
    # （2026-09-10 用户反馈：只显示「基金经理」标签时信息量为零）。
    manager_company: Optional[str] = Field(
        None, description='基金经理所属基金公司名（仅 asset_type=manager 有值，其余恒 null）'
    )
    # 可转债条款补充信息（#1285 消费侧 / #1393）：仅 asset_type=bond 且命中
    # convertible_bond_terms 时有值，其余恒 null；前端「可转债」品类专属列据此渲染，
    # 未落库时列内显示 `—`（不用 0 兜底，避免与真实 0 溢价率混淆）。
    bond_convert_price: Optional[float] = None  # 转股价（元）
    bond_convert_value: Optional[float] = None  # 转股价值（元）
    bond_premium_rate: Optional[float] = None  # 转股溢价率（%）
    bond_force_redeem_price: Optional[float] = None  # 强赎触发价（元）
    bond_redeem_count: Optional[int] = None  # 强赎天计数（已达天数）
    bond_redeem_required: Optional[int] = None  # 强赎触发所需天数（通常 15）
    bond_redeem_status: Optional[str] = None  # 强赎状态（已公告强赎/公告不强赎/…）
    bond_rating: Optional[str] = None  # 信用评级（AA+/AA/…）
    bond_maturity_date: Optional[date] = None  # 到期日（前端据此算「剩余年限」）
    bond_remain_size: Optional[float] = None  # 剩余规模（亿元）
    bond_issue_size: Optional[float] = None  # 发行规模（亿元）
    bond_stock_name: Optional[str] = None  # 正股名称
    # 指数估值补充信息（#1285 消费侧「指数」品类 / #1394）：仅 asset_type=index 且
    # index_valuations 存在该指数记录时下发；口径见后端 IndexValuation 模型注释。
    index_pe: Optional[float] = None  # 市盈率（中证官方列「市盈率1」）
    index_pe_2: Optional[float] = None  # 市盈率2（官方列名，口径以官方为准）
    index_dividend_yield: Optional[float] = None  # 股息率(%)（官方列「股息率1」）
    index_valuation_date: Optional[date] = None  # 估值日期（口径透明：前端可标「截至 X」）
    # 基金最大回撤（#1285 消费侧「基金」品类 / 设计 §3.10）。**不只给数字，同时给口径
    # 元数据**——§3.10 明确要求「存口径元数据，不只存数字」，前端按 basis 决定色与 tooltip。
    # 本期仅产出 fixed_3y（固定窗口近 3 年）；current_tenure / prev_tenure 依赖经理任期
    # 与历任业绩数据（未接入），数据不足时 basis=insufficient 且值保持 None。
    fund_max_drawdown: Optional[float] = None  # 最大回撤(%)，负值
    fund_max_drawdown_basis: Optional[str] = None  # current_tenure|prev_tenure|fixed_3y|insufficient
    fund_max_drawdown_window: Optional[str] = None  # 窗口描述（如「近3年」）
    fund_max_drawdown_as_of: Optional[date] = None  # 序列最后净值日（「截至」）
    # 跨渠道关联（#1285 设计 §3.8）：数量角标 + 浮层明细。
    # links 元素形状：[{code, name, link_type}]；link_type 现有两类：
    #   index_etf —— 指数 ↔ 场内 ETF（第一层）
    #   etf_feeder —— 场内 ETF ↔ 场外联接基金（第二层）
    # 靠名称匹配（实测 akshare 无「跟踪标的」字段），落库口径覆盖率约 66.4%；
    # 跨境/商品 ETF 的跟踪标的不在 index_catalog 内，缺口见 #1419。
    link_count: Optional[int] = None
    links: list[dict] = []


# ── 分组 ──
class WatchlistGroupCreate(BaseModel):
    name: str = Field(..., max_length=50, description='分组名称')
    color: Optional[str] = Field(None, max_length=7, description='颜色')
    entity_type: Optional[str] = Field('ASSET', max_length=20, description='实体类型')


class WatchlistGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50, description='分组名称')
    color: Optional[str] = Field(None, max_length=7, description='颜色')
    sort_order: Optional[int] = Field(None, description='排序')
    is_visible: Optional[bool] = Field(None, description='是否显示')


class WatchlistGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: Optional[str] = None
    sort_order: Optional[int] = None
    is_system: Optional[bool] = None
    is_visible: Optional[bool] = None
    entity_type: Optional[str] = None


# ── 标签定义 ──
class WatchlistTagDefCreate(BaseModel):
    name: str = Field(..., max_length=50, description='标签名称')
    color: Optional[str] = Field(None, max_length=7, description='颜色')


class WatchlistTagDefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: Optional[str] = None


class WatchlistTagDefUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=7)
