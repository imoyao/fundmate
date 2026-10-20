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
from app.core.database import get_db
from app.core.db_factory import market_session_factory, user_session_factory
from app.core.entitlements import get_pro_status_for_family, require_pro_feature
from app.core.validation import parse_query
from app.domains.products.schemas import (
    AdvisorProfileRequest,
    FundRiskRankingRequest,
    FundRiskTypesRequest,
    IndexEtfCompareRequest,
    IndexProfileRequest,
    ManagerProfileRequest,
    ProAllocationRequest,
    ProductResolveRequest,
    ProductTrendRequest,
    ProInsightRequest,
    ProRiskRequest,
    ProStatusRequest,
    RelatedSymbolsRequest,
    StockProfileRequest,
)
from app.services.advisor_profile import build_advisor_profile
from app.services.etf_compare import build_etf_compare
from app.services.fund_holdings_detail import build_fund_holdings_detail
from app.services.fund_performance import build_fund_performance
from app.services.fund_profile import build_fund_profile
from app.services.fund_risk_ranking import (
    SORTABLE_METRICS,
    list_by_metric,
    list_fund_types,
    user_flags_for_codes,
)
from app.services.index_metrics import build_index_returns, build_index_weights
from app.services.index_profile import build_index_profile
from app.services.manager_holdings import build_manager_holdings
from app.services.manager_profile import build_manager_profile
from app.services.pro_allocation import build_symbol_pro_allocation
from app.services.pro_insight import build_symbol_pro_insight
from app.services.pro_risk import build_symbol_pro_risk
from app.services.product_identity import resolve_product_identity
from app.services.product_pro_status import build_pro_status
from app.services.product_trend import empty_product_trend, fetch_product_trend
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


@bp.get('/index-returns/')
def index_returns():
    """指数阶段性收益 + 年化波动率（#2278 · 详情页指数区块）。

    与 ``/index-profile/`` 同域同规则：服务详情页这一个页面。数据是**按需抓的
    外部日线**（中证官网优先 / 腾讯兜底，见 ``index_metrics`` 模块说明），服务端
    现算六窗口收益 + 年化波动后即弃，不入库；TTL 缓存挡重复外部请求。外部源
    全空 → 200 + 全 ``null``（前端逐项「—」），仅名录未命中才 404。
    """
    query: IndexProfileRequest = parse_query(IndexProfileRequest)

    with closing(market_session_factory()()) as db:
        try:
            data = build_index_returns(db, query.symbol)
        except ValueError as e:
            abort(400, str(e))

    if data is None:
        abort(404, f'指数不存在：{query.symbol}')
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/index-weights/')
def index_weights():
    """指数十大权重 + 前十大集中度（#2278 · 详情页指数区块）。

    数据源 akshare ``index_stock_cons_weight_csindex``（中证月频口径），按需抓 +
    TTL 缓存 + 不入库。接口失败 / 码族不适用 → 200 + 空权重形态（``top10: []``、
    其余 ``null``），前端整块降级「—」；仅名录未命中才 404。
    """
    query: IndexProfileRequest = parse_query(IndexProfileRequest)

    with closing(market_session_factory()()) as db:
        try:
            data = build_index_weights(db, query.symbol)
        except ValueError as e:
            abort(400, str(e))

    if data is None:
        abort(404, f'指数不存在：{query.symbol}')
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/index-etf-compare/')
def index_etf_compare():
    """指数详情页关联 ETF 对比表（#2275 · P0）：净值 / 当日涨幅 / 成交额 / 区间涨跌幅 / 跟踪差。

    数据策略与 `/index-returns/` 同款：**按需抓 + TTL 缓存 + 不入库 + 可降级**——
    关联 ETF 清单来自本地 ``channel_links``，净值（``fund_etf_fund_daily_em``）、
    当日快照（新浪 ``fund_etf_category_sina``）、逐只日线（腾讯）均按需外呼，
    整体 30min 缓存。任一字段失败 → 该字段 ``null`` 前端「—」，**不阻塞整表**；
    无关联 ETF → 200 + ``rows: []``（正常情形，覆盖率边界见 #1419）；
    仅名录未命中才 404。
    """
    query: IndexEtfCompareRequest = parse_query(IndexEtfCompareRequest)

    with closing(market_session_factory()()) as db:
        try:
            data = build_etf_compare(db, query.symbol)
        except ValueError as e:
            abort(400, str(e))

    if data is None:
        abort(404, f'指数不存在：{query.symbol}')
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/manager-profile/')
def manager_profile():
    """基金经理资料聚合（#1970 · 详情页经理详情区块）：资料 + 任职基金列表一次取完。

    反向于 `/fund-profile/`（那只回答「某只基金有哪些经理」），此处回答「某位经理管过
    哪些基金」。funds 域无对应端点，故按 #1968 / #1969 的同一硬规则在本域补出口。

    入参用 `mgr_code` 而非姓名：`managers` 实测 119 组重名（最多 6 位同名），
    姓名不是唯一键。放 products 域的理由与同族端点一致——服务的是详情页这一个页面。

    任职起止 / 管理规模 / 任期回报已在 #1970 扩展中接入：`sum_scale` / `best_return`
    由 `ak.fund_manager_em()` 透传落库，`appointment_date` 由该接口「累计从业时间」反推
    （实测 4358/4358 成功；⚠️ 误差 ≤1 天，东财统计截止日未知，不可宣称精确到日），
    `start_date` / `end_date` 来自天天基金 F10 `jjjl` 表 A。

    ⚠️ 转换层不落地在本端点，而在 `services/tenure_display.py`：存原始值、回中文可读文本，
    每个换算值附 `basis` + `raw` 供前端显示口径；**不返回颜色**（配色由前端令牌决定）。
    仍有值缺失时回 `null`，由前端降级「—」（设计 §6 诚实降级，不编造）。
    """
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
    """基金经理代表作的前十大重仓（#1970 扩展 · 详情页经理区块）。

    **为什么单独开一个端点而不塞进 ``manager-profile``**：``fund_holdings`` 要按
    ``fund_code`` 查最新报告期，是一次独立的重查询；经理区块首屏并不总需要重仓
    （没有关联基金、或该基金未到披露期时为空态），塞在一起会让「不关心重仓的用户」
    也承担这份开销。拆开后前端可按需决定发不发。

    入参与 ``manager-profile`` 完全一致（复用 ``ManagerProfileRequest``）：
    ``mgr_code`` 而非姓名 —— 库内119 组重名，姓名不是唯一键。

    **口径透传**：``basis`` / ``basis_label`` / ``report_period`` 必须下发，
    前端要能告诉用户这是「季报前十大」还是「半年报全量」—— 否则「只披露 10 只」
    会被误读成「只买了 10 只」。

    **风格标签（#2044）**：``style_labels[]``（``{dim, key, label, basis}``）挂在本
    端点而非首屏 ``manager-profile``——标签描述的是代表作、与重仓同源同期，且要查
    同一批持仓表；数据不足的维度**缺席**而非回 null，后端不返回颜色（配色由前端令牌决定）。
    """
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
    """投顾组合资料聚合（#1975 · 详情页投顾组合区块）：组合档案 + 可得指标一次取完。

    **为什么补这个出口**：`advisor_portfolios` 的档案与指标字段此前**没有任何端点返回** ——
    funds 域只有 `advisors/<code>/holdings/` 与 `advisors/<code>/adjusts/`，它们回答
    「持什么、调过什么」，回答不了「这是个什么组合」，而详情页首屏要的正是后者。

    放 products 域的理由同 `fund-profile` / `manager-profile`：服务的是**同一个详情页**。
    持仓与调仓**复用已有端点**（前端并发取），本端点不重复搬数据 —— 只额外给出两者的
    条数，让前端据此决定那一块要不要渲染、请求要不要发（实测调仓只覆盖 16/105 个组合）。

    **字段可得性**（本机真实库 105 个组合实测）：`org_name` / `risk_level` / 区间收益 /
    回撤 / 波动率 / 夏普 填充率 91~100%，可直接展示；而 `strategy_type` / `cum_return` /
    `running_days` / `benchmark` / `excess_return` 为 **0%**、`host` **1.9%**、
    `return_ytd` **2.9%** —— 一律回 `null`，由前端降级「—」（设计 §6 诚实降级，不编造）。
    """
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
    ``start`` 为显式起始日（#2171 建仓期），给定时忽略档位。

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
                start_date=query.start,
            )
        except ValueError as e:
            abort(400, str(e))

    if result is None:
        # 品类无序列数据源（指数/基金经理/投顾组合）→ 空序列降级。
        # 响应形态由 service 给出（#1606：视图只做编排，不内联业务规则）
        result = empty_product_trend(query.symbol, query.range_, query.start)
    return jsonify({'data': result, 'message': 'ok'})


def _family_ranking_flags() -> tuple[set, set]:
    """当前家庭的 (持仓代码集, 自选代码集)；未登录两个空集。

    #167 持仓体检定位：快照目标池本就是「持仓 ∪ 自选」（fund_risk_metrics_job），
    标记让榜单回答「我持有的那只排第几」。登录判定 + 双域会话与 /resolve/、
    /trade-timeline/ 同模式；查询口径在 services（user_flags_for_codes）。
    """
    if not _is_authenticated():
        return set(), set()
    with closing(user_session_factory()()) as user_db:
        return user_flags_for_codes(user_db, family_id=get_family_id())


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

    holding_codes, watchlist_codes = _family_ranking_flags()

    with closing(market_session_factory()()) as db:
        data = list_by_metric(
            db,
            fund_type_id=query.fund_type_id,
            metric=metric,
            limit=query.limit,
            ascending=ascending,
            include_distorted=bool(query.include_distorted),
            holding_codes=holding_codes,
            watchlist_codes=watchlist_codes,
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


@bp.get('/pro/')
def pro_status():
    """高级洞察 Pro 状态位（#2272 骨架 → #2324 接入权益）。

    形状沿用一期契约（见 ``services/product_pro_status.py``），
    ``paywall_required`` 由家庭权益驱动；骨架/权益合并/契约说明都在 service。
    """
    query: ProStatusRequest = parse_query(ProStatusRequest)
    family_id = get_family_id() if _is_authenticated() else None
    entitlements = get_pro_status_for_family(family_id) if family_id else None
    data = build_pro_status(query.symbol, query.asset_type, entitlements)
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/pro-insight/')
@require_pro_feature('pro-insight')
def pro_insight():
    """Pro 模块一「深度绩效与归因」——账户级指标聚合（#994 Phase 2 → #2324 接入权益校验）。

    聚合 ``calculate_symbol_xirr``（#1972，资金加权年化）+ ``build_symbol_behavior``
    （Phase 0，FIFO 配对自算的行为画像），全部基于**用户自己的**持仓与流水
    （家庭作用域 ``get_family_id()``）。两服务 symbol 收敛 / 资产类型过滤同一真相源。

    - 无账户数据 → ``has_account_data=false``（正常形态，前端渲染引导，不编数字）；
    - 权益校验：装饰器 @require_pro_feature('pro-insight') 拦截未开通家庭（403 统一信封）。

    会话用**路由会话**（``get_db()``）而非 ``market_session_factory``：#2311 首版
    误用单域工厂，而本端点经 ``calculate_symbol_xirr`` 同时读 user 域
    （positions/transactions）与 market 域（securities/price_history/daily_worth）——
    dev 单库下两域同文件故本地与测试全绿，**双库生产（Turso + Supabase）下
    market 引擎没有 transactions 表，端点必 500**。路由会话逐语句按
    ``DATA_DOMAIN_REGISTRY`` 分派引擎（#1608），单/双库都正确。
    """
    query: ProInsightRequest = parse_query(ProInsightRequest)
    with get_db() as db:
        data = build_symbol_pro_insight(db, query.symbol, family_id=get_family_id(), asset_type=query.asset_type)
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/pro-risk/')
@require_pro_feature('pro-risk')
def pro_risk():
    """Pro 模块二「偏离与风险控制」——单标的 BIAS + 波动率 + VaR（#994 Phase 2 → #2324 接入权益校验）。

    聚合三块：**BIAS**（既有 bias 引擎，刘晨明 LOGBIAS，与温度计同口径）、
    **波动率 + VaR 95%**（``analytics/var.py`` 历史模拟，序列经
    ``fetch_product_trend('1Y')``，与详情页走势/``volatility_1y`` 同源同窗）、
    **账户级 VaR¥**（``calculate_symbol_xirr`` 持仓市值 × VaR%）。

    - 块级自治：基金级指标不依赖账户数据，逐块 ``available`` + ``reason``，
      前端逐块渲染或降级（没有模块一那样的总闸门 ``has_account_data``）；
    - 无持仓 → ``account.has_position=false``，不出 ``var_95_yuan``（不拿虚构
      市值乘出个数）；样本不足 → ``insufficient_reason`` 原样透出；
    - 权益校验：装饰器 @require_pro_feature('pro-risk') 拦截未开通家庭（403 统一信封）。

    会话同 ``/pro-insight/``：跨 user/market 两域（序列在 market、持仓在 user），
    必须走路由会话 ``get_db()``——单域工厂在双库生产下必坏，见上一条 why。
    """
    query: ProRiskRequest = parse_query(ProRiskRequest)
    with get_db() as db:
        try:
            data = build_symbol_pro_risk(db, query.symbol, family_id=get_family_id(), asset_type=query.asset_type)
        except ValueError as e:
            # 空白/纯前缀 symbol（如 'OF.'）过不了 schema 的 min_length，但服务层
            # 归一后为空会抛 ValueError——转 400，不留 500（与 index-returns 同族范式）
            abort(400, str(e))
    return jsonify({'data': data, 'message': 'ok'})


@bp.get('/pro-allocation/')
@require_pro_feature('pro-allocation')
def pro_allocation():
    """Pro 模块三「资产配置与相关性」——当前标的 vs 家庭其余持仓（#994 Phase 2 → #2324 接入权益校验）。

    回答一句话：**你以为分散了吗？** 逐只给出当前标的与家庭其余持仓的日收益
    Pearson 相关系数（|ρ| 降序），并显示「ρ ≥ 0.8 的只数」——那些才是账面分散、
    风险仍集中的部分。

    - 计算全在 ``services/pro_allocation.py`` + ``analytics/correlation.py``；
      相关性按**日收益日期交集**配对（停牌/发布延迟只丢样本、不错配同期）；
      相关系数的收益率算法与模块二 ``var.py`` 同源，不许出现第二套日收益；
    - **诚实降级**：同期交易日 <60 天、或某只收益零方差（货基/停牌）⇒ 该只跳过，
      跳过的只数由 ``skipped_count`` 原样披露——不让它悄悄从结论里消失；
      一只都算不出 ⇒ ``available=false`` + ``reason``；
    - 权益校验：装饰器 @require_pro_feature('pro-allocation') 拦截未开通家庭（403 统一信封）。

    会话跨域同两个兄弟端点：持仓在 user 域 positions、序列在 market 域
    （daily_worth / price_history），**必须走路由会话 ``get_db()``**——
    单域会话工厂在双库生产下必 500。
    """
    query: ProAllocationRequest = parse_query(ProAllocationRequest)
    with get_db() as db:
        try:
            data = build_symbol_pro_allocation(db, query.symbol, family_id=get_family_id(), asset_type=query.asset_type)
        except ValueError as e:
            # 同 pro-risk：空白/纯前缀 symbol 归一为空后的 ValueError 转 400
            abort(400, str(e))
    return jsonify({'data': data, 'message': 'ok'})
