# -*- coding: utf-8 -*-
"""对账差异 →「按流水重算份额」动作（#3134）。

## 为什么这个动作必须存在

域 B 的 `quantity` 差异是「持仓份额 − 按流水算出的份额」。工作台原先把**所有**差异
都指向补录弹窗，而补录的 increment 分支走买卖汇点、**同时**写流水与持仓
（见 `reconciliation_decision._apply_increment`）——差额两端同步移动，恒等于补录前的值。
真库 2026-11-15 实测：用户照卡片提示补了一笔卖出 3000，持仓 4000→1000 份、
流水净额 3000→0，差额**仍是** 1000 份（`discrepancies#378`），卡片一点变化都没有。

份额与流水不自洽时，能改变差额的只有**改持仓**这一侧：`recompute_from_transactions`
（按流水派生）或 `upsert_from_holding`（用户手填）。本模块把前者接进对账工作台，
派生口径与持仓页的「按流水重算份额」是同一份实现，不另写一套。

## 为什么写之前要再判一次

差异卡片是某次 run 生成的，用户点按钮时数据可能已被别的链路改过
（`reconciliation_anchor` 记了同款时点差：#3128 就是两次对账之间把 101 条持仓重算清仓的）。
若此刻按流水派生的净额为**负**（卖出多于买入，典型是买入腿没挂回来），重算会把这只
持仓清零——那是把「流水缺一条腿」误判成「已清仓」。#3127 明确「不敢批量清仓、只报数
交人工」，故负数一律拒绝，并把用户指向手填入口（`kind='set'`，前端标为「改成账单份额」）。

## 两套流水口径必须先对账

对账按业务键 `(ledger_id, symbol)` 取流水（`reconciliation_theory`），重算按
`transactions.position_id` 取（`compute_anchored_state`，份额派生的唯一入口）。绝大多数
情况下两者同一批记录，但「流水没挂回持仓」（悬空流水）时会分叉：卡片说有 100 股，
重算却一条流水都看不到，于是按「无流水且无锚点 ⇒ 删行」把一条**有份额的持仓物理删除**
——静默、不可撤销、且删的正是用户想修的那条。故写库前先比一次两套口径（见
`_assert_same_flow_set`）。
"""

from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.reconciliation.models import ReconciliationDiscrepancy
from app.domains.transactions.models import Transaction
from app.services.position_recompute_entry import recompute_with_audit
from app.services.position_write_support import _find_existing_position
from app.services.reconciliation_adjustment import recompute_linked_discrepancy
from app.services.reconciliation_theory import has_anchor

DEFAULT_REASON = '对账工作台：按流水重算份额'


def _derived_net_units(db: Session, position) -> int:
    """该持仓按现有流水派生出的份额（锚点感知，最小单位）。

    函数内导入：`position_service` 在模块级会牵进一大串依赖，本模块只在这条写路径上用一次。
    """
    from app.services.position_service import compute_anchored_state  # noqa: PLC0415

    net_units, _ = compute_anchored_state(db, position)
    return net_units


def _assert_flows_support_position(db: Session, position) -> None:
    """负数派生额 ⇒ 拒绝重算（见模块 docstring「为什么写之前要再判一次」）。"""
    net_units = _derived_net_units(db, position)
    if net_units < 0:
        raise ValueError(
            f'按现有流水算是 {Money.min_unit_to_shares(net_units):g} 份（卖出多于买入，缺买入流水），'
            '据此重算会把持仓清零。请先补齐缺失的买入流水，或改用「改成账单份额」按账单填当前份额'
        )


def _has_key_flows(db: Session, disc: ReconciliationDiscrepancy) -> bool:
    """对账口径（业务键 `ledger_id + symbol`）下有没有流水。"""
    return (
        db.query(Transaction)
        .filter(
            Transaction.family_id == disc.family_id,
            Transaction.ledger_id == disc.ledger_id,
            Transaction.symbol == disc.symbol,
        )
        .count()
        > 0
    )


def _assert_same_flow_set(db: Session, position, disc: ReconciliationDiscrepancy) -> None:
    """两套口径必须看到同一批流水，否则拒绝（见模块 docstring 末节）。

    只在「持仓名下一笔流水都没有、且无锚点」时开火——那正是重算会删行的那条判据
    （`position_recompute`：无流水且无锚点 ⇒ 空壳行），也只有在那一刻两套口径的分叉
    才会变成**删掉一条有份额的持仓**。有锚点时快照就是份额来源，空流水是合法常态。

    判据看的是「该标的有流水」而**不是**「净额不为 0」：买卖腿齐平（净额 0）时差额
    照旧存在（账上还有份额），而重算同样会把持仓删掉——按净额判会在最常见的幽灵持仓
    形态上漏过去。
    """
    if has_anchor(position):
        return
    if db.query(Transaction).filter(Transaction.position_id == position.id).count():
        return
    if not _has_key_flows(db, disc):
        return
    raise ValueError(
        '这个标的的流水一条都没挂到这条持仓上（悬空流水）：据此重算会把持仓当成空壳行删掉。'
        '请先去「修正数据」把这批流水回补到这条持仓，再回来重算'
    )


def recompute_discrepancy_shares(
    db: Session,
    family_id: int,
    disc: ReconciliationDiscrepancy | None,
    *,
    reason: str | None = None,
    operator=None,
) -> dict:
    """按持仓名下的流水重算份额，并重跑对账返回最新差额。

    标的以**差异行**为准（与「以此为准」同一约定）：payload 里的 symbol / ledger_id 不参与
    定位，前端传错也不会改到别的标的。审计由 `recompute_with_audit` 写一条
    `action='position_recompute'`（带 discrepancy_id），本函数不重复记。
    """
    if disc is None:
        raise ValueError('按流水重算份额必须指定一条差异')
    position = _find_existing_position(db, disc.ledger_id, family_id, disc.symbol or '', '')
    if position is None:
        raise ValueError(
            '这条差异找不到对应持仓：可能已被删除或归到了别的账本。若持仓行确实没了，先去「修正数据」按流水重建持仓'
        )
    _assert_flows_support_position(db, position)
    _assert_same_flow_set(db, position, disc)

    result = recompute_with_audit(
        db,
        family_id,
        position.id,
        reason=reason or DEFAULT_REASON,
        operator=operator,
        discrepancy_id=disc.id,
        run_id=disc.last_run_id,
    )
    return {
        'action': 'recompute',
        'before': {'discrepancy_id': disc.id, 'symbol': disc.symbol, 'ledger_id': disc.ledger_id},
        'after': {
            'position_id': result['position_id'],
            'symbol': result['symbol'],
            'quantity': result['quantity_after'],
            'avg_price': result['avg_price_after'],
            'ownership_status': result['ownership_status_after'],
        },
        'log_id': result['log_id'],
        'recompute': result,
        # 复用同一份「补录完算不算平」判定：真正轧平才 cleared，否则仍留在队列里
        'discrepancy': recompute_linked_discrepancy(db, family_id, disc),
    }
