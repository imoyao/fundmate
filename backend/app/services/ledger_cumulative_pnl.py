# -*- coding: utf-8 -*-
"""账户级「累计盈亏」三段口径的唯一实现（2026-11-10）。

口径与首页「累计总收益」、账户资产快照同源（#1220）::

    累计盈亏 = 已实现盈亏 + 持仓浮盈 − 买入费

## 为什么已实现与买入费必须走流水级

清仓后持仓行会被删除（或 ``ownership_status`` 变为 ``cleared``），而流水还在。若先按
``position_id`` 归集，再按 ``position.ledger_id`` 汇总，那些「已经卖光」的持仓的已实现
盈亏会凭空消失——账户级漏已实现，等于把亏损藏起来。家庭级 ``family_realized_pnl_cents``
早就直接扫流水，账户级此前没有。

## 为什么单独成文件

``scripts/guard_service_size.py`` 把 ``backend/app/services/**`` 的存量文件体量冻结为
「只减不增」，``pnl_service`` / ``pnl_fees`` / ``ledger_service`` / ``summary_service``
四个文件的基线都贴着实测值，新逻辑挤进去必判红；本文件是**新增**文件，按
``NEW_FILE_LIMITS``（≤800 行 / 单函数 ≤120 / 圈复杂度 ≤20）判。

## 依赖方向

本模块**必须是叶子**（只依赖 core 与 models）：``summary_service`` 要 import 它，而
``ledger_service`` 又 import ``summary_service``，反向依赖会成环。
"""

from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.transactions.models import Transaction

# 买入侧手续费：卖出费已在 `realized_pnl` 里扣过，再收一次就是双计（口径同 pnl_fees）
FEE_TXN_TYPES = ('buy', 'deposit')


def realized_pnl_by_ledger(db: Session, family_id: int, ledger_ids: Optional[List[int]] = None) -> dict[int, int]:
    """按**账户**归集的已实现盈亏（分）。

    与 ``pnl_service.realized_pnl_by_position`` 的区别不只是分组键，而是**取数层级**：
    本函数直接扫流水，不经过持仓表——清仓后持仓行会被删除，按持仓归集会让那笔已实现
    凭空消失（理由见模块 docstring）。

    孤儿流水（``ledger_id`` 为 NULL）归哨兵键 0，与 position 级同款。
    ``ledger_ids`` 语义同 ``realized_pnl_by_position``：``None`` = 全家庭，``[]`` = 空表。
    """
    query = db.query(Transaction.ledger_id, func.sum(Transaction.realized_pnl)).filter(
        Transaction.family_id == family_id
    )
    if ledger_ids is not None:
        query = query.filter(Transaction.ledger_id.in_(ledger_ids))
    rows = query.group_by(Transaction.ledger_id).all()
    return {(lid or 0): int(total or 0) for lid, total in rows}


def buy_fee_by_ledger(db: Session, family_id: int, ledger_ids: Optional[List[int]] = None) -> dict[int, int]:
    """按**账户**归集的买入侧手续费（分，正数），口径同 ``pnl_fees.buy_fee_by_position``。

    必须与 :func:`realized_pnl_by_ledger` 保持同一取数层级（都扫流水），否则
    ``total = realized + unrealized − buy_fee`` 在「有清仓历史」的账户上会对不上，
    且差额无从解释。
    """
    query = db.query(Transaction.ledger_id, func.sum(Transaction.fee)).filter(
        Transaction.family_id == family_id,
        Transaction.txn_type.in_(FEE_TXN_TYPES),
    )
    if ledger_ids is not None:
        query = query.filter(Transaction.ledger_id.in_(ledger_ids))
    rows = query.group_by(Transaction.ledger_id).all()
    return {(lid or 0): int(total or 0) for lid, total in rows if total}


def attach_cumulative_pnl(
    item: dict,
    realized_pnl_cents: int,
    buy_fee_cents: int,
    unrealized_yuan: float | None = None,
) -> dict:
    """给账户字典附加「累计盈亏」三段（字段单位：元，两位小数）。

    未实现默认取 ``item['pnl']``——也就是这张卡上方**已经展示**的那个持仓盈亏——而不是
    从持仓再算一遍：同一屏两个浮盈数字哪怕只差一分，用户就会怀疑整张卡；后端两套口径
    某天各自演化时，谁也说不清哪个才对。详情页的字段叫 ``position_pnl``，故留
    ``unrealized_yuan`` 让调用方显式传入同一个数。

    调用方须先判账户类型：bank / property 没有这套口径（bank 的成本基数是流水净投入，
    与卡片上的「市值 − 成本」不是一回事），不调本函数即不下发这三个键——写 0 会被读成
    「不赚不亏」，比不显示更误导。
    """
    realized = Money.cents_to_yuan(int(realized_pnl_cents or 0))
    buy_fee = Money.cents_to_yuan(int(buy_fee_cents or 0))
    base = item.get('pnl') if unrealized_yuan is None else unrealized_yuan
    item['realized_pnl'] = realized
    item['buy_fee'] = buy_fee
    # 三者都是两位小数，但浮点相加会长尾（0.1 + 0.2），故统一 round 回两位
    item['total_pnl'] = round((base or 0.0) + realized - buy_fee, 2)
    return item
