# -*- coding: utf-8 -*-
# Author : imoyao
"""#2619 交易行为画像（账本精灵对话层的取数服务）。

回答的是「我是怎样的投资者」：持有期分布、换手、买卖结构、买点位置。
全部由既有 `transactions` / `positions` / `price_history` 算出，**零新表、零新列、
零外部请求**，FIFO 配对复用 `analytics.behavior.compute_behavior_stats`（#994 口径 v2），
不另造一套算账。

## 三条口径边界（都是真库实测踩出来的）

1. **窗口只筛样本，不筛配对**：`start_date/end_date` 决定「哪些事件计入统计」，
   FIFO 配对始终在**全量**流水上做。若先把流水按窗口裁掉，窗口内的卖出就找不到
   窗口前的买入批次 ⇒ 持有期整批丢失、`unmatched` 暴涨。这是本模块最容易被写错的一处。
2. **换手率是近似值**：`Σ|区间成交额| / 2 / 当前持仓市值`。分母只能用**当前**市值
   ——库里没有历史市值序列（日级 `daily_pnl` 不含水平值，无法反推）。故它与「区间
   日均市值」不可比，偏差方向取决于市值变化（市值涨了偏低、跌了偏高），返回值里
   明写 `turnover_note`，不假装是日均可比口径。
3. **买点分位只认前复权**：`price_history.adj_close` 缺失的标的**整只不参与**，
   绝不拿未复权 `close` 顶替（两者不可混算，见 `price_history` 模型注释）。真库
   实测 `price_history` 仅覆盖 60 个标的、自 2025-06 起 —— 覆盖率会很低，
   故逐笔不可算的买入如实计入 `total_buys` 而不进 `covered_buys`。

## 不做什么

不做「好坏评价」（不输出「换手过高」「追涨」这类判断）、不做收益预测/回测
（#2381 已证伪择时类回测）、不做跨用户对比排名。
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.asset_types import EXCLUDED_ASSET_TYPES
from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.price_history.models import PriceHistory
from app.domains.transactions.models import Transaction
from app.services.analytics.behavior import compute_behavior_stats
from app.services.position_scope import exclude_cleared
from app.services.position_valuation import market_value_cents

# 买点分位的回看窗口（自然日）与最小样本：低于 20 个交易日的分位没有意义
PRICE_LOOKBACK_DAYS = 365
PRICE_MIN_SAMPLES = 20

_BUY_TYPES = frozenset({'buy', 'dividend_reinvest'})
_SELL_TYPES = frozenset({'sell'})


def _txn_date(txn: Any) -> Optional[dt.date]:
    """确认日优先、交易日兜底（与 `analytics.behavior` 同一语义）。"""
    value = getattr(txn, 'confirm_date', None) or getattr(txn, 'trade_date', None)
    if isinstance(value, dt.datetime):
        return value.date()
    return value if isinstance(value, dt.date) else None


def _earliest_confirm_date(db: Session, family_id: int) -> Optional[str]:
    """本家庭最早一笔流水的确认日（「缺省全期」的起点）。

    用 `confirm_date` 而非 `trade_date`：真库 1927 笔中 1211 笔 `trade_date` 为空。
    """
    earliest = db.query(func.min(Transaction.confirm_date)).filter(Transaction.family_id == family_id).scalar()
    return earliest.isoformat() if earliest else None


def _resolve_window(db: Session, family_id: int, start_date: Optional[str], end_date: Optional[str]) -> Tuple[str, str]:
    end = end_date or dt.date.today().isoformat()
    start = start_date or _earliest_confirm_date(db, family_id) or end
    return start, end


def _position_market_value_cents(db: Session, family_id: int, symbol: Optional[str]) -> int:
    """当前持仓市值（分）：排除已清仓与类现金资产，与行为画像/XIRR 同一套过滤。"""
    query = exclude_cleared(db.query(Position)).filter(Position.family_id == family_id)
    if symbol:
        query = query.filter(Position.symbol == symbol)
    total = 0
    for pos in query.all():
        if (getattr(pos, 'asset_type', None) or '') in EXCLUDED_ASSET_TYPES:
            continue
        total += market_value_cents(pos)
    return total


def _percentile_rank(window_closes: List[float], price: float) -> float:
    """买入价在窗口收盘序列中的百分位秩（0–100，含等号）。

    纯函数便于单测：`∑(c ≤ price) / n × 100`。买在窗口最低点 → 0（或最小秩），
    买在最高点 → 100；**不评价好坏**，只是位置。
    """
    if not window_closes:
        raise ValueError('窗口为空：调用方须先保证样本数达标')
    return sum(1 for c in window_closes if c <= price) / len(window_closes) * 100


def _buy_price_percentiles(
    db: Session,
    buys: List[Tuple[str, dt.date, float]],
) -> Dict[str, Any]:
    """每笔买入价在其前复权收盘序列中的百分位秩（0–100），返回均值与覆盖率。

    `buys` = [(symbol, 买入日, 买入价元)]。逐标的批量取一次价格序列（前扩
    `PRICE_LOOKBACK_DAYS`），窗口内不足 `PRICE_MIN_SAMPLES` 个点不计入（分位无意义）。
    """
    by_symbol: Dict[str, List[Tuple[dt.date, float]]] = defaultdict(list)
    for symbol, trade_date, price in buys:
        by_symbol[symbol].append((trade_date, price))

    percentiles: List[float] = []
    covered = 0
    missing_price_symbols = 0
    for symbol, samples in by_symbol.items():
        min_date = min(d for d, _ in samples) - dt.timedelta(days=PRICE_LOOKBACK_DAYS)
        max_date = max(d for d, _ in samples)
        rows = (
            db.query(PriceHistory.trade_date, PriceHistory.adj_close)
            .filter(
                PriceHistory.symbol == symbol,
                PriceHistory.trade_date >= min_date,
                PriceHistory.trade_date <= max_date,
                PriceHistory.adj_close.isnot(None),
            )
            .order_by(PriceHistory.trade_date)
            .all()
        )
        if not rows:
            missing_price_symbols += 1
            continue
        closes = [(row.trade_date, float(row.adj_close)) for row in rows]
        for trade_date, price in samples:
            window = [c for d, c in closes if d <= trade_date]
            if len(window) < PRICE_MIN_SAMPLES:
                continue
            percentiles.append(_percentile_rank(window, price))
            covered += 1

    total = len(buys)
    return {
        'mean': round(sum(percentiles) / len(percentiles), 2) if percentiles else None,
        'covered_buys': covered,
        'total_buys': total,
        'coverage_pct': round(covered / total * 100, 2) if total else None,
        'missing_price_symbols': missing_price_symbols,
        'note': (
            f'分位 = 买入价在「买入日前 {PRICE_LOOKBACK_DAYS} 天」前复权收盘序列中的百分位秩；'
            f'窗口内不足 {PRICE_MIN_SAMPLES} 个点不计入；无前复权价的标的不参与（不与未复权收盘混算）'
        ),
    }


def build_trading_behavior(
    db: Session,
    family_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    symbol: Optional[str] = None,
    include_cash_equivalents: bool = False,
) -> Dict[str, Any]:
    """交易行为画像（#2619）。

    Args:
        start_date / end_date: 统计窗口（缺省全期）；只筛计样本，不裁 FIFO 配对。
        symbol: 限定标的（缺省全部持仓与流水）。
        include_cash_equivalents: 是否纳入货基/逆回购等类现金资产（默认排除）。

    Returns:
        持有期分布 / 交易结构 / 换手 / 买点分位 + `caveats`。算不出的字段为 None，
        **不填 0 冒充**（例如零卖出 ⇒ `buy_sell_ratio` 为 None）。
    """
    start_date, end_date = _resolve_window(db, family_id, start_date, end_date)

    txn_query = db.query(Transaction).filter(Transaction.family_id == family_id)
    if symbol:
        txn_query = txn_query.filter(Transaction.symbol == symbol)
    if not include_cash_equivalents:
        txn_query = txn_query.filter(
            Transaction.asset_type.is_(None) | Transaction.asset_type.not_in(EXCLUDED_ASSET_TYPES)
        )
    transactions = txn_query.all()

    stats = compute_behavior_stats(transactions, start_date, end_date)

    win_start = dt.date.fromisoformat(start_date)
    win_end = dt.date.fromisoformat(end_date)
    window_txns = [t for t in transactions if (d := _txn_date(t)) is not None and win_start <= d <= win_end]

    traded_cents = 0
    buys: List[Tuple[str, dt.date, float]] = []
    for txn in window_txns:
        txn_type = getattr(txn, 'txn_type', None)
        if txn_type in _BUY_TYPES or txn_type in _SELL_TYPES:
            traded_cents += abs(int(getattr(txn, 'amount', None) or 0))
        if txn_type in _BUY_TYPES:
            price_units = int(getattr(txn, 'price', None) or 0)
            buy_date = _txn_date(txn)
            if price_units > 0 and buy_date is not None:
                buys.append((getattr(txn, 'symbol', None) or '', buy_date, Money.price_units_to_yuan(price_units)))

    mv_cents = _position_market_value_cents(db, family_id, symbol)
    turnover_pct = round(traded_cents / 2 / mv_cents * 100, 2) if mv_cents > 0 else None

    buy_count = stats['buy_count']
    sell_count = stats['sell_count']
    caveats = list(stats['caveats'])
    caveats.append(
        '换手率 = Σ|区间成交额| / 2 / 当前持仓市值；分母不是区间日均市值，偏差方向取决于市值变化（涨了偏低、跌了偏高）'
    )
    if stats['unmatched_sell_count'] > 0:
        caveats.append(
            f'{stats["unmatched_sell_count"]} 笔卖出未能全额配对（存量流水缺买入批次）：'
            '持有期样本与「割肉回补」计数会偏低，不是没有发生'
        )
    if buy_count == 0 and sell_count == 0:
        caveats.append('该窗口内没有买卖流水：交易结构类指标为空是「没发生」，不是「算不出」')

    return {
        'symbol': symbol,
        'scope': 'symbol' if symbol else 'family',
        'start_date': start_date,
        'end_date': end_date,
        'holding': {
            'avg_days': stats['avg_holding_days'],
            'p25': stats['holding_days_p25'],
            'p50': stats['holding_days_p50'],
            'p75': stats['holding_days_p75'],
            'samples': stats['holding_days_samples'],
            'note': '分位数样本 = 每笔卖出的份额加权持有天数；avg_days 是全局份额加权，两者分母不同',
        },
        'trading': {
            'buy_count': buy_count,
            'sell_count': sell_count,
            'buy_sell_ratio': round(buy_count / sell_count, 2) if sell_count else None,
            'total_count': buy_count + sell_count,
            'turnover_pct': turnover_pct,
        },
        'structure': {
            'consecutive_add_count': stats['consecutive_add_count'],
            'rebuy_after_loss_count': stats['rebuy_after_loss_count'],
            'closed_count': stats['closed_count'],
            'unmatched_sell_count': stats['unmatched_sell_count'],
        },
        'buy_price_percentile': _buy_price_percentiles(db, buys),
        'caveats': caveats,
    }


__all__ = ['build_trading_behavior']
