# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/23 12:24
# File : backend/app/services/summary_service.py
"""仪表盘聚合与桑基图数据服务."""

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Type

from sqlalchemy import func, or_

from app.core.asset_types import normalize_major_category
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
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.summary.models import AssetSnapshot
from app.domains.transactions.models import Transaction

# #863 口径 A：现金等价物（货基/逆回购）持仓聚合分类单点工具
from app.services.fund_utils import CASH_EQUIVALENT_ASSET_TYPES, is_cash_equivalent_position
from app.services.pnl_service import (
    family_realized_pnl_cents,
    net_invested_by_position,
    position_pnl_cents,
    realized_pnl_by_position,
)

# 🔄 市值口径收口（#1174）：仪表盘市值统一委托唯一口径，override / balance / nav 一并覆盖
from app.services.position_valuation import market_value_cents

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
    """统一加载当前家庭的资产数据（持仓 + 通用资产），按 family_id 隔离（D1）。

    持仓只取 ownership_status='active'（§12.3）：E账户影子记录（shadow，ledger_id=NULL）
    仅对账不参与总资产，过滤后 ledger_id 关联不变，避免暂存区记录虚增总资产。
    """
    positions = db.query(Position).filter(Position.family_id == family_id, Position.ownership_status == 'active').all()
    assets = db.query(Asset).filter(Asset.family_id == family_id).all()
    return positions, assets


# ---------------------------------------------------------------------------
# 孤儿货基/逆回购流水净额口径（position_service 对 money_fund/reverse_repo
# 只建孤立流水：position_id=None、entry_status='orphan'、amount=净额分，不建持仓）。
# 四处聚合（get_summary_data / get_sankey_data / get_account_groups /
# get_overview_stats）统一经 orphan_money_fund_net_by_ledger 并入，保证只计一次。
# 判定用 position_id IS NULL 而非 entry_status='orphan'：新建路径两者等价，
# 但历史导入器早期数据的 entry_status 可能不统一，position_id IS NULL 更可靠、更宽松。
# #863 D1：本金净额口径排除 is_income 收益行——收益只进收益桶，不膨胀本金。
# ---------------------------------------------------------------------------
_ORPHAN_FLOW_ASSET_TYPES = ('money_fund', 'reverse_repo')
_ORPHAN_FLOW_POSITIVE_TYPES = ('buy', 'deposit')
_ORPHAN_FLOW_NEGATIVE_TYPES = ('sell', 'withdraw')


def _not_income_filter(cls) -> Any:
    """SQLAlchemy 过滤：is_income 列未标记或为 False（排除收益行）。"""
    return or_(cls.is_income.is_(None), cls.is_income.is_(False))


def orphan_money_fund_net_by_ledger(db: Session, family_id: int) -> dict[int, int]:
    """孤儿货基/逆回购流水**本金净额**（分），按 ledger_id 归组，None → 0（游离）。

    口径：asset_type IN ('money_fund','reverse_repo') 且 position_id IS NULL
    且**非收益行**（is_income 不为 True，见 #863 D1）；
    净额 = buy/deposit 金额 − sell/withdraw 金额（amount 为分，全程整数运算，
    禁止裸 float 乘除）。净额为 0 的组直接丢弃，避免产生空分组。
    返回 {ledger_id: 净额分}：ledger 有效的净额并入对应账户，悬空（None/已删）
    归 0 键由各调用方按「游离」处理。
    """
    rows = (
        db.query(Transaction.ledger_id, Transaction.txn_type, Transaction.amount)
        .filter(
            Transaction.family_id == family_id,
            Transaction.asset_type.in_(_ORPHAN_FLOW_ASSET_TYPES),
            Transaction.position_id.is_(None),
            _not_income_filter(Transaction),
        )
        .all()
    )
    net_map: dict[int, int] = {}
    for lid, txn_type, amount in rows:
        amount = amount or 0
        if txn_type in _ORPHAN_FLOW_POSITIVE_TYPES:
            delta = amount
        elif txn_type in _ORPHAN_FLOW_NEGATIVE_TYPES:
            delta = -amount
        else:
            continue  # dividend/tax 等不计入净额
        key = lid or 0
        net_map[key] = net_map.get(key, 0) + delta
    return {k: v for k, v in net_map.items() if v != 0}


def orphan_money_fund_income_by_ledger(db: Session, family_id: int) -> dict[int, int]:
    """孤儿货基/逆回购**渠道收益累计**（分，#863 D1 收益桶），按 ledger_id 归组。

    口径：asset_type IN ('money_fund','reverse_repo') 且 position_id IS NULL
    且 is_income=True（渠道导入的收益发放流水，如支付宝「收益发放」映射 deposit）。
    方向同本金净额：buy/deposit 为正、sell/withdraw 为负（纠错类收益行）。
    收益桶只并入总资产，**禁止**进入本金/孤儿净额口径。
    """
    rows = (
        db.query(Transaction.ledger_id, Transaction.txn_type, Transaction.amount)
        .filter(
            Transaction.family_id == family_id,
            Transaction.asset_type.in_(_ORPHAN_FLOW_ASSET_TYPES),
            Transaction.position_id.is_(None),
            Transaction.is_income.is_(True),
        )
        .all()
    )
    income_map: dict[int, int] = {}
    for lid, txn_type, amount in rows:
        amount = amount or 0
        if txn_type in _ORPHAN_FLOW_POSITIVE_TYPES:
            delta = amount
        elif txn_type in _ORPHAN_FLOW_NEGATIVE_TYPES:
            delta = -amount
        else:
            continue
        key = lid or 0
        income_map[key] = income_map.get(key, 0) + delta
    return {k: v for k, v in income_map.items() if v != 0}


def get_summary_data(db: Session, family_id: int = 1) -> dict[str, Any]:
    """返回仪表盘聚合数据（总资产、总负债、净资产、盈亏拆分、市场分布）

    盈亏口径见 `services/pnl_service.py`（#1183）：
    - realized   已实现：卖出结转盈亏 + 现金分红，以**流水**为事实源（清仓后仍可查）
    - unrealized 未实现：持仓浮动盈亏 = 市值 − 成本基数
    - total      总盈亏 = realized + unrealized
    """
    positions, assets = _load_user_assets(db, family_id)

    total_assets = 0.0
    market_distribution: dict[str, float] = {}

    # 两个 map 均按 family 一次性查出；禁止在循环里逐持仓查流水（N+1）
    realized_map = realized_pnl_by_position(db, family_id)
    invested_map = net_invested_by_position(db, family_id)

    # 一次遍历 positions，完成市值、未实现盈亏、市场分布
    unrealized_cents = 0
    for p in positions:
        rate = EXCHANGE_RATES.get(p.currency, 1.0)
        # 市值（#1174 收口）：委托唯一口径，override / balance / nav 三种情形在函数内统一处理
        market_value = Money.cents_to_yuan(market_value_cents(p, rate=rate))
        total_assets += market_value

        unrealized_cents += position_pnl_cents(
            p,
            rate=rate,
            realized_cents=realized_map.get(p.id, 0),
            net_invested=invested_map.get(p.id, 0),
        )['unrealized_pnl_cents']

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

    # 孤儿货基/逆回购流水净额并入总资产（流动资金；净额可为负，按负数处理）
    orphan_net = sum(orphan_money_fund_net_by_ledger(db, family_id).values())
    total_assets += Money.cents_to_yuan(orphan_net)
    # #863 D1 收益桶：渠道 is_income 流水（已确认收益）并入总资产，单独累计、不膨胀本金
    income_net = sum(orphan_money_fund_income_by_ledger(db, family_id).values())
    total_assets += Money.cents_to_yuan(income_net)

    # 已实现盈亏以流水为事实源，含已清仓持仓的结转盈亏与孤儿分红
    realized_cents = family_realized_pnl_cents(db, family_id)

    return {
        'total_assets_cny': round(total_assets, 2),
        'total_liabilities_cny': round(total_liabilities, 2),
        'net_assets_cny': round(total_assets - total_liabilities, 2),
        'realized_pnl_cny': round(Money.cents_to_yuan(realized_cents), 2),
        'unrealized_pnl_cny': round(Money.cents_to_yuan(unrealized_cents), 2),
        'total_pnl_cny': round(Money.cents_to_yuan(realized_cents + unrealized_cents), 2),
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
    # #863 口径 A：现金等价物持仓市值（货基/逆回购）独立统计，分类归「流动资金」
    cash_equiv_total = 0.0

    for p in positions:
        rate = EXCHANGE_RATES.get(p.currency, 1.0)
        mv = Money.min_unit_to_shares(p.quantity) * Money.price_units_to_yuan(p.current_price) * rate
        if mv <= 0:
            continue

        investment_total += mv
        if is_cash_equivalent_position(p):
            # #863 口径 A：货基/逆回购持仓市值归「流动资金/cash」而非「投资理财」
            cash_equiv_total += mv

        # 五笔钱分配
        alloc = p.allocation or _DEFAULT_ALLOC
        alloc_map[alloc] += mv

        # 产品类型明细（翻译为中文标签）
        alloc_label = ALLOCATION_LABELS.get(alloc, alloc)
        type_name = p.asset_type or _UNKNOWN_TYPE
        display_name = TYPE_LABELS.get(type_name, type_name)
        alloc_type_map[alloc_label][display_name] += mv

    # 将投资理财总额归入大类（扣除现金等价物持仓，货基不占「投资理财」）
    category_totals[_INVESTMENT_KEY] += investment_total - cash_equiv_total
    total_assets += investment_total

    # 现金等价物持仓市值 + 孤儿流水本金净额 + 渠道收益 并入「流动资金/cash」大类
    orphan_net = sum(orphan_money_fund_net_by_ledger(db, family_id).values())
    income_net = sum(orphan_money_fund_income_by_ledger(db, family_id).values())
    category_totals['cash'] += cash_equiv_total + Money.cents_to_yuan(orphan_net + income_net)
    total_assets += Money.cents_to_yuan(orphan_net + income_net)

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
        market_value = Money.min_unit_to_shares(p.quantity) * Money.price_units_to_yuan(p.current_price) * rate
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

    # 3. 孤儿货基/逆回购流水按 ledger_id 归组（本金净额 + #863 渠道收益；无 ledger 归「游离」）
    ledger_names = {led.id: led.name for led in db.query(Ledger).filter(Ledger.family_id == family_id).all()}
    orphan_map = orphan_money_fund_net_by_ledger(db, family_id)
    income_map = orphan_money_fund_income_by_ledger(db, family_id)
    merged: dict[int, int] = {}
    for _lid in set(orphan_map) | set(income_map):
        merged[_lid] = orphan_map.get(_lid, 0) + income_map.get(_lid, 0)
    for lid, net_cents in merged.items():
        acc = ledger_names.get(lid, '游离') if lid else '游离'
        groups[acc]['total'] += Money.cents_to_yuan(net_cents)
        groups[acc]['count'] += 1

    # 4. 转换为列表并排序 (金额大的在上)
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
        # 口径分叉修复（#1183 附带修复，同时是 #1181 验收第 3 条的前提）：
        # 原先这里裸算「份额 × 快照价」，绕过唯一市值口径，
        # 导致 balance 模式（份额/价格为 0、市值靠 market_value_override）恒算成 0，
        # 且与 get_summary_data 的仪表盘总额对不上（decisions.md D1 未收口的尾巴）。
        # 快照金额正是由本函数聚合而来，不修则无净值产品永远进不了资产快照。
        rate = EXCHANGE_RATES.get(p.currency, 1.0)
        return Money.cents_to_yuan(market_value_cents(p, rate=rate))

    type_map: dict[str, float] = defaultdict(float)
    alloc_map: dict[str, float] = defaultdict(float)
    market_map: dict[str, float] = defaultdict(float)
    account_map: dict[str, float] = defaultdict(float)
    positions_total_mv = 0.0
    cash_equiv_total = 0.0
    for p in positions:
        mv = _pos_mv(p)
        positions_total_mv += mv
        if is_cash_equivalent_position(p):
            # #863 口径 A：货基/逆回购持仓市值统计入「流动资金」分类（非「投资理财」）
            cash_equiv_total += mv
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
            # #1354：银行理财/投顾/信托/私募/理财型保险归一到「投资理财」，不再各成一档
            label = CATEGORY_META.get(normalize_major_category(a.major_category), (_UNKNOWN_TYPE, None))[0]
            category_map[label] += amount
    # 持仓市值归大类：普通持仓入「投资理财」，货基/逆回购入「流动资金」（#863 口径 A）
    category_map[_INVESTMENT_LABEL] += positions_total_mv - cash_equiv_total
    if cash_equiv_total > 0:
        category_map[CATEGORY_META['cash'][0]] += cash_equiv_total
    # 孤儿流水本金净额 + 渠道收益（#863 D1 收益桶）并入流动资金分类与总资产
    orphan_net = sum(orphan_money_fund_net_by_ledger(db, family_id).values())
    income_net = sum(orphan_money_fund_income_by_ledger(db, family_id).values())
    cash_flow_yuan = Money.cents_to_yuan(orphan_net + income_net)
    if cash_flow_yuan != 0:
        category_map[CATEGORY_META['cash'][0]] += cash_flow_yuan
    total_assets += cash_flow_yuan

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


def get_ledger_distributions(db: Session, family_id: int = 1) -> dict[int, dict[str, float]]:
    """按账户聚合的总资产 / 总负债 / 净资产（元），供账户级快照落库（#1181）。

    口径与家庭级 `get_distributions` 严格对齐：
    - 持仓市值一律走唯一口径 `position_valuation.market_value_cents`
      （含 override / balance / nav 三种情形），因此无净值产品能正确计入；
    - 孤儿货基/逆回购流水净额按 ledger 归组并入对应账户总资产。

    Returns:
        {ledger_id: {'total_assets', 'total_liabilities', 'net_worth'}}；
        无账户归属（ledger_id 为 NULL）的条目统一归到哨兵键 0。
    """
    positions, assets = _load_user_assets(db, family_id)

    totals: dict[int, dict[str, float]] = {}

    def _bucket(ledger_id):
        key = ledger_id or 0
        if key not in totals:
            totals[key] = {'total_assets': 0.0, 'total_liabilities': 0.0, 'net_worth': 0.0}
        return totals[key]

    for p in positions:
        rate = EXCHANGE_RATES.get(p.currency, 1.0)
        _bucket(p.ledger_id)['total_assets'] += Money.cents_to_yuan(market_value_cents(p, rate=rate))

    for a in assets:
        amount = Money.cents_to_yuan(a.amount)
        if amount <= 0:
            continue
        bucket = _bucket(a.ledger_id)
        if a.major_category == _LIABILITY_KEY:
            bucket['total_liabilities'] += amount
        else:
            bucket['total_assets'] += amount

    # 孤儿货基/逆回购流水按账户并入：本金净额 + #863 渠道收益桶（与家庭级口径一致）
    orphan_map = orphan_money_fund_net_by_ledger(db, family_id)
    income_map = orphan_money_fund_income_by_ledger(db, family_id)
    for _lid in set(orphan_map) | set(income_map):
        _bucket(_lid or 0)['total_assets'] += Money.cents_to_yuan(orphan_map.get(_lid, 0) + income_map.get(_lid, 0))

    for bucket in totals.values():
        bucket['net_worth'] = bucket['total_assets'] - bucket['total_liabilities']
    return {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in totals.items()}


# ---------------------------------------------------------------------------
# 维度分组（批次 2b）：持仓/资产按产品类型/账户/配置目标分组，含 items 明细
# ---------------------------------------------------------------------------
_POS_GROUP_DIMENSIONS = ('type', 'account', 'allocation')


def _pos_group_payload(p: Position) -> dict[str, Any]:
    """持仓分组明细：展示单位 + 标签，市值/盈亏按汇率后端换算（唯一出口）。"""
    rate = EXCHANGE_RATES.get(p.currency, 1.0)
    shares = Money.min_unit_to_shares(p.quantity)
    price = Money.price_units_to_yuan(p.current_price)
    cost = Money.price_units_to_yuan(p.avg_price)
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
        'asset_type': normalize_major_category(a.major_category),
        'type_label': CATEGORY_META.get(normalize_major_category(a.major_category), (_UNKNOWN_TYPE, None))[0],
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


def _upsert_snapshot(db: Session, *, family_id: int, ledger_id: int | None, snapshot_date: date) -> AssetSnapshot:
    """按 (family_id, ledger_id, snapshot_date) 幂等 upsert 一条快照（#1181）。

    家庭级行 ledger_id 为 NULL。唯一约束用 `COALESCE(ledger_id, -1)`，
    故 NULL 也参与去重——同一天重复写入是覆盖而非新增。
    """
    q = db.query(AssetSnapshot).filter(
        AssetSnapshot.family_id == family_id,
        AssetSnapshot.snapshot_date == snapshot_date,
    )
    if ledger_id is None:
        q = q.filter(AssetSnapshot.ledger_id.is_(None))
    else:
        q = q.filter(AssetSnapshot.ledger_id == ledger_id)

    row = q.first()
    if row is None:
        row = AssetSnapshot(family_id=family_id, ledger_id=ledger_id, snapshot_date=snapshot_date)
        db.add(row)
    return row


def family_pnl_cents(db: Session, family_id: int = 1) -> dict[str, int]:
    """家庭级三段盈亏（分），口径与 pnl_service 一致，供家庭级快照落库（#1220）。

    realized    = 全流水 realized_pnl 合计（含已清仓持仓结转与孤儿分红）；
    unrealized  = 各 active 持仓（市值 − 成本基数）之和；
    total       = realized + unrealized。
    """
    positions, _ = _load_user_assets(db, family_id)
    realized_map = realized_pnl_by_position(db, family_id)
    invested_map = net_invested_by_position(db, family_id)
    unrealized = 0
    for p in positions:
        rate = EXCHANGE_RATES.get(p.currency, 1.0)
        unrealized += position_pnl_cents(
            p,
            rate=rate,
            realized_cents=realized_map.get(p.id, 0),
            net_invested=invested_map.get(p.id, 0),
        )['unrealized_pnl_cents']
    realized = family_realized_pnl_cents(db, family_id)
    return {
        'realized_pnl_cents': realized,
        'unrealized_pnl_cents': unrealized,
        'total_pnl_cents': realized + unrealized,
    }


def get_ledger_pnl(db: Session, family_id: int = 1) -> dict[int, dict[str, int]]:
    """按账户聚合三段盈亏（分），供账户级快照落库（#1220）。

    口径与 get_ledger_distributions 严格对齐：仅遍历 active 持仓，按 ledger_id 归组；
    无账户归属归哨兵键 0（不单独立行）。已实现盈亏取自该账户 active 持仓的流水结转。
    """
    positions, _ = _load_user_assets(db, family_id)
    realized_map = realized_pnl_by_position(db, family_id)
    invested_map = net_invested_by_position(db, family_id)
    totals: dict[int, dict[str, int]] = {}
    for p in positions:
        rate = EXCHANGE_RATES.get(p.currency, 1.0)
        pnl = position_pnl_cents(
            p,
            rate=rate,
            realized_cents=realized_map.get(p.id, 0),
            net_invested=invested_map.get(p.id, 0),
        )
        key = p.ledger_id or 0
        bucket = totals.setdefault(key, {'realized_pnl_cents': 0, 'unrealized_pnl_cents': 0})
        bucket['realized_pnl_cents'] += pnl['realized_pnl_cents']
        bucket['unrealized_pnl_cents'] += pnl['unrealized_pnl_cents']
    for b in totals.values():
        b['total_pnl_cents'] = b['realized_pnl_cents'] + b['unrealized_pnl_cents']
    return totals


def _money_fund_ledgers_with_holdings(db: Session, family_id: int) -> set[int]:
    """当日有货基表达（孤儿净额非 0 或现金等价持仓）的账户集合（#863 P1-5）。

    仅纳入 active 且 quantity>0 的持仓：已平仓 / NULL 状态的旧货基持仓不应被误判为
    「当日有货基表达」，否则会在快照里写入 money_fund_income_cents（实际已无本金）。
    """
    from sqlalchemy import or_

    net_map = orphan_money_fund_net_by_ledger(db, family_id)
    ledgers = {lid for lid, v in net_map.items() if v != 0 and lid}
    pos_rows = (
        db.query(Position.ledger_id)
        .filter(
            Position.family_id == family_id,
            Position.ledger_id.isnot(None),
            Position.ownership_status == 'active',
            Position.quantity > 0,
            or_(
                Position.asset_type.in_(CASH_EQUIVALENT_ASSET_TYPES),
                Position.is_money_fund.is_(True),
            ),
        )
        .distinct()
        .all()
    )
    for (lid,) in pos_rows:
        if lid:
            ledgers.add(lid)
    return ledgers


def _money_fund_daily_income_cents(db: Session, family_id: int, target: date, ledger_id: int | None = None) -> int:
    """当日货基收益（分）：委托 money_fund_income 单日计算（自动预估，#863 P1-5 展示用）。

    仅作展示列写入快照，不参与 total_assets（总资产含的是渠道 is_income 收益桶）。
    """
    from app.services.money_fund_income import calculate_money_fund_income

    result = calculate_money_fund_income(
        db,
        start_date=target,
        end_date=target,
        scope='ledger' if ledger_id is not None else 'family',
        ledger_id=ledger_id,
        family_id=family_id,
    )
    series = result.get('daily_series') or []
    # 按 target 日期显式过滤，避免依赖返回顺序取到非目标日的数据（AI review #49）
    income = next((item.get('income') for item in series if item.get('date') == target.isoformat()), None)
    # income 可能为 None（当日无万份收益），避免 Money.yuan_to_cents(None) 抛异常
    return Money.yuan_to_cents(income) if income is not None else 0


def write_asset_snapshot(db: Session, family_id: int = 1, snapshot_date: str | None = None) -> dict[str, Any]:
    """记录当日资产快照（幂等 upsert）。

    金额从 get_distributions 聚合而来（元），落库转为整数分（Money 精度）。
    snapshot_date 可选，默认上海时区当日；用于历史回填，须为 YYYY-MM-DD。
    #863 P1-5：家庭/账户行同批写入当日货基收益（money_fund_income_cents，展示用）。
    """
    from app.core.time_utils import now_shanghai

    if snapshot_date is None:
        target = now_shanghai().date()
    else:
        target = datetime.strptime(snapshot_date, '%Y-%m-%d').date()

    dist = get_distributions(db, family_id)
    family_pnl = family_pnl_cents(db, family_id)
    mf_ledgers = _money_fund_ledgers_with_holdings(db, family_id)
    # 每个货基账户当日收益只计算一次（避免账户级循环内 N+1 重复调用 calculate_money_fund_income）
    mf_income_by_ledger: dict[int, int] = {
        lid: _money_fund_daily_income_cents(db, family_id, target, lid) for lid in mf_ledgers
    }

    # 家庭级快照（ledger_id 为 NULL）：既有行为，支撑总资产走势 + 盈亏序列
    family_row = _upsert_snapshot(db, family_id=family_id, ledger_id=None, snapshot_date=target)
    family_row.total_assets = Money.yuan_to_cents(dist['total_assets'])
    family_row.total_liabilities = Money.yuan_to_cents(dist['total_liabilities'])
    family_row.net_worth = Money.yuan_to_cents(dist['net_worth'])
    family_row.realized_pnl_cents = family_pnl['realized_pnl_cents']
    family_row.unrealized_pnl_cents = family_pnl['unrealized_pnl_cents']
    family_row.total_pnl_cents = family_pnl['total_pnl_cents']
    family_row.money_fund_income_cents = sum(mf_income_by_ledger.values()) if mf_ledgers else None

    # 账户级快照（#1181）：同一天为每个有数据的账户各落一行，支撑账户维度走势
    ledger_pnl = get_ledger_pnl(db, family_id)
    for ledger_id, totals in get_ledger_distributions(db, family_id).items():
        if not ledger_id:
            # 哨兵键 0 = 无账户归属（游离资产/持仓）。0 不是合法账户 id，落行会
            # 污染账户维度序列；这部分金额已计入家庭级快照，故跳过不单独立行。
            continue
        row = _upsert_snapshot(db, family_id=family_id, ledger_id=ledger_id, snapshot_date=target)
        row.total_assets = Money.yuan_to_cents(totals['total_assets'])
        row.total_liabilities = Money.yuan_to_cents(totals['total_liabilities'])
        row.net_worth = Money.yuan_to_cents(totals['net_worth'])
        lp = ledger_pnl.get(
            ledger_id,
            {'realized_pnl_cents': 0, 'unrealized_pnl_cents': 0, 'total_pnl_cents': 0},
        )
        row.realized_pnl_cents = lp['realized_pnl_cents']
        row.unrealized_pnl_cents = lp['unrealized_pnl_cents']
        row.total_pnl_cents = lp['total_pnl_cents']
        row.money_fund_income_cents = mf_income_by_ledger.get(ledger_id)

    db.commit()
    return _snapshot_payload(family_row)


def _snapshot_payload(s: AssetSnapshot) -> dict[str, Any]:
    """快照单条输出：金额转元，同比百分比由读取侧计算填充。"""
    return {
        'id': s.id,
        'ledger_id': s.ledger_id,
        'snapshot_date': s.snapshot_date.isoformat(),
        'total_assets': round(Money.cents_to_yuan(s.total_assets), 2),
        'total_liabilities': round(Money.cents_to_yuan(s.total_liabilities), 2),
        'net_worth': round(Money.cents_to_yuan(s.net_worth), 2),
        'realized_pnl': round(Money.cents_to_yuan(s.realized_pnl_cents), 2),
        'unrealized_pnl': round(Money.cents_to_yuan(s.unrealized_pnl_cents), 2),
        'total_pnl': round(Money.cents_to_yuan(s.total_pnl_cents), 2),
        # #863 P1-5：当日货基收益（元，自动预估展示用）；无货基时为 0.0
        'money_fund_income': round(Money.cents_to_yuan(s.money_fund_income_cents or 0), 2),
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
    ledger_id: int | None = None,
) -> list[dict[str, Any]]:
    """查询资产快照列表（按日期升序），并计算每条相对上月同期 / 去年同期的同比。

    ledger_id（#1181）：
    - 传入 → 返回该**账户级**快照序列（`ledger_id = X`）
    - 不传 → 返回**家庭级**快照序列（`ledger_id IS NULL`），保持既有行为不变

    基准取「对应基准日当天或之前最近一条」快照，找不到则为 None：
    - monthly_change_pct：以上月同日为基准
    - yearly_change_pct：以去年同期为基准
    """
    q = db.query(AssetSnapshot).filter(AssetSnapshot.family_id == family_id)
    # 家庭级与账户级快照共存一张表，靠 ledger_id 是否为 NULL 区分。
    # 不传时只取家庭级，否则同一天的账户行会与家庭行混进同一个走势被重复计算。
    if ledger_id is None:
        q = q.filter(AssetSnapshot.ledger_id.is_(None))
    else:
        q = q.filter(AssetSnapshot.ledger_id == ledger_id)
    if start_date:
        q = q.filter(AssetSnapshot.snapshot_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        q = q.filter(AssetSnapshot.snapshot_date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    rows = q.order_by(AssetSnapshot.snapshot_date.asc()).all()

    results: list[dict[str, Any]] = []
    for row in rows:
        monthly_base = _nearest_before(db, family_id, _shift_months(row.snapshot_date, -1), ledger_id)
        yearly_base = _nearest_before(db, family_id, _shift_months(row.snapshot_date, -12), ledger_id)
        payload = _snapshot_payload(row)
        payload['monthly_change_pct'] = _pct_change(payload['net_worth'], _net_of(monthly_base))
        payload['yearly_change_pct'] = _pct_change(payload['net_worth'], _net_of(yearly_base))
        results.append(payload)
    return results


def _nearest_before(db: Session, family_id: int, boundary: date, ledger_id: int | None = None) -> Any | None:
    """取指定日期当天或之前最近的一条快照，作为同比基准。

    同比基准必须与当前序列**同一作用域**（家庭级 vs 账户级），否则会拿家庭总额
    去比账户走势，同比数字没有意义（#1181）。ledger_id 为 None 表示家庭级作用域。
    """
    q = db.query(AssetSnapshot).filter(AssetSnapshot.family_id == family_id, AssetSnapshot.snapshot_date <= boundary)
    if ledger_id is None:
        q = q.filter(AssetSnapshot.ledger_id.is_(None))
    else:
        q = q.filter(AssetSnapshot.ledger_id == ledger_id)
    return q.order_by(AssetSnapshot.snapshot_date.desc()).first()


def _net_of(row: Any | None) -> float | None:
    return None if row is None else round(Money.cents_to_yuan(row.net_worth), 2)


def scan_cross_ledger_duplicates(db: Session, family_id: int) -> list[dict]:
    """#1066 / #1020：family 级「幽灵重复」扫描（非阻断预警）。

    背景：#1065 将导入去重作用域降为 ledger 级后，用户可能无意中对同一份交割单
    在多个账本各导一次，造成交易/收益翻倍。本扫描在 family 级识别「同一笔交易
    疑似出现在多个账本」的组，供前端软提示横幅指名来源账本。

    判定口径（务实近似）：
    - transactions 表未持久化 source，无法反解精确 import_hash，故用内容指纹
      (confirm_date, symbol, txn_type, amount) 作为近似判重键；
    - 同一指纹落在 >=2 个不同 ledger_id 的「成功」交易，视为疑似跨账本重复；
    - 排除 ledger_id 为 NULL 的影子记录与 status != 'success' 的行；
    - 占位历史哈希（legacy|*）天然唯一不会触发，无需特判。
    - 注意：持仓（positions）不做此扫描——同一标的跨账本持有两个持仓可能是
      合法分散持有，误报率高；重复风险主要在交易流水层。

    返回：每组 {symbol, confirm_date, txn_type, amount_yuan, ledger_ids, ledger_names, count}
    """
    ledger_name_map = {led.id: led.name for led in db.query(Ledger).filter(Ledger.family_id == family_id).all()}

    # B4 修复：用 SQL 聚合直接出重复组，避免把 family 级全量交易拉进内存再分组
    # （数据量大时全表 .all() 会 OOM/慢）。SQLite 支持 group_concat(distinct ...)，
    # 一次性拿到每组的去重 ledger_id 列表。
    dup_rows = (
        db.query(
            Transaction.confirm_date,
            Transaction.symbol,
            Transaction.txn_type,
            Transaction.amount,
            func.count(Transaction.id).label('cnt'),
            func.group_concat(func.distinct(Transaction.ledger_id)).label('ledger_ids_csv'),
        )
        .filter(
            Transaction.family_id == family_id,
            Transaction.ledger_id.isnot(None),
            Transaction.status == 'success',
        )
        .group_by(
            Transaction.confirm_date,
            Transaction.symbol,
            Transaction.txn_type,
            Transaction.amount,
        )
        .having(func.count(func.distinct(Transaction.ledger_id)) >= 2)
        .all()
    )

    result: list[dict] = []
    for row in dup_rows:
        ledger_ids = sorted({int(x) for x in (row.ledger_ids_csv or '').split(',') if x})
        result.append(
            {
                'symbol': row.symbol,
                'confirm_date': row.confirm_date.isoformat() if row.confirm_date else None,
                'txn_type': row.txn_type,
                'amount_yuan': round(Money.cents_to_yuan(row.amount), 2),
                'ledger_ids': ledger_ids,
                'ledger_names': [ledger_name_map.get(lid, f'账本{lid}') for lid in ledger_ids],
                'count': row.cnt,
            }
        )

    # 按涉及账本数、笔数降序，最可疑的排前面
    result.sort(key=lambda x: (len(x['ledger_ids']), x['count']), reverse=True)
    return result
