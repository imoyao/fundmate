"""统一解析证券交易日价格区间。

供两类场景复用：
1. ``GET /api/securities/<symbol>/price-range/`` 端点（含实时兜底，供前端展示）。
2. 交易创建时的后端区间校验（默认仅本地 PriceHistory，避免写路径引入网络依赖）。

实时兜底链：本地 PriceHistory 缺失时，优先腾讯财经(qt.gtimg.cn) 实时行情（仅当日），
不可达或历史日再退 akshare 新浪日线；任一不可达均降级为 ``None``，不阻塞主流程。

返回结构与前端 ``getSecurityPriceRange`` 保持一致：
``{symbol, date, low, high, close}``；无数据时返回 ``None``。
"""

from __future__ import annotations

import os
import re
import urllib.request
from datetime import date as _date
from datetime import datetime
from typing import Optional

from app.core.database import get_db
from app.core.symbol_utils import get_normalizer
from app.domains.price_history.models import PriceHistory


def _to_date(value) -> Optional[_date]:
    if value is None:
        return None
    if isinstance(value, (_date, datetime)):
        return value.date() if isinstance(value, datetime) else value
    try:
        return _date.fromisoformat(str(value))
    except ValueError:
        return None


def fetch_live_price_range(symbol: str, target: Optional[_date]) -> Optional[dict]:
    """本地 PriceHistory 缺失时，用 akshare 新浪日线兜底取当日高低收。

    任何异常都吞掉并返回 ``None``——兜底失败不应中断主流程。
    """
    if os.environ.get('FUNDMATE_NO_LIVE_PRICE_FALLBACK'):
        return None
    try:
        from app.services.sync.adapters.akshare_adapter import AkshareAdapter

        adapter = AkshareAdapter()
        end = target or _date.today()
        start = end  # 只取目标日
        rows = adapter.fetch_stock_price(symbol, start_date=start, end_date=end)
        if not rows:
            return None
        r = max(rows, key=lambda x: x['trade_date'])
        if r.get('low') is None or r.get('high') is None:
            return None
        return {
            'symbol': symbol,
            'date': r['trade_date'].isoformat(),
            'low': float(r['low']),
            'high': float(r['high']),
            'close': float(r['close']) if r.get('close') is not None else None,
        }
    except Exception as e:  # noqa: BLE001 - 兜底抓取失败属预期内
        from loguru import logger

        logger.warning(f'实时价格区间兜底失败 {symbol}: {e}')
        return None


def fetch_tencent_price_range(symbol: str, target: Optional[_date]) -> Optional[dict]:
    """腾讯财经实时行情兜底（qt.gtimg.cn），仅覆盖当日（target 为 None 或今天）。

    历史交易日无法用实时接口获取，交由 akshare 历史日线兜底。
    返回 ``{symbol, date, low, high, close}`` 或 ``None``；任何异常/解析失败均降级为 ``None``。
    """
    today = _date.today()
    if target is not None and target != today:
        return None  # 实时行情只能给今天，历史日交给 akshare
    if os.environ.get('FUNDMATE_NO_LIVE_PRICE_FALLBACK'):
        return None
    prefix = symbol[:2].lower() + symbol[2:]  # SH600519 -> sh600519
    url = f'https://qt.gtimg.cn/q={prefix}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = resp.read().decode('gbk', errors='ignore')
        m = re.search(r'="([^"]*)"', body)
        if not m:
            return None
        parts = m.group(1).split('~')
        if len(parts) < 35:
            return None
        high = float(parts[33])
        low = float(parts[34])
        close = float(parts[3])
        if low <= 0 or high <= 0 or low > high:
            return None
        return {
            'symbol': symbol,
            'date': today.isoformat(),
            'low': low,
            'high': high,
            'close': close,
        }
    except Exception as e:  # noqa: BLE001 - 兜底抓取失败属预期内
        from loguru import logger

        logger.warning(f'腾讯财经实时行情兜底失败 {symbol}: {e}')
        return None


def resolve_security_price_range(
    symbol: str,
    target_date: Optional[str] = None,
    use_live_fallback: bool = True,
) -> Optional[dict]:
    """返回交易日价格区间 ``{symbol, date, low, high, close}`` 或 ``None``。

    - 优先 ``PriceHistory``（≤``target_date`` 最近一条）。
    - ``target_date`` 缺省时取最近一个有行情的交易日（≤今天）。
    - ``use_live_fallback=False`` 时仅查本地 ``PriceHistory``（写路径校验用，
      避免引入 akshare 网络依赖与沙箱不可达问题）。
    """
    target = _to_date(target_date)
    normalized, _, _ = get_normalizer().normalize(symbol)
    query_symbol = normalized or symbol

    with get_db() as db:
        q = db.query(
            PriceHistory.trade_date,
            PriceHistory.low,
            PriceHistory.high,
            PriceHistory.close,
        ).filter(PriceHistory.symbol == query_symbol)
        if target is not None:
            q = q.filter(PriceHistory.trade_date <= target)
        row = q.order_by(PriceHistory.trade_date.desc()).first()
        if row and row.low is not None and row.high is not None:
            return {
                'symbol': query_symbol,
                'date': row.trade_date.isoformat(),
                'low': float(row.low),
                'high': float(row.high),
                'close': float(row.close) if row.close is not None else None,
            }

    if not use_live_fallback:
        return None
    # 实时兜底链：腾讯财经实时行情优先（仅当日），历史日或腾讯不可达再退 akshare 新浪日线。
    tencent = fetch_tencent_price_range(query_symbol, target)
    if tencent:
        return tencent
    return fetch_live_price_range(query_symbol, target)
