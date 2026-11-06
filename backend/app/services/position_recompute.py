# -*- coding: utf-8 -*-
"""持仓**份额重算**（删 / 改流水后由剩余流水派生份额与成本，#948 后续回滚）。

`PositionService.recompute_position_from_transactions` 曾是 123 行的方法（第七抽收尾后
`position_service.py` 里最大的函数）。它是「份额派生的唯一入口」——删除 / 编辑交易、
净值回填、孤儿回填、修复脚本、对账服务全都汇到这里，所以它同时是两个历史 bug 的案发现场：

- 「全量流水净额」与快照 SET 语义并存 → 份额被重复累加；
- 删流水整行 `db.delete(position)` → 锚点随行消失，重建时退回全量口径 → 二次累加复发。

结论固定成下面三条判据，**本模块只允许有一种派生口径**：

1. **份额与成本一律委托 `compute_anchored_state`**（锚点感知）。本函数历史上自己实现过一套
   「全量流水净额」循环，与快照导入的 SET 语义并存，正是重复累加的成因。现在只保留一个
   派生入口，避免第二份实现再次分叉；
2. **「无流水即删行」必须以无锚点为前提**（2026-10-18）：纯快照导入的持仓本来就没有明细
   流水，早退删行会让它们在任意一次重算中消失（真实库实测：105 行「有快照日、无流水」的
   持仓里 79 行零流水）。有锚点时走正常派生：`snapshot_quantity` 即基线份额；
3. **净份额归零不再删行**（#2343 第二步，2026-10-18）：改为 `mark_position_cleared`
   （`quantity=0` + `ownership_status='cleared'` + `cleared_at`），锚点原样留存。反向对称：
   `cleared` 行派生出正份额（典型：删除了那笔清仓卖出流水）时自动重新激活回 `active`——
   持仓「复活」，锚点与流水全程无断链。例外：`not txns and not has_anchor` 的空壳行仍删行
   ——那不是清仓历史，是无任何数据支撑的孤儿行，标记成 cleared 反而会伪造一段「曾持有」。

## 持仓行已被物理删除时的重建

旧版本整笔卖出会 `db.delete(position)`，历史库里可能仍有这类残留（行没了、买入流水还在）。
`position_id` 全部指回一个不存在的 id 时，用剩余流水重建持仓行，并把流水重新挂回新行。
重建行的 `market` / `currency` 取默认值——`Transaction` 不携带这两个字段，这是已知边界。

## 依赖方向

`position_service` 在模块级导入本模块（转发薄壳）；本模块只在**函数内**延迟导入主模块的
`compute_anchored_state` 与 `_silent_reconcile_watchlist`（两者都服务买入 / 卖出 / 快照 /
兑付 / 重算多条路径，留主模块才不制造双向依赖）。
"""

from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.constants import OwnershipStatus
from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.positions.state import derive_state_from_txns, mark_position_cleared
from app.domains.transactions.dates import order_by_effective_day
from app.domains.transactions.models import Transaction


def recompute_from_transactions(db: Session, position_id: int) -> Optional[Position]:
    """依据该持仓剩余流水重算份额与成本均价，返回重算后的持仓（已删行 / 已清仓时返回 None）。

    采用「从流水重算」而非只做反向加减：
    - 能正确处理部分卖出（剩余流水仍有买入，净份额 > 0，更新现有持仓）；
    - 也能在「整笔卖出清空持仓」后删除该卖出流水时依据剩余买入流水重建持仓，
      避免份额彻底丢失。

    本段只做**取数与分流**：删空壳行 / 清仓 / 更新 / 重建四种结局分别交给具名步骤，
    每一步的判据见其 docstring。调用方习惯 `PositionService.recompute_position_from_transactions`。
    """
    # 函数内导入：该名字服务多条路径，留主模块才不制造双向依赖。
    from app.services.position_service import compute_anchored_state  # noqa: PLC0415

    txns = order_by_effective_day(
        db.query(Transaction).filter(Transaction.position_id == position_id), descending=False
    ).all()
    pos = db.query(Position).filter_by(id=position_id).first()

    # 「无流水即删行」只能在**无锚点**时成立。有锚点的持仓其份额来自快照，
    # 流水本来就可以为空（纯快照导入的账户，绝大多数持仓没有明细流水）。
    # 2026-10-18 实测：真实库 105 行「有快照日、无流水」的持仓里 79 行零流水，
    # 该早退分支会让它们在任何一次重算中整行消失——锚点模型对这类持仓完全失效。
    has_anchor = pos is not None and pos.snapshot_quantity is not None and pos.snapshot_date is not None
    if not txns and not has_anchor:
        if pos:
            db.delete(pos)
            db.flush()
        return None

    if pos is not None:
        net_qty, avg_price_units = compute_anchored_state(db, pos)
    else:
        # 持仓行已被清空删除：无锚点可用，退回全量流水口径（见模块 docstring 已知边界）
        net_qty, avg_price_units = derive_state_from_txns(txns, 0, 0)

    if net_qty <= 0:
        return _settle_non_positive(db, pos, net_qty)

    if pos is not None:
        _apply_derived_state(db, pos, net_qty, avg_price_units)
        return pos

    return _rebuild_position_from_txns(db, txns, net_qty, avg_price_units)


def _settle_non_positive(db: Session, pos: Optional[Position], net_qty: int) -> None:
    """净份额归零 / 为负：标记清仓而不是删行（#2343 第二步）。

    负数是脏数据（真实份额不可能为负），钳为 0 并留一条 warning：保留负值会让市值算出负数。
    无持仓行时无从标记，直接返回 None——调用方读「None = 该持仓已不存在 / 已清仓」。
    """
    if pos is None:
        return None
    # 归零不再删行：`mark_position_cleared` 打 cleared 状态 + cleared_at，锚点原样留存。
    if net_qty < 0:
        logger.warning(
            '[Recompute] 派生份额为负，钳为 0 并标记清仓: position={} symbol={} net={}',
            pos.id,
            pos.symbol,
            Money.min_unit_to_shares(net_qty),
        )
    mark_position_cleared(pos)
    db.flush()
    return None


def _apply_derived_state(
    db: Session,
    pos: Position,
    net_qty: int,
    avg_price_units: int,
) -> None:
    """把派生结果写回既有持仓行：清仓复活 + 变更可观测 + 赋值 + 自选对齐。"""
    # 函数内导入：同 `recompute_from_transactions`，避免与主模块成环。
    from app.services.position_service import _silent_reconcile_watchlist  # noqa: PLC0415

    # 清仓行派生出正份额 → 持仓复活（典型：删除了那笔清仓卖出流水）。
    # 锚点与 cleared_at 原样保留：锚点仍是上一轮快照口径（删除卖出后全量流水
    # 恰好等于锚点 + 流入，两者自洽），cleared_at 是历史周期下界，不是当前状态。
    if pos.ownership_status == OwnershipStatus.CLEARED.value:
        pos.ownership_status = OwnershipStatus.ACTIVE.value
        logger.info(
            '[Recompute] 已清仓持仓复活: position={} symbol={} qty={}',
            pos.id,
            pos.symbol,
            Money.min_unit_to_shares(net_qty),
        )
    # 锚点重算的可观测性（2026-10-18 评审）：重算覆盖是本类 bug 最隐蔽的复发形态
    # ——净值回填 / 删流水都会静默改写 quantity。只记日志不抛错：重算本来就会正常
    # 变化（补录 / 修正历史流水），抛错会打断 nav_backfill 的任务链。
    if pos.quantity != net_qty and pos.snapshot_quantity is not None:
        logger.warning(
            '[Recompute] 锚点持仓份额变更: position={} symbol={} {} -> {} (anchor={} date={} kind={})',
            pos.id,
            pos.symbol,
            Money.min_unit_to_shares(pos.quantity),
            Money.min_unit_to_shares(net_qty),
            Money.min_unit_to_shares(pos.snapshot_quantity),
            pos.snapshot_date,
            pos.anchor_kind,
        )
    pos.quantity = net_qty
    pos.avg_price = avg_price_units
    if pos.current_price in (None, 0):
        pos.current_price = avg_price_units
    db.flush()
    # #1458 后续：重算后对齐自选状态（静默）
    _silent_reconcile_watchlist(db, pos.family_id, pos.symbol)


def _rebuild_position_from_txns(
    db: Session,
    txns: list[Transaction],
    net_qty: int,
    avg_price_units: int,
) -> Position:
    """持仓行已被整笔卖出物理删除时的重建路径（历史残留，见模块 docstring）。

    `Transaction` 不携带 `market` / `currency`，重建行取默认值——这是已知边界，
    不是遗漏：真正带场所的是持仓行本身，而它已经不在了。
    """
    # 函数内导入：同上，避免与主模块成环。
    from app.services.position_service import _silent_reconcile_watchlist  # noqa: PLC0415

    first = txns[0]
    new_pos = Position(
        ledger_id=first.ledger_id,
        family_id=first.family_id,
        symbol=first.symbol or '',
        name=first.position_name or first.symbol or '',
        asset_type=first.asset_type,
        market='CN_A',
        currency='CNY',
        quantity=net_qty,
        avg_price=avg_price_units,
        current_price=avg_price_units,
        confirm_date=first.confirm_date,
        account_name=first.account_name,
        allocation='longterm',
        notes='',
    )
    db.add(new_pos)
    db.flush()
    for t in txns:
        t.position_id = new_pos.id
    db.flush()
    # #1458 后续：重算后对齐自选状态（静默）
    _silent_reconcile_watchlist(db, new_pos.family_id, new_pos.symbol)
    return new_pos
