# -*- coding: utf-8 -*-
"""Q3「再平衡客观参考」v2 附加事实取数（D112，源 2026-11-12 owner 裁定）。

v1 只算 ``single_position_weight`` / ``valuation_context``，另两类信号被硬钉为缺口。
v2 把能算的算出来，算不出的仍显式声明 —— 三条口径：

1. **行业集中度**：复用 ``penetration.build_penetration`` 的 **csrc 主口径 + 显式覆盖率**。
   v1 文档所称「本地无持仓→行业映射」已被实测推翻：``security_industry_maps``（直持）
   与 ``fund_industry_allocs``（基金穿透）都已落库。但基金侧没有申万一级，故口径从
   设计 §4「申万一级 + HHI」改为「证监会门类 + 已穿透部分 HHI + 覆盖率披露」，
   **禁止 csrc / sw1 / gics 跨体系相加**（穿透模块硬口径）。
2. **历史占比偏离**：全仓无逐标的权重快照表，按 D62 纪律 **as-of 现算**
   （不回填 ``asset_snapshots``、不新建表）。份额复用 ``pnl_calendar._as_of_shares``
   的「流水 + 快照锚点 + ``positions.quantity`` 终点校准」，价格复用同一模块的
   ``_collect_fund_nav`` / ``_collect_price_history`` / ``_price_series_of`` /
   ``_price_for``（前值回填、停牌锚点、跨市场域取价）。跨模块引用私有函数是刻意的：
   口径只有一份，各写一遍必然漂移（同 ``penetration`` 引用
   ``summary_service._load_user_assets`` 的先例），且本模块不改被体量基线冻结的
   ``pnl_calendar.py``。
3. **个基估值分位**：只读本地 ``market_multi_items(item_type='fund')``。A′ 承诺的
   「个基历史估值分位落库」至今无表 / 无 job / 无写入，故这里**不拿宽基分位替代**，
   无记录即返回 None，由规则层声明缺口；将来 A′ 落库写入同名 item_type 即自动生效。

零外部请求、零新增 MCP、零写库、零模型参与（D19 + L1 数据真实性铁律）。

函数按「取数 / 单日权重 / 采样 / 均值」拆开，是为了守住 services 层软闸门
（``guard_service_size.py``：新增文件最长函数 ≤120 行 / 圈复杂度 ≤20）。
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import desc

from app.core.constants import EXCHANGE_RATES
from app.core.time_utils import now_shanghai
from app.domains.temperature.models import MarketMultiItem
from app.services.penetration import DEFAULT_SCHEME, build_penetration
from app.services.pnl_calendar import (
    _as_of_shares,
    _collect_fund_nav,
    _collect_price_history,
    _price_for,
    _price_series_of,
    _trading_days_between,
)
from app.services.thermometer.wind_valuation import WIND_VALUATION_SOURCE

#: 历史占比窗口与采样间隔。采样按 A 股开盘日每 N 个取一个，避免 90 天 × 全持仓的逐日重放。
HISTORY_WINDOW_DAYS = 90
SAMPLE_EVERY_N_TRADING_DAYS = 5
MIN_SAMPLES = 2


def build_industry_fact(db, family_id: int) -> Optional[Dict[str, Any]]:
    """取本地已落库的行业穿透事实；无可用行业 / 覆盖率为 0 时返回 None。"""
    try:
        report = build_penetration(db, family_id, scheme=DEFAULT_SCHEME)
    except Exception as exc:  # 读侧失败统一按「算不出」降级，不让整个工具报错
        logger.warning('Q3 v2 行业穿透不可用：{}', exc)
        return None
    items = report.get('industries') or []
    coverage = report.get('coverage') or {}
    if not items or float(coverage.get('penetrated_cny') or 0) <= 0:
        return None
    return {
        'scheme': report.get('scheme') or DEFAULT_SCHEME,
        'scheme_label': report.get('scheme_label') or '',
        'penetrated_ratio': float(coverage.get('penetrated_ratio') or 0),
        'industries': [
            {
                'code': i.get('code') or '',
                'name': i.get('name') or '',
                'value_cny': float(i.get('value_cny') or 0),
                'ratio_of_penetrated': float(i.get('ratio_of_penetrated') or 0),
            }
            for i in items
        ],
    }


def _load_history_inputs(db, family_id: int, positions: List[Any], start: dt.date, end: dt.date):
    """一次性取回份额增量、价格序列与汇率，避免日循环里重复查库。"""
    shares, _ = _as_of_shares(db, family_id, end)
    symbols = [p.symbol for p in positions if getattr(p, 'symbol', None)]
    fund_nav = _collect_fund_nav(db, start, end, symbols)
    exchange_prices = _collect_price_history(db, symbols, start, end)
    series = {p.id: _price_series_of(p, fund_nav, exchange_prices) for p in positions}
    rates = {p.id: EXCHANGE_RATES.get(getattr(p, 'currency', None) or 'CNY', 1.0) for p in positions}
    deltas = {p.id: shares.get(p.id, {}) for p in positions}
    return deltas, series, rates


def _weights_on_day(day, positions, deltas, series, rates) -> Dict[str, float]:
    """某采样日的相对市值：as-of 份额 × 「≤ 当日最后已知价」× 汇率。

    只求占比，故不做单位换算（份额与价格同为 0.0001 尺度，比例中约掉），
    避免引入第二套金额口径；无价 / 无份额的标的不进分母，不补 0。
    """
    values: Dict[str, float] = {}
    for p in positions:
        qty = sum(v for d, v in deltas[p.id].items() if d <= day)
        if qty <= 0:
            continue
        price = _price_for(day, series[p.id])
        if price is None or price <= 0:
            continue
        values[p.symbol] = qty * price * rates[p.id]
    return values


def _collect_samples(sample_days, positions, deltas, series, rates):
    """逐采样日累计占比；整日无可用市值则跳过该日，不计入样本数。"""
    accum: Dict[str, List[float]] = {}
    priced_days = 0
    for day in sample_days:
        values = _weights_on_day(day, positions, deltas, series, rates)
        total = sum(values.values())
        if total <= 0:
            continue
        priced_days += 1
        for sym, value in values.items():
            accum.setdefault(sym, []).append(value / total * 100)
    return accum, priced_days


def _mean_weights(accum: Dict[str, List[float]]) -> Dict[str, float]:
    """样本数不足的标的不出均值 —— 一个点不构成「历史均值」。"""
    return {sym: round(sum(v) / len(v), 2) for sym, v in accum.items() if len(v) >= MIN_SAMPLES}


def build_history_fact(db, family_id: int, positions: List[Any]) -> Optional[Dict[str, Any]]:
    """as-of 现算逐标的占比序列均值；样本不足 / 无价格一律返回 None。"""
    if not positions:
        return None
    end = now_shanghai().date()
    start = end - dt.timedelta(days=HISTORY_WINDOW_DAYS)
    sample_days = _trading_days_between(start, end)[::SAMPLE_EVERY_N_TRADING_DAYS]
    if not sample_days:
        return None
    try:
        deltas, series, rates = _load_history_inputs(db, family_id, positions, start, end)
    except Exception as exc:  # 取数失败按「算不出」降级，绝不补 0
        logger.warning('Q3 v2 历史占比取数不可用：{}', exc)
        return None
    accum, priced_days = _collect_samples(sample_days, positions, deltas, series, rates)
    means = _mean_weights(accum)
    if not means or priced_days < MIN_SAMPLES:
        return None
    return {
        'window_days': HISTORY_WINDOW_DAYS,
        'sample_days': priced_days,
        'means': means,
        'as_of': end.isoformat(),
    }


def build_fund_valuation_fact(db, symbols: List[str]) -> Optional[Dict[str, Any]]:
    """个基估值分位接入点：A′ 落库前恒为 None，落库后无需改本函数即自动生效。"""
    codes = sorted({s for s in symbols if s})
    if not codes:
        return None
    rows = (
        db.query(MarketMultiItem)
        .filter(
            MarketMultiItem.source == WIND_VALUATION_SOURCE,
            MarketMultiItem.item_type == 'fund',
            MarketMultiItem.item_code.in_(codes),
            MarketMultiItem.stale.is_not(True),
        )
        .order_by(desc(MarketMultiItem.collected_at))
        .all()
    )
    items: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        if row.item_code in seen:
            continue
        pct = (row.data or {}).get('pe_percentile')
        if isinstance(pct, bool) or not isinstance(pct, (int, float)):
            continue
        seen.add(row.item_code)
        items.append(
            {
                'symbol': row.item_code,
                'pe_percentile': float(pct),
                'valuation_date': (row.data or {}).get('valuation_date'),
            }
        )
    return {'items': items} if items else None


__all__ = [
    'HISTORY_WINDOW_DAYS',
    'build_fund_valuation_fact',
    'build_history_fact',
    'build_industry_fact',
]
