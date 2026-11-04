# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/24
# File : scope.py
# backend/app/services/scope.py

"""持仓作用域解析 —— family / ledger / portfolio 三级口径的唯一出口（#2595）。

背景：分析类端点（穿透 / 归因 / 超额 …）陆续要求「全家庭 / 单账户 / 组合」
三级视图。此前组合级解析内联在 `pnl_calendar.compute_range_attribution`
（#2135），若后续端点各自手写成员账本查询，口径一旦漂移会直接破坏
「Σ 账户 ≡ 家庭」的可加性。本模块把解析规则收敛成唯一函数，任何
「按 scope 取持仓」的调用方都必须委托这里，**禁止再手写**。

组合口径与 `portfolio_service.build_portfolio_holdings` 的两路径一致：
**显式归属覆盖继承** —— 持仓 `positions.portfolio_id` 显式指定时优先生效；
未显式指定（None）时继承所属账户的默认组合（`Ledger.portfolio_id`）。

错误约定：参数冲突 / 组合不存在 / 组合非本家庭，一律抛 `ValueError`，
由视图层映射 400（文案与 #2135 相同，不新增错误信封形态）。
"""

from __future__ import annotations

from typing import Optional, Sequence, Set, TypeVar

from sqlalchemy.orm import Session

from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio

# 任意带 `portfolio_id` / `ledger_id` 属性的持仓对象（生产路径即 Position；
# 泛型化是为了让本模块不依赖具体模型、纯按鸭子类型过滤，便于测试造数）。
_T = TypeVar('_T')

ERR_MUTEX = 'ledger_id 与 portfolio_id 互斥'
ERR_NO_PORTFOLIO = '投资组合不存在'


def _member_ledger_ids(db: Session, family_id: int, portfolio_id: int) -> Set[int]:
    """组合成员账本 id 集合（`Ledger.portfolio_id` 显式挂靠）。"""
    return {
        row[0]
        for row in db.query(Ledger.id).filter(Ledger.portfolio_id == portfolio_id, Ledger.family_id == family_id).all()
    }


def _ensure_portfolio(db: Session, family_id: int, portfolio_id: int) -> None:
    """组合必须存在、未删除且属于本家庭，否则抛 `ValueError`（视图转 400）。"""
    portfolio = (
        db.query(Portfolio)
        .filter(Portfolio.id == portfolio_id, Portfolio.is_deleted.is_(False), Portfolio.family_id == family_id)
        .first()
    )
    if not portfolio:
        raise ValueError(ERR_NO_PORTFOLIO)


def member_ledger_ids(db: Session, family_id: int, portfolio_id: int) -> Set[int]:
    """组合成员账本 id 集合（含组合存在性 / 归属校验，校验失败抛 `ValueError`）。

    ⚠️ 这是「组合有哪些账本」的唯一出口：任何按组合取数的调用方都走这里，别各自
    `query(Ledger).filter(portfolio_id=...)` —— 少写一次 family 校验，别人家的
    `portfolio_id` 就能取到数据。

    注意与 :func:`filter_positions_by_scope` 的差别：持仓有「显式归属覆盖继承」
    两个维度（`positions.portfolio_id` / `ledger.portfolio_id`），而**只挂在账本上的
    实体**（交易流水等，表里没有 portfolio_id 字段）只有继承这一个维度，
    组合级就是本集合。别把持仓那套语义硬套到资金流上。
    """
    _ensure_portfolio(db, family_id, portfolio_id)
    return _member_ledger_ids(db, family_id, portfolio_id)


def filter_positions_by_scope(
    db: Session,
    family_id: int,
    positions: Sequence[_T],
    *,
    ledger_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
) -> list[_T]:
    """按三级口径过滤持仓列表（返回新列表，不改入参顺序）。

    Args:
        db: 数据库会话（仅组合级需要查账本/组合表；family / ledger 级纯内存过滤）。
        family_id: 家庭 ID（组合归属校验维度）。
        positions: 待过滤持仓（通常为家庭全量 active 持仓）。
        ledger_id: 账户级口径；与 `portfolio_id` 互斥。
        portfolio_id: 组合级口径；与 `ledger_id` 互斥。

    Returns:
        过滤后的持仓列表。family 级（两参数均空）原样返回。

    Raises:
        ValueError: 两参数同时传（`ERR_MUTEX`）或组合不存在 / 非本家庭
            （`ERR_NO_PORTFOLIO`）。
    """
    if ledger_id is not None and portfolio_id is not None:
        raise ValueError(ERR_MUTEX)

    if ledger_id is not None:
        return [p for p in positions if p.ledger_id == ledger_id]

    if portfolio_id is not None:
        member_ids = member_ledger_ids(db, family_id, portfolio_id)
        # 显式归属覆盖继承，与 portfolio_service.build_portfolio_holdings 口径一致。
        return [
            p
            for p in positions
            if p.portfolio_id == portfolio_id or (p.portfolio_id is None and p.ledger_id in member_ids)
        ]

    return list(positions)


def resolve_scope_label(ledger_id: Optional[int], portfolio_id: Optional[int]) -> str:
    """三级口径的出参标签（与 benchmark_excess / pnl_calendar 的 scope 字段同枚举）。"""
    if portfolio_id is not None:
        return 'portfolio'
    if ledger_id is not None:
        return 'ledger'
    return 'family'
