# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/9
# File : views.py
# app/domains/products/views.py
"""产品域视图层：只做 HTTP 编排（判定的业务规则全在 services/product_identity.py）。

视图层职责边界见 `docs/spec/decisions.md`（2026-09-19「视图层职责边界」，#1606）：
入参解析 → 调 service → 组响应信封。本文件零 `db.query`、零业务分支。
"""

from contextlib import closing

from apiflask import APIBlueprint
from flask import abort, g, jsonify, request

from app.core.auth import get_family_id
from app.core.db_factory import market_session_factory, user_session_factory
from app.core.validation import parse_query
from app.domains.products.schemas import (
    ProductResolveRequest,
    ProductTrendRequest,
    StockProfileRequest,
)
from app.services.fund_profile import build_fund_profile
from app.services.product_identity import resolve_product_identity
from app.services.product_trend import RANGE_DAYS, fetch_product_trend
from app.services.stock_profile import build_stock_profile

bp = APIBlueprint('products', __name__, url_prefix='/api/products')


def _is_authenticated() -> bool:
    """当前请求是否已登录。

    判据是 ``g.current_user`` 是否存在。本端点登记在 ``core/auth.py`` 的
    ``OPTIONAL_AUTH_PREFIXES``（**不是** ``PUBLIC_PREFIXES``）：中间件会尝试解析
    身份，解析到就注入 ``g.current_user`` / ``g.family_id``，解析不到则匿名放行。
    若登记成白名单，中间件压根不解析身份，``g.current_user`` 永远不存在，
    登录用户也拿不到 ``in_watchlist`` / ``has_position``——等于把该功能砍了。

    刻意不用 ``auth_enabled()``：那是「是否强制门禁」的配置开关，与「本次请求
    有没有登录」是两回事。
    """
    return hasattr(g, 'current_user')


@bp.get('/resolve/')
def resolve_product():
    """产品身份解析（#1963）：symbol → 权威 asset_type / 展示名 / 自选与持仓状态。

    - 路径上的 ``asset_type`` 只作入口提示，**以后端判定为准**（设计 §3.3）；
    - 未登录只回公开字段：``in_watchlist`` / ``has_position`` 为 ``null``；
    - 解析不出品类 → 404（前端走空态，而非白屏）。
    """
    query: ProductResolveRequest = parse_query(ProductResolveRequest)
    authenticated = _is_authenticated()

    # 双域会话：watchlist/positions 在 user 域，funds/securities/… 在 market 域，
    # 生产下是独立引擎，必须分别取（详见 services/product_identity 模块 docstring）。
    with closing(user_session_factory()()) as user_db, closing(market_session_factory()()) as market_db:
        try:
            result = resolve_product_identity(
                user_db,
                market_db,
                symbol=query.symbol,
                market=query.market,
                venue=query.venue,
                asset_type_hint=query.asset_type,
                family_id=get_family_id() if authenticated else None,
                include_user_state=authenticated,
            )
        except ValueError as e:
            abort(400, str(e))

    if result is None:
        abort(404, f'未识别的产品代码：{query.symbol}')
    return jsonify({'data': result, 'message': 'ok'})


@bp.get('/fund-profile/')
def fund_profile():
    """基金资料聚合（#1968）：详情页首屏 + 资料区块所需字段一次取完。

    为什么放 products 域而不放 funds 域（两条理由都成立）：

    1. **架构归属**：本端点服务的是「详情页」，与同族的 ``/resolve/``（身份解析）、
       ``/trend/``（走势）是同一族；funds 域管的是基金基础操作（搜索 / 净值 / 费率同步）；
    2. **视图层厚度守卫**：funds 视图已顶在冻结基线上（217 行），再加端点会被守卫拦下。
       products 域是新文件，限额宽裕（lines ≤ 400 / query ≤ 10 / 单函数 ≤ 60）。

    为何要新增而不让前端拼既有端点：**日涨跌**要「最近两日净值」自己算（funds 域无端点
    直出），**基金经理**也没有对应端点（``/managers/search/`` 是按经理名模糊搜，与「某只
    基金有哪些经理」无关；该关系本身在 ``fund_managers`` 关联表里是完整的，funds 域缺的
    只是把它读出来的出口）。详见 ``services/fund_profile.py`` 模块 docstring。
    """
    fund_code = (request.args.get('code') or '').strip()
    with closing(market_session_factory()()) as db:
        try:
            data = build_fund_profile(db, fund_code)
        except ValueError as e:
            abort(400, str(e))
    if data is None:
        abort(404, f'基金不存在：{fund_code}')
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/stock-profile/')
def stock_profile():
    """股票资料聚合（#1969 · 详情页股票详情区块）：基本资料 + 区间行情一次取完。

    与 `/trend/` 的分工（**不是**平行链路，是互补，避免前端重复拉数）：

    - 走势曲线复用已上线的 `/trend/`（前端 `getProductTrend`），本端点**不返回序列**，
      否则同一区块会出现两条行情取数链路；
    - 本端点只补 `/trend/` 给不出的东西：**区间高低**与**基本资料**。区间高低需要在
      最近 N 个交易日上做聚合，而现有唯一的高低价出口 `securities/<symbol>/price-range/`
      是「指定单日」语义（#948 记账回填用），拿到 60 日高低得拉 60 次日请求或把明细
      整段搬到浏览器算——前者拖慢首屏，后者违反「明细不在前端算」的数据策略。

    故按 #1968 的同一硬规则「拼不出首屏就在本卡内补端点」，由后端一次查完。字段缺失
    一律回 `null`，前端降级为「—」（设计 §6 诚实降级），不编造占位值。

    为何放 products 域而不放 securities 域：与 `/resolve/`、`/trend/` 同族，服务的是
    「详情页」这一个页面（理由同 `fund_profile`）。
    """
    query: StockProfileRequest = parse_query(StockProfileRequest)

    with closing(market_session_factory()()) as db:
        try:
            data = build_stock_profile(db, query.symbol, market=query.market)
        except ValueError as e:
            abort(400, str(e))

    if data is None:
        abort(404, f'证券不存在：{query.symbol}')
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/trend/')
def product_trend():
    """产品历史走势序列（#1967 · 详情页走势区块）。

    与 ``/api/watchlist/trends/`` 的区别：本端点**带日期轴**且用区间语义（1M/3M/6M/1Y），
    因为详情页要画坐标轴、并给出「数据日期」口径脚注；trends 面向列表页迷你图，只要数值数组。

    降级：品类本身没有序列数据源（指数 / 基金经理 / 投顾组合）时返回**空序列**而非 404——
    「该品类不提供走势」与「产品不存在」是两件事，前端要分别渲染空态。
    """
    query: ProductTrendRequest = parse_query(ProductTrendRequest)

    with closing(market_session_factory()()) as db:
        try:
            result = fetch_product_trend(
                db,
                symbol=query.symbol,
                asset_type=query.asset_type,
                range_key=query.range_,
            )
        except ValueError as e:
            abort(400, str(e))

    if result is None:
        result = {
            'symbol': (query.symbol or '').strip().upper(),
            'kind': '',
            'dates': [],
            'values': [],
            'source': '',
            'range': query.range_,
            'requested_days': RANGE_DAYS[query.range_],
            'available_days': 0,
        }
    return jsonify({'data': result, 'message': 'ok'})
