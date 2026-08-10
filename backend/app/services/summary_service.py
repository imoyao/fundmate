# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/23 12:24
# File : backend/app/services/summary_service.py
"""仪表盘聚合与桑基图数据服务."""

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Type

from app.core.constants import (
    ALLOCATION_LABELS,
    CATEGORY_META,
    EXCHANGE_RATES,
    MARKET_LABELS,
    TYPE_LABELS,
)
from app.core.database import Session
from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.positions.models import Position
from app.domains.summary.models import AssetSnapshot

# ---------------------------------------------------------------------------
# 业务常量集中定义（消除魔法字符串）
# ---------------------------------------------------------------------------
_LIABILITY_KEY = 'liability'
_INVESTMENT_KEY = 'investment'
_DEFAULT_ALLOC = 'longterm'
_UNKNOWN_TYPE = '其他'
_INVESTMENT_LABEL = CATEGORY_META['investment'][0]
_CENTER_NODE = '总资产'
_NET_NODE = '净资产'
_LIABILITY_NODE = '总负债'
_UNCONFIGURED_NODE = '未配置资产'


def _load_user_assets(db: Session, family_id: int) -> tuple[list[Type[Position]], Any]:
    """统一加载当前家庭的资产数据（持仓 + 通用资产），按 family_id 隔离（D1）。"""
    positions = db.query(Position).filter(Position.family_id == family_id).all()
    assets = db.query(Asset).filter(Asset.family_id == family_id).all()
    return positions, assets


def get_summary_data(db: Session, family_id: int = 1) -> dict[str, Any]:
    """返回仪表盘聚合数据（总资产、总负债、净资产、总盈亏、市场分布）"""
    positions, assets = _load_user_assets(db, family_id)

    total_assets = 0.0
    total_pnl = 0.0
    market_distribution: dict[str, float] = {}

    # 一次遍历 positions，完成市值、盈亏、市场分布
    for p in positions:
        rate = EXCHANGE_RATES.get(p.currency, 1.0)
        # 市值 = 数量(份) * 当前价(元) * 汇率
        market_value = Money.min_unit_to_shares(p.quantity) * Money.cents_to_yuan(p.current_price) * rate
        total_assets += market_value

        # 盈亏 = (当前价 - 成本价) * 数量
        pnl = (
            (Money.cents_to_yuan(p.current_price) - Money.cents_to_yuan(p.avg_price))
            * Money.min_unit_to_shares(p.quantity)
            * rate
        )
        total_pnl += pnl

        market = p.market or '其他市场'
        market_distribution[market] = market_distribution.get(market, 0.0) + market_value

    # 一次遍历 assets，区分负债与资产（暂不做汇率转换）
    total_liabilities = 0.0
    for a in assets:
        amount = Money.cents_to_yuan(a.amount)
        if amount <= 0:
            continue
        if a.major_category == _LIABILITY_KEY:
            total_liabilities += amount
        else:
            total_assets += amount

    return {
        'total_assets_cny': round(total_assets, 2),
        'total_liabilities_cny': round(total_liabilities, 2),
        'net_assets_cny': round(total_assets - total_liabilities, 2),
        'total_pnl_cny': round(total_pnl, 2),
        'market_distribution': {k: round(v, 2) for k, v in market_distribution.items()},
    }


def get_sankey_data(db: Session, family_id: int = 1) -> dict[str, list[dict[str, Any]]]:
    """返回桑基图数据（双流并行模型：资产流在上，负债流在下，无交叉）"""
    positions, assets = _load_user_assets(db, family_id)

    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add_node(name: str) -> None:
        if name and name not in seen:
            nodes.append({'name': name})
            seen.add(name)

    def _add_link(source: str, target: str, value: float) -> None:
        if value > 0:
            links.append(
                {
                    'source': source,
                    'target': target,
                    'value': round(value, 2),
                }
            )

    # =====================================================================
    # 数据聚合阶段：一次遍历完成所有统计，并收集负债明细
    # =====================================================================
    total_assets = 0.0
    total_liabilities = 0.0
    category_totals: dict[str, float] = {k: 0.0 for k in CATEGORY_META}
    liability_details: list[tuple[str, float]] = []  # 收集负债项，避免二次遍历

    for a in assets:
        amount = Money.cents_to_yuan(a.amount)
        if amount <= 0:
            continue
        if a.major_category == _LIABILITY_KEY:
            total_liabilities += amount
            liability_details.append((a.name, amount))
        else:
            total_assets += amount
            if a.major_category in category_totals:
                category_totals[a.major_category] += amount

    # 一次遍历 positions，同时完成投资理财总额、五笔钱分配、产品类型明细
    investment_total = 0.0
    alloc_map: dict[str, float] = defaultdict(float)
    alloc_type_map: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for p in positions:
        rate = EXCHANGE_RATES.get(p.currency, 1.0)
        mv = Money.min_unit_to_shares(p.quantity) * Money.cents_to_yuan(p.current_price) * rate
        if mv <= 0:
            continue

        investment_total += mv

        # 五笔钱分配
        alloc = p.allocation or _DEFAULT_ALLOC
        alloc_map[alloc] += mv

        # 产品类型明细（翻译为中文标签）
        alloc_label = ALLOCATION_LABELS.get(alloc, alloc)
        type_name = p.asset_type or _UNKNOWN_TYPE
        display_name = TYPE_LABELS.get(type_name, type_name)
        alloc_type_map[alloc_label][display_name] += mv

    # 将投资理财总额归入大类
    category_totals[_INVESTMENT_KEY] += investment_total
    total_assets += investment_total

    # 若无任何资产，返回空数据
    if total_assets == 0:
        return {'nodes': [], 'links': []}

    # =====================================================================
    # 图结构构建阶段
    # =====================================================================
    # 第一层：资产大类节点
    for cat_key, total_val in category_totals.items():
        if total_val > 0:
            cat_name, _ = CATEGORY_META[cat_key]
            _add_node(cat_name)

    # 第二层：大类 → 总资产
    _add_node(_CENTER_NODE)
    for cat_key, total_val in category_totals.items():
        if total_val > 0:
            cat_name, _ = CATEGORY_META[cat_key]
            _add_link(cat_name, _CENTER_NODE, total_val)

    net_worth = total_assets - total_liabilities

    # 净资产分支（先添加，使其在图表上方）
    if net_worth > 0:
        _add_node(_NET_NODE)
        _add_link(_CENTER_NODE, _NET_NODE, net_worth)

        # 五笔钱与未配置资产
        configured_total = sum(alloc_map.values())
        for alloc_key, total_val in alloc_map.items():
            label = ALLOCATION_LABELS.get(alloc_key, alloc_key)
            _add_node(label)
            _add_link(_NET_NODE, label, total_val)

        unconfigured = net_worth - configured_total
        if unconfigured > 0:
            _add_node(_UNCONFIGURED_NODE)
            _add_link(_NET_NODE, _UNCONFIGURED_NODE, unconfigured)

        # 五笔钱 → 产品类型
        for alloc_label, type_map in alloc_type_map.items():
            for type_name, total_val in type_map.items():
                _add_node(type_name)
                _add_link(alloc_label, type_name, total_val)

    # 负债分支（后添加，使其在净资产下方）
    if total_liabilities > 0:
        _add_node(_LIABILITY_NODE)
        # 1. 构建具体负债项
        for name, amount in liability_details:
            _add_node(name)
            _add_link(_LIABILITY_NODE, name, amount)
        # 2. 【关键】建立总资产到总负债的连线
        _add_link(_CENTER_NODE, _LIABILITY_NODE, total_liabilities)

    return {'nodes': nodes, 'links': links}


def get_account_groups(db: Session, family_id: int = 1) -> list[dict]:
    """返回按账户分组的汇总数据，负债金额为负数"""
    positions, assets = _load_user_assets(db, family_id)
    groups: dict[str, dict[str, float | int]] = defaultdict(lambda: {'total': 0.0, 'count': 0})

    # 1. 处理持仓 (均为资产)
    for p in positions:
        acc = p.account_name or '未指定账户'
        rate = EXCHANGE_RATES.get(p.currency, 1.0)
        market_value = Money.min_unit_to_shares(p.quantity) * Money.cents_to_yuan(p.current_price) * rate
        if market_value == 0:
            continue
        groups[acc]['total'] += market_value
        groups[acc]['count'] += 1

    # 2. 处理通用资产 (负债取负)
    for a in assets:
        acc = a.account_name or '未指定账户'
        amount = Money.cents_to_yuan(a.amount)
        if amount <= 0:
            continue
        if a.major_category == 'liability':
            amount = -amount
        groups[acc]['total'] += amount
        groups[acc]['count'] += 1

    # 3. 转换为列表并排序 (金额大的在上)
    result = [
        {'name': name, 'total': round(data['total'], 2), 'count': data['count']}
        for name, data in groups.items()
        if data['count'] > 0
    ]
    result.sort(key=lambda x: abs(x['total']), reverse=True)
    return result


def get_distributions(db: Session, family_id: int = 1) -> dict[str, Any]:
    """家庭级多维市值分布聚合（后端唯一出口）。

    供 Overview / AssetPanorama 等分布图表消费：持仓按产品类型 / 五笔钱 /
    市场 / 账户四维聚合，通用资产按大类聚合（负债单独统计），并返回
    总资产 / 总负债 / 净资产汇总。聚合与汇率换算全部收敛后端，前端不再
    遍历全量明细自行计算（D5：后端是唯一数据出口）。
    """
    positions, assets = _load_user_assets(db, family_id)

    def _pos_mv(p) -> float:
        rate = EXCHANGE_RATES.get(p.currency, 1.0)
        return Money.min_unit_to_shares(p.quantity) * Money.cents_to_yuan(p.current_price) * rate

    type_map: dict[str, float] = defaultdict(float)
    alloc_map: dict[str, float] = defaultdict(float)
    market_map: dict[str, float] = defaultdict(float)
    account_map: dict[str, float] = defaultdict(float)
    positions_total_mv = 0.0
    for p in positions:
        mv = _pos_mv(p)
        positions_total_mv += mv
        type_map[TYPE_LABELS.get(p.asset_type, p.asset_type or _UNKNOWN_TYPE)] += mv
        alloc_map[ALLOCATION_LABELS.get(p.allocation, p.allocation or _DEFAULT_ALLOC)] += mv
        market_map[MARKET_LABELS.get(p.market, p.market or _UNKNOWN_TYPE)] += mv
        account_map[p.account_name or '未指定账户'] += mv

    # 通用资产按大类聚合；负债单独统计，不进大类分布与总资产
    total_assets = positions_total_mv
    total_liabilities = 0.0
    category_map: dict[str, float] = defaultdict(float)
    liability_map: dict[str, float] = defaultdict(float)
    for a in assets:
        amount = Money.cents_to_yuan(a.amount)
        if amount <= 0:
            continue
        if a.major_category == _LIABILITY_KEY:
            total_liabilities += amount
            liability_map[a.name or '其他负债'] += amount
        else:
            total_assets += amount
            label = CATEGORY_META.get(a.major_category, (_UNKNOWN_TYPE, None))[0]
            category_map[label] += amount
    # 持仓市值统一归入投资理财大类
    category_map[_INVESTMENT_LABEL] += positions_total_mv

    def _to_list(d: dict[str, float]) -> list[dict[str, float]]:
        return [{'name': k, 'value': round(v, 2)} for k, v in sorted(d.items(), key=lambda kv: -kv[1]) if v > 0]

    return {
        'type_distribution': _to_list(type_map),
        'allocation_distribution': _to_list(alloc_map),
        'market_distribution': _to_list(market_map),
        'account_distribution': _to_list(account_map),
        'category_distribution': _to_list(category_map),
        'liability_distribution': _to_list(liability_map),
        'total_assets': round(total_assets, 2),
        'total_liabilities': round(total_liabilities, 2),
        'net_worth': round(total_assets - total_liabilities, 2),
        'positions_total_mv': round(positions_total_mv, 2),
    }


# ---------------------------------------------------------------------------
# 维度分组（批次 2b）：持仓/资产按产品类型/账户/配置目标分组，含 items 明细
# ---------------------------------------------------------------------------
_POS_GROUP_DIMENSIONS = ('type', 'account', 'allocation')


def _pos_group_payload(p: Position) -> dict[str, Any]:
    """持仓分组明细：展示单位 + 标签，市值/盈亏按汇率后端换算（唯一出口）。"""
    rate = EXCHANGE_RATES.get(p.currency, 1.0)
    shares = Money.min_unit_to_shares(p.quantity)
    price = Money.cents_to_yuan(p.current_price)
    cost = Money.cents_to_yuan(p.avg_price)
    return {
        'id': p.id,
        'name': p.name,
        'symbol': p.symbol,
        'asset_type': p.asset_type,
        'type_label': TYPE_LABELS.get(p.asset_type, p.asset_type or _UNKNOWN_TYPE),
        'market': p.market,
        'market_label': MARKET_LABELS.get(p.market, p.market),
        'allocation': p.allocation,
        'allocation_label': ALLOCATION_LABELS.get(p.allocation, p.allocation or '未分类'),
        'account_name': p.account_name,
        'quantity': shares,
        'current_price': price,
        'market_value': round(shares * price * rate, 2),
        'pnl': round((price - cost) * shares * rate, 2),
    }


def _asset_group_payload(a: Asset) -> dict[str, Any]:
    """通用资产分组明细（非负债），金额为人民币元。"""
    return {
        'id': a.id,
        'name': a.name,
        'asset_type': a.major_category,
        'type_label': CATEGORY_META.get(a.major_category, (_UNKNOWN_TYPE, None))[0],
        'account_name': a.account_name,
        'market_value': round(Money.cents_to_yuan(a.amount), 2),
        'pnl': 0.0,
    }


def get_position_groups(db: Session, family_id: int = 1, dimension: str = 'type') -> list[dict[str, Any]]:
    """按维度分组汇总持仓/资产（含 items 明细），供资产总览分组卡片消费。

    聚合、汇率换算、市值/盈亏全部在后端；前端纯渲染，不再保留 EXCHANGE_RATES。
    dimension: type（产品类型）/ account（账户，含非负债通用资产）/ allocation（配置目标）。
    返回列表按 total 降序，与 distributions 接口口径一致。
    """
    if dimension not in _POS_GROUP_DIMENSIONS:
        dimension = 'type'
    positions, assets = _load_user_assets(db, family_id)

    groups: dict[str, dict[str, Any]] = {}

    def _add(key: str, payload: dict[str, Any]) -> None:
        g = groups.get(key)
        if g is None:
            g = groups[key] = {'name': key, 'total': 0.0, 'total_pnl': 0.0, 'count': 0, 'items': []}
        g['total'] += payload['market_value']
        g['total_pnl'] += payload['pnl']
        g['count'] += 1
        g['items'].append(payload)

    if dimension == 'account':
        for p in positions:
            _add(p.account_name or '未指定账户', _pos_group_payload(p))
        for a in assets:
            amount = Money.cents_to_yuan(a.amount)
            if amount <= 0 or a.major_category == _LIABILITY_KEY:
                continue
            _add(a.account_name or '未指定账户', _asset_group_payload(a))
    elif dimension == 'allocation':
        for p in positions:
            key = ALLOCATION_LABELS.get(p.allocation, p.allocation or '未分类')
            _add(key, _pos_group_payload(p))
    else:
        for p in positions:
            key = TYPE_LABELS.get(p.asset_type, p.asset_type or _UNKNOWN_TYPE)
            _add(key, _pos_group_payload(p))

    result = sorted(groups.values(), key=lambda g: -g['total'])
    for g in result:
        g['total'] = round(g['total'], 2)
        g['total_pnl'] = round(g['total_pnl'], 2)
    return result


# ---------------------------------------------------------------------------
# 资产快照（同比计算底座）：asset_snapshots 表实现每日总资产历史，供
# 「较上月/较去年同期」真实展示；历史积累期无数据时前端降级展示（见方案文档）。
# ---------------------------------------------------------------------------
def _shift_months(d: date, months: int) -> date:
    """将日期向前/向后平移 N 个月，月末日期自动 clamp 到目标月最后一天。

    例：2026-03-31 -1 月 → 2026-02-28，避免日期溢出。
    """
    import calendar

    month_index = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(month_index, 12)
    month = month0 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def write_asset_snapshot(db: Session, family_id: int = 1, snapshot_date: str | None = None) -> dict[str, Any]:
    """记录当日资产快照（幂等 upsert）。

    金额从 get_distributions 聚合而来（元），落库转为整数分（Money 精度）。
    snapshot_date 可选，默认上海时区当日；用于历史回填，须为 YYYY-MM-DD。
    """
    from app.core.time_utils import now_shanghai

    if snapshot_date is None:
        target = now_shanghai().date()
    else:
        target = datetime.strptime(snapshot_date, '%Y-%m-%d').date()

    dist = get_distributions(db, family_id)

    row = (
        db.query(AssetSnapshot)
        .filter(AssetSnapshot.family_id == family_id, AssetSnapshot.snapshot_date == target)
        .first()
    )
    if row is None:
        row = AssetSnapshot(family_id=family_id, snapshot_date=target)
        db.add(row)
    row.total_assets = Money.yuan_to_cents(dist['total_assets'])
    row.total_liabilities = Money.yuan_to_cents(dist['total_liabilities'])
    row.net_worth = Money.yuan_to_cents(dist['net_worth'])
    db.commit()
    return _snapshot_payload(row)


def _snapshot_payload(s: AssetSnapshot) -> dict[str, Any]:
    """快照单条输出：金额转元，同比百分比由读取侧计算填充。"""
    return {
        'id': s.id,
        'snapshot_date': s.snapshot_date.isoformat(),
        'total_assets': round(Money.cents_to_yuan(s.total_assets), 2),
        'total_liabilities': round(Money.cents_to_yuan(s.total_liabilities), 2),
        'net_worth': round(Money.cents_to_yuan(s.net_worth), 2),
    }


def _pct_change(current: float, base: float | None) -> float | None:
    """同比百分比；无基准或基准为 0 时返回 None（前端降级展示）。"""
    if base is None or base == 0:
        return None
    return round((current - base) / abs(base) * 100, 2)


def get_snapshots(
    db: Session,
    family_id: int = 1,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """查询资产快照列表（按日期升序），并计算每条相对上月同期 / 去年同期的同比。

    基准取「对应基准日当天或之前最近一条」快照，找不到则为 None：
    - monthly_change_pct：以上月同日为基准
    - yearly_change_pct：以去年同期为基准
    """
    q = db.query(AssetSnapshot).filter(AssetSnapshot.family_id == family_id)
    if start_date:
        q = q.filter(AssetSnapshot.snapshot_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        q = q.filter(AssetSnapshot.snapshot_date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    rows = q.order_by(AssetSnapshot.snapshot_date.asc()).all()

    results: list[dict[str, Any]] = []
    for row in rows:
        monthly_base = _nearest_before(db, family_id, _shift_months(row.snapshot_date, -1))
        yearly_base = _nearest_before(db, family_id, _shift_months(row.snapshot_date, -12))
        payload = _snapshot_payload(row)
        payload['monthly_change_pct'] = _pct_change(payload['net_worth'], _net_of(monthly_base))
        payload['yearly_change_pct'] = _pct_change(payload['net_worth'], _net_of(yearly_base))
        results.append(payload)
    return results


def _nearest_before(db: Session, family_id: int, boundary: date) -> Any | None:
    """取指定日期当天或之前最近的一条快照，作为同比基准。"""
    return (
        db.query(AssetSnapshot)
        .filter(AssetSnapshot.family_id == family_id, AssetSnapshot.snapshot_date <= boundary)
        .order_by(AssetSnapshot.snapshot_date.desc())
        .first()
    )


def _net_of(row: Any | None) -> float | None:
    return None if row is None else round(Money.cents_to_yuan(row.net_worth), 2)
