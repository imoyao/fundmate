# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/13 20:47
# File : models.py
"""自选股数据模型 v2.1 — 命名优化版"""

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class WatchlistItem(Base, PrimaryKeyMixin, TimestampMixin):
    """自选资产关注表"""

    __tablename__ = 'watchlist'

    symbol = Column(String(50), nullable=False, comment='标准化代码')
    market = Column(String(10), nullable=False, comment='市场代码')
    asset_type = Column(String(20), comment='资产类型：STOCK/ETF/FUND/CB/INDEX')
    venue = Column(String(10), default='EXCHANGE', comment='EXCHANGE(场内) / OTC(场外)')
    status = Column(String(20), default='HOLDING', comment='HOLDING(持仓中) / WATCHING(观察中)')
    bookmarked = Column(Boolean, default=False, comment='特别关注标记')
    bookmarked_at = Column(Date, comment='设为特别关注的日期')
    source_cycle_id = Column(Integer, comment='关联的清仓周期ID')
    is_pinned = Column(Boolean, default=False, comment='是否置顶')
    pinned_at = Column(DateTime, comment='置顶时间')
    add_reason = Column(String(500), comment='添加自选时的关注理由')
    notes = Column(String(2000), comment='投资笔记/交易手札')

    # 关系：关联分组与标签
    group_links = relationship('WatchlistItemGroup', back_populates='watchlist_item', cascade='all, delete-orphan')
    tag_links = relationship('WatchlistItemTag', back_populates='watchlist_item', cascade='all, delete-orphan')

    __table_args__ = (UniqueConstraint('symbol', 'market', 'venue', name='uk_watchlist_symbol_market_venue'),)


class WatchlistGroup(Base, PrimaryKeyMixin, TimestampMixin):
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


class WatchlistTagDef(Base, PrimaryKeyMixin, TimestampMixin):
    """标签定义表"""

    __tablename__ = 'watchlist_tag_defs'

    name = Column(String(50), nullable=False, unique=True)
    color = Column(String(7))


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


class ClearedPosition(Base, PrimaryKeyMixin, TimestampMixin):
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
