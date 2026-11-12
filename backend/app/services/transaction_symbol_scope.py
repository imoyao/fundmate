# -*- coding: utf-8 -*-
"""多标的的流水身份匹配：把「N 个标的 × 4 个等式」的 OR 链折叠成两列 IN。

**WHY**：`DataProvider.trades(symbols=...)` 曾把每个标的经
`symbol_scope.build_transaction_symbol_conditions` 得到的 4 个等式（1 个字面量 +
3 种 venue 的 `symbol_norm` 身份键）展平进**同一个** `or_()`。本机 265 行持仓
→ 1060 个 OR 项，超过 SQLite `SQLITE_MAX_EXPR_DEPTH=1000`，
`GET /api/strategy/engine/behavior/` 于 2026-11-12 17:03 直接 500。

按布尔分配律，`⋁(symbol = s ∨ norm ∈ I(s))` 等价于
`symbol ∈ ⋃{s} ∨ norm ∈ ⋃I(s)`：两列各用 `IN`，表达式深度恒为 2，OR 项数不再
随标的数增长；集合去重还让参数数从 265×4=1060 降到 160+480=640（本机实况）。

**不假装防变量上限**：把多个 `IN` 塞进同一条语句并不减少总变量数——旧 SQLite
的 999 上限真要兼容，得像 `price_depth.first_transaction_dates` 那样**分多次查询**
再合并结果，而不是切几个 IN 制造「已经分块」的错觉。本机 SQLite 3.53.1 上限
32766、PG 65535，当前规模远未触及；若将来要落老构建，按上面的形态改。

**口径来源**：身份键候选与 `symbol_scope.build_transaction_symbol_conditions` 同源，
一致性由 `tests/services/strategy_engine/test_trades_symbol_scope.py` 钉住，避免
又长出一分漂移的实现（仓库里 `price_depth.first_transaction_dates` 已有一份）。
"""

from typing import Iterable

from sqlalchemy import ColumnElement, false, or_

from app.core.symbol_utils import symbol_identity
from app.domains.transactions.models import Transaction


def symbol_identity_candidates(symbol: str) -> set[str]:
    """单标的的三种 venue 身份键；归一失败时降级为空集（与单标的版同款取舍）。"""
    try:
        return {
            ident
            for ident in (
                symbol_identity(symbol),
                symbol_identity(symbol, venue='EXCHANGE'),
                symbol_identity(symbol, venue='OTC'),
            )
            if ident
        }
    except Exception:  # noqa: BLE001 — 归一失败不应让整个查询失败
        return set()


def build_transaction_scope(symbols: Iterable[str]) -> ColumnElement[bool]:
    """多标的流水的 WHERE 条件：`symbol IN (...) OR symbol_norm IN (...)`。

    两列各一个 `IN`：先去重再排序，参数不随重复持仓膨胀、编译出的 SQL 可复现。
    空输入返回 `false()`：`or_()` 无参数会编译成空串，那等于「不过滤」，
    会把整个家庭的流水读回来——必须显式钉成不匹配任何行。
    """
    literals = {s for s in symbols if s}
    identities: set[str] = set()
    for symbol in literals:
        identities |= symbol_identity_candidates(symbol)

    conditions = []
    if literals:
        conditions.append(Transaction.symbol.in_(sorted(literals)))
    if identities:
        conditions.append(Transaction.symbol_norm.in_(sorted(identities)))
    return or_(*conditions) if conditions else false()
