# -*- coding: utf-8 -*-
"""场内标的的「卖出日及之前最近一条**前复权**收盘价」批量查询（#2773 场内收口）。

WHY 单独成模块
    清仓后涨跌幅的场外一侧走 `NavService.get_navs_at_or_before`（`daily_worth`），
    场内一侧要用 `price_history.adj_close`。两者是**两张表、两套口径**，但查询形状
    完全一样（每只取 ``date <= target`` 的最近一条 + 批量）。把它塞进 `nav_service`
    会让「基金净值」这个模块开始读行情表；塞进 `price_range_service`（那模块的
    职责是「某交易日的价格**区间**」）又会让它多出一个「历史锚点」语义。故单列。

WHY 必须用 ``adj_close`` 而不是 ``close``
    `price_history.close` 是**未复权**收盘价，`adj_close` 是**前复权**（#1104 拍板，
    见 `adapters/akshare_adapter.fetch_stock_price` 的 docstring）。跨分红除权时
    未复权价会向下跳一个等于分红幅度的台阶，于是「卖出后跌了 5%」可能纯属除权——
    那是把分红算成亏损，方向都错了。区间收益一律用前复权，这条没有例外。

WHY 不做远程兜底
    这是复盘页的批量计算，不允许在请求路径内触网（与 `get_navs_at_or_before`
    同一条约束）。缺数据就如实报「算不出」，由数据同步任务去补。
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.symbol_utils import get_normalizer
from app.domains.price_history.models import PriceHistory


def get_adj_close_at_or_before(
    db: Session,
    symbols: List[str],
    target_date: date,
) -> Dict[str, Tuple[float, date]]:
    """批量取每只标的在 ``target_date`` **当日或之前最近一条**前复权收盘价。

    Args:
        db: 会话。
        symbols: ``price_history.symbol`` 形态的代码（即归一后的 ``SZ000001`` /
            ``SH600519`` / ``HK00700``；调用方可从身份键 ``EXCHANGE:xxxx`` 直接切出）。
        target_date: 上界（含）。卖出日不一定是交易日，故按「<= 最近一条」取。

    Returns:
        ``{symbol: (adj_close, trade_date)}``。``adj_close`` 缺失或非正的行**直接缺席**
        （不从 ``close`` 顶替）——混口径会让跨分红的涨幅凭空多出一截，比没有数更糟。
        ``trade_date`` 是实际命中的交易日，可能早于 ``target_date``。
    """
    if not symbols:
        return {}

    normalized = []
    normalizer = get_normalizer()
    for symbol in symbols:
        try:
            code, _, _ = normalizer.normalize(symbol)
        except Exception:  # noqa: BLE001 — 归一失败退字面量，别让整批查挂掉
            code = symbol
        if code:
            normalized.append(code)
    if not normalized:
        return {}

    try:
        latest_dates = (
            db.query(
                PriceHistory.symbol,
                func.max(PriceHistory.trade_date).label('max_date'),
            )
            .filter(
                PriceHistory.symbol.in_(normalized),
                PriceHistory.trade_date <= target_date,
            )
            .group_by(PriceHistory.symbol)
            .subquery()
        )
        rows = (
            db.query(
                PriceHistory.symbol,
                PriceHistory.adj_close,
                PriceHistory.trade_date,
            )
            .join(
                latest_dates,
                (PriceHistory.symbol == latest_dates.c.symbol) & (PriceHistory.trade_date == latest_dates.c.max_date),
            )
            .all()
        )
    except Exception:
        logger.exception('查询 price_history 前复权锚点失败')
        return {}

    result: Dict[str, Tuple[float, date]] = {}
    for symbol, adj_close, trade_date in rows:
        if not symbol or trade_date is None:
            continue
        if adj_close is None or float(adj_close) <= 0:
            continue  # 无前复权价 = 这条不可用，等同没查到（不回落 close）
        result[symbol] = (float(adj_close), trade_date)
    return result


def symbol_of_exchange_identity(identity: Optional[str]) -> Optional[str]:
    """``EXCHANGE:SZ000001`` → ``SZ000001``；非场内身份返回 None。

    身份键的 venue 部分**已经**是归一后的行情代码（`symbol_identity` 与
    `get_normalizer().normalize()` 共用同一套规范化），故这里只切不做二次归一。
    """
    if not identity or not identity.startswith('EXCHANGE:'):
        return None
    code = identity.split(':', 1)[1].strip()
    return code or None
