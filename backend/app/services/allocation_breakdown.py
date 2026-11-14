# -*- coding: utf-8 -*-
"""五笔钱（配置目标）统计出口的唯一实现（#3031 / G4）。

## WHY 独立成模块

``summary_service.get_distributions`` 与 ``get_position_groups`` 原先把
``alloc_map`` / ``allocation`` 分组都写成「只遍历 positions」，于是
**资产行整类对五笔钱零影响**（P0-1）：本机家庭总资产 338 万，五笔钱只见得到
持仓 66.9 万、且全挤在「长期增值」一档；账户现金即使录进 ``assets`` 也冒不出
「活钱」。成员边界与归置规则的真相源是 ``core/allocation_rules``（G2），
本模块只负责**按该规则把成员算进分布**，不复制任何 elif 链。

同时 ``summary_service.py`` 被 ``scripts/guard_service_size.py`` 冻结
（dev 基线 lines 1417 / max_func 107 / max_cc 17，只减不增；本批下沉后 1414），
故聚合实现必须外置。

## 成员边界（G0 冻结口径，`docs/design/allocation-governance.md` §三）

- 分母 = **持仓 + 非负债成员资产行**（``is_allocation_member``）；
- 房产 / 应收 / 固定资产 / 车辆 / 贵金属 / custom 属「未纳入」，进
  ``allocation_scope.excluded``，**不进任何桶**；
- 负债永不进分布（``conventions.md`` §2.9），只以 ``liabilities_total`` 单列；
- **账外 222 笔类现金流水（¥465,178.56）按用户 2026-11-12 拍板本轮不纳入分母**，
  故本模块**不读** transactions —— 将来放行时应在调用方把「已核实类现金」
  作为一笔显式成员金额传入，而不是在这里偷读流水。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from app.core.allocation_rules import (
    DEFAULT_ALLOCATION,
    SOURCE_GOVERNANCE,
    SOURCE_IMPORT,
    SOURCE_USER,
    derive_allocation,
    is_allocation_member,
)
from app.core.asset_types import normalize_major_category
from app.core.constants import ALLOCATION_LABELS, CATEGORY_META
from app.core.money import Money

_LIABILITY_KEY = 'liability'
_UNCLASSIFIED_ALLOC = '未分类'
_UNKNOWN_TYPE = '其他'

#: 这三个来源是「有人显式定过」，分布必须尊重存储值，不能被推导规则改写。
#: 与 ``scripts/backfill_allocation.py`` 的回填判据（只放 ``default``）互为镜像。
_PROTECTED_SOURCES = frozenset({SOURCE_USER, SOURCE_IMPORT, SOURCE_GOVERNANCE})


def asset_allocation_value(a: Any) -> str:
    """资产行归入哪一笔钱（返回枚举 key）。

    判据顺序即 G0 冻结的优先级链「用户显式设置 > 大类推导 > 默认值」：

    1. ``allocation_source`` 属受保护来源且存储值非空 → 用存储值；
    2. 否则按大类推导（``derive_allocation``，cash ⇒ ``liquid``）；
    3. 推导为 ``None``（投机类留人工）→ 回落到存储值，再回落 ``longterm``。

    调用方**必须先过滤负债**：``derive_allocation`` 对负债抛
    ``LiabilityAllocationError``，那是给「聚合侧漏过滤」准备的规则级守卫，
    本函数不替它兜底。
    """
    source = getattr(a, 'allocation_source', None)
    stored = getattr(a, 'allocation', None)
    if source in _PROTECTED_SOURCES and stored:
        return stored
    derived = derive_allocation(a.major_category)
    if derived:
        return derived
    return stored or DEFAULT_ALLOCATION


def asset_allocation_key(a: Any) -> str:
    """资产行的桶名（中文标签），与 `_pos_group_payload` 的 ``allocation_label`` 同源。"""
    return ALLOCATION_LABELS.get(asset_allocation_value(a), _UNCLASSIFIED_ALLOC)


def _category_label(major_category: str | None) -> str:
    label = CATEGORY_META.get(normalize_major_category(major_category), (_UNKNOWN_TYPE, None))[0]
    return label or _UNKNOWN_TYPE


def allocation_payload(
    positions: list[Any],
    assets: list[Any],
    *,
    pos_value: Callable[[Any], float],
    liabilities_total: float,
) -> dict[str, Any]:
    """五笔钱分布 + 成员边界说明（`/api/summary/distributions/` 的两个键）。

    ``pos_value`` 由调用方注入（持仓市值换算的唯一口径在
    ``position_valuation.market_value_cents``，本模块不许自己算第二个）。
    ``liabilities_total`` 同样来自 ``family_totals`` 这个唯一出口。

    **恒等关系**：``Σ allocation_distribution.value == allocation_scope.denominator``。
    两个值都由同一批已 round 到分位的输入相加得到，故可要求严格相等
    （测试见 ``tests/services/test_allocation_breakdown.py``）。
    """
    buckets: dict[str, float] = defaultdict(float)
    positions_total = 0.0
    for p in positions:
        mv = pos_value(p)
        positions_total += mv
        buckets[ALLOCATION_LABELS.get(p.allocation, p.allocation or DEFAULT_ALLOCATION)] += mv

    member_total = 0.0
    excluded: dict[str, float] = defaultdict(float)
    for a in assets:
        amount = Money.cents_to_yuan(a.amount)
        if amount <= 0 or a.major_category == _LIABILITY_KEY:
            continue
        if is_allocation_member(a.major_category):
            member_total += amount
            buckets[asset_allocation_key(a)] += amount
        else:
            # 「未纳入」必须显式可见：房产/应收 220 万若静默消失，用户会以为算错了
            excluded[_category_label(a.major_category)] += amount

    distribution = [
        {'name': k, 'value': round(v, 2)} for k, v in sorted(buckets.items(), key=lambda kv: -kv[1]) if round(v, 2) > 0
    ]
    excluded_rows = [
        {'name': k, 'value': round(v, 2)} for k, v in sorted(excluded.items(), key=lambda kv: -kv[1]) if round(v, 2) > 0
    ]
    return {
        'allocation_distribution': distribution,
        'allocation_scope': {
            'denominator': round(positions_total + member_total, 2),
            'excluded_total': round(sum(row['value'] for row in excluded_rows), 2),
            'excluded': excluded_rows,
            'liabilities_total': round(liabilities_total, 2),
            'buckets': _buckets_with_zeros(buckets),
        },
    }


def _buckets_with_zeros(buckets: dict[str, float]) -> list[dict[str, Any]]:
    """五笔钱**全档位**（含 0 值），顺序即 ``ALLOCATION_LABELS`` 的声明序。

    为什么不复用 ``allocation_distribution``：那是图表契约，``> 0`` 过滤是对的——
    饼图/桑基图不该画零值扇区。但首页「心理账户」卡要回答的是「我这五笔钱各是多少」，
    **空档本身就是信息**（保命钱为 0 是财务健康信号，静默不显示等于替用户藏了一件事）。

    故另开一个键而非改老键：改 ``allocation_distribution`` 会把 0 值扇区塞进所有图表。
    两键的恒等关系一致——``Σ buckets.value == allocation_scope.denominator``。

    ``key`` / ``label`` 一律由后端输出，前端只展示不翻译（``conventions.md`` §2.9）。
    兜底：存储值不在枚举内时，``buckets`` 字典的键是中文字面量（如「未分类」），
    此类条目追加在末尾，``key`` 与 ``label`` 同值。
    """
    known = set(ALLOCATION_LABELS.values())
    rows = [
        {'key': key, 'label': label, 'value': round(buckets.get(label, 0.0), 2)}
        for key, label in ALLOCATION_LABELS.items()
    ]
    rows.extend(
        {'key': name, 'label': name, 'value': round(value, 2)}
        for name, value in sorted(buckets.items(), key=lambda kv: -kv[1])
        if name not in known
    )
    return rows


def allocation_group_items(
    positions: list[Any],
    assets: list[Any],
    pos_payload: Callable[[Any], dict[str, Any]],
    asset_payload: Callable[[Any], dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    """`get_position_groups('allocation')` 的成员序列：持仓 + 非负债成员资产行。

    资产行的 payload 由调用方注入（``_asset_group_payload``），以便 items 里
    同时带上 ``allocation`` / ``allocation_label`` 供「活钱」下钻。
    负债与非成员大类一律不出现在序列里（零命中判据）。
    """
    items: list[tuple[str, dict[str, Any]]] = []
    for p in positions:
        key = ALLOCATION_LABELS.get(p.allocation, p.allocation or _UNCLASSIFIED_ALLOC)
        items.append((key, pos_payload(p)))
    for a in assets:
        if Money.cents_to_yuan(a.amount) <= 0 or a.major_category == _LIABILITY_KEY:
            continue
        if not is_allocation_member(a.major_category):
            continue
        items.append((asset_allocation_key(a), asset_payload(a)))
    return items
