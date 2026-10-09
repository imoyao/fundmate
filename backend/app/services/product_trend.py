# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/9
# File : product_trend.py
# app/services/product_trend.py
"""产品历史走势取数（#1967 · 产品详情页走势区块）。

与 ``/api/watchlist/trends/``（#990 迷你走势图）的差别，也正是本模块存在的理由：

1. **带日期轴**：trends 只返回数值数组（迷你图不画坐标轴），而详情页区块要在
   x 轴上展示、并给出「数据日期」口径脚注，故此处返回 ``dates`` + ``values``；
2. **单标的 + 区间语义**：trends 是批量 sparkline 数据源（``symbols`` csv、``days``
   限幅 250 自然日），本模块只服务详情页一个产品，区间用 ``1M/3M/6M/1Y`` 表达。

数据口径（与既有实现对齐，**不另起链路**）：

- 场内（stock / etf / bond）：``price_history``，**优先 ``adj_close``（前复权）**，
  缺失时回退 ``close``。同 ``pnl_calendar._collect_price_history`` 的理由——除权日用
  ``close`` 会跳空，画出来的「走势」是假的（``close`` 的口径是未复权收盘价，供最新价
  展示与持仓盈亏用，``adj_close`` 才是前复权、供区间收益与收益率曲线用）；
- 场外（fund）：``daily_worth.unit_nav``。``fund_code`` 是**裸 6 位码**，入库侧没有
  ``OF.`` 前缀（见 ``core/venues.py``；该前缀只是 watchlist trends 接口的历史入参约定）；
- 指数 / 基金经理 / 投顾组合：**无历史序列数据源**（``index_daily`` 仅 10 个 ``.WI``
  有日线、且无 API 出口），故返回 ``None`` 由调用方降级为 ``—``，不假装有数据。
"""

from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.domains.funds.models import DailyWorth
from app.domains.price_history.models import PriceHistory

# 区间 → 自然日天数（设计 §5 B 区块：1M / 3M / 6M / 1Y）
RANGE_DAYS: Dict[str, int] = {
    '1M': 30,
    '3M': 90,
    '6M': 180,
    '1Y': 365,
}
# 设计 §12 ⑤：默认档 3M
DEFAULT_RANGE = '3M'

# 无历史序列能力的品类：指数（index_daily 无 API 出口）、基金经理、投顾组合
_NO_SERIES_TYPES = frozenset({'index', 'manager', 'portfolio'})


def _fetch_close_series(db: Session, symbol: str, start: dt.date) -> List[Tuple[dt.date, float]]:
    """场内前复权收盘价序列（``adj_close`` 缺失时回退 ``close``）。"""
    rows = (
        db.query(PriceHistory.trade_date, PriceHistory.adj_close, PriceHistory.close)
        .filter(PriceHistory.symbol == symbol, PriceHistory.trade_date >= start)
        .order_by(PriceHistory.trade_date)
        .all()
    )
    series: List[Tuple[dt.date, float]] = []
    for trade_date, adj_close, close in rows:
        value = adj_close if adj_close is not None else close
        if value is None:
            continue
        series.append((trade_date, round(float(value), 4)))
    return series


def _fetch_nav_series(db: Session, symbol: str, start: dt.date) -> List[Tuple[dt.date, float]]:
    """场外基金单位净值序列（``daily_worth.fund_code`` 为裸 6 位码）。"""
    code = symbol[3:] if symbol.startswith('OF.') else symbol
    rows = (
        db.query(DailyWorth.date, DailyWorth.unit_nav)
        .filter(DailyWorth.fund_code == code, DailyWorth.date >= start)
        .order_by(DailyWorth.date)
        .all()
    )
    series: List[Tuple[dt.date, float]] = []
    for nav_date, unit_nav in rows:
        if unit_nav is None:
            continue
        series.append((nav_date, round(float(unit_nav), 4)))
    return series


def fetch_product_trend(
    market_db: Session,
    symbol: str,
    asset_type: Optional[str] = None,
    range_key: str = DEFAULT_RANGE,
) -> Optional[Dict]:
    """取单产品的历史序列（含日期轴）。

    Args:
        market_db: **market 域**会话（``price_history`` / ``daily_worth`` 都在 market 域）。
        symbol: 产品代码（带市场前缀形态，如 ``SZ000001``；场外为裸 6 位码）。
        asset_type: 后端判定的品类（来自 ``resolve_product_identity``）。为空时按
            ``fund`` 之外都走场内路径——**前端不推断品类**，故该值应由后端 resolver 给。
        range_key: ``1M`` / ``3M`` / ``6M`` / ``1Y``。

    Returns:
        ``{symbol, kind, dates, values, source, range, requested_days, available_days}``；
        品类本身无序列数据源（指数等）时返回 ``None``，由调用方降级。

    Raises:
        ValueError: ``symbol`` 为空或 ``range_key`` 非法。
    """
    code = (symbol or '').strip().upper()
    if not code:
        raise ValueError('缺少 symbol 参数')
    if range_key not in RANGE_DAYS:
        raise ValueError(f'range 参数非法，仅支持 {"/".join(RANGE_DAYS)}')

    normalized_type = (asset_type or '').strip().lower()
    if normalized_type in _NO_SERIES_TYPES:
        return None

    days = RANGE_DAYS[range_key]
    start = dt.date.today() - dt.timedelta(days=days)

    if normalized_type == 'fund':
        series = _fetch_nav_series(market_db, code, start)
        kind, source = 'nav', 'daily_worth 单位净值'
    else:
        series = _fetch_close_series(market_db, code, start)
        kind, source = 'close', 'price_history 前复权收盘价'

    # 实际可用跨度：用于前端「无长历史自动收敛到可用档」（设计 §12 ⑤），数据不足时
    # 由前端提示收敛，而不是画一条只有几天的曲线假装是 3M。
    available_days = (series[-1][0] - series[0][0]).days if len(series) >= 2 else 0

    return {
        'symbol': code,
        'kind': kind,
        'dates': [d.isoformat() for d, _ in series],
        'values': [v for _, v in series],
        'source': source,
        'range': range_key,
        'requested_days': days,
        'available_days': available_days,
    }
