# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/16
# File : fund_risk_views.py
# app/domains/products/fund_risk_views.py
"""产品域 · 基金风险榜视图（#167 两端点）。

从 `products/views.py` 拆出——该文件（dev 版）已 395 行、触新文件厚度守卫上限
400，两端点回植即超限，故独立成文件（仿 `importers/e_account_views.py` 先例）。
路由路径不变：`/api/products/fund-risk-{ranking,types}/`，API 契约零变化。
视图层职责边界同 views.py（`decisions.md` 2026-09-19「视图层职责边界」，#1606）：
入参解析 → 调 service → 组响应信封。
"""

from contextlib import closing

from apiflask import APIBlueprint
from flask import abort, jsonify

from app.core.db_factory import market_session_factory
from app.core.validation import parse_query
from app.domains.products.schemas import FundRiskRankingRequest, FundRiskTypesRequest
from app.services.fund_risk_ranking import SORTABLE_METRICS, list_by_metric, list_fund_types

# 与 products/views.py 的 bp 同前缀（不同 blueprint 名，Flask 端点不冲突），
# 两端点路径保持 /api/products/... 不变。
fund_risk_bp = APIBlueprint('products_fund_risk', __name__, url_prefix='/api/products')


@fund_risk_bp.get('/fund-risk-ranking/')
def fund_risk_ranking():
    """按风险指标筛同类基金（#167）。口径 / 为什么 `fund_type_id` 必填见
    `services/fund_risk_ranking.list_by_metric` 的 docstring——视图只做入参校验与编排。"""
    query: FundRiskRankingRequest = parse_query(FundRiskRankingRequest)

    metric = (query.metric or '').strip()
    if metric not in SORTABLE_METRICS:
        abort(400, f'不支持的排序指标：{metric}')

    ascending = None
    if query.order:
        order = query.order.strip().lower()
        if order not in ('asc', 'desc'):
            abort(400, f'order 只能是 asc / desc：{query.order}')
        ascending = order == 'asc'

    with closing(market_session_factory()()) as db:
        data = list_by_metric(
            db,
            fund_type_id=query.fund_type_id,
            metric=metric,
            limit=query.limit,
            ascending=ascending,
            include_distorted=bool(query.include_distorted),
        )
    return jsonify({'data': data, 'message': 'ok'})


@fund_risk_bp.get('/fund-risk-types/')
def fund_risk_types():
    """列出**当前有榜**的基金小类（#167）。为什么单开端点见
    `services/fund_risk_ranking.list_fund_types` 的 docstring。"""
    query: FundRiskTypesRequest = parse_query(FundRiskTypesRequest)
    with closing(market_session_factory()()) as db:
        data = list_fund_types(db, caliber_version=query.caliber_version)
    return jsonify({'data': data, 'message': 'ok'})
