# -*- coding: utf-8 -*-
# File : transaction_scope.py
# backend/app/services/transaction_scope.py

"""流水级三级口径过滤（family / ledger / portfolio）—— 组合档的唯一出口。

## 为什么不能直接按 ``transactions.ledger_id`` 过滤

``transactions`` 表里**没有** ``portfolio_id``：流水只能靠 ``position_id`` 归属到
持仓，再由持仓的「显式归属覆盖继承」规则落到组合上（与
``services/scope.filter_positions_by_scope`` 同一套语义）。按账户过滤历史流水，
等于把「组合」当成「组合成员账户的并集」——两处会静默分叉：

- 持仓显式指派到组合 P、但账本默认组合是 Q ⇒ 该持仓的流水按账户过滤会被漏掉；
- 持仓显式指派到别处的 Q、流水却记在 P 的成员账户里（#1916 的历史错配形态）
  ⇒ 按账户过滤会把别人的流水算进 P。

故组合档必须**逐笔判归属**，且判据与持仓侧同源。``services/scope.py`` 的模块
注释写明「只挂在账本上的实体（交易流水等）只有继承这一个维度」——那句话成立的
前提是「流水不属于任何持仓」。带 ``position_id`` 的流水属于持仓，就得走本模块。

## 归属判据（三条，按优先级）

1. 流水有 ``position_id``，且该持仓**显式**指定了 ``portfolio_id`` ⇒ 只认持仓，
   显式归属覆盖继承（``positions.portfolio_id`` 永远优先，见 D20 一期回归测试）；
2. 流水有 ``position_id``、持仓未显式指定 ⇒ 继承**持仓所在账户**的默认组合。
   用持仓的 ``ledger_id`` 而不是流水的——「持仓在 A、流水记在 B」时份额与已实现
   都按持仓归集（#1916），归属也必须跟着持仓走；
3. 无 ``position_id``（出入金、孤儿、类现金）⇒ 只能按流水自己的 ``ledger_id``。

## 错误约定

``ledger_id`` 与 ``portfolio_id`` 互斥、组合不存在 / 非本家庭，一律抛
``ValueError``（复用 ``scope.member_ledger_ids`` 的校验与文案），由视图层转 400。
"""

from __future__ import annotations

from typing import Optional, Sequence, TypeVar

from sqlalchemy.orm import Session

from app.domains.positions.models import Position
from app.services.scope import ERR_MUTEX, member_ledger_ids

_T = TypeVar('_T')


def filter_transactions_by_scope(
    db: Session,
    family_id: int,
    transactions: Sequence[_T],
    *,
    ledger_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
) -> list[_T]:
    """按三级口径过滤流水（返回新列表，保持入参顺序）。

    Args:
        db: 数据库会话（组合级需查持仓归属与成员账本；family / ledger 级纯内存过滤）。
        family_id: 家庭 ID（组合归属校验维度）。
        transactions: 待过滤流水（通常为家庭全量）。
        ledger_id: 账户级口径；与 ``portfolio_id`` 互斥。
        portfolio_id: 组合级口径；与 ``ledger_id`` 互斥。

    Raises:
        ValueError: 两参数同时传（``ERR_MUTEX``）或组合不存在 / 非本家庭。
    """
    if ledger_id is not None and portfolio_id is not None:
        raise ValueError(ERR_MUTEX)
    if portfolio_id is None:
        if ledger_id is None:
            return list(transactions)
        return [t for t in transactions if t.ledger_id == ledger_id]

    member_ids = member_ledger_ids(db, family_id, portfolio_id)
    # 一次取全家庭持仓归属（id → (显式组合, 所属账户)）：条数与持仓数同阶，
    # 逐笔查会退化成 N+1；`Position` 全量 select 反而比 `in_` 分批更省。
    owner = {
        row[0]: (row[1], row[2])
        for row in db.query(Position.id, Position.portfolio_id, Position.ledger_id)
        .filter(Position.family_id == family_id)
        .all()
    }

    def _belongs(t) -> bool:  # noqa: ANN001 — 鸭子类型：无需约束具体流水模型
        explicit, pos_ledger = owner.get(getattr(t, 'position_id', None), (None, None))
        if explicit is not None:
            return explicit == portfolio_id
        return (pos_ledger if pos_ledger is not None else t.ledger_id) in member_ids

    return [t for t in transactions if _belongs(t)]
