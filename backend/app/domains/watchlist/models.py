# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/13 20:47
# File : models.py
"""自选股数据模型 v2.1 — 命名优化版"""

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base, FamilyScopedMixin, PrimaryKeyMixin, TimestampMixin


class WatchlistItem(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """自选资产关注表"""

    __tablename__ = 'watchlist'

    symbol = Column(
        String(50),
        nullable=False,
        comment='标准化代码（场内 SH600519 形态/场外基金 6 位码；经理 MGR_ 前缀/组合平台原生码，#1286）',
    )
    market = Column(String(10), nullable=False, default='', comment='市场代码（无市场实体如经理/组合存空串，#1286）')
    asset_type = Column(
        String(20), comment='资产类型：stock/etf/fund/bond/index/manager/portfolio（小写，单一来源 core/asset_types）'
    )
    venue = Column(
        String(10),
        nullable=False,
        default='',
        comment='EXCHANGE(场内) / OTC(场外)；无交易场所实体（经理/组合）存空串，#1286',
    )
    status = Column(String(20), default='HOLDING', comment='HOLDING(持仓中) / WATCHING(观察中)')
    favorite = Column(Boolean, default=False, comment='特别关注标记')
    favorite_at = Column(Date, comment='设为特别关注的日期')
    # 复盘提醒日期：未竟之蹊（/the-road-not-taken）卡片「下次复盘」字段，
    # 与 cleared_positions.next_review_date 语义一致，但挂在自选条目上
    # （清仓周期快照只在真清仓后才有一行，观察中/持仓中的标的也需要复盘节奏）。
    next_review_date = Column(Date, comment='下次复盘提醒日期（用户可设置）')
    source_cycle_id = Column(Integer, comment='关联的清仓周期ID')
    is_pinned = Column(Boolean, default=False, comment='是否置顶')
    pinned_at = Column(DateTime, comment='置顶时间')
    add_reason = Column(String(500), comment='添加自选时的关注理由')
    notes = Column(String(2000), comment='投资笔记/交易手札')
    # 探市迁移透传的观察参考价/份额（仅展示，不参与记账计算）
    cost_price = Column(Float, comment='观察参考成本价（元）')
    quantity = Column(Float, comment='观察参考份额')

    # 关系：关联分组与标签
    group_links = relationship('WatchlistItemGroup', back_populates='watchlist_item', cascade='all, delete-orphan')
    tag_links = relationship('WatchlistItemTag', back_populates='watchlist_item', cascade='all, delete-orphan')

    # #1286：唯一键回归设计基线 (symbol, market, venue)——原 (symbol, venue) 无法区分
    # 跨市场同码（000001 上证指数 vs 平安银行）。注意 SQLite UNIQUE 中 NULL 互不相等，
    # 无市场实体必须存空串 '' 而非 NULL，否则唯一性静默失效。
    __table_args__ = (UniqueConstraint('symbol', 'market', 'venue', name='uk_watchlist_symbol_market_venue'),)


class WatchlistGroup(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """自选分组表"""

    __tablename__ = 'watchlist_groups'

    name = Column(String(50), nullable=False, comment='分组名称')
    color = Column(String(7), comment='分组颜色')
    sort_order = Column(Integer, default=0)
    is_system = Column(Boolean, default=False)
    is_visible = Column(Boolean, default=True)
    entity_type = Column(String(20), default='ASSET', comment='ASSET(资产) / MANAGER(经理)')

    group_links = relationship('WatchlistItemGroup', back_populates='watchlist_group', cascade='all, delete-orphan')


class WatchlistItemGroup(Base, PrimaryKeyMixin):
    """自选资产-分组关联表"""

    __tablename__ = 'watchlist_item_group'

    item_id = Column(Integer, ForeignKey('watchlist.id', ondelete='CASCADE'), nullable=False)
    group_id = Column(Integer, ForeignKey('watchlist_groups.id', ondelete='CASCADE'), nullable=False)

    watchlist_item = relationship('WatchlistItem', back_populates='group_links')
    watchlist_group = relationship('WatchlistGroup', back_populates='group_links')

    __table_args__ = (UniqueConstraint('item_id', 'group_id', name='uk_item_group'),)


class WatchlistTagDef(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """标签定义表"""

    __tablename__ = 'watchlist_tag_defs'

    name = Column(String(50), nullable=False)
    color = Column(String(7))

    __table_args__ = (UniqueConstraint('family_id', 'name', name='uk_tag_family_name'),)


class WatchlistItemTag(Base, PrimaryKeyMixin):
    """自选资产-标签关联表"""

    __tablename__ = 'watchlist_item_tags'

    item_id = Column(Integer, ForeignKey('watchlist.id', ondelete='CASCADE'), nullable=False)
    tag_id = Column(Integer, ForeignKey('watchlist_tag_defs.id', ondelete='CASCADE'), nullable=False)

    watchlist_item = relationship('WatchlistItem', back_populates='tag_links')

    __table_args__ = (UniqueConstraint('item_id', 'tag_id', name='uk_item_tag'),)


class WatchlistAlert(Base, PrimaryKeyMixin, TimestampMixin):
    """异动提醒表"""

    __tablename__ = 'watchlist_alerts'

    item_id = Column(Integer, ForeignKey('watchlist.id', ondelete='CASCADE'), nullable=False)
    alert_type = Column(String(20), nullable=False, comment='PRICE_UP/PRICE_DOWN/CHANGE_PCT')
    threshold_value = Column(Float)
    is_active = Column(Boolean, default=True)
    last_triggered_at = Column(DateTime)


class ClearedPosition(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """清仓周期快照表"""

    __tablename__ = 'cleared_positions'

    symbol = Column(String(50), nullable=False, comment='标准化代码')
    cycle_number = Column(Integer, nullable=False, comment='第几次清仓')
    first_buy_date = Column(Date, nullable=False)
    last_sell_date = Column(Date, nullable=False)
    total_buy_amount = Column(Float)
    total_sell_amount = Column(Float)
    total_fee = Column(Float)
    realized_pnl = Column(Float, comment='已实现盈亏')
    realized_pnl_pct = Column(Float, comment='盈亏率(%)')
    holding_days = Column(Integer)
    trade_count = Column(Integer)
    benchmark_return = Column(Float, comment='同期基准涨跌幅(%)')
    next_review_date = Column(Date, comment='下次复盘提醒日期')
    review_notes = Column(String(2000), comment='复盘笔记')

    __table_args__ = (
        Index('idx_cleared_symbol', 'symbol'),
        Index('idx_cleared_date', 'last_sell_date'),
    )
