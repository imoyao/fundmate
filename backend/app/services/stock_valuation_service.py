# -*- coding: utf-8 -*-
"""个股估值分位：用户触达范围 → 万得只读取数（#2944）。

数据准入（``conventions.md`` §16.2）：抓取目标池**必须显式来自用户触达范围**——
这里只取 ``positions``（active 持仓）∪ ``watchlist`` 中 ``asset_type == 'stock'`` 的
代码，或调用方显式传入的 ``codes``；禁止空目标池静默退化成全市场扫描。
本层**不落库、不建表、不新增 job**：上游估值随交易日变动，且尚无页面消费历史序列。

失败语义：数据源不可用 / 上游报错时返回 ``degraded=True`` + ``warning``，
``items`` 为空数组。绝不把「没取到」写成 0 或假装「这批股票没有估值」。
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

from loguru import logger
from sqlalchemy import func

from app.domains.positions.models import Position
from app.domains.watchlist.models import WatchlistItem
from app.services.adapters import wind_stock_valuation as adapter
from app.services.adapters.wind_stock import to_wind_code
from app.services.position_scope import active_holdings
from app.services.watchlist_service import bare_code_of, looks_like_exchange_code

#: 单次请求最多问多少只（显式参数与用户触达集合共用）。防止一次打爆上游问句长度。
MAX_CODES = 50


def _to_wind_code(symbol: Any) -> Optional[str]:
    """仓内 symbol → 万得代码；认不出 / 非 A 股形态返回 ``None``。

    ``bare_code_of`` 会抹掉命名空间，必须与 ``looks_like_exchange_code`` 成对使用
    （#2029：``ZH012926`` 会被压成真实基金代码而错配）。已带 ``.SH`` 后缀的输入
    直接走 ``to_wind_code``，不再过裸码闸门。
    """
    raw = str(symbol or '').strip().upper()
    if not raw:
        return None
    if '.' in raw:
        return to_wind_code(raw)
    if not looks_like_exchange_code(raw):
        return None
    return to_wind_code(bare_code_of(raw))


def resolve_codes(db: Any, family_id: int, codes_param: Optional[str] = None) -> Tuple[List[str], bool]:
    """解析目标池，返回 ``(万得代码列表, 是否因上限截断)``。

    - 传 ``codes``：逗号分隔，逐项归一；全都不是有效 A 股代码 ⇒ ``ValueError``。
    - 不传：当前持仓 ∪ 自选，只取股票、按家庭过滤、去重。
    - 用户触达集合超过 :data:`MAX_CODES` 时截断并置 ``truncated=True``（显式告知，
      不静默少几只）；显式参数超限直接 ``ValueError``（视图转 400）。
    """
    if codes_param is not None and str(codes_param).strip():
        parsed: List[str] = []
        for raw in str(codes_param).split(','):
            wind_code = _to_wind_code(raw)
            if wind_code and wind_code not in parsed:
                parsed.append(wind_code)
        if not parsed:
            raise ValueError('codes 参数里没有可识别的 A 股代码')
        if len(parsed) > MAX_CODES:
            raise ValueError(f'codes 最多 {MAX_CODES} 只，收到 {len(parsed)} 只')
        return parsed, False

    symbols: List[str] = []
    held = (
        active_holdings(db.query(Position.symbol))
        .filter(Position.family_id == family_id, func.lower(Position.asset_type) == 'stock')
        .distinct()
        .all()
    )
    symbols.extend(row[0] for row in held)
    watched = (
        db.query(WatchlistItem.symbol)
        .filter(WatchlistItem.family_id == family_id, func.lower(WatchlistItem.asset_type) == 'stock')
        .all()
    )
    symbols.extend(row[0] for row in watched)

    wind_codes: List[str] = []
    for symbol in symbols:
        wind_code = _to_wind_code(symbol)
        if wind_code and wind_code not in wind_codes:
            wind_codes.append(wind_code)
    wind_codes.sort()
    truncated = len(wind_codes) > MAX_CODES
    return wind_codes[:MAX_CODES], truncated


def get_stock_valuations(db: Any, family_id: int, codes_param: Optional[str] = None) -> Dict[str, Any]:
    """只读端点的数据出口：调 Wind 取 PE/PB 近 5 年分位，不落库。

    ``items`` 每行自带 ``date``（上游交易日）与 ``window='5y'``；不同股票的日期可能
    不同，故**不在顶层造一个统一的 as_of**，避免把「最近一天」伪装成全体口径。
    """
    codes, truncated = resolve_codes(db, family_id, codes_param)
    result: Dict[str, Any] = {
        'items': [],
        'window': adapter.WINDOW,
        'source': adapter.SOURCE,
        'count': 0,
        'requested': len(codes),
        'truncated': truncated,
        'degraded': False,
        'warning': None,
    }
    if not codes:
        return result
    if not adapter.is_available():
        result['degraded'] = True
        result['warning'] = '个股估值数据源未配置'
        return result
    try:
        rows: Sequence[Dict[str, Any]] = adapter.fetch_stock_valuations(codes)
    except Exception as exc:  # noqa: BLE001 - 上游故障必须显式降级，不吞成「没有估值」
        logger.warning(f'[#2944] Wind 个股估值取数失败：{type(exc).__name__}')
        result['degraded'] = True
        result['warning'] = '个股估值数据源暂时不可用'
        return result
    result['items'] = list(rows)
    result['count'] = len(result['items'])
    return result


__all__ = ['MAX_CODES', 'get_stock_valuations', 'resolve_codes']
