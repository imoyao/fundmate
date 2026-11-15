# -*- coding: utf-8 -*-
"""「按流水重算」的两个入口侧职能（#3127）：份额一致性检查 + 带审计的手动重算。

为什么单独一个模块：``dangling_ref_service.py``（587 行）与 ``position_recompute.py``
（200 行）都被 ``guard_service_size.py`` 按存量基线冻结、**只减不增**——把它们变厚是最容易
犯的错（新增注释就能顶破）。新职能放新文件，原模块只留一行调用。

两件事的共同点：都以 ``compute_anchored_state``（份额派生的**唯一**入口）为准，
不同点是前者只读、后者写库并留审计。
"""

import json

from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.reconciliation.models import AdjustmentLog

# 份额差异判定阈值（份）：与 dangling 检出的 ``net_mismatch`` 同量级，只用于区分浮点噪声。
SHARE_EPSILON = 0.0001


def _anchored(db: Session, position: Position) -> tuple[int, int]:
    """取「锚点感知」的份额与成本（函数内导入，避免与 position_service 成环）。"""
    from app.services.position_service import compute_anchored_state  # noqa: PLC0415

    return compute_anchored_state(db, position)


def share_check(db: Session, target: Position, quantity_now: float) -> dict:
    """挂回后「持仓份额 vs 按现有流水派生」的差异（**只读**，不改任何值）。

    回补按契约只改归属、不重算份额，于是「挂回后份额是否仍与流水自洽」没有任何人回答
    ——#3127 真库 95 条幽灵持仓就是这么来的：买入腿先建成 270 张，卖腿补码挂回，份额不动。

    判据必须走 ``compute_anchored_state`` 而不是自己求和：有锚点的持仓，锚点前流水本来就
    不计入份额，自己算会造出一堆假差异（把合法挂回报成「份额错了」）。
    """
    net_units, _ = _anchored(db, target)
    expected = Money.min_unit_to_shares(net_units)
    diff = round(expected - quantity_now, 4)
    suggested = abs(diff) > SHARE_EPSILON
    return {
        'quantity_now': quantity_now,
        'quantity_if_recomputed': expected,
        'diff': diff,
        'recompute_suggested': suggested,
        'hint': (
            f'挂回只改归属、不改份额：按现有流水派生应为 {expected:g} 份，当前持仓 {quantity_now:g} 份'
            f'（差 {diff:+g}）。若要以此为准，请用「按流水重算份额」对齐；本接口不会自动改。'
        )
        if suggested
        else None,
    }


def reattach_payload(
    db: Session, log, target: Position, updated: int, quantity_before: float, quantity_after: float
) -> dict:
    """回补接口的返回体（含 ``share_check``）。

    独立成函数有两个理由：返回体是**契约**，集中一处好核对；``reattach_transactions``
    的函数体已被体量守卫冻结（max_func），返回体留在里面会把指标顶破。
    """
    return {
        'log_id': log.id,
        'updated': updated,
        'recompute': False,
        'quantity_before': quantity_before,
        'quantity_after': quantity_after,
        'share_check': share_check(db, target, quantity_after),
    }


def recompute_with_audit(
    db: Session,
    family_id: int,
    position_id: int,
    *,
    reason: str | None = None,
    operator=None,
    discrepancy_id: int | None = None,
    run_id: int | None = None,
) -> dict:
    """按流水重算某条持仓的份额，并把「改前 / 改后」写进审计日志（#3127 的补救入口）。

    WHY 需要单独一个入口：回补关联按契约**只改归属、不重算份额**，而 docstring 一直写着
    「如需对齐份额，到持仓页手动重算」——但持仓域从来没有这个路由，脏数据一旦产生无路可修。
    真库 2026-11-15 实测 104 条「卖完未清仓」（95 条由重建造出，虚增市值 ≈64 万元）。

    语义完全复用 ``recompute_from_transactions``（同一派生入口、同一清仓 / 删行判据），
    本函数只多做两件事：取改前快照、写 ``adjustment_logs``。审计动作名用
    ``position_recompute``，与悬空流水那条链路的 ``dangling_ref_*`` 同族。

    返回里 ``deleted`` 为真表示「无流水且无锚点 ⇒ 空壳行被删」，此时 ``quantity_after`` 记 0
    ——调用方要让用户看到这件事，不能只报成功。

    ``discrepancy_id`` / ``run_id`` 只有对账工作台会传（#3134）：从差异卡点「按流水重算份额」时，
    审计要能回指是哪条差异、哪一轮对账触发的，否则复盘时只能凭时间猜。
    """
    from app.services.position_recompute import recompute_from_transactions  # noqa: PLC0415

    pos = db.query(Position).filter_by(id=position_id, family_id=family_id).first()
    if pos is None:
        raise ValueError(f'持仓 {position_id} 不存在或不属于当前家庭')

    # 改前快照：份额按「份」、均价按「元」，与接口对外单位一致（内部一律最小单位整数）。
    before = {
        'quantity': Money.min_unit_to_shares(pos.quantity),
        'avg_price': Money.price_units_to_yuan(pos.avg_price),
        'ownership_status': pos.ownership_status,
        'symbol': pos.symbol,
    }

    recompute_from_transactions(db, position_id)

    after_row = db.query(Position).filter_by(id=position_id, family_id=family_id).first()
    deleted = after_row is None
    after = {
        'quantity': 0.0 if deleted else Money.min_unit_to_shares(after_row.quantity),
        'avg_price': 0.0 if deleted else Money.price_units_to_yuan(after_row.avg_price),
        'ownership_status': 'deleted' if deleted else after_row.ownership_status,
    }

    log = AdjustmentLog(
        family_id=family_id,
        discrepancy_id=discrepancy_id,
        run_id=run_id,
        action='position_recompute',
        before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(after, ensure_ascii=False),
        reason=reason,
        operator=operator,
    )
    db.add(log)
    db.flush()

    return {
        'log_id': log.id,
        'position_id': position_id,
        'symbol': before['symbol'],
        'deleted': deleted,
        'changed': deleted
        or abs(after['quantity'] - before['quantity']) > SHARE_EPSILON
        or after['ownership_status'] != before['ownership_status'],
        'quantity_before': before['quantity'],
        'quantity_after': after['quantity'],
        'avg_price_before': before['avg_price'],
        'avg_price_after': after['avg_price'],
        'ownership_status_before': before['ownership_status'],
        'ownership_status_after': after['ownership_status'],
    }
