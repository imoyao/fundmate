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
    AdvisorProfileRequest,
    FundRiskRankingRequest,
    FundRiskTypesRequest,
    IndexProfileRequest,
    ManagerProfileRequest,
    ProductResolveRequest,
    ProductTrendRequest,
    RelatedSymbolsRequest,
    StockProfileRequest,
)
from app.services.advisor_profile import build_advisor_profile
from app.services.fund_holdings_detail import build_fund_holdings_detail
from app.services.fund_performance import build_fund_performance
from app.services.fund_profile import build_fund_profile
from app.services.fund_risk_ranking import SORTABLE_METRICS, list_by_metric, list_fund_types
from app.services.index_profile import build_index_profile
from app.services.manager_holdings import build_manager_holdings
from app.services.manager_profile import build_manager_profile
from app.services.product_identity import resolve_product_identity
from app.services.product_trend import RANGE_DAYS, fetch_product_trend
from app.services.related_symbols import build_related_symbols
from app.services.stock_profile import build_stock_profile
from app.services.trade_timeline import build_trade_timeline, empty_trade_timeline

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
    """基金资料聚合（#1968）。字段缺失降级为 null，口径见 `services/fund_profile.build_fund_profile`。"""
    fund_code = (request.args.get('code') or '').strip()
    with closing(market_session_factory()()) as db:
        try:
            data = build_fund_profile(db, fund_code)
        except ValueError as e:
            abort(400, str(e))
    if data is None:
        abort(404, f'基金不存在：{fund_code}')
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/fund-performance/')
def fund_performance():
    """基金业绩与风险（#2029 卡 B · 详情页业绩与风险卡）。

    一次算完区间收益切面（近1周~成立以来）+ 最大回撤（近3年）+ 年化波动率（近1年），
    前端一次请求拿到表现卡全部字段。口径与自选域同源 ``daily_worth.acc_nav``，
    业务日走 ``today_shanghai()``。

    货基分支：货币基金无日涨跌 / 回撤口径，改返万份收益 + 七日年化
    （``money_fund_daily_worth``），不显净值型指标（设计卡 §4.2⑧）。

    字段缺失一律回 ``null``，前端降级「—」（设计 §6 诚实降级，不编造）。
    """
    fund_code = (request.args.get('code') or '').strip()
    with closing(market_session_factory()()) as db:
        try:
            data = build_fund_performance(db, fund_code)
        except ValueError as e:
            abort(400, str(e))
    if data is None:
        abort(404, f'基金不存在：{fund_code}')
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/fund-holdings-detail/')
def fund_holdings_detail():
    """基金行业配置 + 持仓明细（#2029 卡 C · 详情页行业配置卡 + 持仓明细卡）。

    两张卡共用一个端点：同属「持仓穿透」语义，且「取最新报告期 + 选口径」的
    逻辑完全一致（``fund_position_job`` 一次写两张表）。拆成两个请求只会让
    详情页多一次往返，而两者能同时为空的情形极少。

    口径不在本端点定，全部下沉到 ``services/fund_holdings_detail.py``：
    行业配置按 ``scheme`` 分区（csrc 主口径 / gics 单列，**禁止跨体系相加**），
    持仓明细同期内 ``full`` 优先并下发 ``basis_label``（季报前十大 ≠ 半年报全量）。

    「基金不存在」返 404；「存在但无披露数据」返 ``applicable: false`` —— 两者
    是不同语义，前端据此分别渲染 404 页与空态卡。
    """
    fund_code = (request.args.get('code') or '').strip()
    with closing(market_session_factory()()) as db:
        try:
            data = build_fund_holdings_detail(db, fund_code)
        except ValueError as e:
            abort(400, str(e))
    if data is None:
        abort(404, f'基金不存在：{fund_code}')
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/stock-profile/')
def stock_profile():
    """个股资料（#1963）。口径见 `services/stock_profile.build_stock_profile`。"""
    query: StockProfileRequest = parse_query(StockProfileRequest)

    with closing(market_session_factory()()) as db:
        try:
            data = build_stock_profile(db, query.symbol, market=query.market)
        except ValueError as e:
            abort(400, str(e))

    if data is None:
        abort(404, f'证券不存在：{query.symbol}')
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/index-profile/')
def index_profile():
    """指数资料聚合（#2028 · 详情页指数详情区块）：资料 + 官方估值 + 历史分位一次取完。

    与同族端点同一硬规则（#1968 / #1969）：三张指数表（``index_catalog`` /
    ``index_valuations`` / ``index_valuation_baselines``）均无 API 出口，拼不出
    首屏就在本域补端点；放 products 域的理由同 ``fund-profile``——服务的是「详情页」
    这一个页面。

    分位在读路径现算（乐咕月频近 5 年窗口，#1407 拍板），样本不足或无基线的指数
    回 ``null``，前端诚实降级「—」。股息率分位本期恒为 ``null``（乐咕无该序列）。
    """
    query: IndexProfileRequest = parse_query(IndexProfileRequest)

    with closing(market_session_factory()()) as db:
        try:
            data = build_index_profile(db, query.symbol)
        except ValueError as e:
            abort(400, str(e))

    if data is None:
        abort(404, f'指数不存在：{query.symbol}')
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/manager-profile/')
def manager_profile():
    """基金经理资料（#167）。字段与降级规则见 `services/manager_profile.build_manager_profile`。"""
    query: ManagerProfileRequest = parse_query(ManagerProfileRequest)

    with closing(market_session_factory()()) as db:
        try:
            data = build_manager_profile(db, query.mgr_code, fund_limit=query.fund_limit)
        except ValueError as e:
            abort(400, str(e))

    if data is None:
        abort(404, f'基金经理不存在：{query.mgr_code}')
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/manager-holdings/')
def manager_holdings():
    """基金经理持仓（#167）。聚合口径见 `services/manager_holdings.build_manager_holdings`。"""
    query: ManagerProfileRequest = parse_query(ManagerProfileRequest)

    with closing(market_session_factory()()) as db:
        try:
            data = build_manager_holdings(db, query.mgr_code, fund_limit=query.fund_limit)
        except ValueError as e:
            abort(400, str(e))

    if data is None:
        abort(404, f'基金经理不存在：{query.mgr_code}')
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/advisor-profile/')
def advisor_profile():
    """投顾平台资料。口径见 `services/advisor_profile.build_advisor_profile`。"""
    query: AdvisorProfileRequest = parse_query(AdvisorProfileRequest)

    with closing(market_session_factory()()) as db:
        try:
            data = build_advisor_profile(db, query.code)
        except ValueError as e:
            abort(400, str(e))

    if data is None:
        abort(404, f'投顾组合不存在：{query.code}')
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/related-symbols/')
def related_symbols():
    """跨渠道关联标的（#1976 · 详情页关联标的区块）：指数 ↔ 场内 ETF ↔ 场外联接。

    关系表`channel_links` 存有向关系，此处按裸代码双向查，对任一端都返回「另一侧」，
    前端无需判断方向（与自选页角标同一套规则）。

    与自选域的取舍：`watchlist_display._apply_channel_link_fields` 逻辑同源但挂在列表页
    批量 enrich 链上（签名是「往 out dict 塞字段」）。详情页是单标的按需取数，走自选域
    会破坏域边界，故独立成 `services/related_symbols.py`，取数规则保持一致。

    **无关联不返回 404**：关系靠名称匹配建立（覆盖率约 66.4%，缺口见 #1419），
    无关联是正常情形而非错误，前端据此降级 `—`。
    """
    query: RelatedSymbolsRequest = parse_query(RelatedSymbolsRequest)

    with closing(market_session_factory()()) as db:
        data = build_related_symbols(db, query.symbol)

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


@bp.get('/fund-risk-ranking/')
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


@bp.get('/fund-risk-types/')
def fund_risk_types():
    """列出**当前有榜**的基金小类（#167）。为什么单开端点见
    `services/fund_risk_ranking.list_fund_types` 的 docstring。"""
    query: FundRiskTypesRequest = parse_query(FundRiskTypesRequest)
    with closing(market_session_factory()()) as db:
        data = list_fund_types(db, caliber_version=query.caliber_version)
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/trade-timeline/')
def product_trade_timeline():
    """持仓交易时间线（#2171 · 详情页走势叠加买卖点 / 成本线）。流水是私有数据：
    未登录 / 无流水均返回空序列（可选登录，与 /resolve/ 一致）；重放口径见 service。
    """
    symbol = (request.args.get('symbol') or '').strip()
    if not symbol:
        abort(400, '缺少 symbol 参数')
    ledger_raw = (request.args.get('ledger_id') or '').strip()
    ledger_id = int(ledger_raw) if ledger_raw.isdigit() else None

    if not _is_authenticated():
        return jsonify({'data': empty_trade_timeline(symbol), 'message': 'ok'})

    with closing(user_session_factory()()) as db:
        try:
            data = build_trade_timeline(db, symbol=symbol, family_id=get_family_id(), ledger_id=ledger_id)
        except ValueError as e:
            abort(400, str(e))
    return jsonify({'data': data, 'message': 'ok'})