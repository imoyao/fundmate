# -*- coding: utf-8 -*-
"""持仓流水的**读侧**口径：按身份键取数（#3004 从 ``position_display`` 拆出）。

## 为什么单独一个模块

``position_display.py`` 已经贴着 services 体量闸门（``scripts/guard_service_size.py``）的
基线，而「某持仓的流水应该取哪些行」是**独立的读侧契约**——持仓抽屉、删除持仓前的
清理、以及将来任何按持仓看流水的地方都必须共用同一套判据，否则「列表里看得见、
按持仓查却看不见」这类自相矛盾会反复出现。

## 判据

- 身份键：``(ledger_id, symbol 各写法)``——``account_name`` 是可编辑快照，不能做键
  （重名账户会把别人的交易卷进来，见 #2372）；
- 优先 ``position_id``（历史行大多有它），但**必须**并上同身份的孤儿行
  （``position_id IS NULL``）：卖出降级成孤儿后，抽屉里看不到它，用户以为「只有买入」；
- 只并孤儿，不外扩到「同身份的其它持仓行」——同一 symbol 可能存在重复持仓（历史脏数据），
  把别人的行拉进来会变成多算。孤儿无主，归到本持仓是唯一合理归属。
"""

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.symbol_scope import build_transaction_symbol_conditions
from app.services.transaction_service import order_by_effective_day


def identity_conditions(position: Position) -> list:
    """身份键的**列条件**：``[or_(symbol 各写法), ledger_id 条件]``，AND 起来即身份相等。

    ⚠️ ``build_transaction_symbol_conditions`` 返回的是**同一字段的多个写法变体**
    （字面量 + 三种 venue 身份键），只能 ``or_``；把它们直接 AND 进去会要求
    ``symbol_norm`` 同时等于三个值 → 一行都查不到。
    """
    conditions = [or_(*build_transaction_symbol_conditions(position.symbol))]
    conditions.append(
        Transaction.ledger_id == position.ledger_id
        if position.ledger_id is not None
        else Transaction.ledger_id.is_(None)
    )
    return conditions


def query_transactions_by_identity(db: Session, position: Position):
    """按身份键构造流水查询：``(ledger_id, symbol)``，未归档持仓只匹配未归档流水。

    ``ledger_id`` 为 NULL（未归档持仓 / 探市迁移行）时只匹配同属未归档的流水——
    宁可少查，也不拿名字去猜（猜错的表现是明细里混入别人账户的交易，且不会报错）。
    """
    return db.query(Transaction).filter(and_(*identity_conditions(position)))


def list_position_transactions(db: Session, position: Position) -> list[Transaction]:
    """某持仓的交易流水（持仓抽屉数据源）。

    有 ``position_id`` 命中的行时返回「自己的行 ∪ 同身份孤儿」；一条都没有时退回
    全量身份键查询（#2372 旧兜底，覆盖「流水压根没挂过 position_id」的历史数据）。
    排序统一走 ``order_by_effective_day``（#2712）。
    """
    if position.id:
        has_own_rows = db.query(Transaction.id).filter(Transaction.position_id == position.id).first()
        if has_own_rows is not None:
            return order_by_effective_day(
                db.query(Transaction).filter(
                    or_(
                        Transaction.position_id == position.id,
                        and_(Transaction.position_id.is_(None), *identity_conditions(position)),
                    )
                )
            ).all()
    return order_by_effective_day(query_transactions_by_identity(db, position)).all()
