from sqlalchemy import Column, Date, Float, String, Text

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class Position(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'positions'

    symbol = Column(String(30), nullable=False)
    name = Column(String(100))
    market = Column(String(20))
    asset_type = Column('type', String(20))  # ⬅️ 唯一改动：属性名 asset_type，列名仍是 type
    account_name = Column(String(100))
    quantity = Column(Float, default=0)
    avg_price = Column(Float, default=0)
    currency = Column(String(10), default='CNY')
    current_price = Column(Float, default=0)
    purchase_date = Column(Date)
    notes = Column(Text)
    allocation = Column(String(20), default='longterm')
