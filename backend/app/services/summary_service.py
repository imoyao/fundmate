# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/23 12:24
# File : backend/app/services/summary_service.py
"""仪表盘聚合与桑基图数据服务."""

from collections import defaultdict
from typing import Any

from app.core.constants import ALLOC_LABELS, CATEGORY_META, EXCHANGE_RATES
from app.core.database import Session
from app.core.enums import TYPE_LABELS
from app.domains.assets.models import Asset
from app.domains.positions.models import Position

# ---------------------------------------------------------------------------
# 业务常量集中定义（消除魔法字符串）
# ---------------------------------------------------------------------------
_LIABILITY_KEY = 'liability'
_INVESTMENT_KEY = 'investment'
_DEFAULT_ALLOC = 'longterm'
_UNKNOWN_TYPE = '其他'
_CENTER_NODE = '总资产'
_NET_NODE = '净资产'
_LIABILITY_NODE = '总负债'
_UNCONFIGURED_NODE = '未配置资产'


def _load_user_assets(db: Session, user_id: int) -> tuple[list[Position], list[Asset]]:
    """统一加载用户资产数据（持仓 + 通用资产）"""
    positions = db.query(Position).all()
    assets = db.query(Asset).filter(Asset.user_id == user_id).all()
    return positions, assets


def get_summary_data(db: Session, user_id: int = 1) -> dict[str, Any]:
    """返回仪表盘聚合数据（总资产、总负债、净资产、总盈亏、市场分布）"""
    positions, assets = _load_user_assets(db, user_id)

    total_assets = 0.0
    total_pnl = 0.0
    market_distribution: dict[str, float] = {}

    # 一次遍历 positions，完成市值、盈亏、市场分布
    for p in positions:
        rate = EXCHANGE_RATES.get(p.currency, 1.0)
        market_value = p.quantity * (p.current_price or 0.0) * rate
        total_assets += market_value

        pnl = ((p.current_price or 0.0) - (p.avg_price or 0.0)) * p.quantity * rate
        total_pnl += pnl

        market = p.market or '其他市场'
        market_distribution[market] = market_distribution.get(market, 0.0) + market_value

    # 一次遍历 assets，区分负债与资产（暂不做汇率转换）
    total_liabilities = 0.0
    for a in assets:
        amount = a.amount or 0.0
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


def get_sankey_data(db: Session, user_id: int = 1) -> dict[str, list[dict[str, Any]]]:
    """返回桑基图数据（合并资产/负债，负债从总资产流出）"""
    positions, assets = _load_user_assets(db, user_id)

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
        amount = a.amount or 0.0
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
        mv = p.quantity * (p.current_price or 0.0) * rate
        if mv <= 0:
            continue

        investment_total += mv

        # 五笔钱分配
        alloc = p.allocation or _DEFAULT_ALLOC
        alloc_map[alloc] += mv

        # 产品类型明细（翻译为中文标签）
        alloc_label = ALLOC_LABELS.get(alloc, alloc)
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
            label = ALLOC_LABELS.get(alloc_key, alloc_key)
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
        _add_link(_CENTER_NODE, _LIABILITY_NODE, total_liabilities)

        # 具体负债项（直接使用第一次遍历时收集的明细）
        for name, amount in liability_details:
            _add_node(name)
            _add_link(_LIABILITY_NODE, name, amount)

    return {'nodes': nodes, 'links': links}
