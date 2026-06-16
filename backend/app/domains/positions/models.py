from sqlalchemy import Column, Date, Integer, String, Text

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class Position(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'positions'

    symbol = Column(String(30), nullable=False)
    name = Column(String(100))
    market = Column(String(20))
    asset_type = Column('type', String(20))
    account_name = Column(String(100))
    quantity = Column(Integer, default=0, comment='持仓数量(0.0001份/单位)')
    avg_price = Column(Integer, default=0, comment='成本均价(分)')
    currency = Column(String(10), default='CNY')
    current_price = Column(Integer, default=0, comment='当前市价(分)')
    confirm_date = Column(Date)
    notes = Column(Text)
    allocation = Column(String(20), default='longterm')
