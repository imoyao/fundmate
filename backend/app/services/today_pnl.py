# -*- coding: utf-8 -*-
"""首页「最新收益」卡：当日盈亏 + 按大类拆分 + 估/确认状态。

## 为什么单起一个出口，而不是前端拿持仓自己算

回答的是**同一个问题**：「今天赚了多少」，而盈亏口径全站只有一条
（`pnl_calendar._compute_days` 的 `total_pnl` 日差分，见 `pnl_calendar` 模块头）。
前端另算一套必然分叉，第一个坏结果是「首页卡 +1,227.88，收益日历当日格 +1,198.20」，
用户不会相信任何一侧。故本模块**复用同一次遍历**：只给 `_compute_days` 追加一个
`class_breakdown` 收集器，按 `asset_class` 把同一条水平值链聚到 3 个桶里。
构造上 `Σ 分项 ≡ 当日合计`，不是对账对出来的。

## 三个数字的先后关系（卡内自洽）

    Σ 大类当日盈亏 = 最新收益（本卡 hero）
    Σ 大类市值     = 投资类资产（本卡次级，= 股票 + 基金）
    家庭净资产 / 总负债 = 另一层刻度（含房产、现金、负债），由调用方从 /summary/ 取

覆盖范围（`CARD_CLASSES`）：**场内权益 + 场外基金**——前者含股票 / ETF / 可转债
（`position_price_job` 同一集合，都有交易所报价、盘中可取实时价），后者只有每日
净值 / 收盘估值。房产、银行理财、实物、货基没有统一的当日估值口径，硬塞进分项
只能填 0——那会把「不知道」画成「没赚没亏」。
（2026-11-04 起 `asset_class` 把 etf / bond 归权益侧，此前二者分别落在「基金」
与「其他」，可转债因此完全不进卡面。）

## 估 / 确认（用户 2026-11-03 拍板）

    estimated  当日价里有基金来自收盘估值定格（`fund_valuation_daily`，#2141）
               ⇒ 徽标「估」，官方净值公布后自动翻转
    confirmed  该大类当日全部持仓都有官方当日价（场内收盘价 / 场外确认净值）
    partial    部分标的本日还没出价（盘中、或同步没跑）：金额只算了已出价的
    empty      该大类当日没有持仓

`estimated` **不按日期推断**，只看引擎真的用了估值行——语义与收益日历当日格的
`estimated` 同源（同一份 `_merge_today_estimates`）。

## 日期选择（为什么可能不是今天）

盘中（15:00 前）今日收盘价 / 当日净值都不存在，硬算出来是「0.00」——
那是把「还没有数据」说成「今天没赚没亏」（#1942 起全站禁止的形态）。
故取「**最近一个真有当日报价的日子**」；盘中自然落到上一交易日，前端再用实时
行情做价格替换（只替换价，不重算盈亏），收盘后估值定格一落地就自动切回今天。
"""

from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.money import Money
from app.core.time_utils import now_shanghai
from app.services.asset_class import (
    CLASS_FUND,
    CLASS_LABELS,
    CLASS_ORDER,
    CLASS_OTHER,
    CLASS_STOCK,
)
from app.services.pnl_calendar import (
    STATE_NO_POSITION,
    STATE_NO_PRICE,
    _as_of_shares,
    _compute_days,
    _positions,
    _price_presence,
)

# 回看窗口：覆盖国庆 / 春节（最长 8 天假）+ 一个交易日，足以找到「最近有价的一天」
LOOKBACK_DAYS = 10

# 卡面只出这两类（有当日估值口径）
CARD_CLASSES = (CLASS_STOCK, CLASS_FUND)

STATUS_ESTIMATED = 'estimated'
STATUS_CONFIRMED = 'confirmed'
STATUS_PARTIAL = 'partial'
STATUS_EMPTY = 'empty'


def _yuan(cents: Optional[int]) -> Optional[float]:
    return None if cents is None else round(Money.cents_to_yuan(cents), 2)


def _rate(pnl_cents: Optional[int], prev_mv_cents: Optional[int]) -> Optional[float]:
    """收益率（%）= 当日盈亏 / 前一基准日市值。分母缺失 ⇒ None，不造 0。"""
    if pnl_cents is None or not prev_mv_cents:
        return None
    return round(pnl_cents / abs(prev_mv_cents) * 100, 2)


def _class_status(key: str, rec: dict) -> str:
    held = rec['held'].get(key, 0)
    present = rec['present'].get(key, 0)
    if held <= 0:
        return STATUS_EMPTY
    if key in rec['estimated']:
        return STATUS_ESTIMATED
    if present >= held:
        return STATUS_CONFIRMED
    return STATUS_PARTIAL


def _pick_target(breakdown: Dict[str, dict], today: dt.date) -> str:
    """最近一个「真有当日报价」的日子；盘中 / 净值未出时回退到上一交易日。

    `_compute_days` 只记录 `daily_pnl is not None` 的日子，故 `breakdown` 的键
    天然都是「算得出数」的日期（休市 / 无价 / 无持仓的日子不在其中）。
    """
    dates = sorted(breakdown)
    latest = dates[-1]
    rec = breakdown.get(today.isoformat())
    if rec is None:
        return latest
    # 今天有任一标的拿到**当天**报价（含估值定格）才认今天；否则今天的
    # 「0.00」只是前值回填的产物，不能当成当日收益。
    has_fresh = any(rec['present'].get(k, 0) > 0 for k in CLASS_ORDER)
    if has_fresh:
        return today.isoformat()
    earlier = [d for d in dates if d < today.isoformat()]
    return earlier[-1] if earlier else latest


def _merge_holdings(rows: List[dict]) -> List[dict]:
    """逐持仓 → 按 (大类, 代码) 合并，供前端做**价格替换**。

    单位统一到「元 / 份」：引擎内部价是 0.0001 元、份额是 0.0001 份，出口一次折完，
    前端只做 `(实时价 − 当日价) × 份额`（不做盈亏计算，也不碰成本）。
    外币按引擎同一条 `EXCHANGE_RATES` 折进价格，`quantity` 保持份额原值。
    """
    merged: Dict[str, dict] = {}
    for row in rows:
        cls = row['class']
        if cls not in CARD_CLASSES or not row['symbol'] or row['quantity'] <= 0:
            continue
        key = f'{cls}:{row["symbol"]}:{row["fx"]}'
        item = merged.setdefault(
            key,
            {
                'symbol': row['symbol'],
                'class': cls,
                'quantity': 0.0,
                'price': 0.0,
            },
        )
        item['quantity'] += row['quantity'] / 10000
        item['price'] = round(row['price'] / 10000 * row['fx'], 6)
    for item in merged.values():
        item['quantity'] = round(item['quantity'], 4)
    return sorted(merged.values(), key=lambda x: (x['class'], x['symbol']))


def _empty_payload(today: dt.date, reason: str) -> dict:
    return {
        'date': today.isoformat(),
        'is_today': True,
        'state': reason,
        'status': 'no_data',
        'total_pnl': None,
        'total_rate': None,
        'invested_value': None,
        'other_value': None,
        'classes': [],
        'holdings': [],
    }


def build_today_pnl(db: Session, family_id: int = 1) -> dict:
    """首页「最新收益」卡的数据出口（家庭级）。

    Returns:
        `date` / `is_today` / `state` / `status` / `total_pnl` / `total_rate` /
        `invested_value`（股票+基金市值）/ `other_value`（其他类市值，卡面不出）/
        `classes[]`（key, label, pnl, rate, market_value, status）/
        `holdings[]`（symbol, class, quantity, price——盘中价格替换用）。
    """
    today = now_shanghai().date()
    positions = _positions(db, family_id, None)
    if not positions:
        return _empty_payload(today, STATE_NO_POSITION)

    window_start = today - dt.timedelta(days=LOOKBACK_DAYS)
    shares, txns = _as_of_shares(db, family_id, today)
    no_price_ids, _latest = _price_presence(db, positions, window_start, today)
    if len(no_price_ids) >= len({p.id for p in positions}):
        # 全部持仓都没有价格序列（纯 balance 模式账户）：不存在「当日收益」这回事
        return _empty_payload(today, STATE_NO_PRICE)

    breakdown: Dict[str, dict] = {}
    _compute_days(
        db,
        family_id,
        positions,
        positions,
        window_start,
        today,
        None,
        window_start,
        no_price_ids,
        shares,
        txns,
        class_breakdown=breakdown,
    )
    if not breakdown:
        return _empty_payload(today, STATE_NO_PRICE)

    target = _pick_target(breakdown, today)
    rec = breakdown[target]

    classes: List[dict] = []
    invested_cents = 0
    covered_pnl_cents = 0
    covered_prev_cents = 0
    for key in CARD_CLASSES:
        held = rec['held'].get(key, 0)
        if held <= 0:
            continue
        status = _class_status(key, rec)
        pnl_cents = rec['pnl'].get(key, 0)
        mv_cents = rec['mv'].get(key, 0)
        prev_cents = rec['prev_mv'].get(key, 0)
        invested_cents += mv_cents
        covered_prev_cents += prev_cents
        # 该大类今天一个真报价都没有 ⇒ 金额是前值回填出来的 0，不是「没涨没跌」
        pnl_value = None if rec['present'].get(key, 0) == 0 else _yuan(pnl_cents)
        if pnl_value is not None:
            covered_pnl_cents += pnl_cents
        classes.append(
            {
                'key': key,
                'label': CLASS_LABELS[key],
                'pnl': pnl_value,
                'rate': _rate(pnl_cents, prev_cents) if pnl_value is not None else None,
                'market_value': _yuan(mv_cents),
                'status': status,
            }
        )

    estimated = sorted(rec['estimated'])
    if estimated:
        status = STATUS_ESTIMATED
    elif any(c['status'] == STATUS_PARTIAL for c in classes):
        status = STATUS_PARTIAL
    elif classes:
        status = STATUS_CONFIRMED
    else:
        status = STATUS_EMPTY

    payload = {
        'date': target,
        'is_today': target == today.isoformat(),
        'state': rec['state'],
        'status': status,
        'total_pnl': _yuan(covered_pnl_cents),
        'total_rate': _rate(covered_pnl_cents, covered_prev_cents),
        'invested_value': _yuan(invested_cents),
        'other_value': _yuan(rec['mv'].get(CLASS_OTHER, 0)),
        'classes': classes,
        'holdings': _merge_holdings(rec['holdings']),
    }
    logger.debug(
        '首页当日收益派生完成 日期={} 状态={} 合计={} 覆盖市值={}',
        payload['date'],
        status,
        payload['total_pnl'],
        payload['invested_value'],
    )
    return payload


__all__ = ['build_today_pnl', 'LOOKBACK_DAYS']
