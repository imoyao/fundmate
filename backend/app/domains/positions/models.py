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

    __table_args__ = (
        # 核心业务约束：同一账户下 symbol 唯一
        UniqueConstraint('ledger_id', 'symbol', name='uq_positions_ledger_symbol'),
        # 常用查询索引
        Index('idx_positions_ledger_id', 'ledger_id'),
        Index('idx_positions_symbol', 'symbol'),
        Index('idx_positions_account_name', 'account_name'),
        Index('idx_positions_ledger_asset_type', 'ledger_id', 'type'),
    )
