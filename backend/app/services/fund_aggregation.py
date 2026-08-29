# -*- coding: utf-8 -*-
"""场外基金（含 E 账户）持仓跨账本聚合（#1101）。

聚合范式已下沉至 `services/position_aggregation.py`，与 #1132 场内证券**共用同一实现**，
本文件只保留「场外基金」的品类口径与薄封装入口，避免两份逻辑漂移。

#1133 结论要点：
- 页面顶部「数据日期」= 持仓快照日（导入对账日期 / Excel「份额日期」），
  取自 `position_import_meta.snapshot_date`，**不取**「持仓最新更新日期」；
- 管理人 / 分红方式 / 基金账户等产品信息同出自该表，零 schema 迁移；
- 原 `app`（交易前端）维度已收敛去掉，其本质即销售机构，属重复维度。
"""

from __future__ import annotations

from app.services.position_aggregation import _position_market_value_cents, aggregate_positions

# 场外基金口径：E账户仅覆盖场外份额，故聚合不含 ETF/LOF 等场内品种
FUND_ASSET_TYPES = ('fund', 'money_fund')

# 向后兼容：securities_aggregation 等模块曾从本文件导入该私有函数
__all__ = ['FUND_ASSET_TYPES', 'get_fund_aggregation', '_position_market_value_cents']


def get_fund_aggregation(
    session,
    family_id: int,
    dimension: str = 'product',
    **kwargs,
) -> dict:
    """聚合家族场外基金持仓。

    参数与返回值见 `position_aggregation.aggregate_positions`。
    dimension 支持 'product'（默认）与 'institution'。
    """
    return aggregate_positions(session, family_id, FUND_ASSET_TYPES, dimension, **kwargs)
