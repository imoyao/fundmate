# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/13 20:47
# File : models.py
"""自选股数据模型 v2.1 — 命名优化版"""

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship, validates

from app.core.asset_types import normalize_asset_type
from app.core.database import Base, FamilyScopedMixin, PrimaryKeyMixin, TimestampMixin


class WatchlistItem(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """自选资产关注表"""

    __tablename__ = 'watchlist'

    symbol = Column(
        String(50),
        nullable=False,
        comment='标准化代码（场内 SH600519 形态/场外基金 6 位码；经理 MGR_ 前缀/组合平台原生码，#1286）',
    )
    name = Column(
        String(100),
        comment='产品名称快照（#1508：创建自选时随搜索回显一并落库；读取优先用快照，缺失才回退反查链）',
    )
    market = Column(String(10), nullable=False, default='', comment='市场代码（无市场实体如经理/组合存空串，#1286）')
    asset_type = Column(
        String(20), comment='资产类型：stock/etf/fund/bond/index/manager/portfolio（小写，单一来源 core/asset_types）'
    )

    @validates('asset_type')
    def _validate_asset_type(self, key: str, value: str | None) -> str | None:
        # 空值放行（兼容存量 / 可选）；非空按小写命中权威集合，否则拒绝写入；
        # 命中后规范化为小写存储，消除大小写漂移（#1527；系统读取 / 过滤端已统一 .lower()）。
        if value in (None, ''):
            return value
        return normalize_asset_type(value)

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

    # #1491 评审：唯一键必须含 family_id——本表继承 FamilyScopedMixin（含 family_id），
    # 写入查重也是家庭维度（watchlist_service.create_watchlist_item）。若唯一键不含 family_id，
    # 家庭 B 关注家庭 A 已关注的同一标的时，应用层查重判定「不存在」→ INSERT 撞 DB 唯一约束
    # → IntegrityError(500)，即「一个家庭关注过的标的，其他家庭再也加不进来」。
    # 另：#1286 起用 (symbol, market, venue) 区分跨市场同码（000001 上证指数 vs 平安银行）。
    # 注意 SQLite UNIQUE 中 NULL 互不相等，无市场实体必须存空串 '' 而非 NULL，否则唯一性静默失效。
    __table_args__ = (
        UniqueConstraint('family_id', 'symbol', 'market', 'venue', name='uk_watchlist_family_symbol_market_venue'),
    )


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
    """自选标的提醒规则（逐标的一行/类型）。

    ## 数据准入四问（AGENTS.md「数据策略」）
      1. 谁在用？—— 自选行「提醒」入口（`QuickViewAlertSection.vue`）与提醒扫描
         （`services/alerts/service.refresh_alerts`）。
      2. 什么场景用？—— 用户给某只自选设「涨到 / 跌到 X 元」「单日跌幅超过 N%」
         「自近 N 日高点回撤超过 N%」，越线时落一条站内通知。
      3. 缺了会怎样？—— 提醒只剩「事后看行情」，到价那一刻没人告诉用户；
         无降级替代（人工盯盘不算产品能力）。
      4. 成本多大？—— 每家庭行数 = 自选数 × 至多 4，读写都是本家庭范围；
         扫描时行情批量取（两次 IN 查询），随自选数线性、不受通知量放大。

    ## 语义
    - `PRICE_UP` / `PRICE_DOWN`：到价提醒，**一次性**——触发后 `is_active` 置 False，
      由用户重设（到价是事件，不是持续状态，常驻会天天重复）。
    - `CHANGE_PCT`：单日跌幅监控，阈值取正数（5 表示跌 5%），常驻。
    - `DRAWDOWN`：自窗口高点回撤监控，窗口天数在家庭设置里（`WatchlistAlertSettings`），常驻。
    - 本行为「逐标的覆盖」：存在且启用 ⇒ 用它；存在但停用 ⇒ 该标的关掉这类提醒
      （即使家庭默认开启）；不存在 ⇒ 回落到家庭默认配置。
    """

    __tablename__ = 'watchlist_alerts'

    item_id = Column(Integer, ForeignKey('watchlist.id', ondelete='CASCADE'), nullable=False)
    alert_type = Column(String(20), nullable=False, comment='PRICE_UP/PRICE_DOWN/CHANGE_PCT/DRAWDOWN')
    threshold_value = Column(Float, nullable=False, comment='阈值：到价为价格（元），幅度类为百分比正数')
    is_active = Column(Boolean, default=True, comment='是否启用（到价触发后置 False）')
    last_triggered_at = Column(DateTime, comment='最近一次触发时间（到价一次性语义的依据）')

    __table_args__ = (
        UniqueConstraint('item_id', 'alert_type', name='uq_watchlist_alert_item_type'),
        Index('ix_watchlist_alerts_item', 'item_id'),
    )


class WatchlistAlertSettings(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """家庭级提醒默认配置（逐类型一行）。

    ## 为什么单独一张表而不是在 `watchlist_alerts` 上挂全局行
    「某只标的的规则」与「这个家庭的默认口径」是两个生命周期：前者随标的增删，
    后者与标的无关。混在一张表里会让「没有自选标的时无法配置默认值」，
    也会让扫描逻辑分不清「这行是覆盖」还是「这行是默认」。

    ## 为什么用「类型 + 列」而不是一个 JSON 大字段
    阈值是会被 SQL/报表直接读的数（后续做「提醒效果复盘」时要按类型聚合），
    JSON 字段在 SQLite/Postgres 两侧的可移植与可比性都差；按类型一行则新增
    一种提醒只是多一行数据 + 一条默认值，**不需要改表结构**（低耦合）。

    ## 默认值不在库里
    表里只存「用户改过的口径」。读取时由 `services/alerts/rules.DEFAULT_SETTINGS`
    补齐缺行——这样调整默认阈值不必迁移数据，也不会把开发默认值固化成
    「用户配置」（用户没设过的东西不该显示成他设过）。
    """

    __tablename__ = 'watchlist_alert_settings'

    alert_type = Column(String(20), nullable=False, comment='CHANGE_PCT/DRAWDOWN（到价类逐标的配置，不走本表）')
    is_enabled = Column(Boolean, nullable=False, default=False, comment='该类型是否默认对全部自选生效')
    threshold_value = Column(Float, nullable=False, comment='默认阈值（百分比正数）')
    window_days = Column(Integer, comment='回看窗口天数（仅 DRAWDOWN；其余类型为 NULL）')

    __table_args__ = (UniqueConstraint('family_id', 'alert_type', name='uq_watchlist_alert_settings_family_type'),)


class ClearedPosition(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """清仓周期快照表。

    ⚠️ **已废弃（2026-10-18，#2131 拍板）**：本表自建立起零写入、零读者，踩数据策略
    硬规则「新表必须有读路径」。清仓周期统计改由 `services/analytics/cleared_cycles.py`
    从流水实时聚合（不新增写入方），故本表不再作为缓存表启用——缓存会引入回填与
    一致性成本，而聚合成本≈0。保留表定义仅为避免破坏性删表（`WatchlistItem.
    source_cycle_id` 仍引用其语义），去留登记见 `docs/spec/tech-debt.md`。
    **禁止新增任何读写本表的代码。**
    """

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
