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
}

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
