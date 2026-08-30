# -*- coding: utf-8 -*-
"""场内证券（股票/ETF/可转债）持仓跨账本聚合（#1132）。

聚合范式复用 `services/position_aggregation.py`（与 #1101 场外基金**同一实现**），
本文件只保留「场内证券」的品类口径与薄封装入口，避免两份逻辑漂移。
设计见 docs/working-notes/securities-aggregation-design-2026-08-29.md（D1~D4 已确认）。

市值口径与 #1101 完全一致：份额(份) × 当前价(元) × 汇率 → 整数「分」，禁止浮点直接累积。
"""

from __future__ import annotations

from app.services.position_aggregation import aggregate_positions

# #1132 范围（D1 已确认）：股票 + ETF + 可转债，即全部场内证券
SECURITIES_ASSET_TYPES = ('etf', 'bond', 'stock')

__all__ = ['SECURITIES_ASSET_TYPES', 'get_securities_aggregation']


def get_securities_aggregation(
    session,
    family_id: int,
    dimension: str = 'product',
    **kwargs,
) -> dict:
    """聚合家族场内证券持仓。

    参数与返回值见 `position_aggregation.aggregate_positions`。
    dimension 支持 'product'（默认）与 'institution'。
    """
    return aggregate_positions(session, family_id, SECURITIES_ASSET_TYPES, dimension, **kwargs)
