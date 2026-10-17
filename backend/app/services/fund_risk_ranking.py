# -*- coding: utf-8 -*-
"""按风险指标横向筛（#167 · 用户在 #167 认可的「按指标选基」）。

数据源只有一个：``fund_risk_metrics`` 快照表（**同类内排序**的分组键 `fund_type_id`
随行落库，见该表 docstring）。本模块不读净值、不现算——全市场逐只现算撑不起排序，
这也是当初把指标物化的理由。

## 排序口径：同类内，不做跨类榜

风险比跨类别不可比（债基波动 2%、股基 25%，夏普把波动当风险 ⇒ 债基系统性偏高）。
故榜单**必须**限定在一个 `fund_type_id` 内。`list_by_metric` 因此把 `fund_type_id`
列为**必填**——不做「不传就全市场排」的默认，那种默认会被误用成跨类榜，
而这正是用户担心的那件事。

## 口径版本

只取 `caliber_version == CALIBER_VERSION` 的行。旧口径的行留在库里；若一起进榜，
榜单看起来完全正常，但「两代口径混排」——比缺数据难发现得多（同
`fund_peer_rank` 的模块 docstring）。

## 榜单的降级纪律

- `basis != 'acc_nav'`（跳变污染 / 样本不足）的行**默认剔除**。「净值被份额折算污染」
  的基金算出来的夏普可能是全类第一，而那个数是假的——把它排进榜比漏掉它危险得多。
- 需要看被剔除的部分时传 `include_distorted=True`，返回值里逐条带 `basis`。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from sqlalchemy.orm import Session

# 允许排序的指标白名单。**白名单而非黑名单**：`as_of` / `sample_points` 这类列
# 可排序但作为榜单指标没有意义，黑名单迟早会漏。
SORTABLE_METRICS: Dict[str, bool] = {
    # 指标名 → 默认降序（True = 越大越好，即数值大者排前）
    'sharpe': True,
    'sortino': True,
    'calmar': True,
    'upi': True,
    'return_drawdown_ratio': True,
    'win_rate': True,
    'annual_return': True,
    'max_drawdown': True,  # 负数：越大越浅（-8 优于 -25）⇒ 降序
    'current_drawdown': True,  # 同上
    'annual_volatility': False,  # 正数：越小越好 ⇒ 升序
    'ret_1m': True,  # 区间收益（#2284）：越大越好 ⇒ 默认降序
    'ret_3m': True,
    'ret_1y': True,
}

DEFAULT_LIMIT = 20
MAX_LIMIT = 200


def _clamp_limit(limit: Optional[int]) -> int:
    if not limit or limit <= 0:
        return DEFAULT_LIMIT
    return min(int(limit), MAX_LIMIT)


def user_flags_for_codes(user_db: Session, *, family_id: Optional[int]) -> tuple:
    """查一个家庭的全部私有标记：``(持仓代码集, 自选代码集)``。

    **user 域**查询（positions / watchlist 与 funds 快照分属不同引擎，无跨域 JOIN），
    与 ``product_identity.resolve_product_identity`` 的私有状态查询同模式；
    口径与 ``fund_risk_metrics_job._codes_from_user_scope``（快照目标池）同源——
    否则榜上标了「持仓」的基金可能压根没进过快照池，标记与数据两套真相。

    不做候选码预过滤：家庭维度持仓 + 自选通常只有几十上百个符号，一次
    ``distinct`` 查询比「先查榜、再按码查」少一轮往返，也不要求调用方预知码集。

    Args:
        user_db: user 域会话。
        family_id: 家庭 ID；为 None（未登录）时两个集均为空。

    Returns:
        ``(holding_codes, watchlist_codes)``：该家庭出现过的 symbol（strip 后）。
    """
    from app.domains.positions.models import Position
    from app.domains.watchlist.models import WatchlistItem

    if family_id is None:
        return set(), set()

    def _symbols(model) -> set:
        rows = user_db.query(model.symbol).filter(model.family_id == family_id).distinct().all()
        return {(r[0] or '').strip() for r in rows if r[0]}

    return _symbols(Position), _symbols(WatchlistItem)


def list_by_metric(
    db: Session,
    *,
    fund_type_id: int,
    metric: str,
    limit: Optional[int] = None,
    ascending: Optional[bool] = None,
    include_distorted: bool = False,
    caliber_version: Optional[int] = None,
    holding_codes: Optional[set] = None,
    watchlist_codes: Optional[set] = None,
) -> Dict[str, Any]:
    """在**同一 `fund_type_id` 内**按某个指标排序取前 N。

    Args:
        db: market 域会话（`fund_risk_metrics` 是 market 域）。
        fund_type_id: 同类分组键，**必填**（见模块 docstring 的「不做跨类榜」）。
        metric: 排序指标，须在 `SORTABLE_METRICS` 内。
        limit: 条数上限（默认 20，硬上限 200）。
        ascending: 强制升降序；不给则用 `SORTABLE_METRICS` 的默认方向。
        include_distorted: 是否把 `basis != 'acc_nav'` 的行也纳入（默认剔除）。
        caliber_version: 口径版本；不给则用当前 `CALIBER_VERSION`。
        holding_codes: 家庭**持仓**代码集（可选）。给定时每行带 `in_holdings`，
            让「我持有的那只在同类里排第几」可回答（#167 后续 · 持仓体检定位）。
        watchlist_codes: 家庭**自选**代码集（可选）。同上，每行带 `in_watchlist`。

    Returns:
        ``{'fund_type_id', 'metric', 'order', 'rows', 'excluded_distorted'}``。
        `rows[]` 每项 = 快照列 + `fund_code` + `fund_name` + `in_holdings` +
        `in_watchlist`；`excluded_distorted` 是因口径被剔除的条数——不报它的话，
        「榜上只有 3 只」会被误读成「同类只有 3 只有数据」。
    """
    from app.domains.funds.models import Fund, FundRiskMetrics
    from app.services.sync.jobs.fund_risk_metrics_job import CALIBER_VERSION

    if metric not in SORTABLE_METRICS:
        raise ValueError(f'不支持的排序指标：{metric}')
    if not fund_type_id:
        raise ValueError('必须指定 fund_type_id（同类内排序，不做跨类榜）')

    version = CALIBER_VERSION if caliber_version is None else caliber_version
    order_desc = SORTABLE_METRICS[metric] if ascending is None else not ascending
    column = getattr(FundRiskMetrics, metric)

    base = db.query(FundRiskMetrics).filter(
        FundRiskMetrics.fund_type_id == int(fund_type_id),
        FundRiskMetrics.caliber_version == version,
    )
    # 值缺失的行不进榜：NULL 在 ORDER BY 里会排到一端，看起来像「排最后一名」，
    # 实际是「没算出来」。两者必须分开。
    base = base.filter(column.isnot(None))

    distorted_q = base.filter(FundRiskMetrics.basis != 'acc_nav')
    excluded = distorted_q.count()

    query = base if include_distorted else base.filter(FundRiskMetrics.basis == 'acc_nav')
    query = query.order_by(column.desc() if order_desc else column.asc())
    rows = query.limit(_clamp_limit(limit)).all()

    # 基金名称（market 域内两步法，不做跨域）：只显示 6 位代码用户认不出产品。
    # funds 表可能缺该 code（新基金未同步资料）——缺失回退 None，由前端降级显示代码。
    codes = [r.fund_code for r in rows]
    name_by_code: Dict[str, str] = {}
    if codes:
        name_by_code = {
            code: name for code, name in db.query(Fund.fund_code, Fund.name).filter(Fund.fund_code.in_(codes)).all()
        }

    return {
        'fund_type_id': int(fund_type_id),
        'metric': metric,
        'order': 'desc' if order_desc else 'asc',
        'caliber_version': version,
        'rows': [
            _row_payload(
                r,
                fund_name=name_by_code.get(r.fund_code),
                in_holdings=r.fund_code in (holding_codes or set()),
                in_watchlist=r.fund_code in (watchlist_codes or set()),
            )
            for r in rows
        ],
        'excluded_distorted': excluded,
    }


def list_fund_types(db: Session, *, caliber_version: Optional[int] = None) -> Dict[str, Any]:
    """列出**榜上真的有货**的基金小类（供前端做类型选择器）。

    为什么不能直接用「全库 fund_types 名录」当选择器：名录里有 20+ 个小类，
    而快照只覆盖其中一部分（其它类样本不足 / 口径不适用 / 尚未算）。选中一个
    没数据的类，用户看到的是空榜——他分不清「这个类没有基金」与「我们没算」。
    故只交出发出过快照行的类型，并**带上各自的样本数**（`count`），
    让前端能显示「债券型-长期纯债（312）」而不是一个光秃秃的下拉项。

    样本数只算**当前口径**且 `basis == 'acc_nav'` 的行——与榜单同一条纪律：
    口径可疑的行不能当「这个类有货」的凭据，否则点进去还是空榜。

    Args:
        db: market 域会话（`fund_risk_metrics` 是 market 域）。
        caliber_version: 口径版本；不给则用当前 `CALIBER_VERSION`。

    Returns:
        ``{'caliber_version', 'types': [{'fund_type_id', 'name', 'count'}]}``，
        按 `count` 降序（有货多的排前），`name` 取自 `fund_types`（缺失回退
        ``'类型#<id>'``，不编造名称）。
    """
    from sqlalchemy import func

    from app.domains.funds.models import FundRiskMetrics, FundType
    from app.services.sync.jobs.fund_risk_metrics_job import CALIBER_VERSION

    version = CALIBER_VERSION if caliber_version is None else caliber_version

    # 聚合在 DB 侧完成：快照表是这个项目最容易长大的表之一，不把它整表拉进内存分组。
    rows = (
        db.query(FundRiskMetrics.fund_type_id, func.count(FundRiskMetrics.id))
        .filter(
            FundRiskMetrics.caliber_version == version,
            FundRiskMetrics.basis == 'acc_nav',
            FundRiskMetrics.fund_type_id.isnot(None),
        )
        .group_by(FundRiskMetrics.fund_type_id)
        .all()
    )
    if not rows:
        return {'caliber_version': version, 'types': []}

    type_ids = [int(tid) for tid, _ in rows]
    name_by_id = {
        int(tid): name for tid, name in db.query(FundType.id, FundType.name).filter(FundType.id.in_(type_ids)).all()
    }

    types = [
        {
            'fund_type_id': int(tid),
            'name': name_by_id.get(int(tid)) or f'类型#{int(tid)}',
            'count': int(cnt),
        }
        for tid, cnt in rows
    ]
    types.sort(key=lambda x: (-x['count'], x['name']))
    return {'caliber_version': version, 'types': types}


def _row_payload(
    row, *, fund_name: Optional[str] = None, in_holdings: bool = False, in_watchlist: bool = False
) -> Dict[str, Any]:
    """快照行 → 榜单条目（数值一律 float，口径字段原样带出）。

    ``fund_name`` 来自 ``funds`` 表（调用方两步法查好传入）；缺失为 None，
    前端回退显示代码——不编造名称。

    ``in_holdings`` / ``in_watchlist``：家庭私有标记（未登录 / 未给定时恒 False）。
    **False 表示「查了，没有」，不是「没查」**——前端据此渲染「持仓 / 自选」徽章，
    两者皆 False 时不渲染（诚实缺席，不占位）。
    """

    def f(name):
        v = getattr(row, name, None)
        return float(v) if v is not None else None

    return {
        'fund_code': row.fund_code,
        'fund_name': fund_name,
        'fund_type_id': row.fund_type_id,
        'as_of': row.as_of.isoformat() if row.as_of else None,
        'in_holdings': bool(in_holdings),
        'in_watchlist': bool(in_watchlist),
        'max_drawdown': f('max_drawdown'),
        'current_drawdown': f('current_drawdown'),
        'drawdown_days': row.drawdown_days,
        'annual_return': f('annual_return'),
        'annual_volatility': f('annual_volatility'),
        'ret_1m': f('ret_1m'),
        'ret_3m': f('ret_3m'),
        'ret_1y': f('ret_1y'),
        'sharpe': f('sharpe'),
        'sortino': f('sortino'),
        'calmar': f('calmar'),
        'ulcer_index': f('ulcer_index'),
        'upi': f('upi'),
        'return_drawdown_ratio': f('return_drawdown_ratio'),
        'win_rate': f('win_rate'),
        'sample_points': row.sample_points,
        'basis': row.basis,
        'window_label': row.window_label,
    }


def peer_percentiles_for(db: Session, codes: Sequence[str]) -> Dict[str, Dict[str, float]]:
    """给一批基金代码算「同类内分位」（供详情页显示「同类排前 X%」）。

    两次查询（不是 N+1）：① 取这些 code 的 `fund_type_id`；② 把**这些类型下的全部
    快照行**一次捞出来，在内存里分组算分位。② 的行数上限 = 同类基金只数 × 1
    （当前口径行），不是全表——不做全表扫描（数据策略硬约束 §6）。

    返回 ``{fund_code: {metric: percentile}}``；分位不足（同类样本 < 5）的条目
    **不出现**，调用方降级为「—」。
    """
    from app.domains.funds.models import FundRiskMetrics
    from app.services.fund_peer_rank import peer_percentiles
    from app.services.sync.jobs.fund_risk_metrics_job import CALIBER_VERSION

    wanted = [c for c in {c.strip() for c in codes if c and c.strip()} if c]
    if not wanted:
        return {}

    type_by_code: Dict[str, int] = {}
    for i in range(0, len(wanted), 500):
        chunk = wanted[i : i + 500]
        for code, type_id in (
            db.query(FundRiskMetrics.fund_code, FundRiskMetrics.fund_type_id)
            .filter(FundRiskMetrics.fund_code.in_(chunk), FundRiskMetrics.fund_type_id.isnot(None))
            .all()
        ):
            type_by_code[code] = int(type_id)
    if not type_by_code:
        return {}

    type_ids = sorted(set(type_by_code.values()))
    metrics = (
        'sharpe',
        'sortino',
        'calmar',
        'upi',
        'return_drawdown_ratio',
        'win_rate',
        'max_drawdown',
        'current_drawdown',
        'annual_volatility',
    )
    # 只捞需要的列，不取整个 ORM 实体（同类可能有上千只，实体化没必要）
    sample_rows = (
        db.query(
            FundRiskMetrics.fund_code,
            FundRiskMetrics.fund_type_id,
            *(getattr(FundRiskMetrics, m) for m in metrics),
        )
        .filter(
            FundRiskMetrics.fund_type_id.in_(type_ids),
            FundRiskMetrics.caliber_version == CALIBER_VERSION,
            FundRiskMetrics.basis == 'acc_nav',  # 口径可疑的行不进分母（与榜单同一条纪律）
        )
        .all()
    )

    payloads = []
    for row in sample_rows:
        values = {m: (float(v) if v is not None else None) for m, v in zip(metrics, row[2:])}
        payloads.append((row[0], row[1], values))

    all_pcts = peer_percentiles(payloads, metrics)
    return {code: all_pcts[code] for code in wanted if code in all_pcts}


__all__ = [
    'DEFAULT_LIMIT',
    'MAX_LIMIT',
    'SORTABLE_METRICS',
    'list_by_metric',
    'list_fund_types',
    'peer_percentiles_for',
    'user_flags_for_codes',
]
