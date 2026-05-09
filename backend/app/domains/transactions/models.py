# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/9 19:23
# File : models.py


from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Transaction(Base):
    __tablename__ = 'transactions'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(Integer, ForeignKey('positions.id'), nullable=False)

    # --- 核心交易要素 (MVP 必填) ---
    # buy, sell, dividend, deposit, withdraw, split, conversion, in specie
    type: Mapped[str] = mapped_column(String(20), default='buy')
    trade_date: Mapped[date] = mapped_column(Date)  # 交易发起日期 (T日)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)  # 操作数量 (股/张/份)
    price: Mapped[float] = mapped_column(Float, default=0.0)  # 操作价格 (成交价)
    fee: Mapped[float] = mapped_column(Float, default=0.0)  # 手续费
    amount: Mapped[float] = mapped_column(Float, default=0.0)  # 操作总金额

    # --- 进阶记帐要素 (P1 必填，MVP 可选) ---
    confirm_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # 确认日期 (到账日)
    unit_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 单位: share, lot, piece
    total_cost: Mapped[float | None] = mapped_column(Float, nullable=True)  # 含手续费总成本

    # --- 审计要素 (P1 可选) ---
    record_code: Mapped[str | None] = mapped_column(String(36), nullable=True)  # 平台流水号 (用于对账)
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)  # 复盘备注
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
