# -*- coding: utf-8 -*-
"""资产构成流向桑基图数据源（从 summary_service 下沉，D94）。

本模块只负责「资金来源 → 资产运用」单轴守恒桑基图（见 get_sankey_data 文档），
把原 summary_service 里 220+ 行 / 圈复杂度 53 的 get_sankey_data 拆成多个
≤120 行 / 圈复杂度 ≤20 的小函数，符合 services 层体量闸门的新增上限。

历史：2026-11-09 D94 收敛——删除「未配置资产」与五笔钱/产品类型整支，改为守恒图。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.core.asset_types import normalize_major_category
from app.core.constants import CATEGORY_META, EXCHANGE_RATES, TYPE_LABELS
from app.core.money import Money
from app.services.fund_utils import is_cash_equivalent_position
from app.services.position_valuation import market_value_cents
from app.services.summary_service import (
    _load_user_assets,
    family_totals,
    orphan_money_fund_totals_by_ledger,
)

# 节点名（与前端 sankeyLayout 的语义一致）。
_CENTER_NODE = '总资产'
_NET_NODE = '净资产'
_LIABILITY_NODE = '总负债'
_LIABILITY_KEY = 'liability'
_INVESTMENT_KEY = 'investment'
_UNKNOWN_TYPE = '其他'
_INVESTMENT_LABEL = CATEGORY_META['investment'][0]

# 大类固定顺序：与参考图「固定资产 / 流动资金 / 投资理财」一致；历史细分类已由
# normalize_major_category 并入 investment，这里只决定展示先后。
_CATEGORY_ORDER = (
    'fixed',
    'cash',
    'investment',
    'receivable',
    'insurance',
    'real_estate',
    'precious_metal',
    'custom',
)

# 保留名：大类名 + 汇总节点名。明细名撞它们会形成自环边（X → X），ECharts 判
# 「Sankey is a DAG」直接白屏；跨大类的同名明细同样危险。
_RESERVED_NAMES = {CATEGORY_META[k][0] for k in CATEGORY_META} | {
    _CENTER_NODE,
    _NET_NODE,
    _LIABILITY_NODE,
}


def _add_node(nodes: list[dict[str, Any]], seen: set[str], name: str) -> None:
    if name and name not in seen:
        nodes.append({'name': name})
        seen.add(name)


def _add_link(links: list[dict[str, Any]], source: str, target: str, value: float) -> None:
    if value > 0:
        links.append({'source': source, 'target': target, 'value': round(value, 2)})


def _unique_node_name(raw: str, fallback: str, used_names: set[str]) -> str:
    """返回全局唯一、且不与保留名（大类 / 汇总节点）冲突的节点名。"""
    base = (raw or '').strip() or fallback
    if base not in _RESERVED_NAMES and base not in used_names:
        used_names.add(base)
        return base
    idx = 2
    while True:
        candidate = f'{base}·{idx}'
        if candidate not in _RESERVED_NAMES and candidate not in used_names:
            used_names.add(candidate)
            return candidate
        idx += 1


def _collect_buckets(
    db: Session, family_id: int, assets: list, positions: list
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """资产运用侧：按「大类 → 明细」两级同源累加。

    返回 (detail_buckets, liability_details)。持仓按 asset_type 归到
    投资理财 / 流动资金；账外类现金并入流动资金。
    """
    detail_buckets: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    # 同名负债按名字聚合：不同账户的同一负债合并成一条带，避免重复平行边。
    liability_details: dict[str, float] = defaultdict(float)

    for a in assets:
        amount = Money.cents_to_yuan(a.amount)
        if amount <= 0:
            continue
        if a.major_category == _LIABILITY_KEY:
            liability_details[a.name or '未命名负债'] += amount
            continue
        # 历史「银行理财/投顾/信托/私募/理财型保险」大类归一到 investment（#1354），
        # 与 get_distributions 的 category_map 同一套归一，避免两处分类漂移。
        cat_key = normalize_major_category(a.major_category)
        if cat_key not in CATEGORY_META:
            cat_key = 'custom'
        detail_buckets[cat_key][a.name or ''] += amount

    for p in positions:
        rate = EXCHANGE_RATES.get(p.currency, 1.0)
        mv = Money.cents_to_yuan(market_value_cents(p, rate=rate))
        if mv <= 0:
            continue
        # #863 口径 A：货基/逆回购持仓归「流动资金」，其余归「投资理财」。
        cat_key = 'cash' if is_cash_equivalent_position(p) else _INVESTMENT_KEY
        type_name = p.asset_type or _UNKNOWN_TYPE
        detail_buckets[cat_key][TYPE_LABELS.get(type_name, type_name)] += mv

    # 账外类现金（不建持仓、不进市值）：本金净额 + 渠道收益并入流动资金。
    # 两项都可能为负（净赎回 / 代扣税），先如实计入，下游统一做「只画正流量」配平。
    net_map, income_map = orphan_money_fund_totals_by_ledger(db, family_id)
    if net_map:
        detail_buckets['cash']['货基/逆回购净额'] += Money.cents_to_yuan(sum(net_map.values()))
    if income_map:
        detail_buckets['cash']['渠道收益'] += Money.cents_to_yuan(sum(income_map.values()))
    return detail_buckets, liability_details


def _build_funding_side(
    nodes: list[dict[str, Any]],
    links: list[dict[str, Any]],
    seen: set[str],
    used_names: set[str],
    liability_details: dict[str, float],
    liability_sum: float,
    net_worth: float,
    total_assets: float,
) -> float:
    """画资金来源侧（净资产 + 总负债 → 总资产），返回资金来源侧总额。

    净资产 ≤ 0（资不抵债）时不画资金来源侧，退化为「仅资产运用」单轴图：
    总资产作根节点，不伪造权益入边。
    """
    if net_worth <= 0:
        return total_assets
    if liability_sum > 0:
        _add_node(nodes, seen, _LIABILITY_NODE)
        for raw_name, amount in liability_details.items():
            name = _unique_node_name(raw_name, '未命名负债', used_names)
            _add_node(nodes, seen, name)
            _add_link(links, name, _LIABILITY_NODE, amount)
        # 总负债入边和 = 出边和：取明细之和而非 family_totals 的 round 值，
        # 避免 0.01 元级浮点差破坏守恒。
        _add_link(links, _LIABILITY_NODE, _CENTER_NODE, liability_sum)
    _add_node(nodes, seen, _NET_NODE)
    _add_link(links, _NET_NODE, _CENTER_NODE, net_worth)
    return round(net_worth + liability_sum, 2)


def _balance_conservation(
    detail_buckets: dict[str, dict[str, float]], source_total: float
) -> dict[str, dict[str, float]]:
    """丢弃 ≤0 明细后做守恒配平：差额在正明细最大的大类里补/扣回来。

    返回正明细字典；若没有任何正明细则返空 dict。
    """
    positive: dict[str, dict[str, float]] = {}
    for cat_key, details in detail_buckets.items():
        kept = {name: round(v, 2) for name, v in details.items() if v > 0.005}
        if kept:
            positive[cat_key] = kept
    residual = round(source_total - sum(sum(d.values()) for d in positive.values()), 2)
    if abs(residual) > 0.005 and positive:
        _apply_residual(positive, residual)
    return positive


def _apply_residual(positive: dict[str, dict[str, float]], residual: float) -> None:
    """把守恒差额在明细最大的大类里补（residual>0）或扣（residual<0）回来。

    与旧版「未配置资产」有本质区别：这里的差额是浮点 / 账外净流出的净额，
    量纲同为「资产 A」，不是拿权益 E 减毛持仓 P 配出来的假资产。
    """
    anchor = max(positive, key=lambda k: sum(positive[k].values()))
    if residual > 0:
        positive[anchor]['其他资产'] = round(positive[anchor].get('其他资产', 0.0) + residual, 2)
        return
    need = -residual
    for name in sorted(positive[anchor], key=lambda k: -positive[anchor][k]):
        if need <= 0.005:
            break
        cut = min(positive[anchor][name], need)
        positive[anchor][name] = round(positive[anchor][name] - cut, 2)
        need = round(need - cut, 2)
    positive[anchor] = {k: v for k, v in positive[anchor].items() if v > 0.005}
    for key in [k for k in positive if not positive[k]]:
        del positive[key]


def _assemble_graph(
    nodes: list[dict[str, Any]],
    links: list[dict[str, Any]],
    seen: set[str],
    used_names: set[str],
    positive: dict[str, dict[str, float]],
) -> None:
    """按列从左到右组装节点与边。数组顺序即前端同列上下次序（见 sankeyLayout.ts）。"""
    cat_order = [k for k in _CATEGORY_ORDER if k in positive] + [k for k in positive if k not in _CATEGORY_ORDER]
    _add_node(nodes, seen, _CENTER_NODE)
    for cat_key in cat_order:
        _add_node(nodes, seen, CATEGORY_META[cat_key][0])
    for cat_key in cat_order:
        cat_name = CATEGORY_META[cat_key][0]
        # 明细节点名统一定名：全局唯一 + 不撞大类/汇总节点名（防自环）。
        # 无名资产归「其他资产」；同名资产在不同大类下自动加后缀区分。
        renamed = [
            (_unique_node_name(raw, '其他资产', used_names), amount) for raw, amount in positive[cat_key].items()
        ]
        cat_total = round(sum(amount for _, amount in renamed), 2)
        if cat_total <= 0:
            continue
        _add_link(links, _CENTER_NODE, cat_name, cat_total)
        for name, amount in sorted(renamed, key=lambda kv: -kv[1]):
            _add_node(nodes, seen, name)
            _add_link(links, cat_name, name, amount)


def get_sankey_data(db: Session, family_id: int = 1, member_id: int | None = None) -> dict[str, list[dict[str, Any]]]:
    """返回「资产构成流向」桑基图数据。

    ⚠️ **会计守恒契约（2026-11-09 定死，见 docs/spec/decisions.md）**

    桑基图是守恒流量图，**一条链只能承载一个分类轴**。本图只画
    「资金来源 → 资产运用」这一条轴，列语义与资产总览参考图一致::

        负债明细 ─→ 总负债 ─┐
        净资产   ──────────┴─→ 总资产 ─→ 资产大类 ─→ 资产明细

    恒等式 ``A = L + E``：总资产入边 = 净资产 + 总负债，出边 = Σ 资产大类
    = Σ 资产明细；每个中间节点入边和与出边和相等（浮点容差 0.02 元）。

    ⚠️ **不画「五笔钱配置目标 / 产品类型」这条正交分类轴**。五笔钱是持仓的
    配置目标（毛市值 P），净资产是权益 E；把 E 拆成 P 是量纲错位。旧版为此
    造出 ``未配置资产 = E − ΣP`` 当配平塞子——零持仓、只有「一套房 220 万 +
    房贷 176 万」也会凭空出现「未配置资产 44 万」，且负债一变它跟着变。
    它不是资产，是错账，故整支删除（含产品类型明细）。五笔钱分布请走
    ``/api/summary/distributions/`` 的 ``allocation_distribution``。

    ⚠️ 负债隔离（docs/spec/conventions.md §2.9）：负债是资产负债表减项，
    只在资金来源侧出现一次，不参与资产配置统计。
    """
    positions, assets = _load_user_assets(db, family_id, member_id)

    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    seen: set[str] = set()
    used_names: set[str] = set()

    detail_buckets, liability_details = _collect_buckets(db, family_id, assets, positions)
    totals = family_totals(db, family_id, positions=positions, assets=assets)
    total_assets = totals['total_assets']
    if total_assets <= 0:
        return {'nodes': [], 'links': []}

    net_worth = totals['net_worth']
    liability_sum = round(sum(liability_details.values()), 2)
    source_total = _build_funding_side(
        nodes,
        links,
        seen,
        used_names,
        liability_details,
        liability_sum,
        net_worth,
        total_assets,
    )

    positive = _balance_conservation(detail_buckets, source_total)
    if not positive:
        return {'nodes': [], 'links': []}

    _assemble_graph(nodes, links, seen, used_names, positive)
    return {'nodes': nodes, 'links': links}
