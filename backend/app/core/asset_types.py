# -*- coding: utf-8 -*-
"""资产类型（asset_type）与资产大类（major_category）标签的单一权威定义。

收口此前散落在多处的资产标签映射，避免前后端 / 各模块不一致：
- core/constants.TYPE_LABELS（资产类型标签）
- core/constants.ASSET_CATEGORY_LABELS（资产大类标签）
- watchlist/views._ASSET_TYPE_LABELS（仅 4 类的局部副本，已废弃）
- performance/constants.EXCLUDED_ASSET_TYPES（收益计算排除项）

所有需要「资产类型 / 大类 → 中文标签」的地方统一从此处取，禁止在视图 / 服务里
重复硬编码标签表。前端通过 GET /api/utils/enums 拉取本模块下发的两张映射，
禁止前端手抄第二份（见 frontend/src/composables/useEnumLabels.ts）。

维度说明（关键，避免混用）：
- asset_type：交易性持仓的细类，取值如 stock/etf/fund/bond/index/crypto/...
- major_category：通用资产（assets 表）的大类，取值如 cash/fixed/investment/
  receivable/liability/insurance/real_estate/precious_metal/custom
两者是不同维度，标签表也不同。注意 bond 属于 asset_type 维度。

bond 澄清（#1171 枚举一致性收口）：本系统的 bond 即可转债（convertible bond，
可在券商账户交易的可转债），不是广义债券。故 label 固定为「可转债」。纯债券
（国债 / 企业债）不在持仓范围。此前 core/constants 误写为「债券」、watchlist 写为
「可转债」，本次统一为「可转债」，并在唯一来源处定调，禁止再改回「债券」。
"""

from __future__ import annotations

# ── 资产类型（asset_type）标签：唯一权威映射 ──
ASSET_TYPE_LABELS: dict[str, str] = {
    'stock': '股票',
    'etf': 'ETF',
    'fund': '基金',
    'bond': '可转债',
    'index': '指数',
    'crypto': '加密货币',
    'money_fund': '货币基金',
    'reverse_repo': '逆回购',
    'cash': '现金',
    'bank': '银行',
    'real_estate': '房产',
    'insurance': '保险',
    'precious_metal': '贵金属',
    'static': '其他',
    'liability': '负债',
}

# ── 资产大类（major_category）标签：唯一权威映射 ──
ASSET_CATEGORY_LABELS: dict[str, str] = {
    'cash': '流动资金',
    'fixed': '固定资产',
    'investment': '投资理财',
    'receivable': '应收款',
    'liability': '负债',
    'insurance': '保险',
    'real_estate': '房产',
    'precious_metal': '贵金属',
    'custom': '自定义',
    'bank_wealth': '银行理财',
    'advisory': '投顾',
    'trust': '信托',
    'private_fund': '私募',
    'wealth_insurance': '理财型保险',
}

# ── 投资理财的细分子类（#1354 大类收敛）──
# 历史背景：银行理财 / 投顾 / 信托 / 私募 / 理财型保险 曾被建成与「投资理财」平级的
# major_category，但它们本质同属投资理财，副作用有三：
#   1. 盘点页大类标签栏从 6 个膨胀到 11 个；
#   2. 这 5 类从未配置任何子类型入口，点进去「快捷操作」为空，是纯占位；
#   3. 资产分布 / 大类汇总里各成一档，把本该合并的投资理财拆得七零八落。
# 收敛口径（兼容存量，不做数据迁移）：
#   - 写入侧：新的细分走 minor_category，major_category 统一为 investment；
#   - 读取侧：normalize_major_category() 把历史 5 类归一为 investment，
#     聚合 / 展示自动合并，存量数据零迁移、零丢失。
# 注意：ASSET_CATEGORY_LABELS 仍保留这 5 个键，供存量明细的标签回退使用，
# 禁止在「大类」维度新增同类细分。
# 投资理财细分子类的标签直接复用 ASSET_CATEGORY_LABELS，避免两处标签漂移
# （历史上这 5 个键本就是 ASSET_CATEGORY_LABELS 的「投资理财」平级大类，收敛后
# 作为 minor_category 的键 + 标签来源）。
INVESTMENT_MINOR_CATEGORIES: dict[str, str] = {
    k: ASSET_CATEGORY_LABELS[k] for k in ('bank_wealth', 'advisory', 'trust', 'private_fund', 'wealth_insurance')
}

# 「投资理财」在盘点 / 汇总口径下包含的全部 major_category 取值（含历史细分类）。
# 用 .keys() 显式展开字典键，可读性优于 *dict 解包（#1355 AI review）。
INVESTMENT_CATEGORIES: frozenset[str] = frozenset(INVESTMENT_MINOR_CATEGORIES.keys()) | {'investment'}

# ── 不参与投资收益 / 资产配置口径计算的资产类型 ──
EXCLUDED_ASSET_TYPES: tuple[str, ...] = ('money_fund', 'reverse_repo', 'cash')

# 兼容历史引用：core/constants.TYPE_LABELS 曾为资产类型标签的别名
TYPE_LABELS = ASSET_TYPE_LABELS


def get_asset_type_label(asset_type: str | None) -> str:
    """资产类型 → 中文标签；空值返回空串，未知类型原样返回（上游应保证类型合法）。"""
    if not asset_type:
        return ''
    return ASSET_TYPE_LABELS.get(asset_type, asset_type)


def get_asset_category_label(major_category: str | None) -> str:
    """资产大类 → 中文标签；空值返回空串，未知大类原样返回。"""
    if not major_category:
        return ''
    return ASSET_CATEGORY_LABELS.get(major_category, major_category)


def normalize_major_category(major_category: str | None) -> str | None:
    """把历史上的「投资理财细分大类」归一为 investment，其余原样返回。

    仅用于聚合 / 筛选口径（盘点页大类、资产分布、大类汇总）；明细展示仍用原始
    major_category，保证存量数据可追溯。
    """
    if major_category in INVESTMENT_MINOR_CATEGORIES:
        return 'investment'
    return major_category


def get_investment_minor_label(minor_category: str | None) -> str:
    """投资理财细分子类 → 中文标签；空值返回空串，未知值原样返回。"""
    if not minor_category:
        return ''
    return INVESTMENT_MINOR_CATEGORIES.get(minor_category, minor_category)
