# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/7 21:16
# File : models.py

"""持仓数据模型 — 继承自旧版 AccountTransactionRecord 设计，适配统一一张表."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Position(Base):
    __tablename__ = 'positions'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(50))
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    market: Mapped[str] = mapped_column(String(10))
    type: Mapped[str] = mapped_column(String(20))
    account_name: Mapped[str] = mapped_column(String(50))
    allocation: Mapped[str | None] = mapped_column(String(20), nullable=True, default='longterm')
    quantity: Mapped[float] = mapped_column(Float)
    avg_price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default='CNY')
    current_price: Mapped[float] = mapped_column(Float, default=0.0)
    purchase_date: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
