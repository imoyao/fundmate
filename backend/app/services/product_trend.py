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
- 场外（fund）：``daily_worth`` 的**累计净值** ``acc_nav``（缺失回退 ``unit_nav``，
  与 ``fund_metrics.load_nav_points`` 同源，#2171 修订）。单位净值遇现金分红除息
  跳空，画出来是假暴跌；``fund_code`` 是**裸 6 位码**，入库侧没有 ``OF.`` 前缀
  （见 ``core/venues.py``；该前缀只是 watchlist trends 接口的历史入参约定）；
- 指数（index，#2028）：``index_daily`` 收盘点位，裸 6 位码按交易所后缀候选匹配
  （``000300`` → ``000300.SH`` / ``000300.SZ``）。**有日线才出曲线**：库里没有该
  指数的日线（覆盖极低，万得系 ``.WI`` 码无法从裸码推导）时返回 ``None``，
  前端诚实降级「该品类暂无走势序列」，不假装有数据（#2028 拍板口径结论）；
- 基金经理 / 投顾组合：**无历史序列数据源**，返回 ``None`` 由调用方降级为 ``—``。
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.data_sources import FUND_NAV_SOURCE_LABEL, data_source_label
from app.domains.funds.models import DailyWorth
from app.domains.indices.models import IndexDaily
from app.domains.price_history.models import PriceHistory
from app.services.fund_nav_on_demand import maybe_trigger_nav_backfill

# 区间 → 自然日天数（设计 §5 B 区块：1M / 3M / 6M / 1Y）
RANGE_DAYS: Dict[str, int] = {
    '1M': 30,
    '3M': 90,
    '6M': 180,
    '1Y': 365,
}
# 设计 §12 ⑤：默认档 3M
DEFAULT_RANGE = '3M'


def requested_days_for(range_key: str, start_date: Optional[dt.date] = None) -> int:
    """请求跨度（天）——档位语义，或显式起始日（#2171 建仓期）语义。

    视图层的「无数据降级」分支也要报同一个数，故收口在这里，不两处各算一遍。
    """
    if start_date is not None:
        return (dt.date.today() - min(start_date, dt.date.today())).days + 1
    return RANGE_DAYS.get(range_key, RANGE_DAYS[DEFAULT_RANGE])

# 无历史序列能力的品类：基金经理、投顾组合。指数自 #2028 起走 index_daily（有日线
# 才出曲线，无日线返回 None，见 _fetch_index_series）。
_NO_SERIES_TYPES = frozenset({'manager', 'portfolio'})


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


def _latest_price_source(db: Session, symbol: str) -> str:
    """该标的日线的来源码（取**最近一条**非空 `source`）。

    取最近一条而非全表去重：同一标的的来源可能随时间变过（如 ETF 曾走新浪、后改走
    东财），脚注要反映「眼下这段数据从哪来」，最近一条是最合理的近似。图上真跨了
    来源时以最近为准——不为此扫描整段序列，性价比不划算。
    """
    row = (
        db.query(PriceHistory.source)
        .filter(PriceHistory.symbol == symbol, PriceHistory.source.isnot(None))
        .order_by(PriceHistory.trade_date.desc())
        .first()
    )
    return row[0] if row else ''


def _fetch_ohlc_series(db: Session, symbol: str, start: dt.date) -> List[Dict]:
    """场内 OHLCV 序列（K 线与成交量副图用）。

    **未复权**而非前复权：K 线是「当时真实成交的价格」，用户要拿它跟自己的持仓成本
    对账（同花顺 / 雪球默认也是不复权）。前复权价只在算区间收益时才需要，那条走
    `_fetch_close_series`。

    `open/high/low` 可能为 NULL（存量行或个别来源缺列）——原样回 `None`，不在这里
    用 close 编造盘中数据；前端绘制时按「无盘中数据则退化为收盘价」降级。
    """
    rows = (
        db.query(
            PriceHistory.trade_date,
            PriceHistory.open,
            PriceHistory.high,
            PriceHistory.low,
            PriceHistory.close,
            PriceHistory.volume,
        )
        .filter(PriceHistory.symbol == symbol, PriceHistory.trade_date >= start)
        .order_by(PriceHistory.trade_date)
        .all()
    )
    out: List[Dict] = []
    for trade_date, open_, high, low, close, volume in rows:
        if close is None:
            # close 是 NOT NULL 列，这里防御的是历史脏行；缺收盘价的 K 线没有意义
            continue
        out.append(
            {
                'date': trade_date.isoformat(),
                'open': float(open_) if open_ is not None else None,
                'high': float(high) if high is not None else None,
                'low': float(low) if low is not None else None,
                'close': float(close),
                'volume': float(volume) if volume is not None else None,
            }
        )
    return out


def _fetch_nav_series(db: Session, symbol: str, start: dt.date) -> List[Tuple[dt.date, float]]:
    """场外基金净值序列（``daily_worth.fund_code`` 为裸 6 位码）。

    #2171：优先 **累计净值** ``acc_nav``，缺失回退 ``unit_nav``——与
    ``fund_metrics.load_nav_points`` / ``fund_performance`` 同源。单位净值在现金分红
    除息日会向下跳空（分红从净值扣除），画出来是「产品暴跌」的假象；买方视角要看
    的是持有期间的真实涨幅，累计净值（分红不再投的近似复权序列）才诚实。此前本模块
    只用 ``unit_nav``，与同页「业绩与风险」卡（acc_nav）口径分裂，属 #2153 一类问题。
    """
    code = symbol[3:] if symbol.startswith('OF.') else symbol
    rows = (
        db.query(DailyWorth.date, DailyWorth.acc_nav, DailyWorth.unit_nav)
        .filter(DailyWorth.fund_code == code, DailyWorth.date >= start)
        .order_by(DailyWorth.date)
        .all()
    )
    series: List[Tuple[dt.date, float]] = []
    for nav_date, acc_nav, unit_nav in rows:
        value = acc_nav if acc_nav is not None else unit_nav
        if value is None:
            continue
        series.append((nav_date, round(float(value), 4)))
    return series


def _fetch_index_series(db: Session, symbol: str, start: dt.date) -> Tuple[List[Tuple[dt.date, float]], str]:
    """指数收盘点位序列（``index_daily``，#2028 拍板「有日线才出曲线」）。

    ``index_daily.index_code`` 存**数据源原生形态**（``000300.SH`` / ``881001.WI``），
    而详情页入口是裸 6 位码——按交易所后缀候选匹配（沪 / 深 / 裸），命中哪个用哪个。
    万得系 ``.WI`` 码（881001 等）无法从裸码推导，不在本路径覆盖范围。

    返回 ``(序列, source码)``；无日线时序列为空，调用方据此返回 ``None`` 诚实降级。
    点位口径含 ``raw`` / ``anchored`` 混合（见 IndexDaily.price_mode），仅作展示曲线，
    脚注按「点位走势，非全收益」表述。
    """
    m = re.search(r'\d{6}', (symbol or '').strip().upper())
    if not m:
        return [], ''
    bare = m.group(0)
    candidates = [f'{bare}.SH', f'{bare}.SZ', bare]
    rows = (
        db.query(IndexDaily.index_code, IndexDaily.trade_date, IndexDaily.close, IndexDaily.source)
        .filter(IndexDaily.index_code.in_(candidates), IndexDaily.trade_date >= start)
        .order_by(IndexDaily.trade_date)
        .all()
    )
    series: List[Tuple[dt.date, float]] = []
    source_code = ''
    for _code, trade_date, close, source in rows:
        if close is None:
            continue
        series.append((trade_date, round(float(close), 4)))
        if source:
            source_code = source
    return series, source_code


def fetch_product_trend(
    market_db: Session,
    symbol: str,
    asset_type: Optional[str] = None,
    range_key: str = DEFAULT_RANGE,
    start_date: Optional[dt.date] = None,
) -> Optional[Dict]:
    """取单产品的历史序列（含日期轴）。

    Args:
        market_db: **market 域**会话（``price_history`` / ``daily_worth`` 都在 market 域）。
        symbol: 产品代码（带市场前缀形态，如 ``SZ000001``；场外为裸 6 位码）。
        asset_type: 后端判定的品类（来自 ``resolve_product_identity``）。为空时按
            ``fund`` 之外都走场内路径——**前端不推断品类**，故该值应由后端 resolver 给。
        range_key: ``1M`` / ``3M`` / ``6M`` / ``1Y``。
        start_date: 显式起始日（#2171「建仓期」：首笔买入日至今）。给定时忽略
            ``range_key`` 档位；晚于今天按今天算（空序列由前端降级）。

    Returns:
        ``{symbol, kind, dates, values, source, basis, ohlc, range, requested_days,
        available_days}``；``source`` 是**站点名**（如「新浪财经」），``basis`` 是口径
        说明——用户看来源，需要时看口径（#1969）。``ohlc`` 为场内**未复权** OHLCV
        （画 K 线 + 成交量），场外为空数组（改画净值线）。
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

    # 窗口起点：默认按档位回看；显式 start_date（建仓期）优先，晚于今天按今天算
    # （首笔买入日就是今天时窗口为 0 天，空序列由前端降级，不报错）。
    today = dt.date.today()
    if start_date is not None:
        start = min(start_date, today)
        days = (today - start).days + 1
    else:
        days = RANGE_DAYS[range_key]
        start = today - dt.timedelta(days=days)

    if normalized_type == 'fund':
        series = _fetch_nav_series(market_db, code, start)
        # #2120 P0-2：冷集长曲线按需取——本地窗口盖不住本次请求区间时，后台单只回补
        # 全历史净值。**本请求不等待**（外部 HTTP 在 async_backfill 的后台线程里），
        # 本次仍按现有 `available_days` 诚实降级；下次进同一页面即有完整曲线。
        # 触发条件用**本次请求的窗口**而非最长档，避免「只看 3M 却为 5Y 回补」。
        maybe_trigger_nav_backfill(code, series, start)
        # 来源与口径分开给：来源是站点名（用户看得懂），口径是「怎么算的」
        kind, basis, source = 'nav', '累计净值（分红不再投近似复权，缺失回退单位净值）', data_source_label(FUND_NAV_SOURCE_LABEL)
        # 场外基金只有单位净值，没有 OHLCV —— 前端据此画净值线而不是 K 线（品类差异化）
        ohlc: List[Dict] = []
    elif normalized_type == 'index':
        # 指数：index_daily 收盘点位（#2028）。无日线 → None 诚实降级，不画假曲线。
        index_series, index_source = _fetch_index_series(market_db, code, start)
        if not index_series:
            return None
        series = index_series
        kind, basis, source = 'close', '指数收盘点位（点位走势，非全收益）', data_source_label(index_source)
        # 指数日线只有收盘点位，无 OHLCV —— 前端画单线而非 K 线
        ohlc = []
    else:
        series = _fetch_close_series(market_db, code, start)
        ohlc = _fetch_ohlc_series(market_db, code, start)
        kind = 'close'
        # 图上是未复权 K 线（与持仓成本可比），而区间涨跌幅仍按前复权算（除权日不跳空）——
        # 两者口径不同，必须在脚注讲清楚，否则用户会拿图上首尾差去核对涨跌幅
        basis = '未复权 K 线；区间涨跌幅按前复权'
        source = data_source_label(_latest_price_source(market_db, code))

    # 实际可用跨度：用于前端「无长历史自动收敛到可用档」（设计 §12 ⑤），数据不足时
    # 由前端提示收敛，而不是画一条只有几天的曲线假装是 3M。
    available_days = (series[-1][0] - series[0][0]).days if len(series) >= 2 else 0

    return {
        'symbol': code,
        'kind': kind,
        'dates': [d.isoformat() for d, _ in series],
        'values': [v for _, v in series],
        # source 是**站点名**（新浪财经 / 天天基金…），不是内部表名或抓取管线码（#1969）
        'source': source,
        'basis': basis,
        # 场内：未复权 OHLCV（画 K 线 + 成交量）；场外：空数组（改画净值线）
        'ohlc': ohlc,
        'range': range_key,
        'requested_days': days,
        'available_days': available_days,
    }
