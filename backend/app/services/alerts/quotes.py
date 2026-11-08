# -*- coding: utf-8 -*-
"""自选提醒的**行情供给层**：把「一批标的」压成两次批量查询，输出统一报价。

## 为什么要独立一层
提醒判据（`watchlist_alert_rules`）只认数字，不该知道行情在哪张表；
提醒编排（`watchlist_alert_service`）只调 `load_quotes` 拿结果。这样：

- 以后换/加行情源（实时报价、港股、美股）只改本文件，判据与编排不动；
- 多租户下扫描是**按家庭**跑的，行情是共享的只读数据——本层不做任何用户态过滤，
  也就没有「谁的家庭」泄漏面。

## 两个数据源，口径各自成立
- 场内（股票 / ETF / 指数 / 可转债）：`price_history.close`，**未复权**。
  提醒关心「今天跌了多少」，与用户看到的行价一致；除权日会有一天口径偏差，
  与收益日历同源问题，文案里不写「一定是跌」（`pct_message` 只陈述涨跌幅）。
- 场外基金：`daily_worth.unit_nav`（单位净值）。

## 「近 N 日高点」为什么用自然日近似
逐标的取最近 N 条再求最大值，最坏 250 行 × 自选数（几十万行）——请求路径扛不住。
改为「自然日窗口 ≥ 交易日窗口」：`cutoff = today - window_days * 1.5`，
配合一条 `GROUP BY symbol` 的 `MAX(close)`，查询量与自选数同阶、与窗口无关。
代价是高点可能比「恰好 N 个交易日」更早几天（回撤算得略大一点点），
方向偏向「更早提醒」，对提醒类是安全的一侧。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.funds.models import DailyWorth
from app.domains.price_history.models import PriceHistory
from app.services.watchlist_service import bare_code_of

# 自然日 → 交易日的放大系数（含节假日余量），见模块 docstring。
_CALENDAR_DAYS_FACTOR = 1.5
_CALENDAR_DAYS_PADDING = 7

# 无行情意义的品类：经理（MGR_）、投顾组合（平台原生码）没有自己的行情。
_NO_QUOTE_TYPES = frozenset({'manager', 'portfolio'})


@dataclass(frozen=True)
class SymbolQuote:
    """某标的的提醒用报价快照（缺失字段一律 None，不拿 0 兜底）。"""

    latest: Optional[float] = None
    prev: Optional[float] = None
    window_high: Optional[float] = None
    as_of: Optional[date] = None
    source: str = ''


def is_fund_like(asset_type: Optional[str]) -> bool:
    """场外基金判据：与 `watchlist_display` 的基金口径一致（asset_type=='fund'）。"""
    return (asset_type or '').strip().lower() == 'fund'


def has_quote(asset_type: Optional[str]) -> bool:
    """该品类是否有行情可比（经理/投顾组合没有，扫描直接跳过）。"""
    return (asset_type or '').strip().lower() not in _NO_QUOTE_TYPES


def load_quotes(
    db: Session,
    targets: Sequence[tuple[str, Optional[str]]],
    window_days: int,
) -> dict[str, SymbolQuote]:
    """批量取报价：`targets` 为 `(symbol, asset_type)` 列表，返回 `symbol → SymbolQuote`。

    两次查询（场内一次、场外一次），与标的数量同阶；缺数据的标的**不出现在结果里**
    （调用方据此判「无可比行情」而跳过，不会拿旧值硬算）。
    """
    if not targets:
        return {}

    market_symbols: list[str] = []
    fund_codes: list[str] = []
    for symbol, asset_type in targets:
        if not symbol or not has_quote(asset_type):
            continue
        if is_fund_like(asset_type):
            code = bare_code_of(symbol) or symbol
            if code not in fund_codes:
                fund_codes.append(code)
        elif symbol not in market_symbols:
            market_symbols.append(symbol)

    quotes: dict[str, SymbolQuote] = {}
    quotes.update(_load_price_history(db, market_symbols, window_days))
    for code, quote in _load_daily_worth(db, fund_codes, window_days).items():
        quotes.setdefault(code, quote)
    return quotes


def _window_cutoff(window_days: int) -> date:
    days = int(max(1, window_days) * _CALENDAR_DAYS_FACTOR) + _CALENDAR_DAYS_PADDING
    return date.today() - timedelta(days=days)


def _last_two_rows(db: Session, code_column, date_column, value_column, codes: Iterable[str]):
    """最近两条（当日 + 前一交易日）的批量取法：`ROW_NUMBER() <= 2` 一次拿齐。"""
    rn = func.row_number().over(partition_by=code_column, order_by=date_column.desc()).label('rn')
    sub = (
        db.query(code_column.label('code'), date_column.label('as_of'), value_column.label('value'), rn)
        .filter(code_column.in_(list(codes)), value_column.isnot(None))
        .subquery()
    )
    return db.query(sub.c.code, sub.c.as_of, sub.c.value).filter(sub.c.rn <= 2).all()


def _window_highs(db: Session, code_column, date_column, value_column, codes: list[str], window_days: int) -> dict:
    """窗口内最高值（自然日近似，见模块 docstring）。"""
    if not codes:
        return {}
    rows = (
        db.query(code_column, func.max(value_column))
        .filter(code_column.in_(codes), date_column >= _window_cutoff(window_days), value_column.isnot(None))
        .group_by(code_column)
        .all()
    )
    return {code: high for code, high in rows if high is not None}


def _load_price_history(db: Session, symbols: list[str], window_days: int) -> dict[str, SymbolQuote]:
    """场内行情：价格历史表（未复权收盘价）。"""
    if not symbols:
        return {}
    rows = _last_two_rows(db, PriceHistory.symbol, PriceHistory.trade_date, PriceHistory.close, symbols)
    highs = _window_highs(db, PriceHistory.symbol, PriceHistory.trade_date, PriceHistory.close, symbols, window_days)
    return _assemble(rows, highs, 'price_history')


def _load_daily_worth(db: Session, codes: list[str], window_days: int) -> dict[str, SymbolQuote]:
    """场外基金：每日单位净值。"""
    if not codes:
        return {}
    rows = _last_two_rows(db, DailyWorth.fund_code, DailyWorth.date, DailyWorth.unit_nav, codes)
    highs = _window_highs(db, DailyWorth.fund_code, DailyWorth.date, DailyWorth.unit_nav, codes, window_days)
    return _assemble(rows, highs, 'daily_worth')


def _assemble(rows, highs: dict, source: str) -> dict[str, SymbolQuote]:
    """把「最近两行 + 窗口高点」拼成报价快照。"""
    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row.code, []).append(row)
    quotes: dict[str, SymbolQuote] = {}
    for code, items in grouped.items():
        items.sort(key=lambda r: r.as_of, reverse=True)
        latest_row = items[0]
        prev_row = items[1] if len(items) > 1 else None
        quotes[code] = SymbolQuote(
            latest=_as_float(latest_row.value),
            prev=_as_float(prev_row.value) if prev_row is not None else None,
            window_high=_as_float(highs.get(code)) or _as_float(latest_row.value),
            as_of=latest_row.as_of,
            source=source,
        )
    return quotes


def _as_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
