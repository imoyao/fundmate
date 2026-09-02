from datetime import date
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
)
from sqlalchemy.orm import validates

from app.core.constants import POSITION_SOURCE_LABELS, VALUATION_MODE_LABELS, PositionSource, ValuationMode
from app.core.database import Base, FamilyScopedMixin, PrimaryKeyMixin, TimestampMixin


class Position(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    __tablename__ = 'positions'

    symbol = Column(String(30), nullable=False)
    name = Column(String(100))
    market = Column(String(20))
    asset_type = Column('type', String(20))
    ledger_id = Column(Integer, ForeignKey('ledgers.id', ondelete='RESTRICT'), nullable=True, comment='关联账户ID')
    portfolio_id = Column(
        Integer,
        ForeignKey('portfolios.id', ondelete='SET NULL'),
        nullable=True,
        comment='所属组合ID(D20 持仓级组合; 空=继承账户默认组合 ledger.portfolio_id)',
    )
    account_name = Column(String(100))
    quantity = Column(Integer, default=0, comment='持仓数量(0.0001份/单位)')
    avg_price = Column(Integer, default=0, comment='成本均价(0.0001元)')
    currency = Column(String(10), default='CNY')
    current_price = Column(Integer, default=0, comment='当前市价(0.0001元)')

    # ── 双态计价字段（#1174 / 决策 D1 方案 A）──
    # valuation_mode 决定市值如何计算：nav=份额×净值；balance=直接余额（无净值产品，市值靠人工录入）。
    # 设为持仓的一等属性，而非靠「有没有 override」隐式推断，后续盈亏口径才能跟着模式走。
    valuation_mode = Column(
        String(20),
        nullable=False,
        default=ValuationMode.NAV.value,
        server_default=ValuationMode.NAV.value,
        comment='计价模式: 见 app.core.constants.ValuationMode（nav=份额×净值 / balance=直接余额）',
    )
    market_value_override = Column(
        Integer,
        nullable=True,
        comment='人工录入的可写市值(分)；非空时优先于派生计算（投顾/理财等无净值产品）',
    )
    value_override_at = Column(DateTime, nullable=True, comment='市值覆写时间（用于判断新鲜度）')

    confirm_date = Column(Date)
    notes = Column(Text)
    allocation = Column(String(20), default='longterm')

    # ── 去重与溯源字段（issue #928，参照 transactions.import_hash 治本方案）──
    import_hash = Column(String(64), nullable=True, comment='持仓去重哈希(内容哈希,唯一约束拦截重复)')
    source = Column(
        String(30),
        nullable=False,
        default=PositionSource.MANUAL.value,
        comment='数据来源: 见 app.core.constants.PositionSource',
    )
    source_import_id = Column(String(36), nullable=True, comment='导入批次ID(溯源展示/归集)')
    source_broker = Column(String(50), nullable=True, comment='来源券商/平台(展示)')

    @validates('source')
    def _validate_source(self, key, value):
        # 约束：source 必须是 PositionSource 枚举的合法值，禁止任意字符串。
        # 兼容传入枚举实例或字符串；非法值立即报错，把散落字符串问题在写入时拦截。
        if isinstance(value, PositionSource):
            return value.value
        if value not in POSITION_SOURCE_LABELS:
            raise ValueError(f'非法持仓来源 source={value!r}，必须是 app.core.constants.PositionSource 的合法值')
        return value

    @validates('valuation_mode')
    def _validate_valuation_mode(self, key, value):
        # 约束：valuation_mode 必须是 ValuationMode 枚举的合法值，禁止任意字符串。
        # 与 source 同理——三处市值计算若各自按隐式约定判断「这到底是净值型还是余额型」，
        # 迟早再次分叉（历史上 position_aggregation 与 summary_service 已分叉过一次）。
        if isinstance(value, ValuationMode):
            return value.value
        if value not in VALUATION_MODE_LABELS:
            raise ValueError(f'非法计价模式 valuation_mode={value!r}，必须是 app.core.constants.ValuationMode 的合法值')
        return value

    @property
    def holding_days(self) -> Optional[int]:
        """截至今天的持有时长（天），基于首次建仓确认日 confirm_date；无确认日返回 None。

        用于基金/持仓详情页展示「持有时长」（issue #862）。按服务器本地日期计日，不做时区修正。
        """
        if not self.confirm_date:
            return None
        return (date.today() - self.confirm_date).days

    ownership_status = Column(
        String(20),
        nullable=False,
        default='active',
        comment='active=参与总资产; shadow=仅对账不参与总资产',
    )

    __table_args__ = (
        # 核心业务约束：同一账户下 symbol 唯一
        UniqueConstraint('ledger_id', 'symbol', name='uq_positions_ledger_symbol'),
        # 去重约束：持仓内容哈希唯一，撞 key 由 service 层转 upsert（更新数量/成本,保留溯源）。
        # 去重作用域降为 ledger 级（#1020 / #1065）：import_hash 已含 ledger_id，复合约束与代码语义对齐。
        UniqueConstraint('ledger_id', 'import_hash', name='uq_positions_import_hash'),
        # 常用查询索引
        Index('idx_positions_ledger_id', 'ledger_id'),
        Index('idx_positions_portfolio_id', 'portfolio_id'),
        Index('idx_positions_symbol', 'symbol'),
        Index('idx_positions_account_name', 'account_name'),
        Index('idx_positions_ledger_asset_type', 'ledger_id', 'type'),
    )


class PositionImportMeta(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """持仓导入溯源元数据（#1012 E账户文件导入 / OCR 截图导入共用）。

    与 positions 1:1 关联（position_id 唯一）：承载快照导入时样本/识别结果中的
    溯源上下文字段（基金管理人、份额类别、平台账号、分红方式等），避免把
    这些低频展示字段直接堆进 positions 主表。

    语义说明：
    - position_id 唯一 → 同一持仓（ledger_id+symbol）多次导入时覆盖更新，保留末次快照的溯源信息；
    - source / source_import_id / source_broker 与 positions 对应字段保持一致（冗余便于按批次溯源查询）；
    - market_value 为快照日资产市值（分），用于追溯导入时的账面口径。
    """

    __tablename__ = 'position_import_meta'

    position_id = Column(
        Integer,
        ForeignKey('positions.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        comment='关联持仓ID',
    )
    symbol = Column(String(30), nullable=False, comment='基金代码(冗余,便于按代码溯源)')
    ledger_id = Column(Integer, ForeignKey('ledgers.id', ondelete='RESTRICT'), nullable=True, comment='账户ID(冗余)')
    snapshot_date = Column(Date, nullable=True, comment='持仓快照日期')
    source = Column(String(30), nullable=False, default='', comment='数据来源: e_account_holding / ai_holding')

    @validates('source')
    def _validate_source(self, key, value):
        # 与 positions.source 同源约束：必须是 PositionSource 合法值，禁止散落字符串。
        # 区别：允许空串 ''（兼容「无来源快照」的历史数据），其余非法值立即拦截。
        if isinstance(value, PositionSource):
            return value.value
        if value != '' and value not in POSITION_SOURCE_LABELS:
            raise ValueError(
                f'非法持仓来源 source={value!r}，必须是 app.core.constants.PositionSource 的合法值（空串表示无来源快照）'
            )
        return value

    source_import_id = Column(String(36), nullable=True, comment='导入批次ID')
    source_broker = Column(String(50), nullable=True, comment='销售机构(展示/溯源)')
    fund_manager = Column(String(100), nullable=True, comment='基金管理人')
    share_class = Column(String(20), nullable=True, comment='份额类别(前收费/后收费)')
    fund_account = Column(String(50), nullable=True, comment='基金账户(平台侧账号)')
    trade_account = Column(String(50), nullable=True, comment='交易账户(资金账号)')
    dividend_preference = Column(String(20), nullable=True, comment='分红方式(现金分红/红利转投)')
    market_value = Column(Integer, nullable=True, comment='资产市值(分)')
    raw_extra = Column(Text, nullable=True, comment='原始扩展信息(JSON)，后续新字段先落此处')

    # ── E账户对账与归因字段（#1021 扩展，设计文档 e-account-reconciliation-design-2026-08-16）──
    # 语义：is_attributed/is_ignored 是「防复活」标记——已归因/已忽略的 E账户记录
    # 在后续导入中自动跳过，避免快照全量 SET 把已归因持仓拉回暂存区（§1.2 原则 4）。
    # 仅影子记录（source_broker/fund_manager 非空）使用；渠道 meta 两列恒为 NULL（§3.2）。
    is_attributed = Column(Boolean, default=False, comment='防复活标记：已归因/已核对记录导入跳过')
    is_ignored = Column(Boolean, default=False, comment='用户忽略标记：导入跳过')
    attributed_at = Column(DateTime, nullable=True, comment='归因时间')
    attributed_to_ledger_id = Column(
        Integer,
        ForeignKey('ledgers.id', ondelete='RESTRICT'),
        nullable=True,
        comment='归因目标账户ID',
    )
    import_error = Column(Boolean, default=False, comment='导入失败行标记')
    sales_institution_id = Column(
        Integer,
        ForeignKey('sales_institutions.id', ondelete='SET NULL'),
        nullable=True,
        comment='关联的基金销售机构（AMAC 权威名录，由 source_broker 匹配派生；可选，机构下架置 NULL）',
    )

    __table_args__ = (
        Index('idx_pim_ledger_symbol', 'ledger_id', 'symbol'),
        Index('idx_pim_source_import_id', 'source_import_id'),
        # 部分唯一索引（SQLite 语法）：仅约束影子记录（source_broker/fund_manager 非空即影子记录）。
        # 渠道 meta 这两列必须为 NULL——SQLite 对 NULL 不触发唯一约束，多渠道同 symbol 可共存（§12.2）。
        Index(
            'idx_import_meta_unique',
            'symbol',
            'source_broker',
            'fund_manager',
            unique=True,
            sqlite_where=and_(source_broker.isnot(None), fund_manager.isnot(None)),
        ),
    )


class SalesInstitution(Base, PrimaryKeyMixin, TimestampMixin):
    """基金销售机构权威名录（AMAC 公示，唯一基准）。

    身份证语义：org_name 为 AMAC 权威全称，永远不变，是记录/校验的唯一基准；
    display_name 为常见机构别名（支付宝/天天基金等），仅用于展示。
    is_active 标记机构是否仍在 AMAC 公示名单内（下架/倒闭时置 False，历史数据保留不删除）。
    is_common/common_sort 为平台级「常用机构」策展位（#1081）：由 AMAC 同步 job 按
    代码常量 CURATED_INSTITUTIONS 幂等覆写，禁止手工维护——保证多环境迁移收敛。
    """

    __tablename__ = 'sales_institutions'

    org_name = Column(String(200), unique=True, nullable=False, comment='权威全称（AMAC 公示，唯一基准）')
    reg_addr = Column(String(200), comment='注册地址')
    org_type = Column(String(50), comment='机构类型')
    check_time = Column(String(20), comment='检查时间(YYYY-MM)')
    display_name = Column(String(100), comment='常用别名（展示用）')
    is_active = Column(Boolean, default=True, comment='是否在 AMAC 公示名单内')
    is_common = Column(
        Boolean, nullable=False, default=False, server_default='0', comment='常用机构标志（代码策展，勿手工维护）'
    )
    common_sort = Column(
        Integer, nullable=True, comment='常用组内排序（小者在前），取中基协保有规模排名；非常用为 NULL'
    )
    pinyin_short = Column(String(100), nullable=True, comment='名称拼音首字母简拼（同步 job 派生，供前端检索过滤）')


class FundManagementCompany(Base, PrimaryKeyMixin, TimestampMixin):
    """公募基金管理人权威名录（AMAC 公示，唯一基准）。

    is_active 标记管理人是否仍在公示名单内（注销/停业时置 False，历史数据保留不删除）。
    """

    __tablename__ = 'fund_management_companies'

    house_name = Column(String(200), unique=True, nullable=False, comment='管理人全称（AMAC 公示，唯一基准）')
    register_addr = Column(String(200), comment='注册地址')
    office_addr = Column(String(200), comment='办公地址')
    website = Column(String(200), comment='官网')
    phone = Column(String(100), comment='客服电话')
    is_active = Column(Boolean, default=True, comment='是否在 AMAC 公示名单内')


def resolve_sales_institution_id(db, source_broker):
    """按销售机构名（source_broker）匹配 AMAC 权威名录，返回机构 id；无匹配返回 None。

    匹配链路与 orchestrator._get_or_create_channel_ledger 保持一致（先 org_name 权威全称，
    再 display_name 别名），但本函数只查不建——不自动创建 Ledger，仅供导入时派生
    PositionImportMeta.sales_institution_id 使用。仅匹配在册（is_active）机构。
    """
    if not source_broker:
        return None
    institution = (
        db.query(SalesInstitution)
        .filter(SalesInstitution.is_active.is_(True), SalesInstitution.org_name == source_broker)
        .first()
    )
    if institution is None:
        institution = (
            db.query(SalesInstitution)
            .filter(SalesInstitution.is_active.is_(True), SalesInstitution.display_name == source_broker)
            .first()
        )
    return institution.id if institution else None
