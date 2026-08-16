from datetime import datetime
from zoneinfo import ZoneInfo

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
    func,
)

from app.core.database import Base, FamilyScopedMixin, PrimaryKeyMixin, TimestampMixin


class Position(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    __tablename__ = 'positions'

    symbol = Column(String(30), nullable=False)
    name = Column(String(100))
    market = Column(String(20))
    asset_type = Column('type', String(20))
    ledger_id = Column(Integer, ForeignKey('ledgers.id', ondelete='RESTRICT'), nullable=True, comment='关联账户ID')
    account_name = Column(String(100))
    quantity = Column(Integer, default=0, comment='持仓数量(0.0001份/单位)')
    avg_price = Column(Integer, default=0, comment='成本均价(分)')
    currency = Column(String(10), default='CNY')
    current_price = Column(Integer, default=0, comment='当前市价(分)')
    confirm_date = Column(Date)
    notes = Column(Text)
    allocation = Column(String(20), default='longterm')

    # ── 去重与溯源字段（issue #928，参照 transactions.import_hash 治本方案）──
    import_hash = Column(String(64), nullable=True, comment='持仓去重哈希(内容哈希,唯一约束拦截重复)')
    source = Column(String(30), nullable=False, default='manual', comment='数据来源: manual / broker_xxx / ai_holding')
    source_import_id = Column(String(36), nullable=True, comment='导入批次ID(溯源展示/归集)')
    source_broker = Column(String(50), nullable=True, comment='来源券商/平台(展示)')
    ownership_status = Column(
        String(20),
        nullable=False,
        default='active',
        comment='active=参与总资产; shadow=仅对账不参与总资产',
    )

    __table_args__ = (
        # 核心业务约束：同一账户下 symbol 唯一
        UniqueConstraint('ledger_id', 'symbol', name='uq_positions_ledger_symbol'),
        # 去重约束：持仓内容哈希唯一，撞 key 由 service 层转 upsert（更新数量/成本,保留溯源）
        UniqueConstraint('import_hash', name='uq_positions_import_hash'),
        # 常用查询索引
        Index('idx_positions_ledger_id', 'ledger_id'),
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


class SalesBrokerMapping(Base, PrimaryKeyMixin):
    """销售机构名称映射（E账户 source_broker → 用户友好名称，§3.3）。

    系统内置映射（蚂蚁→支付宝等）由 seed_sales_broker_mappings 幂等写入；
    用户在账户设置页可覆盖（user_override=True），系统不覆盖用户自定义。
    本表为平台级映射，不按 family 隔离（所有家庭共享同一套销售机构名称）。
    """

    __tablename__ = 'sales_broker_mappings'

    source_name = Column(String(200), nullable=False, unique=True, comment='E账户原始名称（销售机构字段）')
    display_name = Column(String(100), nullable=False, comment='用户友好名称')
    user_override = Column(Boolean, default=False, comment='用户是否自定义覆盖')
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(ZoneInfo('Asia/Shanghai')),
        server_default=func.now(),
        comment='创建时间',
    )


def seed_sales_broker_mappings(db) -> None:
    """幂等写入销售机构内置映射（§3.3）：按 source_name 查无则插。

    只处理销售机构字段，基金管理人不参与映射（直销场景：基金公司官网即销售机构）。
    """
    builtin_mappings = (
        ('蚂蚁（杭州）基金销售有限公司', '支付宝'),
        ('上海天天基金销售有限公司', '天天基金'),
        ('招商银行股份有限公司', '招商银行'),
        ('易方达基金管理有限公司', '易方达直销'),
    )
    for source_name, display_name in builtin_mappings:
        if not db.query(SalesBrokerMapping).filter_by(source_name=source_name).first():
            db.add(SalesBrokerMapping(source_name=source_name, display_name=display_name, user_override=False))
    db.commit()
