# -*- coding: utf-8 -*-
"""持仓交易时间线重放（#2171 · 详情页买卖点 / 成本线叠加）。

买方视角：用户要看清「每笔买卖发生在什么价位、当时成本线在哪」。与 XIRR
（``services/performance``）的分工——XIRR 回答「年化多少」，本模块回答
「过程长什么样」：逐笔交易点 + 交易后成本线序列，供走势图叠加。

## 口径（全部有出处，开发时不得偏离）

- **收敛键 = ``symbol`` 写法变体集合**（``symbol_scope``，与 #1966 我的持仓 /
  #2009 XIRR 收敛同一真相源）；**禁用 ``transactions.position_id``**——其覆盖率
  仅 45%（#2009 实测），靠它收敛等于漏掉一半流水；
- **``ledger_id`` 可选过滤**：不传 = 该家庭该产品**全部账户合并**（产品级视角，
  与 ``calculate_symbol_xirr`` 同源）；传入 = 单账户（分渠道展示时接）；
- **重放按 ``trade_date`` 升序**：买方视角是「我哪天操作的」（#2171 定稿），
  确认日（``confirm_date``）随交易点返回供悬浮展示，不错位曲线；
- **成本含手续费**：买入 / 转入 成本 = 成交金额（``amount``，分）+ 手续费
  （``fee``，分）；卖出 / 取出按**移动加权比例缩减**剩余成本（成本率不变），
  全部清空则成本归零——「成本总额不变」会让成本率随减持被动抬升，且下一轮
  建仓会续上前轮成本（两者均在 #2171 开发实测中抓到）；
- **清仓中断**：份额归零后不再产出成本线点（该笔交易点带 ``closed=True``），
  新一轮建仓自然重放出新的成本线；
- **现金分红（``dividend``）不进成本线**：它改变现金流而非份额 / 成本，
  计入 ``summary.dividend_count``；累计收益曲线（P1）再消费它；
- **其余类型（拆分 / 兑付 / 扣税 / 其他）不参与重放**：计入
  ``summary.ignored_*`` 计数，不静默丢弃。

## 单位（与 ``core/money.py`` 一致）

入参：金额存**分**、价格存 **0.0001 元**、份额存最小单位（**0.0001 份**）。
输出统一换算为「元 / 份」（前端不接触存储单位），保留位数见各字段注释。
"""

from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.symbol_scope import (
    collect_transaction_symbol_variants,
    query_positions_by_symbol,
)

# 参与成本重放但**不作为买卖点**展示的类型：转入 / 取出改变份额与成本，
# 却不是用户的买卖决策（#2171 定稿：叠加层只画 buy/sell 决策点）。
_SHARE_TYPES = frozenset({'buy', 'sell', 'deposit', 'withdraw'})
# 买卖决策点（前端 scatter 层只画这两类）
_DECISION_TYPES = frozenset({'buy', 'sell'})
# 不参与重放的其余类型（拆分 / 兑付 / 扣税 / 其他），仅计数
_IGNORED_TYPES = frozenset({'split', 'bond_redeem', 'tax', 'other'})

# 存储单位 → 输出单位换算
_CENTS_PER_YUAN = 100
_PRICE_UNITS = 10_000  # 0.0001 元
_QTY_UNITS = 10_000  # 0.0001 份


def _to_yuan(cents: Optional[int]) -> float:
    return round((cents or 0) / _CENTS_PER_YUAN, 2)


def _to_price_yuan(units: Optional[int]) -> float:
    return round((units or 0) / _PRICE_UNITS, 4)


def _to_qty(units: Optional[int]) -> float:
    return round((units or 0) / _QTY_UNITS, 4)


def _trade_day(txn: Transaction) -> Optional[dt.date]:
    """交易日（T 日）。``trade_date`` 是 DateTime，确认日 ``confirm_date`` 是 Date。"""
    value = txn.trade_date
    if value is None:
        return None
    return value.date() if isinstance(value, dt.datetime) else value


def empty_trade_timeline(symbol: str) -> Dict:
    """空时间线（未登录 / 无流水）：与 :func:`build_trade_timeline` 结构一致。

    前端不分支：拿到的永远是同一形状，``points`` 为空即不渲染叠加层。
    """
    return {
        'symbol': (symbol or '').strip().upper(),
        'points': [],
        'cost_line': [],
        'summary': {
            'buy_count': 0,
            'sell_count': 0,
            'dividend_count': 0,
            'total_buy_amount_yuan': 0.0,
            'total_sell_amount_yuan': 0.0,
            'total_fee_yuan': 0.0,
            'first_trade_date': None,
            'last_trade_date': None,
            'current_quantity': 0.0,
            'current_cost_yuan': 0.0,
            'current_avg_cost_yuan': None,
            'ignored_count': 0,
            'ignored_types': {},
        },
    }


def build_trade_timeline(
    db: Session,
    *,
    symbol: str,
    family_id: int,
    ledger_id: Optional[int] = None,
) -> Dict:
    """重放该产品（可选单账户）的全量流水，输出交易点 + 成本线 + 汇总。

    Args:
        db: **user 域**会话（transactions / positions 都在 user 域）。
        symbol: 产品代码（任意入口形态，变体收敛由 symbol_scope 负责）。
        family_id: 家庭 ID（数据隔离）。
        ledger_id: 可选，只重放某一账户的流水。

    Returns:
        ``{symbol, points, cost_line, summary}``；无流水时 points / cost_line
        为空数组、summary 计数为 0（**不是错误**——没持仓的用户走不到这个端点，
        走到的一般是「有持仓但流水被删」的异常态，空序列让前端降级不渲染叠加层）。
    """
    code = (symbol or '').strip()
    if not code:
        raise ValueError('缺少 symbol 参数')

    # 两步读（数据策略 §3）：先用持仓侧拿真实 symbol 写法，再对交易表做 IN。
    # 不过滤 quantity——清仓行的流水同样是重放对象（#2171「历轮买卖」）。
    positions: List[Position] = query_positions_by_symbol(db, code, family_id)
    variants = collect_transaction_symbol_variants(code, positions)

    query = db.query(Transaction).filter(
        Transaction.family_id == family_id,
        Transaction.symbol.in_(sorted(variants)),
    )
    if ledger_id is not None:
        query = query.filter(Transaction.ledger_id == ledger_id)
    transactions = query.order_by(Transaction.trade_date.asc(), Transaction.id.asc()).all()

    qty_units = 0  # 份额（最小单位）
    cost_cents = 0  # 持仓成本（分）
    points: List[Dict] = []
    cost_line: List[Dict] = []
    ignored_types: Dict[str, int] = {}
    buy_count = sell_count = dividend_count = 0
    total_buy_cents = total_sell_cents = total_fee_cents = 0
    first_day: Optional[dt.date] = None
    last_day: Optional[dt.date] = None

    for txn in transactions:
        day = _trade_day(txn)
        if day is None:
            # 没有交易日期的流水无法定位到曲线，跳过并计数（不静默）
            ignored_types['no_date'] = ignored_types.get('no_date', 0) + 1
            continue
        if first_day is None:
            first_day = day
        last_day = day

        txn_type = (txn.txn_type or '').strip().lower()
        amount_cents = txn.amount or 0
        fee_cents = txn.fee or 0
        qty = txn.quantity or 0
        price = txn.price or 0

        if txn_type == 'buy':
            qty_units += qty
            cost_cents += amount_cents + fee_cents
            total_buy_cents += amount_cents
            total_fee_cents += fee_cents
            buy_count += 1
        elif txn_type == 'deposit':
            # 转入视同买入：增份额、增成本，但不是「买卖决策」
            qty_units += qty
            cost_cents += amount_cents + fee_cents
            total_fee_cents += fee_cents
        elif txn_type in ('sell', 'withdraw'):
            # 卖出 / 取出：移动加权——剩余成本按剩余份额**比例缩减**（成本率不变），
            # 全部清空则成本归零（否则新一轮建仓会续上前轮成本，#2171 实测教训）。
            # 注意「成本总额不变」是错的：那会让成本率随减持被动抬升。
            remaining = qty_units - qty
            if remaining > 0:
                cost_cents = int(cost_cents * remaining / qty_units)
            else:
                cost_cents = 0
            qty_units = remaining
            if txn_type == 'sell':
                total_sell_cents += amount_cents
                total_fee_cents += fee_cents
                sell_count += 1
            else:
                total_fee_cents += fee_cents
        elif txn_type == 'dividend':
            # 现金分红：份额与成本均不变（P1 累计收益曲线再消费）
            dividend_count += 1
        elif txn_type in _IGNORED_TYPES:
            ignored_types[txn_type] = ignored_types.get(txn_type, 0) + 1
            continue
        else:
            # 未识别类型：不猜语义，计数跳过
            ignored_types[txn_type or 'empty'] = ignored_types.get(txn_type or 'empty', 0) + 1
            continue

        if txn_type in _DECISION_TYPES:
            points.append(
                {
                    'date': day.isoformat(),
                    'side': txn_type,
                    'amount_yuan': _to_yuan(amount_cents),
                    'quantity': _to_qty(qty),
                    'price_yuan': _to_price_yuan(price),
                    'fee_yuan': _to_yuan(fee_cents),
                    'confirm_date': txn.confirm_date.isoformat() if txn.confirm_date else None,
                    'account_name': txn.account_name or None,
                    # 该笔之后的成本线值；清仓笔为 0（前端在此断线）
                    'cost_after_yuan': _to_yuan(cost_cents) if qty_units > 0 else 0.0,
                    'closed': qty_units <= 0,
                }
            )

        # 成本线只由**改变持仓**的类型产出（buy/sell/deposit/withdraw）：现金分红
        # 当日成本不变，产线只会得到与上一条等值的重复点；成本线的「延续」由
        # 前端折线自然完成，不需要在这里补点。
        # 按日去重：同日多笔只保留当日最后一笔后的值。
        if txn_type in _SHARE_TYPES and qty_units > 0:
            if cost_line and cost_line[-1]['date'] == day.isoformat():
                cost_line[-1]['cost_yuan'] = _to_yuan(cost_cents)
            else:
                cost_line.append({'date': day.isoformat(), 'cost_yuan': _to_yuan(cost_cents)})

    summary = {
        'buy_count': buy_count,
        'sell_count': sell_count,
        'dividend_count': dividend_count,
        'total_buy_amount_yuan': _to_yuan(total_buy_cents),
        'total_sell_amount_yuan': _to_yuan(total_sell_cents),
        'total_fee_yuan': _to_yuan(total_fee_cents),
        'first_trade_date': first_day.isoformat() if first_day else None,
        'last_trade_date': last_day.isoformat() if last_day else None,
        'current_quantity': _to_qty(qty_units),
        'current_cost_yuan': _to_yuan(cost_cents),
        # 成本均价（0.0001 元口径存的是分×份额，这里换算回元）
        'current_avg_cost_yuan': (
            round(cost_cents * _PRICE_UNITS / _CENTS_PER_YUAN / qty_units, 4) if qty_units > 0 else None
        ),
        'ignored_count': sum(ignored_types.values()),
        'ignored_types': ignored_types,
    }

    return {
        'symbol': code,
        'points': points,
        'cost_line': cost_line,
        'summary': summary,
    }
