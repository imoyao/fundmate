# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/14
# File : money_fund_income.py
"""
货币基金每日收益计算服务。

打通 `money_fund_daily_worth`（万份收益）→ 每日收益的完整链路：
持有金额（孤儿流水净额 + positions 货基市值，两口径合并）× 万份收益。

持有金额口径（合并）：
- 孤儿流水净额：`asset_type IN ('money_fund', 'reverse_repo')` 且 `position_id IS NULL`，
  buy/deposit 为正、sell/withdraw 为负，按确认日累计；
- positions 货基市值：`asset_type='money_fund'` 的持仓，current_price × quantity
  （走 Money.multiply_price_quantity），作为迁移前兼容的恒定基线。
  迁移完成后仅剩孤儿流水，但本服务兼容迁移前数据。

计算式（全程整数分，禁止裸 float）：
    每日收益（分）= 持有金额（分）× nav_per_10k（元）÷ 10000，round half-up 到分。
    推导：万份收益 w 元 = 每 10000 元当日收益 w 元；持有 H 元 → 收益 = H×w/10000 元。
          分单位代入：H分 = H×100 → 收益分 = H分 × w / 10000。
    示例：H=50000 分（500 元）、w=0.35 元 → 50000×0.35/10000 = 1.75 分 → round 到 2 分。
    为什么 round 到整数分：金额最小单位是分，1.75 分无法在展示层表达；
    逐基金 round half-up 到整数分再求和，符合「金额展示到分」的人类阅读习惯。
    单位说明（2026-08-14 实测修正）：nav_per_10k 存储单位是「元」（万份收益，
    如 000198 余额宝 2026-08-14 为 0.2233 元/万元/日），不是分；早期实现按分
    处理导致真实数据收益恒为 0（0.2233 分 → 量化 0 分），已修正换算因子。
"""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.funds.models import MoneyFundDailyWorth
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.importer.mappings import BusinessType

# 万份收益换算因子：持有金额(分) × 万份收益(元) ÷ 10000 → 当日收益(分)
# （nav_per_10k 存储单位是元，见模块 docstring 单位说明）
_INCOME_DIVISOR = Decimal('10000')

# 孤儿流水方向：buy/deposit 增加持有（正），sell/withdraw 减少持有（负）
_INFLOW_TYPES = {BusinessType.BUY.code, BusinessType.DEPOSIT.code}
_OUTFLOW_TYPES = {BusinessType.SELL.code, BusinessType.WITHDRAW.code}

# 孤儿流水资产类型（货基 + 逆回购，均为现金管理类）
_ORPHAN_ASSET_TYPES = ('money_fund', 'reverse_repo')

# 默认时间窗口：近 30 天（含首尾）
_DEFAULT_WINDOW_DAYS = 30


def _empty_result() -> dict:
    """无数据时的零值结构（不报错）。"""
    return {
        'today_income': 0.0,
        'total_income': 0.0,
        'daily_series': [],
    }


def _collect_orphan_flows(db: Session, family_id: int, ledger_id: Optional[int]) -> Dict[str, Dict[dt.date, int]]:
    """孤儿流水净额：{fund_code: {date: net_cents}}。

    buy/deposit 为正、sell/withdraw 为负；确认日为空时回退到交易日的日期。
    """
    query = db.query(Transaction).filter(
        Transaction.position_id.is_(None),
        Transaction.asset_type.in_(_ORPHAN_ASSET_TYPES),
        Transaction.family_id == family_id,
        # #863 D1：收益行（is_income）不进本金基线，防止收益再产生收益
        or_(Transaction.is_income.is_(None), Transaction.is_income.is_(False)),
    )
    if ledger_id is not None:
        query = query.filter(Transaction.ledger_id == ledger_id)

    flows: Dict[str, Dict[dt.date, int]] = {}
    for txn in query.all():
        fund_code = txn.symbol or ''
        if not fund_code:
            continue
        eff_date = txn.confirm_date or (txn.trade_date.date() if txn.trade_date else None)
        if eff_date is None:
            continue
        if txn.txn_type in _INFLOW_TYPES:
            sign = 1
        elif txn.txn_type in _OUTFLOW_TYPES:
            sign = -1
        else:
            # 分红/扣税等其他类型不参与持有口径
            continue
        day_map = flows.setdefault(fund_code, {})
        day_map[eff_date] = day_map.get(eff_date, 0) + sign * (txn.amount or 0)
    return flows


def _collect_position_market_value(db: Session, family_id: int, ledger_id: Optional[int]) -> Dict[str, int]:
    """positions 中货基市值：{fund_code: cents}（迁移前兼容口径，作为恒定基线）。"""
    query = db.query(Position).filter(
        Position.asset_type == 'money_fund',
        Position.family_id == family_id,
        Position.quantity > 0,
    )
    if ledger_id is not None:
        query = query.filter(Position.ledger_id == ledger_id)

    mv: Dict[str, int] = {}
    for pos in query.all():
        fund_code = pos.symbol or ''
        if not fund_code or not pos.current_price:
            continue
        mv[fund_code] = mv.get(fund_code, 0) + Money.multiply_price_quantity(pos.current_price, pos.quantity)
    return mv


def _collect_nav_map(db: Session, start: dt.date, end: dt.date) -> Dict[str, Dict[dt.date, int]]:
    """万份收益：{fund_code: {date: nav_per_10k(分)}}（范围 [start, end]）。"""
    rows = (
        db.query(MoneyFundDailyWorth).filter(MoneyFundDailyWorth.date >= start, MoneyFundDailyWorth.date <= end).all()
    )
    nav_map: Dict[str, Dict[dt.date, int]] = {}
    for row in rows:
        day_map = nav_map.setdefault(row.fund_code, {})
        day_map[row.date] = row.nav_per_10k or 0
    return nav_map


def _daily_holdings(
    flows: Dict[str, Dict[dt.date, int]],
    position_mv: Dict[str, int],
    start: dt.date,
    end: dt.date,
) -> Dict[dt.date, Dict[str, int]]:
    """逐日各货基持有金额（分）：孤儿流水净额截至当日累计 + positions 货基市值。"""
    fund_codes = sorted(set(flows) | set(position_mv))
    sorted_flows = {f: sorted(flows.get(f, {}).items()) for f in fund_codes}
    idx = {f: 0 for f in fund_codes}
    running = {f: position_mv.get(f, 0) for f in fund_codes}

    result: Dict[dt.date, Dict[str, int]] = {}
    day = start
    while day <= end:
        for f in fund_codes:
            items = sorted_flows.get(f, [])
            while idx[f] < len(items) and items[idx[f]][0] <= day:
                running[f] += items[idx[f]][1]
                idx[f] += 1
        result[day] = dict(running)
        day += dt.timedelta(days=1)
    return result


def _daily_income(day: dt.date, holdings: Dict[str, int], nav_map: Dict[str, Dict[dt.date, int]]) -> int:
    """单日收益（分）：Σ 各货基 持有金额 × 万份收益(元) ÷ 10000，round half-up 到分。

    nav_per_10k 缺失日：当日收益记 0（序列仍含该日）。
    """
    total = 0
    for fund_code, holding in holdings.items():
        if holding <= 0:
            continue
        nav = nav_map.get(fund_code, {}).get(day, 0)
        if nav <= 0:
            # 万份收益缺失（节假日/未同步）：当日收益记 0，序列仍含该日
            continue
        income = (Decimal(holding) * Decimal(nav)) / _INCOME_DIVISOR
        total += int(income.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return total


def calculate_money_fund_income(
    db: Session,
    start_date: Optional[dt.date] = None,
    end_date: Optional[dt.date] = None,
    scope: str = 'family',
    ledger_id: Optional[int] = None,
    family_id: int = 1,
) -> dict:
    """计算货币基金每日收益序列与汇总。

    Args:
        db: 数据库会话
        start_date: 起始日期（含），默认近 30 天
        end_date: 结束日期（含），默认今天
        scope: 'family'（家庭全量）或 'ledger'（指定账户）
        ledger_id: scope='ledger' 时必填
        family_id: 家庭 ID（家庭隔离键）

    Returns:
        {
            'today_income': 序列最后一日收益（元，两位小数）,
            'total_income': 区间累计收益（元，两位小数）,
            'daily_series': [{'date': 'YYYY-MM-DD', 'income': 元}, ...],
        }
    """
    if scope not in ('ledger', 'family'):
        raise ValueError('scope 参数非法，仅支持 ledger / family')
    if scope == 'ledger' and not ledger_id:
        raise ValueError('scope=ledger 时必须提供 ledger_id')

    end = end_date or dt.date.today()
    start = start_date or (end - dt.timedelta(days=_DEFAULT_WINDOW_DAYS - 1))
    if start > end:
        # 防御：范围倒挂时返回空序列，不报错
        return _empty_result()

    flows = _collect_orphan_flows(db, family_id, ledger_id if scope == 'ledger' else None)
    position_mv = _collect_position_market_value(db, family_id, ledger_id if scope == 'ledger' else None)
    nav_map = _collect_nav_map(db, start, end)
    holdings_by_day = _daily_holdings(flows, position_mv, start, end)

    daily_series: List[dict] = []
    total_income_cents = 0
    day = start
    while day <= end:
        income_cents = _daily_income(day, holdings_by_day[day], nav_map)
        daily_series.append({'date': day.isoformat(), 'income': Money.cents_to_yuan(income_cents)})
        total_income_cents += income_cents
        day += dt.timedelta(days=1)

    return {
        'today_income': daily_series[-1]['income'] if daily_series else 0.0,
        'total_income': Money.cents_to_yuan(total_income_cents),
        'daily_series': daily_series,
    }
