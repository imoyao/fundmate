# -*- coding: utf-8 -*-
"""盈亏口径的唯一出口（#1183：已实现 / 未实现 / 总盈亏）。

WHY
    改造前全系统只有一种盈亏：`(current_price − avg_price) × quantity`
    （`summary_service.get_summary_data` 与 `ledger_service` 各算各的），
    既没有已实现 / 未实现的拆分，dividend 在汇总与 XIRR 两处口径也不一致——
    汇总的孤儿流水净额把 dividend `continue` 排除，XIRR 却把 `dividend_cash`
    记为正现金流（见 `performance/xirr_engine.py`）。

口径定义（本模块是唯一实现，禁止各处再算一套）：

- **成本法：移动加权平均**。建仓按 `(old_cost + new_cost) / total_qty` 重算均价
  （`position_service.process_buy_or_deposit`），**卖出不改变成本均价**。
  不是 FIFO——FIFO 仅用于赎回费预估（`services/fund_service.py`）。
- **已实现盈亏 realized**：卖出/取出时按「(成交价 − 成本均价) × 份额 − 手续费」
  结转并落库到流水的 `realized_pnl`；现金分红按分红金额全额计入已实现。
  记在**流水**而非持仓上：清仓时持仓行会被 delete，记在持仓上会随持仓一起丢失。
- **未实现盈亏 unrealized**：持仓浮动部分 = 市值 − 成本基数。
  nav 模式成本基数 = 成本均价 × 份额；balance 模式（无份额可乘）成本基数 =
  该持仓的净投入（Σ买入/存入 − Σ卖出/取出；分红不冲减成本基数，已在 realized 侧计过）。
- **总盈亏 total = realized + unrealized**。

与 XIRR 口径的自洽性（决策 D3：balance 模式盈亏复用 XIRR 现金流定义）：
两种模式下恒有

    total = 市值 + Σ卖出回款 + Σ现金分红 − Σ投入 − Σ手续费

即 XIRR 的现金流口径（卖出 / 现金分红为流入，买入 / 红利再投资为流出），
因此本模块的 total 与 `performance/xirr_engine.py` 的现金流定义一致。

已知边界：realized 取自流水金额，**不做汇率折算**（与账本侧既有的流水汇总一致）；
unrealized 的市值与成本基数则同乘 `rate` 折算为 CNY，与仪表盘总资产口径一致。
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import ValuationMode
from app.core.money import Money
from app.domains.transactions.models import Transaction
from app.services.position_valuation import market_value_cents

# 投入（+）与回款（−）的流水类型；分红/送股不参与成本基数（分红记 realized，送股只稀释均价）
_INVEST_TXN_TYPES = ('buy', 'deposit')
_DIVEST_TXN_TYPES = ('sell', 'withdraw')


def _scale_cents(cents: int, rate: float | None) -> int:
    """按汇率折算金额（分），ROUND_HALF_UP，与市值口径一致。"""
    if rate is None or rate == 1.0:
        return int(cents or 0)
    return int((Decimal(str(cents or 0)) * Decimal(str(rate))).to_integral_value(rounding=ROUND_HALF_UP))


def compute_sell_realized_cents(
    *,
    price_units: int,
    avg_price_units: int,
    qty_units: int,
    fee_cents: int = 0,
) -> int:
    """单笔卖出/取出的已实现盈亏（分）=（成交价 − 成本均价）× 份额 − 手续费。

    移动加权平均下卖出不改变成本均价，故此处必须用**卖出当时的**成本均价计算，
    不能事后再按当前均价反推——否则后续买入拉低/抬高均价会让已落袋的盈亏漂移，
    违反「卖出后已实现盈亏不随后续净值变动」的验收要求。
    """
    gross = Money.multiply_price_quantity((price_units or 0) - (avg_price_units or 0), qty_units or 0)
    return int(gross) - int(fee_cents or 0)


def realized_pnl_by_position(db: Session, family_id: int) -> dict[int, int]:
    """按持仓归集的已实现盈亏（分）。

    以**流水**为事实源而非持仓：清仓后持仓行被删除，但卖出流水仍在，
    盈亏不能随之消失。孤儿流水（position_id 为 NULL）统一归到哨兵键 0。
    """
    rows = (
        db.query(Transaction.position_id, func.sum(Transaction.realized_pnl))
        .filter(Transaction.family_id == family_id)
        .group_by(Transaction.position_id)
        .all()
    )
    return {(pid or 0): int(total or 0) for pid, total in rows}


def family_realized_pnl_cents(db: Session, family_id: int) -> int:
    """家庭级已实现盈亏合计（分），含已清仓持仓的结转盈亏与孤儿分红。"""
    total = db.query(func.sum(Transaction.realized_pnl)).filter(Transaction.family_id == family_id).scalar()
    return int(total or 0)


def net_invested_by_position(db: Session, family_id: int) -> dict[int, int]:
    """按持仓归集的净投入（分）= Σ买入/存入金额 − Σ卖出/取出金额。

    balance 模式（无份额可乘）的成本基数取这里的值。分红**不**冲减成本基数：
    分红已在 realized 侧按全额计过，再冲减会重复计算（见模块 docstring 的恒等式）。
    """
    rows = (
        db.query(Transaction.position_id, Transaction.txn_type, func.sum(Transaction.amount))
        .filter(Transaction.family_id == family_id)
        .group_by(Transaction.position_id, Transaction.txn_type)
        .all()
    )
    net: dict[int, int] = {}
    for pid, txn_type, amount in rows:
        key = pid or 0
        amount = int(amount or 0)
        if txn_type in _INVEST_TXN_TYPES:
            net[key] = net.get(key, 0) + amount
        elif txn_type in _DIVEST_TXN_TYPES:
            net[key] = net.get(key, 0) - amount
    return net


def cost_basis_cents(position, net_invested: int | None = None) -> int:
    """持仓成本基数（分）。

    nav 模式：成本均价 × 份额（移动加权平均账面成本）。
    balance 模式：无份额可乘，成本基数只能来自现金流净投入。
    """
    mode = getattr(position, 'valuation_mode', None) or ValuationMode.NAV.value
    if mode == ValuationMode.BALANCE.value:
        return int(net_invested or 0)
    return Money.multiply_price_quantity(position.avg_price or 0, position.quantity or 0)


def position_pnl_cents(
    position,
    *,
    effective_nav_yuan: float | None = None,
    rate: float | None = None,
    realized_cents: int = 0,
    net_invested: int | None = None,
) -> dict[str, int]:
    """单笔持仓的三段盈亏（分）。

    Args:
        position: 持仓记录（同 `position_valuation.market_value_cents` 的字段要求）。
        effective_nav_yuan: 有效净值（元），基金类由调用方传入最新净值。
        rate: 本币 → CNY 汇率；None 按 1.0。市值与成本基数同乘该汇率。
        realized_cents: 该持仓的已实现盈亏（分），由 `realized_pnl_by_position` 批量取。
        net_invested: 该持仓的净投入（分），balance 模式用作成本基数。
    """
    market_value = market_value_cents(position, effective_nav_yuan=effective_nav_yuan, rate=rate)
    cost = _scale_cents(cost_basis_cents(position, net_invested), rate)
    realized = int(realized_cents or 0)
    unrealized = market_value - cost
    return {
        'market_value_cents': market_value,
        'cost_basis_cents': cost,
        'realized_pnl_cents': realized,
        'unrealized_pnl_cents': unrealized,
        'total_pnl_cents': realized + unrealized,
    }
