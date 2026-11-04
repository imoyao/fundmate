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
from app.domains.transactions.models import Transaction
from app.services.position_scope import exclude_shadow


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


def build_transaction_symbol_conditions(symbol: str) -> list:
    """构造「同一产品」的流水匹配条件：字面量 + 三种 venue 的归一身份键。

    与 `build_position_symbol_conditions` 同构，用途是把两边的口径钉在同一套判据上。

    ## 为什么流水侧此前只能「两步法」

    本模块原先写着「`transactions` 表没有 `symbol_norm` 列，故先在持仓侧做归一匹配拿到
    真实写法，再对交易表做 `IN`」（`collect_transaction_symbol_variants`）。两步法的
    前提是「持仓与流水的 symbol 写法一致」——而它**恰恰不成立**：本机实测持仓是裸码
    `001937`、流水是 `SZ001937`，两步法拿到 `001937` 后对流水 `IN` 一条也命中不了。

    现 `transactions.symbol_norm` 已由迁移回填、并由 mapper 事件在写入时保证，
    两侧可以直接在同一列上做同等判定。

    ## 为什么仍要 OR 上字面量

    两个理由，都不是冗余：

    - 迁移前写入的 `NO_VENUE:` 降级行（`asset_type` 当时为空的现金/边角流水）；
    - 调用方传入的 symbol 可能本身就是流水里的写法变体（如 `00700.HK` 与 `HK00700`），
      此时三种 identity 已能覆盖；但若传入值与某行的字面量恰好相等，直配零成本且更直观。

    「多一个 OR，远便宜于漏命中」——与 positions 版同一条取舍。
    """
    conditions = [Transaction.symbol == symbol]
    try:
        identities = {
            symbol_identity(symbol),
            symbol_identity(symbol, venue='EXCHANGE'),
            symbol_identity(symbol, venue='OTC'),
        }
    except Exception:  # noqa: BLE001 — 归一失败不应让查询整体失败
        identities = set()
    conditions += [Transaction.symbol_norm == ident for ident in identities if ident]
    return conditions


def query_positions_by_symbol(db: Session, symbol: str, family_id: int = 1) -> List[Position]:
    """取该产品在**全部账户**下的持仓行（**不含 E账户对账镜像行**）。

    **不过滤数量**：清仓（`quantity=0`）的历史持仓没有市值，但它名下的买卖 / 分红流水
    仍是「持有年化」的现金流，这里滤掉会让已清仓产品的 XIRR 凭空变成 0。市值口径由
    调用方自行按 `quantity > 0` 收敛。

    **过滤 `shadow`（2026-10-28）**：镜像行是「E账户说有、系统还没认领」的待核对项，
    不是持仓。它没有自己的流水，却带着一份与真身等量的 `quantity`——留在结果里会让
    期末市值翻倍（本地库实测 021180：真身 3,421.9622 份 + 镜像 3,421.96 份），
    直接把产品级持有年化算歪。这里只排 `shadow`、不动 `cleared`，理由见
    `services/position_scope.exclude_shadow`。
    """
    return exclude_shadow(
        db.query(Position).filter(Position.family_id == family_id, or_(*build_position_symbol_conditions(symbol)))
    ).all()


def collect_transaction_symbol_variants(symbol: str, positions: Iterable[Position]) -> Set[str]:
    """该产品在 `transactions.symbol`（字面量快照）里可能出现的写法集合。

    **⚠️ 已被 `build_transaction_symbol_conditions` 取代，新代码不要再走两步法。**

    历史原因：`transactions` 表此前只有字面量 `symbol` 快照，没有 `symbol_norm` 列
    （#1662 的归一身份键只落在 `positions` 上），故只能在应用层先用持仓侧的归一匹配
    拿到「真实写法」，再对交易表做 `IN`。而这一步的前提「持仓与流水写法一致」
    **恰恰不成立** —— 本机实测持仓 `001937`、流水 `SZ001937`，两步法对交易表
    `IN ('001937')` 一条也命中不了，正是本卡要修的那个漏算。

    现 `transactions.symbol_norm` 已具备（迁移回填 + 写入时 mapper 事件保证），
    调用方应直接用 `build_transaction_symbol_conditions`。本函数**暂时保留**给
    尚未迁移的调用方，其返回值仍包含原始 `symbol`（产品已清仓、写法变体未命中时的兜底）。
    """
    variants: Set[str] = {symbol}
    variants.update(p.symbol for p in positions if p.symbol)
    return variants
