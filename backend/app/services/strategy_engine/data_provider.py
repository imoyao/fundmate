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
from datetime import date, timedelta
from typing import Iterable, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from app.core.money import Money
from app.domains.funds.models import DailyWorth, Fund
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
        # 请求内缓存（#2639）
        #     DataProvider 由视图按**请求**新建（`behavior_profiles` 内一次性传入），
        #     故实例级 dict 天然是请求作用域，不存在跨请求读到陈旧数据的问题；
        #     也正因如此才不引入进程级/外部缓存——那需要失效策略，收益不值。
        self._fund_type_cache: dict[str, int | None] = {}
        self._peer_codes_cache: dict[int, tuple[str, ...] | None] = {}
        self._peer_returns_cache: dict[tuple[int, date, int], tuple[float, ...] | None] = {}

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

    # ── 同类分组（#2382 buy_percentile 用） ──

    def fund_type_id_of(self, fund_code: str) -> int | None:
        """基金小类 id（`funds.fund_type_id`）；查不到返回 None。

        分步查询：funds 表在 market 域，与 daily_worth 同库，无 join。
        请求内按 fund_code 缓存（#2639）：画像逐标的、逐买入日都会问一次同一个代码。
        """
        if fund_code in self._fund_type_cache:
            return self._fund_type_cache[fund_code]
        row = self.market_db.query(Fund.fund_type_id).filter(Fund.fund_code == fund_code).first()
        value = int(row[0]) if row and row[0] is not None else None
        self._fund_type_cache[fund_code] = value
        return value

    def _peer_codes_of(self, type_id: int) -> tuple[str, ...] | None:
        """该小类下全部基金裸码（按代码升序）；无则 None。请求内按 type 缓存（#2639）。"""
        if type_id in self._peer_codes_cache:
            return self._peer_codes_cache[type_id]
        codes = tuple(
            sorted(
                r[0] for r in self.market_db.query(Fund.fund_code).filter(Fund.fund_type_id == type_id).all() if r[0]
            )
        )
        self._peer_codes_cache[type_id] = codes or None
        return self._peer_codes_cache[type_id]

    def peer_year_returns(
        self,
        fund_code: str,
        as_of: date,
        window_days: int = 365,
    ) -> tuple[float, ...] | None:
        """as_of 回看 window_days，同 `fund_type_id` 基金的区间收益率集合（%，含自身）。

        用于 `buy_percentile`（#2382）：判断买入时点该基金在同类中的分位。

        口径
            - 每只同类基金取窗口内**最早**与**最晚**两条净值算区间收益
              （不要求同一起止日，诚实按各自可得数据）；
            - 窗口内无净值 / 起点为 0 的基金不计入（宁缺勿假）；
            - 返回集合**含自身**（`percentile_rank` 的中位秩口径要求 peers 含自身）；
            - 自身不在窗口内（新基金）仍返回同类集合，由调用方降级。

        性能（#2639 重写，口径未变）
            旧实现把窗口内**全部净值行**拉进 Python 再逐行求首末，实测单类型 1,381 只
            同类基金时单次 11,214 行 / 32ms，画像接口 311 次调用共 32–42 秒。
            两处浪费：只为 52 个值读了 11,214 行；同一 `(type_id, as_of)` 被不同标的
            重复计算。

            现改为**一条语句只取首末净值**：先在子查询里 `GROUP BY fund_code` 求
            窗口内首末日期（走 `(fund_code, date)` 覆盖索引，不回表），再自连接回
            `daily_worth` 只取这 2×N 个点的 `unit_nav`。返回行数 11,214 → 52，
            实测 32.1ms → 19.3ms（其中纯 SQL 21.9 → 11.7ms）。
            结果按 `(type_id, as_of, window_days)` 请求内缓存——同类型同买入日的计算
            完全可复用，实测画像请求 311 次调用收敛为 126 次真实计算。

            试过但**更慢**的写法，勿回退：`JOIN funds` 替代 `fund_code IN (...)`
            会让 SQLite 走 `SCAN funds` + 嵌套索引查找，实测 122ms（是 IN 版的 4 倍）。
        """
        type_id = self.fund_type_id_of(fund_code)
        if type_id is None:
            return None

        key = (type_id, as_of, window_days)
        if key in self._peer_returns_cache:
            return self._peer_returns_cache[key]

        peer_codes = self._peer_codes_of(type_id)
        if not peer_codes:
            self._peer_returns_cache[key] = None
            return None

        window_start = as_of - timedelta(days=window_days)
        first_last = (
            select(
                DailyWorth.fund_code.label('fund_code'),
                func.min(DailyWorth.date).label('first_date'),
                func.max(DailyWorth.date).label('last_date'),
            )
            .where(
                DailyWorth.fund_code.in_(peer_codes),
                DailyWorth.date >= window_start,
                DailyWorth.date <= as_of,
                # 与旧实现同口径：净值缺失的点不参与「首末」判定
                DailyWorth.unit_nav.is_not(None),
            )
            .group_by(DailyWorth.fund_code)
            .subquery()
        )
        head = aliased(DailyWorth)
        tail = aliased(DailyWorth)
        rows = self.market_db.execute(
            select(first_last.c.fund_code, head.unit_nav, tail.unit_nav)
            .join(head, and_(head.fund_code == first_last.c.fund_code, head.date == first_last.c.first_date))
            .join(tail, and_(tail.fund_code == first_last.c.fund_code, tail.date == first_last.c.last_date))
            .order_by(first_last.c.fund_code)
        ).all()

        out: list[float] = []
        for _code, first_nav, last_nav in rows:
            if first_nav is None or last_nav is None:
                continue
            first, last = float(first_nav), float(last_nav)
            if first == 0:  # 起点为 0 无法算收益，不计入（宁缺勿假）
                continue
            out.append((last - first) / first * 100.0)
        result = tuple(out)
        self._peer_returns_cache[key] = result
        return result

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
