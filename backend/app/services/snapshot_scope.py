# -*- coding: utf-8 -*-
"""资产快照的三级口径（家庭 / 账户 / 组合）——读写两侧的唯一出口（D135）。

## 为什么组合档净值曲线走快照表，而不是走 as-of 引擎

`pnl_calendar` 的 `net_worth` 能算组合档（D134），但它是**现算**的：真库实测
组合 #1 全周期（1063 天）一次派生 **7.83s**，而 `get_snapshots` 读同规模序列
只要 **240ms**。每天打开页面为一张曲线付 8 秒不可接受，且同页的收益日历已经在
付这笔钱。故组合档补**快照维度**，与家庭 / 账户档共用一条读路径。

## 口径差：组合行只含持仓市值（不是 bug）

通用资产（房产 / 负债 / 现金）与孤儿货基流水都只挂在**账户**上，没有组合归属
（组合的归属规则见 `services/scope.py`：显式 `positions.portfolio_id` 覆盖
账户继承）。故：

    Σ组合持仓市值 ≤ Σ账户市值 ≤ 家庭总资产

差额是「不属于任何组合的东西」，不是漏算。组合行的 `total_liabilities` 恒 0
（持仓不可能是负债）。

## 历史从启用日起累积（D62 的直接后果）

`asset_snapshots` 记的是「**落库那一刻**」的当前状态，**禁止回填**（D62：回填等于
把今天的值贴到历史日期上）。所以组合曲线只能从首次写入那天长起，与 #1181 账户档
当年的处境相同。前端必须显式说明这一点，不能让用户以为曲线断了。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Query, Session

from app.core.constants import EXCHANGE_RATES
from app.domains.portfolios.models import Portfolio
from app.domains.positions.models import Position
from app.domains.summary.models import AssetSnapshot
from app.services.nav_service import NavService
from app.services.position_valuation import market_value_cents
from app.services.scope import ERR_MUTEX, filter_positions_by_scope

#: 需要注入「库内最新净值」的资产类型（与 `summary_service._per_ledger_buckets` 同源）
_NAV_ASSET_TYPES = ('fund', 'money_fund')


def apply_snapshot_scope(
    query: Query,
    ledger_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
) -> Query:
    """按档位过滤 `AssetSnapshot` 查询。

    家庭档（两参数皆空）= `ledger_id IS NULL AND portfolio_id IS NULL`：三级行
    共存一张表，只有两个维度都为空的才是家庭行，否则同一天的账户 / 组合行会与
    家庭行混进同一条走势被重复计算。

    Raises:
        ValueError: 两参数同时传（`scope.ERR_MUTEX`），由视图映射 400。
    """
    if ledger_id is not None and portfolio_id is not None:
        raise ValueError(ERR_MUTEX)
    if portfolio_id is not None:
        return query.filter(AssetSnapshot.portfolio_id == portfolio_id)
    # 家庭 / 账户档：组合维度必须为 NULL，否则同日的组合行会混进同一条走势
    query = query.filter(AssetSnapshot.portfolio_id.is_(None))
    if ledger_id is not None:
        return query.filter(AssetSnapshot.ledger_id == ledger_id)
    return query.filter(AssetSnapshot.ledger_id.is_(None))


def upsert_snapshot(
    db: Session,
    *,
    family_id: int,
    snapshot_date,
    ledger_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
) -> AssetSnapshot:
    """按 (family_id, ledger_id, portfolio_id, snapshot_date) 幂等 upsert 一条快照。

    唯一键用 `COALESCE(ledger_id, -1) + COALESCE(portfolio_id, -1)` 落哨兵，
    故 NULL 也参与去重——同一天重复写入是覆盖而非新增（#1181 / D135）。
    """
    q = db.query(AssetSnapshot).filter(
        AssetSnapshot.family_id == family_id, AssetSnapshot.snapshot_date == snapshot_date
    )
    row = apply_snapshot_scope(q, ledger_id, portfolio_id).first()
    if row is None:
        row = AssetSnapshot(
            family_id=family_id,
            ledger_id=ledger_id,
            portfolio_id=portfolio_id,
            snapshot_date=snapshot_date,
        )
        db.add(row)
    return row


def portfolio_totals(db: Session, family_id: int, positions=None) -> dict[int, int]:
    """{portfolio_id: 持仓市值（分）}——组合级快照行的唯一取数口径。

    `positions` 可传入已加载的 active 持仓复用查询；不传则自行加载（**排除**
    E账户镜像行：镜像行 `ownership_status='shadow'`，已被 active 过滤排掉）。

    归属过滤一律委托 `scope.filter_positions_by_scope`（显式覆盖继承），本函数
    不重复实现归属规则——两条实现迟早漂移，而漂移的表现是「组合余额与组合详情页
    对不上」，肉眼极难发现。
    """
    if positions is None:
        positions = (
            db.query(Position).filter(Position.family_id == family_id, Position.ownership_status == 'active').all()
        )
    symbols = [p.symbol for p in positions if p.symbol and p.asset_type in _NAV_ASSET_TYPES]
    latest_navs = NavService.get_latest_navs(db, symbols, allow_remote=False) if symbols else {}
    portfolio_ids = [
        row[0]
        for row in db.query(Portfolio.id)
        .filter(Portfolio.family_id == family_id, Portfolio.is_deleted.is_(False))
        .all()
    ]
    totals: dict[int, int] = {}
    for pid in portfolio_ids:
        cents = 0
        for p in filter_positions_by_scope(db, family_id, positions, portfolio_id=pid):
            rate = EXCHANGE_RATES.get(p.currency, 1.0)
            nav = latest_navs.get(p.symbol) if (p.symbol and p.asset_type in _NAV_ASSET_TYPES) else None
            cents += market_value_cents(p, rate=rate, effective_nav_yuan=nav)
        totals[pid] = cents
    return totals
