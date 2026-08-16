from sqlalchemy import Column, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint

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

    __table_args__ = (
        Index('idx_pim_ledger_symbol', 'ledger_id', 'symbol'),
        Index('idx_pim_source_import_id', 'source_import_id'),
    )
