# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/9
# File : stock_profile.py
# app/services/stock_profile.py
"""股票资料聚合（#1969 · 产品详情页股票详情区块）。

为什么需要这个聚合函数（沿用 #1968 的硬规则「拼不出首屏就在本卡内补端点」）：

- **基本资料**：securities 域只有 ``search/``（关键词搜列表）与 ``<symbol>/price-range/``
  ——后者是**记账回填用**的单日可成交价区间（#948：手动记账补价与区间校验），语义上不是
  「这只股票的资料」，也没有行业 / 币种等字段的出口；
- **区间行情**：行情明细在 ``price_history``。若让前端自己算区间高低，就得把整段明细拉回
  浏览器再聚合——违反数据策略（明细不在前端算）。

故此处**一次查完**并返回，前端一次请求拿到「基本资料 + 区间行情」。字段缺失一律返回
``None`` 由前端降级为「—」，不编造占位值。

数据口径（与既有实现对齐，**不另起链路**）：

- 收盘价取 ``adj_close``（前复权），缺失时回退 ``close``——同 ``services/product_trend``
  与 ``pnl_calendar`` 的理由：除权日用 ``close`` 会跳空，算出来的区间涨跌幅是假的；
- 区间高低用 ``high`` / ``low`` 原值（**不**复权）：展示口径与持仓页「当日最高 / 最低」
  一致，复权后的高低对用户没有解释成本；
- 区间默认 **60 个交易日**，与自选迷你走势（``/api/watchlist/trends/`` 的 60 日窗口）
  同口径，便于两处数字对得上；``trading_days`` 如实回实际条数，历史不足时前端可提示。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.data_sources import data_source_label

# 区间统计窗口（交易日）。与 watchlist 迷你走势的 60 日一致，见模块 docstring。
DEFAULT_WINDOW = 60


def _quote_stats(db: Session, symbol: str, window: int = DEFAULT_WINDOW) -> Dict[str, Any]:
    """区间行情统计：最新收盘 + 区间最高 / 最低 + 区间涨跌幅。

    取最近 ``window`` 个**交易日**（按 ``trade_date`` 倒序取满 ``window`` 行再统计），
    而不是按自然日切窗口——停牌与假期会让自然日窗口内的交易日条数忽多忽少，「近 60 日」
    在不同股票上口径会漂。

    区间涨跌幅 = (最新收盘 − 区间最早收盘) ÷ 区间最早收盘。分母为 0 或缺失时返回 ``None``
    而非 0，避免「没数据」被读成「没涨」。
    """
    from app.domains.price_history.models import PriceHistory

    rows = (
        db.query(
            PriceHistory.trade_date,
            PriceHistory.adj_close,
            PriceHistory.close,
            PriceHistory.high,
            PriceHistory.low,
            PriceHistory.source,
        )
        .filter(PriceHistory.symbol == symbol)
        .order_by(PriceHistory.trade_date.desc())
        .limit(window)
        .all()
    )
    if not rows:
        return {
            'quote_date': None,
            'close': None,
            'high': None,
            'low': None,
            'change_pct': None,
            'trading_days': 0,
            'source': '',
        }

    # 倒序：第 0 条是最新。收盘价口径与走势一致——优先前复权。
    closes_desc = [adj if adj is not None else close for _d, adj, close, _h, _l, _s in rows]
    closes_desc = [c for c in closes_desc if c is not None]
    highs = [h for _d, _a, _c, h, _l, _s in rows if h is not None]
    lows = [low for _d, _a, _c, _h, low, _s in rows if low is not None]

    latest_close = closes_desc[0] if closes_desc else None
    earliest_close = closes_desc[-1] if closes_desc else None
    change_pct = (
        round((latest_close - earliest_close) / earliest_close * 100, 2)
        if latest_close is not None and earliest_close
        else None
    )

    return {
        'quote_date': rows[0][0].isoformat() if rows[0][0] else None,
        'close': float(latest_close) if latest_close is not None else None,
        'high': float(max(highs)) if highs else None,
        'low': float(min(lows)) if lows else None,
        'change_pct': change_pct,
        'trading_days': len(rows),
        # 站点名（新浪财经 / 东方财富…）而非 price_history 这类内部表名（#1969）
        'source': data_source_label(rows[0][5]),
    }


def build_stock_profile(
    db: Session,
    symbol: str,
    market: Optional[str] = None,
    window: int = DEFAULT_WINDOW,
) -> Optional[Dict[str, Any]]:
    """一次拼出单只股票的资料 + 区间行情（详情页股票区块）。

    Args:
        db: **market 域**会话（``securities`` 与 ``price_history`` 都在 market 域，
            生产下是独立引擎，见 ``core/db_factory.DATA_DOMAIN_REGISTRY``）。
        symbol: 产品代码（带市场前缀形态，如 ``SZ000001``）。
        market: 市场消歧。同码跨市场时由详情页 resolve 结果带下来；为空则不按市场过滤。
        window: 区间统计窗口（交易日）。

    Returns:
        资料 dict；**证券不存在时返回 None**（由调用方转 404）。

    Raises:
        ValueError: ``symbol`` 为空。
    """
    from app.domains.securities.models import Security

    code = (symbol or '').strip().upper()
    if not code:
        raise ValueError('缺少 symbol 参数')

    query = db.query(Security).filter(Security.symbol == code)
    if market:
        query = query.filter(Security.market == market)
    security = query.first()
    if security is None:
        return None

    stats = _quote_stats(db, code, window)

    return {
        'symbol': security.symbol,
        'name': security.name,
        'market': security.market,
        # securities.type 存的即品类（stock / etf / bond / future / crypto），
        # 对外统一叫 asset_type，与 resolve 端点及其他区块口径一致
        'asset_type': security.type,
        'currency': security.currency,
        # 行业 / 板块：securities.sector 填充率有限（同步 job 覆盖度问题），
        # 缺失时前端降级为「—」，不为凑版面去外部数据源补（设计 §6「诚实降级」）
        'sector': security.sector,
        'window_days': window,
        # 口径说明（与来源分开）：来源回答「哪来的」，口径回答「怎么算的」
        'basis': '前复权收盘价 / 未复权高低',
        **stats,
    }