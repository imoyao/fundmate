# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/9
# File : symbol_scope.py
# app/services/symbol_scope.py
"""按 symbol 匹配「同一产品」的查询口径（单一真相源）。

**为什么单独成模块**：「这个 symbol 指的是不是同一个标的」在两处必须完全一致——

- 持仓列表（#1966 详情页「我的持仓」，`position_service.build_position_list`）；
- 产品级持有年化（#1972 XIRR `scope=symbol`，`performance.calculators.calculate_symbol_xirr`）。

两边各写一份匹配逻辑，迟早漂移成「列表里有三行、年化只算了两行」这种自相矛盾的详情页，
故把判定收口到这里，两处都从这里取。

**匹配口径**（沿用 #1662 的归一身份键，说明原样迁自 `build_position_list`）：

- 字面量 `Position.symbol == symbol` 直配；
- 再并上三种 venue 的 `symbol_norm` 归一候选——实测**不传 venue** 时
  `symbol_identity('SZ000001')` 与 `symbol_identity('000001.SZ')` 分别得到
  `NO_VENUE:SZ000001` 与 `NO_VENUE:000001.SZ`——并不等价；只有传 `venue='EXCHANGE'`
  才双双归一为 `EXCHANGE:SZ000001`。而持仓行的 `symbol_norm` 是**写入时**按当时的
  asset_type / venue 算的，彼此可能不同，故一次把三种候选都列进 WHERE：
  多一个 OR 索引，远便宜于漏命中导致详情页显示「无持仓」。
"""

from typing import Iterable, List, Set

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.symbol_utils import symbol_identity
from app.domains.positions.models import Position


def build_position_symbol_conditions(symbol: str) -> list:
    """构造「同一产品」的持仓匹配条件：字面量 + 三种 venue 的归一身份键。

    归一不了（异常）时退化为纯字面量匹配，不阻断查询——宁可少命中几行写法变体，
    也不该让整个区块因为一次归一失败而报错。
    """
    conditions = [Position.symbol == symbol]
    try:
        identities = {
            symbol_identity(symbol),
            symbol_identity(symbol, venue='EXCHANGE'),
            symbol_identity(symbol, venue='OTC'),
        }
    except Exception:  # noqa: BLE001 — 归一失败不应让查询整体失败
        identities = set()
    conditions += [Position.symbol_norm == ident for ident in identities if ident]
    return conditions


def query_positions_by_symbol(db: Session, symbol: str, family_id: int = 1) -> List[Position]:
    """取该产品在**全部账户**下的持仓行。

    **不过滤数量**：清仓（`quantity=0`）的历史持仓没有市值，但它名下的买卖 / 分红流水
    仍是「持有年化」的现金流，这里滤掉会让已清仓产品的 XIRR 凭空变成 0。市值口径由
    调用方自行按 `quantity > 0` 收敛。
    """
    return (
        db.query(Position).filter(Position.family_id == family_id, or_(*build_position_symbol_conditions(symbol))).all()
    )


def collect_transaction_symbol_variants(symbol: str, positions: Iterable[Position]) -> Set[str]:
    """该产品在 `transactions.symbol`（字面量快照）里可能出现的写法集合。

    **为什么不能在 SQL 里归一**：`transactions` 表只有字面量 `symbol` 快照，
    没有 `symbol_norm` 列（#1662 的归一身份键只落在 `positions` 上）。故改走「两步法」
    （数据策略硬约束 §3 的应用层两步读）：先用持仓侧的归一匹配拿到**真实写法**，
    再用它们对交易表做 `IN`。交易与持仓共用同一份写法——写入侧建流水时按
    `Transaction.symbol == position.symbol` 对齐（见 `domains/positions/views.py`）。

    原始 `symbol` 参数本身也保留在集合里：产品已清仓、持仓行数量归零或写法变体
    未被归一命中时，它仍是交易表里最可能的写法。
    """
    variants: Set[str] = {symbol}
    variants.update(p.symbol for p in positions if p.symbol)
    return variants
