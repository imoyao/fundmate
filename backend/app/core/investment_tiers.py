# -*- coding: utf-8 -*-
"""投资分档（tier）：三层收益口径的唯一真相源。

## 这一层要解决什么

XIRR 是全账户一个数，回答不了两个不同的问题：

    「我主动选股 / 选基赚了多少」（投资水平）
    「我的活钱 / 稳健仓位赚了多少」（资金管理）

把两者混成一个年化，用户没法衡量自己的选品能力——2 万货基的 1.8% 会稀释掉
50 万权益仓的 48%。用户要的是**风险梯度上可比的三个数**：

    active  第一梯队：主动投资（股票 / ETF / 基金 / 可转债 / 加密 / 贵金属 / 投顾组合）
    stable  第二梯队：稳健与现金管理（银行理财 / 货基 / 逆回购 / 存款 / 现金）
    other   兜底：不进交易口径的持仓（指数 / 经理 / 房产 / 保险 / 静态 / 负债）
    all     全账户 = active ∪ stable ∪ other

## 三个易混淆维度，禁止互相代用

| 维度 | 定义处 | 用途 | 取值 |
|---|---|---|---|
| **tier** | 本模块 | 分层看收益 | active / stable / other |
| **是否算投资** | `asset_types.EXCLUDED_ASSET_TYPES` | XIRR 分子分母纳不纳入 | money_fund / reverse_repo / cash |
| **配置目标** | `constants.ALLOCATION_LABELS`（五笔钱） | 用户手工标注的配比目标 | liquid / stable / longterm / speculative / security |

三者**正交**，典型反例：

- **银行理财**：tier=stable（稳健梯队），但**不**在 EXCLUDED 里 ⇒ 它算投资、算投资收益。
  把 tier 当 EXCLUDED 用，会把理财收益错记成「现金管理收益」。
- **股票标成 liquid**：tier 仍按 asset_type 算 active，allocation 不影响分档。
  （allocation 是「我想放多少钱在这」，不是「这东西是什么」。）

## 为什么判据按 asset_type，不按 allocation

实测 2026-11-03 真实库 family 1：282 行持仓的 `allocation` **全部**是 `'longterm'`，
16 个账户的 `default_allocation` 除 1 个（住房=stable）外也全是 `'longterm'`。
用户从未标注过 ⇒ 按 allocation 分档会让所有资产落进同一档，表建了却恒等于「全账户」。

故主判据是 `asset_type`（自动、零维护）。`allocation` 只能作为后续的**用户覆盖项**，
不能当主判据——否则第一天就是错的。

## 新增 asset_type 时必须同步登记

`ASSET_TYPE_TIER` 必须覆盖 `ASSET_TYPE_VALUES` 全量。未登记会落进 `other`（不抛错，
避免阻断存量读写），但 `unregistered_asset_types()` 会把它们报出来，测试用例
`test_all_asset_types_are_registered` 以此钉住——新增品类忘了登记会直接红。

用集合差集而不是「遍历后断言非空」：后者在表整体为空时反而通过（AGENTS.md
「已登记类守卫禁止全文 includes」的同一条教训）。
"""

from __future__ import annotations

from app.core.asset_types import ASSET_TYPE_VALUES

# ── 分档取值（唯一权威字符串，禁止业务代码手写 'active' / 'stable'）──
TIER_ACTIVE = 'active'
TIER_STABLE = 'stable'
TIER_OTHER = 'other'

TIER_VALUES: tuple[str, ...] = (TIER_ACTIVE, TIER_STABLE, TIER_OTHER)

TIER_LABELS: dict[str, str] = {
    TIER_ACTIVE: '主动投资',
    TIER_STABLE: '稳健与现金管理',
    TIER_OTHER: '其他资产',
}

# 对用户暴露的收益口径（三层）。other 不作为独立口径展示：它装的是房产、保险这类
# 没有交易流水的资产，单独算年化没有意义；它只用来把 all 凑齐（见 tier_completeness）。
SCOPE_ALL = 'all'
TIER_SCOPES: tuple[str, ...] = (TIER_ACTIVE, TIER_STABLE, SCOPE_ALL)

# ── asset_type → tier 判据表 ──
ASSET_TYPE_TIER: dict[str, str] = {
    # ── 第一梯队：主动投资 ──
    # 判据是「收益由市场波动决定、且用户是主动选择标的」，不是「名字里有没有股」。
    'stock': TIER_ACTIVE,
    'etf': TIER_ACTIVE,
    # fund 默认主动投资：场外公募的主力是偏股 / 混合型。债基、货基不会落在这里——
    # 货基有 is_money_fund 标记（见 tier_of_position），债基在本仓没有独立 asset_type
    # （`bond` 是可转债，见下），按 asset_type 无法细分，接受这个粗糙度。
    'fund': TIER_ACTIVE,
    # bond 在本仓**特指可转债**（core/asset_types 模块 docstring 已钉死），
    # 不是国债 / 企业债。可转债股性强、波动等同正股，故归第一梯队而非稳健。
    # 若将来引入「纯债」，必须新增独立 asset_type，不能复用 bond。
    'bond': TIER_ACTIVE,
    'crypto': TIER_ACTIVE,
    # 贵金属（积存金 / 黄金 ETF / 实物金）：波动率介于股债之间，但它是「投资品」
    # 而非「现金管理工具」，与货基区别在于不保本。归 active 是**可争议项**，
    # 若将来用户认为该算稳健，改这一行即可（无需动任何消费方）。
    'precious_metal': TIER_ACTIVE,
    # 投顾组合：用户真实付钱买的一篮子产品，策略由投顾定但风险敞口是主动投资的。
    'portfolio': TIER_ACTIVE,
    # ── 第二梯队：稳健与现金管理 ──
    'money_fund': TIER_STABLE,
    'reverse_repo': TIER_STABLE,
    'bank_wealth': TIER_STABLE,
    'bank': TIER_STABLE,
    'cash': TIER_STABLE,
    # ── 兜底：不进交易口径 ──
    # index / manager 按设计不进 positions（见 core/asset_types 注释），登记在此只为让
    # 判据表完备——万一有脏数据落进来，也不会被算进主动投资。
    'index': TIER_OTHER,
    'manager': TIER_OTHER,
    'real_estate': TIER_OTHER,
    'insurance': TIER_OTHER,
    'static': TIER_OTHER,
    'liability': TIER_OTHER,
}


def tier_of_asset_type(asset_type: str | None) -> str:
    """asset_type → tier。未登记 / 空值归 other（不抛错，避免脏数据阻断读取）。"""
    if not asset_type:
        return TIER_OTHER
    return ASSET_TYPE_TIER.get(asset_type.strip().lower(), TIER_OTHER)


def tier_of_position(position) -> str:
    """持仓 → tier。**货基标记优先于 asset_type**。

    货基持仓的 `asset_type` 是 `'fund'`（`'money_fund'` 只出现在流水上，写入侧口径见
    `services/fund_utils`）⇒ 只看 asset_type 会把货基错分进第一梯队。
    实测真实库：231 行 fund 持仓里有 20 行 `is_money_fund=1`。

    这里只认 `is True`（而非 truthy）：SQL 三值逻辑下 `is_money_fund` 可能为 NULL
    （普通持仓），NULL 与 False 都表示「不是货基」，行为一致。
    """
    if getattr(position, 'is_money_fund', None) is True:
        return TIER_STABLE
    return tier_of_asset_type(getattr(position, 'asset_type', None))


def unregistered_asset_types() -> tuple[str, ...]:
    """尚未登记 tier 的 asset_type（正常应为空）。

    用「全量 − 已登记」的差集，而不是「有登记项」这类存在性检查：后者在判据表整体为空
    时反而通过，等于没守。新增 asset_type 后此函数会立刻报出来。
    """
    return tuple(t for t in ASSET_TYPE_VALUES if t not in ASSET_TYPE_TIER)


def tier_completeness() -> dict[str, int]:
    """各档登记的 asset_type 数量，供自检 / 文档用。

    `other` 必须 > 0 且 `active` + `stable` + `other` == 全量 —— 这就是「三层互斥且完备」
    的可验证形式（互斥由 dict 天然保证：一个 key 只能有一个 tier）。
    """
    counts = {tier: 0 for tier in TIER_VALUES}
    for tier in ASSET_TYPE_TIER.values():
        counts[tier] = counts.get(tier, 0) + 1
    return counts
