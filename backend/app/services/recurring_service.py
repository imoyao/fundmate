# -*- coding: utf-8 -*-
"""定投计划口径（#2138）。

**计划表只存意图，执行事实全在流水**：

- 「下次扣款日 / 最近应扣款日」按 ``frequency`` + ``day_of_period`` + ``start_date`` 推算；
- 「累计投入 / 已执行期数 / 最近一次执行」按 ``transactions.plan_id`` 聚合；
- 「是否断投」= 最近一期应扣款日已过 ``OVERDUE_GRACE_DAYS`` 天，且该期之后没有计划流水。

为什么不把 ``next_due_date`` 落库：它是纯派生值，落库就要有写入方负责推进
（本仓当下没有任何调度会推进它），而且一旦与流水不同步就是第二份事实源，
排查时无法判断哪份对——#2343 的「清仓列」已在同类问题上付过学费。

日期推算的边界（**都是刻意选择，不是遗漏**）：

- 月末对齐：``day_of_period=31`` 遇 2 月落到 28/29 日（不会跳月）；
- ``weekly`` 给了 ``day_of_period``（1=周一）时，把首期对齐到 ``start_date`` 之后最近的该星期几；
- ``biweekly`` **不**做星期对齐：14 天相位的锚点是 ``start_date``，再对齐会破坏相位；
- ``paused`` / ``ended`` 不推进下次扣款日（返回 ``None``）。
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.recurring.models import RecurringPlan
from app.domains.transactions.models import Transaction

#: 断投宽限天数。为什么不是 0：定投当日买入要隔一两个交易日才确认，用户也可能次日补录，
#: 卡在当天会天天误报。7 天覆盖一个完整交易周。
OVERDUE_GRACE_DAYS = 7

#: 日期推进的硬上限（防脏数据导致死循环）：3000 步 ≈ 57 年周投 / 250 年月投。
MAX_STEPS = 3000

#: PATCH 允许改的字段。``status`` 走独立的 pause/resume/end 端点，不在此列。
EDITABLE_FIELDS = (
    'ledger_id',
    'account_name',
    'symbol',
    'position_name',
    'asset_type',
    'amount',
    'frequency',
    'day_of_period',
    'start_date',
    'end_date',
    'note',
)


def _clamp_day(year: int, month: int, day: int) -> int:
    """把「每月第几日」夹到当月天数内（2 月 31 日 → 28/29 日）。"""
    return min(day, calendar.monthrange(year, month)[1])


def _add_month(cur: date, day: int) -> date:
    year, month = (cur.year + 1, 1) if cur.month == 12 else (cur.year, cur.month + 1)
    return date(year, month, _clamp_day(year, month, day))


def first_due_date(plan: RecurringPlan) -> date:
    """计划的首期应扣款日（可能早于今天）。"""
    start = plan.start_date
    if plan.frequency == 'monthly':
        day = plan.day_of_period or start.day
        candidate = date(start.year, start.month, _clamp_day(start.year, start.month, day))
        return candidate if candidate >= start else _add_month(candidate, day)
    if plan.frequency == 'weekly' and plan.day_of_period:
        # 1=周一。start 当天或之后的第一个该星期几。
        return start + timedelta(days=(plan.day_of_period - 1 - start.weekday()) % 7)
    return start


def _step(plan: RecurringPlan, cur: date) -> date:
    if plan.frequency == 'monthly':
        return _add_month(cur, plan.day_of_period or plan.start_date.day)
    return cur + timedelta(days=7 if plan.frequency == 'weekly' else 14)


def next_due_date(plan: RecurringPlan, today: Optional[date] = None) -> Optional[date]:
    """下一次应扣款日；非 active / 已过 end_date / 推进超限时返回 None。"""
    if plan.status != 'active':
        return None
    today = today or date.today()
    cur = first_due_date(plan)
    steps = 0
    while cur < today:
        cur = _step(plan, cur)
        steps += 1
        if steps > MAX_STEPS:
            return None
    if plan.end_date and cur > plan.end_date:
        return None
    return cur


def last_due_date(plan: RecurringPlan, today: Optional[date] = None) -> Optional[date]:
    """最近一期「已经到期」的应扣款日（<= today）；尚未到首期时返回 None。"""
    today = today or date.today()
    cur = first_due_date(plan)
    if cur > today:
        return None
    steps = 0
    while True:
        nxt = _step(plan, cur)
        if nxt > today:
            break
        cur = nxt
        steps += 1
        if steps > MAX_STEPS:
            break
    if plan.end_date and cur > plan.end_date:
        return None
    return cur


def _to_date(value) -> Optional[date]:
    """把 ``MAX(trade_date)`` 的返回值归一成 date（SQLite/PG/字符串三种形态都见过）。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).date()
    except ValueError:
        return None


def _execution_rows(db: Session, family_id: int, plan_ids: Iterable[int]) -> dict:
    """一次聚合多张计划的执行事实：``{plan_id: (累计投入分, 笔数, 最近执行日)}``。

    只统计 ``buy``：定投执行落库就是买入；分红/卖出即使挂了 plan_id 也不算这一期的执行。
    """
    ids = list(plan_ids)
    if not ids:
        return {}
    rows = (
        db.query(
            Transaction.plan_id,
            func.coalesce(func.sum(Transaction.amount), 0),
            func.count(Transaction.id),
            func.max(Transaction.trade_date),
        )
        .filter(
            Transaction.family_id == family_id,
            Transaction.plan_id.in_(ids),
            Transaction.txn_type == 'buy',
        )
        .group_by(Transaction.plan_id)
        .all()
    )
    return {plan_id: (int(total or 0), int(count or 0), last) for plan_id, total, count, last in rows}


def to_dict(plan: RecurringPlan) -> dict:
    """计划本体的基础字段（不含派生状态）。"""
    return {
        'id': plan.id,
        'ledger_id': plan.ledger_id,
        'account_name': plan.account_name,
        'symbol': plan.symbol,
        'position_name': plan.position_name,
        'asset_type': plan.asset_type,
        'amount': plan.amount,
        'frequency': plan.frequency,
        'day_of_period': plan.day_of_period,
        'start_date': plan.start_date.isoformat() if plan.start_date else None,
        'end_date': plan.end_date.isoformat() if plan.end_date else None,
        'status': plan.status,
        'note': plan.note,
        'created_at': plan.created_at.isoformat() if plan.created_at else None,
        'updated_at': plan.updated_at.isoformat() if plan.updated_at else None,
    }


def summarize(plan: RecurringPlan, stats=None, today: Optional[date] = None) -> dict:
    """计划 + 派生状态。``stats`` 来自 :func:`_execution_rows` 的单条元组。"""
    today = today or date.today()
    invested, count, last_trade = stats or (0, 0, None)
    last_executed = _to_date(last_trade)
    next_due = next_due_date(plan, today)
    last_due = last_due_date(plan, today)

    overdue_days = 0
    # 「一期都没执行过」不算断投，按「尚未开始」处理：
    # 写入路径（记账时选计划）可能还没接线，此时每张计划都会命中「最近一期未执行」，
    # 整页飘红等于把提醒做成噪音。断投只对**已经开始执行**的计划有意义。
    if plan.status == 'active' and last_due is not None and count > 0:
        # 最近一期之后有买入 = 该期已执行（哪怕晚于约定日）；否则看是否超过宽限期。
        covered = last_executed is not None and last_executed >= last_due
        if not covered:
            raw_days = (today - last_due).days
            if raw_days > OVERDUE_GRACE_DAYS:
                overdue_days = raw_days

    data = to_dict(plan)
    data.update(
        {
            'next_due_date': next_due.isoformat() if next_due else None,
            'last_due_date': last_due.isoformat() if last_due else None,
            'invested_amount': invested,
            'executed_count': count,
            'last_executed_on': last_executed.isoformat() if last_executed else None,
            'overdue_days': overdue_days,
            'is_overdue': overdue_days > 0,
        }
    )
    return data


def summarize_one(db: Session, family_id: int, plan: RecurringPlan, today: Optional[date] = None) -> dict:
    """单条计划的派生状态（列表外的详情/写后回显共用，避免视图碰内部聚合函数）。"""
    stats = _execution_rows(db, family_id, [plan.id]).get(plan.id)
    return summarize(plan, stats, today)


def list_plans(db: Session, family_id: int, status: Optional[str] = None, today: Optional[date] = None) -> list:
    """家庭全部计划（可按状态过滤），一次聚合流水后逐条派生状态。"""
    query = db.query(RecurringPlan).filter(RecurringPlan.family_id == family_id)
    if status:
        query = query.filter(RecurringPlan.status == status)
    plans = query.order_by(RecurringPlan.id.desc()).all()
    stats = _execution_rows(db, family_id, [p.id for p in plans])
    return [summarize(p, stats.get(p.id), today) for p in plans]


def get_plan(db: Session, family_id: int, plan_id: int) -> Optional[RecurringPlan]:
    """按家庭 + id 取计划（越权/不存在都返回 None，由视图统一 404）。"""
    return db.query(RecurringPlan).filter(RecurringPlan.family_id == family_id, RecurringPlan.id == plan_id).first()


def _resolve_account_name(db: Session, family_id: int, ledger_id, fallback=None):
    """账户名快照：给了 ledger_id 就按当前账户名刷新，查不到沿用 fallback。"""
    if ledger_id is None:
        return fallback
    from app.domains.ledgers.models import Ledger

    ledger = db.query(Ledger).filter(Ledger.family_id == family_id, Ledger.id == ledger_id).first()
    if ledger is None:
        return fallback
    return ledger.name


def create_plan(db: Session, family_id: int, payload: dict) -> RecurringPlan:
    data = {k: v for k, v in payload.items() if k in EDITABLE_FIELDS}
    data['account_name'] = _resolve_account_name(db, family_id, data.get('ledger_id'), data.get('account_name'))
    plan = RecurringPlan(family_id=family_id, **data)
    db.add(plan)
    # 读-写同事务：SessionLocal 是 autoflush=False，不显式 flush 的话紧接着的
    # query 看不到这一行（#51912643 的教训）。
    db.flush()
    return plan


def update_plan(db: Session, plan: RecurringPlan, payload: dict) -> RecurringPlan:
    data = {k: v for k, v in payload.items() if k in EDITABLE_FIELDS}
    if 'ledger_id' in data:
        data['account_name'] = _resolve_account_name(
            db, plan.family_id, data['ledger_id'], data.get('account_name', plan.account_name)
        )
    # 切到 biweekly 时清掉 day_of_period：该频率不接受星期对齐（见 schemas 的说明），
    # 留着会让「上次 monthly 的第 15 号」继续影响展示，属于看不见的脏数据。
    if data.get('frequency') == 'biweekly':
        data['day_of_period'] = None
    # 校验必须在 setattr 之前：abort 抛异常后事务边界在 teardown，已经改到一半的
    # 对象属性不保证被回滚（且 update 端点复用请求级 Session）。
    next_start = data.get('start_date', plan.start_date)
    next_end = data.get('end_date', plan.end_date)
    if next_end and next_start and next_end < next_start:
        raise ValueError('end_date 不能早于 start_date')
    for key, value in data.items():
        setattr(plan, key, value)
    db.flush()
    return plan


def set_status(db: Session, plan: RecurringPlan, status: str) -> RecurringPlan:
    """暂停 / 恢复 / 结束。状态机刻意宽松：任意状态可切任意状态（用户改主意不该被拦）。"""
    plan.status = status
    db.flush()
    return plan
