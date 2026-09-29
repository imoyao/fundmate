# -*- coding: utf-8 -*-
"""分红与股息统计（#872）——「分红收益」这一知识的**唯一归口**。

## 为什么不再建「分红事件表」

分红事件的事实来源已经是 `transactions`：现金分红 / 红利再投 / 送股 / 红利税
全部由导入链路与手动记账写在该表上（列名 `type`，属性名 `txn_type`），
口径见 `docs/spec/importer-architecture.md` 与 `services/position_service.py`。
再建一张 `dividend_events` 表等于把同一事实存两遍，迟早出现「流水有、事件表没有」
或金额不一致，故本域只补一份**用户私有配置**（`dividend_targets`，见 `domains/dividends/models.py`）：
逐持仓的**实际**股息率一律实时从流水算，不落库。

## 流水层的事实（判据依据）

- 现金分红：`txn_type='dividend'`，无配对流水；`amount` = 分红金额（分，正）。
- 红利再投：`txn_type='dividend'` **且** 与同 `link_group_id` 的 `txn_type='buy'`
  成对（`_create_dividend_cash_txn` + `_build_reinvest_buy_data` 双流水）。
  判据取「同组存在 buy 流水」而非「link_group_id 非空」——后者是通用配对列，
  单看非空会把未来的其它配对场景误判成再投。`txn_type='dividend_reinvest'`
  **从不落库**（它只是入参 op_type，落库时被拆成上面两笔）。
- 红利税：`txn_type='dividend_tax'`，`amount` 为**负值**（orchestrator_commit）。
- 送股/拆分：`txn_type='split'`，`amount=0`，只增份额不改成本。
- 债券兑付（`bond_redeem`）**不计入**：它是还本付息，不是持有期分红，
  计入会把本金回收算成股息收入。

## 两个口径（不要混用）

- `totals` / `by_year`：**全量流水口径**——含已清仓持仓与孤儿（`position_id IS NULL`）
  的分红，回答「历史上一共分了多少」。
- `portfolio` / `holdings`：**在管持仓口径**——分母是当前成本 / 市值，
  回答「现在的组合股息率是多少」。分子只取在管持仓的分红，否则分母已清仓、
  分子还在，比率会虚高。

## 已知边界

- **不分折汇率**：股息率是同币种内的比率（分子分红与分母成本取自同一持仓、同一币种），
  逐持仓口径严格自洽；组合口径是各持仓本币值的直接相加，与
  `position_aggregation.py` 的明细口径一致，**假设组合以单一本币为主**——
  跨币种混合组合请以逐持仓股息率为准。
- **送股不产生金额**：`split` 只计入事件数，不进股息率分子。
- 通过 `market_value_override` 人工录市值的持仓，无法反推「再投入收益」
  （没有可信的当前价），该字段返回 `None`（前端显示 `--`）。
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.dividends.models import DividendTarget
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.nav_service import NavService
from app.services.pnl_service import cost_basis_cents, net_invested_by_position
from app.services.position_valuation import market_value_cents

# 进入分红统计的流水类型（bond_redeem 有意排除，见模块 docstring）
DIVIDEND_TXN_TYPES = ('dividend', 'dividend_tax', 'split')
# 基金/货基取最新净值的资产类型（与 position_aggregation 一致）
_NAV_ASSET_TYPES = ('fund', 'money_fund')

# 事件种类（响应体里的 kind，也是 totals/by_year 的分列依据）
KIND_CASH = 'cash'
KIND_REINVEST = 'reinvest'
KIND_TAX = 'tax'
KIND_SPLIT = 'split'

# 查询参数边界（views 与前端共用同一份约束）
MONTHS_MIN, MONTHS_MAX = 1, 60
YEARS_MIN, YEARS_MAX = 1, 20


@dataclass(frozen=True)
class DividendEvent:
    """一笔标准化的分红事件（现金分红 / 红利再投 / 红利税 / 送股）。"""

    txn_id: int
    kind: str
    position_id: Optional[int]
    symbol: Optional[str]
    name: Optional[str]
    asset_type: Optional[str]
    occurred_on: Optional[date]
    amount_cents: int  # 现金/再投为正，红利税为负（与流水一致）
    quantity: int = 0
    price: int = 0
    link_group_id: Optional[str] = None


def _event_date(txn: Transaction) -> Optional[date]:
    """流水发生日：确认日优先，未确认退回交易日（与 position_valuation 同口径）。"""
    if txn.confirm_date is not None:
        return txn.confirm_date if isinstance(txn.confirm_date, date) else None
    if txn.trade_date is None:
        return None
    return txn.trade_date.date() if isinstance(txn.trade_date, datetime) else txn.trade_date


def _reinvest_group_ids(db: Session, family_id: int) -> set[str]:
    """红利再投的配对组 ID = 存在同组 buy 流水的 link_group_id（见模块 docstring）。"""
    rows = (
        db.query(Transaction.link_group_id)
        .filter(
            Transaction.family_id == family_id,
            Transaction.txn_type == 'buy',
            Transaction.link_group_id.isnot(None),
        )
        .distinct()
        .all()
    )
    return {gid for (gid,) in rows if gid}


def load_dividend_events(db: Session, family_id: int) -> list[DividendEvent]:
    """把分红族流水标准化成事件列表（本模块是全系统唯一入口）。

    一次查询 + 一次配对组查询，无 N+1；按发生日升序，便于按年/窗口切片。
    """
    rows = (
        db.query(Transaction)
        .filter(
            Transaction.family_id == family_id,
            Transaction.txn_type.in_(DIVIDEND_TXN_TYPES),
        )
        .all()
    )
    if not rows:
        return []

    reinvest_groups = _reinvest_group_ids(db, family_id)
    events: list[DividendEvent] = []
    for txn in rows:
        if txn.txn_type == 'dividend':
            kind = KIND_REINVEST if txn.link_group_id in reinvest_groups else KIND_CASH
        elif txn.txn_type == 'dividend_tax':
            kind = KIND_TAX
        else:
            kind = KIND_SPLIT
        events.append(
            DividendEvent(
                txn_id=txn.id,
                kind=kind,
                position_id=txn.position_id,
                symbol=txn.symbol or None,
                name=txn.position_name or None,
                asset_type=txn.asset_type or None,
                occurred_on=_event_date(txn),
                amount_cents=int(txn.amount or 0),
                quantity=int(txn.quantity or 0),
                price=int(txn.price or 0),
                link_group_id=txn.link_group_id,
            )
        )
    events.sort(key=lambda e: (e.occurred_on or date.min, e.txn_id))
    return events


def _months_ago(anchor: date, months: int) -> date:
    """anchor 往前推 N 个自然月（月末安全：1/31 往前一月落到 2/28 或 2/29）。"""
    month_index = anchor.month - 1 - months
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _pct(numerator_cents: int, denominator_cents: int) -> Optional[float]:
    """比率（%），分母非正时返回 None（前端显示 `--`，不显示误导性的 0）。"""
    if denominator_cents <= 0:
        return None
    return round(numerator_cents / denominator_cents * 100, 2)


def _sum_cents(events: Iterable[DividendEvent], kind: str) -> int:
    """按种类求金额（分）。红利税在流水里是负数，此处**返回正数**供展示。"""
    total = sum(e.amount_cents for e in events if e.kind == kind)
    return abs(total) if kind == KIND_TAX else total


def _count_kind(events: Iterable[DividendEvent], kind: str) -> int:
    return sum(1 for e in events if e.kind == kind)


def _bucket(events: Iterable[DividendEvent]) -> dict[str, int]:
    """一组事件的分列汇总（分）：cash / reinvest / tax / net / event_count / split_count。

    net（净分红）= 现金 + 再投 − 红利税：这是「分红权益」的完整口径，
    红利再投虽未落袋为现金，但份额已经增加，与现金分红同属分红回报。
    """
    events = list(events)
    cash = _sum_cents(events, KIND_CASH)
    reinvest = _sum_cents(events, KIND_REINVEST)
    tax = _sum_cents(events, KIND_TAX)
    return {
        'cash_cents': cash,
        'reinvest_cents': reinvest,
        'tax_cents': tax,
        'net_cents': cash + reinvest - tax,
        'event_count': len(events),
        'split_count': _count_kind(events, KIND_SPLIT),
    }


def _reinvest_gain_cents(buys: list[Transaction], price_yuan: Optional[float]) -> Optional[int]:
    """红利再投至今的浮盈（分）= Σ[ 再投份额 × 当前价 − 再投成本 ]。

    成本取该申购流水的 `amount`（导入/记账时已按净值算出），缺失时用
    `price × quantity` 兜底。`price_yuan` 为 None（人工录市值的持仓）时返回 None。
    """
    if price_yuan is None or price_yuan <= 0:
        return None
    gain = 0
    for row in buys:
        shares = Money.min_unit_to_shares(row.quantity or 0)
        if shares <= 0:
            continue
        value_cents = int((Decimal(str(shares * price_yuan)) * 100).to_integral_value(rounding=ROUND_HALF_UP))
        cost_cents = int(row.amount or 0) or Money.multiply_price_quantity(row.price or 0, row.quantity or 0)
        gain += value_cents - cost_cents
    return gain


def _effective_price_yuan(position: Position, latest_nav_yuan: Optional[float]) -> Optional[float]:
    """当前有效价（元）：基金/货基用最新净值，其余用快照价；人工录市值时为 None。"""
    if getattr(position, 'market_value_override', None) is not None:
        return None  # 市值被人工覆写，快照价不再可信 → 不反推再投收益
    if latest_nav_yuan is not None and latest_nav_yuan > 0:
        return latest_nav_yuan
    price = Money.price_units_to_yuan(position.current_price or 0)
    return price if price > 0 else None


def _reinvest_buys_by_position(db: Session, family_id: int, group_ids: set[str]) -> dict[int, list[Transaction]]:
    """按持仓归集红利再投的申购流水（用于算再投浮盈）。"""
    if not group_ids:
        return {}
    rows = (
        db.query(Transaction)
        .filter(
            Transaction.family_id == family_id,
            Transaction.txn_type == 'buy',
            Transaction.link_group_id.in_(group_ids),
        )
        .all()
    )
    grouped: dict[int, list[Transaction]] = {}
    for row in rows:
        if row.position_id is not None:
            grouped.setdefault(row.position_id, []).append(row)
    return grouped


def _load_holdings(db: Session, family_id: int) -> list[Position]:
    return db.query(Position).filter(Position.family_id == family_id, Position.ownership_status == 'active').all()


def _latest_navs(db: Session, positions: list[Position]) -> dict[str, float]:
    """在管基金/货基的最新净值（用户触发的同步请求，禁止远程拉取）。"""
    symbols = [p.symbol for p in positions if p.symbol and p.asset_type in _NAV_ASSET_TYPES]
    if not symbols:
        return {}
    return NavService.get_latest_navs(db, symbols, allow_remote=False)


def build_dividend_summary(
    db: Session,
    family_id: int,
    *,
    months: int = 12,
    years: int = 5,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """分红与股息总览（#872）。

    Args:
        db: 会话。
        family_id: 家庭 ID。
        months: 股息率 / 近期分红的统计窗口（自然月），默认 12 即 TTM 口径。
        years: `by_year` 回溯的年数（含当年）。
        today: 统计基准日，默认今天；注入以便测试与历史复盘。

    Returns:
        dict：`as_of` / `period` / `totals` / `by_year` / `portfolio` / `holdings` / `target`。
        金额一律**整数分**（与全仓 `*_cents` 约定一致，前端除以 100）；比率为百分比 float，
        分母非正时为 None。
    """
    anchor = today or date.today()
    start = _months_ago(anchor, months)

    events = load_dividend_events(db, family_id)
    holdings = _load_holdings(db, family_id)
    navs = _latest_navs(db, holdings)
    net_invested = net_invested_by_position(db, family_id)

    group_ids = {e.link_group_id for e in events if e.kind == KIND_REINVEST and e.link_group_id}
    buys_by_position = _reinvest_buys_by_position(db, family_id, group_ids)

    events_by_position: dict[int, list[DividendEvent]] = {}
    for event in events:
        if event.position_id is not None:
            events_by_position.setdefault(event.position_id, []).append(event)

    # ── 逐持仓（在管口径）──
    rows: list[dict[str, Any]] = []
    for position in holdings:
        own = events_by_position.get(position.id, [])
        ttm = [e for e in own if e.occurred_on is not None and start <= e.occurred_on <= anchor]
        bucket_ttm = _bucket(ttm)
        bucket_all = _bucket(own)

        cost = cost_basis_cents(position, net_invested.get(position.id))
        latest_nav = navs.get(position.symbol) if position.asset_type in _NAV_ASSET_TYPES else None
        market_value = market_value_cents(position, effective_nav_yuan=latest_nav)
        last_date = max((e.occurred_on for e in own if e.occurred_on), default=None)

        rows.append(
            {
                'position_id': position.id,
                'symbol': position.symbol,
                'name': position.name,
                'asset_type': position.asset_type,
                'account_name': position.account_name,
                'ledger_id': position.ledger_id,
                'cost_cents': cost,
                'market_value_cents': market_value,
                **bucket_ttm,
                # 分母统一为「当前成本」：股息率的定义就是「投入的钱每年拿回多少分红」
                'yield_on_cost_pct': _pct(bucket_ttm['net_cents'], cost),
                'cash_yield_on_cost_pct': _pct(bucket_ttm['cash_cents'], cost),
                'yield_on_value_pct': _pct(bucket_ttm['net_cents'], market_value),
                'all_time_cash_cents': bucket_all['cash_cents'],
                'all_time_net_cents': bucket_all['net_cents'],
                'all_time_event_count': bucket_all['event_count'],
                'reinvest_gain_cents': _reinvest_gain_cents(
                    buys_by_position.get(position.id, []),
                    _effective_price_yuan(position, latest_nav),
                ),
                'last_dividend_date': last_date.isoformat() if last_date else None,
            }
        )

    # 有分红的排前面（金额降序），其次按市值降序——页面上「谁在分红」一眼可见
    rows.sort(key=lambda r: (-r['net_cents'], -r['market_value_cents'], r['position_id']))

    # ── 组合（在管口径，分子分母同域）──
    total_cost = sum(r['cost_cents'] for r in rows)
    total_mv = sum(r['market_value_cents'] for r in rows)
    p_cash = sum(r['cash_cents'] for r in rows)
    p_reinvest = sum(r['reinvest_cents'] for r in rows)
    p_tax = sum(r['tax_cents'] for r in rows)
    p_net = p_cash + p_reinvest - p_tax
    gains = [r['reinvest_gain_cents'] for r in rows if r['reinvest_gain_cents'] is not None]
    portfolio = {
        'holding_count': len(rows),
        'paying_count': sum(1 for r in rows if r['net_cents'] > 0),
        'cost_cents': total_cost,
        'market_value_cents': total_mv,
        'cash_cents': p_cash,
        'reinvest_cents': p_reinvest,
        'tax_cents': p_tax,
        'net_cents': p_net,
        'yield_on_cost_pct': _pct(p_net, total_cost),
        'cash_yield_on_cost_pct': _pct(p_cash, total_cost),
        'yield_on_value_pct': _pct(p_net, total_mv),
        'reinvest_gain_cents': sum(gains) if gains else None,
    }

    return {
        'as_of': anchor.isoformat(),
        'period': {'months': months, 'start': start.isoformat(), 'end': anchor.isoformat()},
        'totals': _totals_block(events, start, anchor),
        'by_year': _by_year_block(events, anchor.year, years),
        'portfolio': portfolio,
        'holdings': rows,
        'target': _target_block(db, family_id, portfolio['yield_on_cost_pct']),
    }


def _totals_block(events: list[DividendEvent], start: date, anchor: date) -> dict[str, Any]:
    """全量口径（含已清仓 / 孤儿分红）＋近窗口口径。"""
    ttm = [e for e in events if e.occurred_on is not None and start <= e.occurred_on <= anchor]
    all_time = _bucket(events)
    dated = [e.occurred_on for e in events if e.occurred_on]
    return {
        'ttm': _bucket(ttm),
        'all_time': all_time,
        'first_date': min(dated).isoformat() if dated else None,
        'last_date': max(dated).isoformat() if dated else None,
    }


def _by_year_block(events: list[DividendEvent], anchor_year: int, years: int) -> list[dict[str, Any]]:
    """按自然年汇总（降序，含当年，最多 `years` 年）。"""
    earliest = anchor_year - years + 1
    grouped: dict[int, list[DividendEvent]] = {}
    for event in events:
        if event.occurred_on is None:
            continue
        grouped.setdefault(event.occurred_on.year, []).append(event)
    return [
        {'year': year, **_bucket(grouped.get(year, []))}
        for year in sorted((y for y in grouped if y >= earliest), reverse=True)
    ]


def read_target(db: Session, family_id: int) -> dict[str, Any]:
    """只读股息目标配置（不含达成度——达成度依赖实际股息率，见 `build_dividend_summary`）。"""
    row = db.query(DividendTarget).filter(DividendTarget.family_id == family_id).first()
    if row is None:
        return {'configured': False, 'target_yield_pct': None, 'notes': None}
    return {
        'configured': True,
        'target_yield_pct': float(row.target_yield_pct),
        'notes': row.notes,
    }


def _target_block(db: Session, family_id: int, current_yield_pct: Optional[float]) -> dict[str, Any]:
    """股息目标达成度。未设置目标时 `configured=False`，达成度字段为 None。

    达成度用「成本口径的实际股息率」（`portfolio.yield_on_cost_pct`）作分子，
    与目标同为「年化股息率」，量纲一致；分母非正（无成本）时达成度不可算，
    返回 None 而不是 0，避免把「没有持仓」显示成「0% 达成」。
    """
    base = read_target(db, family_id)
    if not base['configured']:
        return {**base, 'progress_pct': None, 'gap_pct': None, 'met': None}
    target = base['target_yield_pct']
    if current_yield_pct is None or target <= 0:
        return {**base, 'progress_pct': None, 'gap_pct': None, 'met': None}
    return {
        **base,
        'progress_pct': round(current_yield_pct / target * 100, 2),
        'gap_pct': round(current_yield_pct - target, 2),
        'met': bool(current_yield_pct >= target),
    }


def upsert_target(db: Session, family_id: int, *, target_yield_pct: float, notes: Optional[str]) -> DividendTarget:
    """设置 / 更新家庭股息目标（一个家庭一条），调用方负责 commit。"""
    row = db.query(DividendTarget).filter(DividendTarget.family_id == family_id).first()
    if row is None:
        row = DividendTarget(family_id=family_id, target_yield_pct=target_yield_pct, notes=notes)
        db.add(row)
    else:
        row.target_yield_pct = target_yield_pct
        row.notes = notes
    db.flush()
    return row


def clear_target(db: Session, family_id: int) -> bool:
    """清除股息目标；返回是否确有删除（未设置时返回 False）。"""
    row = db.query(DividendTarget).filter(DividendTarget.family_id == family_id).first()
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True
