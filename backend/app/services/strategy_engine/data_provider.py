# -*- coding: utf-8 -*-
"""策略引擎数据适配层（#2224）——把库内数据翻译成契约层要的纯数据。

边界
    - 只做「取数 + 单位换算 + 排序」，**不做任何策略判断**（判断在 strategy 层）；
    - 金额 / 份额换算一律走 `core.money.Money`，本模块不硬编码 10000 / 100；
    - **不跨域 JOIN**：`daily_worth` / `price_history` 属 market 域，
      `positions` / `transactions` 属 user 域，生产双库下两者不在同一会话。
      故 `market_db` 可显式注入；未注入时复用同一会话（本地单库），
      两种情况都是**分步查询**，不写任何跨表 join。

单位口径（沿用本仓既有约定，勿改）
    - quantity：0.0001 份 → `Money.min_unit_to_shares`
    - price：0.0001 元   → `Money.price_units_to_yuan`
    - daily_worth.unit_nav：元（Decimal，精度 6）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Sequence

from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.funds.models import DailyWorth
from app.domains.positions.models import Position
from app.domains.price_history.models import PriceHistory
from app.domains.transactions.models import Transaction
from app.services.strategy_engine.behavior_profile import TradeRecord
from app.services.strategy_engine.contracts import SeriesPoint

#: 场内/场外都可能出现的前缀形态；取数字尾部 6 位作为基金裸码
_FUND_CODE_RE = re.compile(r'\d+')


@dataclass(frozen=True)
class HoldingRow:
    """归一化持仓（单位已换算：份 / 元）。"""

    position_id: int
    symbol: str
    name: str
    asset_type: str
    quantity: float
    avg_price: float


def extract_fund_code(symbol: str | None) -> str | None:
    """从展示形态 symbol 提取 6 位基金裸码；不足 6 位数字返回 None。

    例：`OTC:004369` → `004369`，`EXCHANGE:SZ159915` → `159915`。
    """
    if not symbol:
        return None
    digits = ''.join(_FUND_CODE_RE.findall(symbol))
    return digits[-6:] if len(digits) >= 6 else None


class DataProvider:
    """策略引擎的取数出口。策略层永远不直接碰 Session。"""

    def __init__(self, db: Session, market_db: Session | None = None) -> None:
        self.db = db
        self.market_db = market_db if market_db is not None else db

    # ── 行情 ──

    def nav_series(self, symbol: str, limit: int = 260) -> tuple[SeriesPoint, ...]:
        """取标的的净值 / 收盘价序列（升序，最多 `limit` 条最近的）。

        先查场外 `daily_worth`（基金净值），再回落场内 `price_history`（收盘价）。
        两者都是**分步查询**，无 join。取不到返回空元组——由策略层降级成 WATCH，
        本层不补零、不伪造日期。
        """
        code = extract_fund_code(symbol)
        if code:
            rows = (
                self.market_db.query(DailyWorth.date, DailyWorth.unit_nav)
                .filter(DailyWorth.fund_code == code)
                .order_by(DailyWorth.date.desc())
                .limit(limit)
                .all()
            )
            points = tuple(
                SeriesPoint(date=r[0], value=float(r[1])) for r in reversed(rows) if r[0] and r[1] is not None
            )
            if points:
                return points

        rows = (
            self.market_db.query(PriceHistory.trade_date, PriceHistory.close)
            .filter(PriceHistory.symbol == symbol)
            .order_by(PriceHistory.trade_date.desc())
            .limit(limit)
            .all()
        )
        return tuple(SeriesPoint(date=r[0], value=float(r[1])) for r in reversed(rows) if r[0] and r[1] is not None)

    # ── 持仓 / 流水 ──

    def holdings(self, family_id: int) -> list[HoldingRow]:
        """当前有份额的持仓（单位已换算）。"""
        rows = (
            self.db.query(Position)
            .filter(Position.family_id == family_id, Position.quantity > 0)
            .order_by(Position.id.asc())
            .all()
        )
        return [
            HoldingRow(
                position_id=r.id,
                symbol=r.symbol or '',
                name=r.name or '',
                asset_type=r.asset_type or '',
                quantity=Money.min_unit_to_shares(r.quantity),
                avg_price=Money.price_units_to_yuan(r.avg_price),
            )
            for r in rows
        ]

    def trades(
        self,
        family_id: int,
        symbol: str | None = None,
        symbols: Iterable[str] | None = None,
    ) -> list[TradeRecord]:
        """买卖流水（FIFO 配对所需）。只取 buy / sell，其余类型（分红等）不参与行为画像。"""
        query = self.db.query(Transaction).filter(
            Transaction.family_id == family_id,
            Transaction.txn_type.in_(('buy', 'sell')),
        )
        if symbol:
            query = query.filter(Transaction.symbol == symbol)
        elif symbols:
            query = query.filter(Transaction.symbol.in_(list(symbols)))

        rows = query.order_by(Transaction.trade_date.asc(), Transaction.id.asc()).all()
        out: list[TradeRecord] = []
        for r in rows:
            day = r.trade_date.date() if r.trade_date else r.confirm_date
            if day is None:  # 无日期无法参与持有天数计算，跳过而非伪造
                continue
            out.append(
                TradeRecord(
                    symbol=r.symbol or '',
                    trade_date=day,
                    side=r.txn_type,
                    quantity=Money.min_unit_to_shares(r.quantity),
                    price=Money.price_units_to_yuan(r.price),
                )
            )
        return out

    def group_trades_by_symbol(self, trades: Sequence[TradeRecord]) -> dict[str, list[TradeRecord]]:
        grouped: dict[str, list[TradeRecord]] = {}
        for t in trades:
            grouped.setdefault(t.symbol, []).append(t)
        return grouped


def last_nav_date(points: Sequence[SeriesPoint]) -> date | None:
    return points[-1].date if points else None
