# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/13 21:57
# File : views.py
# 自选模块 API

import csv
import io
from datetime import date, timedelta

from apiflask import APIBlueprint
from flask import Response, abort, jsonify, request
from loguru import logger
from sqlalchemy import desc, func, or_

from app.core.auth import get_family_id, get_owned_or_404
from app.core.constants import TYPE_LABELS
from app.core.database import get_db
from app.core.money import Money
from app.core.utils import api_response, with_db
from app.core.validation import parse_body
from app.domains.funds.models import AdvisorHolding, AdvisorPortfolio, ChannelLink, DailyWorth
from app.domains.indices.models import IndexValuation
from app.domains.positions.models import Position
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import ConvertibleBondTerm
from app.domains.transactions.models import Transaction
from app.domains.watchlist.models import (
    WatchlistGroup,
    WatchlistItem,
    WatchlistItemGroup,
    WatchlistItemTag,
    WatchlistTagDef,
)
from app.domains.watchlist.schemas import (
    WatchlistGroupCreate,
    WatchlistGroupOut,
    WatchlistGroupUpdate,
    WatchlistItemCreate,
    WatchlistItemOut,
    WatchlistItemUpdate,
    WatchlistTagDefCreate,
    WatchlistTagDefOut,
    WatchlistTagDefUpdate,
)
from app.services.fund_metrics import compute_max_drawdown, load_nav_points
from app.services.watchlist_service import (
    build_groups_data,
    build_home_summary,
    create_watchlist_item,
    ensure_watchlist_for_positions,
    get_filtered_items_query,
    get_holding_gaps,
    lookup_manager,
    reconcile_watchlist_status,
    resolve_display_name,
)

watchlist_bp = APIBlueprint('watchlist', __name__, url_prefix='/api/watchlist')

# CSV 导出字段值 → 中文 label 映射
_VENUE_LABELS = {'EXCHANGE': '场内', 'OTC': '场外'}
_STATUS_LABELS = {'HOLDING': '持仓中', 'WATCHING': '观察中'}

# 资产类型中文 label 统一取后端唯一来源 app.core.constants.TYPE_LABELS（收口自 asset_types），
# 不再在此私藏局部副本，避免与全局枚举漂移（#1171 枚举一致性）。

# 常量定义（放在文件顶部，导入之后）
HOME_PINNED_LIMIT = 6
HOME_DISPLAY_LIMIT = 5
TAG_LIST_LIMIT = 50

# 分组颜色定义（供前端参考，后端仅用于构建分组列表）
GROUP_COLORS = {
    'all': '#999',
    'holding': '#ff4d4f',
    'watching': '#52c41a',
    'cleared': '#fa8c16',
    'exchange': '#1890ff',
    'otc': '#722ed1',
    'favorite': '#a6a6d2',
}


# ─────────────── 辅助函数 ───────────────
# 展示名解析（resolve_display_name）与经理回查（lookup_manager）已收口到
# services.watchlist_service：首页自选摘要与自选列表页**共用同一实现**。
# 此前两处各写一份，只有本文件补了 Manager/AdvisorPortfolio 分支，导致列表页
# 正常而首页仍显示 MGR_xxx（2026-09-10 复盘），故不再在此另立副本。


def _to_float(value):
    """Decimal/数值 → float（None 安全）。

    SafeNumeric 落库为 Decimal，若直接塞进响应 dict 会把 Decimal 带进 JSON
    （Flask 默认编码器不认识 Decimal）。统一在此转换。
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _apply_bond_fields(out: dict, symbol: str, db) -> None:
    """可转债条款 enrich（#1285 消费侧 / #1393）。

    仅当 convertible_bond_terms 命中该 symbol 时填充（表未落库/非转债则一律保持
    None，前端据此显示 `—`，不渲染假数据）。
    """
    term = db.query(ConvertibleBondTerm).filter_by(symbol=symbol).first()
    if term is None:
        return
    out['bond_convert_price'] = _to_float(term.convert_price)
    out['bond_convert_value'] = _to_float(term.convert_value)
    out['bond_premium_rate'] = _to_float(term.premium_rate)
    out['bond_force_redeem_price'] = _to_float(term.force_redeem_price)
    out['bond_redeem_count'] = term.redeem_count
    out['bond_redeem_required'] = term.redeem_required
    out['bond_redeem_status'] = term.redeem_status
    out['bond_rating'] = term.rating
    out['bond_maturity_date'] = term.maturity_date
    out['bond_remain_size'] = _to_float(term.remain_size)
    out['bond_issue_size'] = _to_float(term.issue_size)
    out['bond_stock_name'] = term.stock_name


def _bare_code(symbol: str) -> str:
    """'SH000300' / 'CSI930950' / 'OF000001' → '000300' / '930950' / '000001'。

    指数估值表（index_valuations）与基金净值表（daily_worth）都按**裸代码**存储，
    故统一在此抽取数字部分。
    """
    return ''.join(ch for ch in (symbol or '') if ch.isdigit())


def _apply_index_valuation_fields(out: dict, symbol: str, db) -> None:
    """指数估值 enrich（#1285 消费侧「指数」品类 / #1394）。

    取该指数**最新一期**估值（历史序列留给后续的估值详情页）；表为空或该指数没有
    官方估值文件时保持 None —— 前端显示 `—`，不编造数据。
    """
    code = _bare_code(symbol)
    if not code:
        return
    row = (
        db.query(IndexValuation)
        .filter(IndexValuation.index_code == code)
        .order_by(IndexValuation.trade_date.desc())
        .first()
    )
    if row is None:
        return
    out['index_pe'] = _to_float(row.pe_1)
    out['index_pe_2'] = _to_float(row.pe_2)
    out['index_dividend_yield'] = _to_float(row.dividend_yield_1)
    out['index_valuation_date'] = row.trade_date


# ── 基金最大回撤（#1285 消费侧「基金」品类 / 设计 §3.10）──
DRAWDOWN_FIXED_WINDOW_DAYS = 365 * 3  # 固定窗口档：近 3 年
DRAWDOWN_FIXED_WINDOW_LABEL = '近3年'
# 样本不足（次新基金/净值稀疏）时不下发数字，只标 basis=insufficient，前端显示 `—`
DRAWDOWN_MIN_SAMPLES = 60


def _apply_fund_drawdown_fields(out: dict, symbol: str, asset_type: str, db) -> None:
    """基金最大回撤 enrich（口径见设计 §3.10「存口径元数据，不只存数字」）。

    **本期口径**：固定窗口「近 3 年」，日频，基于 `daily_worth.acc_nav`（累计净值）
    自算，`basis='fixed_3y'`。

    为何不是「现任经理任期」：§3.10 对**主动权益类**要求绑定有效管理人任期，该档位
    依赖经理任期 / 历任任期业绩 / 同类排名数据（均未接入），故本期不产出
    `current_tenure` / `prev_tenure` 两档；字段与前端色板已按 basis 预留，
    数据接入后只需在此处改 `basis` 选择逻辑，算法与服务层无需改动。
    """
    # 仅场外基金：daily_worth 按 6 位基金代码存净值；货基用万份收益口径，不适用本算法
    if (asset_type or '').lower() != 'fund':
        return
    code = _bare_code(symbol)
    if not code:
        return

    since = date.today() - timedelta(days=DRAWDOWN_FIXED_WINDOW_DAYS)
    rows = (
        db.query(DailyWorth)
        .filter(DailyWorth.fund_code == code, DailyWorth.date >= since)
        .order_by(DailyWorth.date)
        .all()
    )
    result = compute_max_drawdown(load_nav_points(rows))
    if result is None or result.sample_size < DRAWDOWN_MIN_SAMPLES:
        out['fund_max_drawdown_basis'] = 'insufficient'
        return

    out['fund_max_drawdown'] = round(result.max_drawdown, 2)
    out['fund_max_drawdown_basis'] = 'fixed_3y'
    out['fund_max_drawdown_window'] = DRAWDOWN_FIXED_WINDOW_LABEL
    out['fund_max_drawdown_as_of'] = result.as_of


def _apply_channel_link_fields(out: dict, symbol: str, db) -> None:
    """跨渠道关联 enrich（#1285 设计 §3.8）：数量角标 + 浮层明细。

    `channel_links` 存**有向**关系（index→etf），但本函数按裸代码**双向查**并对任一端
    都返回「另一侧」清单：指数行看到 ETF、ETF 行看到指数，前端无需判断方向。
    无关联时不写字段（前端渲染 `—`）。
    """
    code = _bare_code(symbol)
    if not code:
        return
    rows = db.query(ChannelLink).filter(or_(ChannelLink.from_symbol == code, ChannelLink.to_symbol == code)).all()
    if not rows:
        return
    links = []
    for r in rows:
        if r.from_symbol == code:
            links.append({'code': r.to_symbol, 'name': r.to_name, 'link_type': r.link_type})
        else:
            links.append({'code': r.from_symbol, 'name': r.from_name, 'link_type': r.link_type})
    out['link_count'] = len(links)
    out['links'] = links


def _apply_advisor_fields(out: dict, symbol: str, db) -> None:
    """投顾品类差异化指标 enrich（#1392）。

    命中 AdvisorPortfolio（按 code=symbol）时补充：平台/主理人/策略类型（#1167）+ 区间收益
    （return_1w/1m/1y/ytd/since_incep，来自天天 SYL_* 实测映射）+ 最大回撤/超额/业绩基准
    （API 不直接提供时为空）+ 持仓集中度（HHI = Σ占比²，由 advisor_holdings.after_ratio 现算）。
    非投顾标的（advisor 为 None）时上述字段一律置 None —— 前端品类列据此渲染 `—`，不编造。
    """
    # #1392 投顾品类列所需字段（区间收益 + 回撤 + 超额），统一先在 out 挂默认 None，
    # 命中 advisor 再覆盖，避免非投顾标的漏字段导致前端 key 缺失
    _ADVISOR_METRIC_KEYS = (
        'return_1w',
        'return_1m',
        'return_1y',
        'return_ytd',
        'return_since_incep',
        'max_drawdown',
        'excess_return',
    )
    for k in _ADVISOR_METRIC_KEYS:
        out[k] = None
    out['advisor_benchmark'] = None
    out['advisor_holding_count'] = None
    out['advisor_concentration'] = None
    # #1167 既有字段默认 None（命中再覆盖）
    out['advisor_platform'] = None
    out['advisor_host'] = None
    out['advisor_strategy_type'] = None
    out['advisor_org_name'] = None

    advisor = db.query(AdvisorPortfolio).filter_by(code=symbol).first()
    if advisor is None:
        return
    out['advisor_platform'] = advisor.platform
    out['advisor_host'] = advisor.host
    out['advisor_strategy_type'] = advisor.strategy_type
    out['advisor_org_name'] = advisor.org_name
    for k in _ADVISOR_METRIC_KEYS:
        out[k] = _to_float(getattr(advisor, k))
    out['advisor_benchmark'] = advisor.benchmark
    # 持仓集中度：HHI = Σ(占比%²)，越高越集中；同时给持仓基金数（信息密度）
    ratios = [
        float(r[0])
        for r in db.query(AdvisorHolding.after_ratio).filter_by(portfolio_id=advisor.id).all()
        if r[0] is not None
    ]
    if ratios:
        out['advisor_holding_count'] = len(ratios)
        out['advisor_concentration'] = round(sum(r * r for r in ratios), 1)
    else:
        out['advisor_holding_count'] = 0
        out['advisor_concentration'] = None


def _enrich_item(item: WatchlistItem, db) -> dict:
    out = WatchlistItemOut.model_validate(item).model_dump()
    # watchlist.asset_type 历史存放大写（STOCK/ETF/...），对外统一归一为小写，
    # 与后端 asset_types 单一来源（stock/etf/fund/bond/index）及 positions 域保持一致（#1171）。
    out['asset_type'] = item.asset_type.lower() if item.asset_type else None
    # 资产类型中文标签：单一来源 app.core.constants.TYPE_LABELS（#1171 枚举一致性），
    # 供前端「资产类型」列（#1332 候选列）直接展示，免前端再映射。
    out['type_label'] = TYPE_LABELS.get(out['asset_type']) or out['asset_type'] or ''
    out['display_name'] = resolve_display_name(item.symbol, db)
    out['group_ids'] = [link.group_id for link in item.group_links]
    out['tag_ids'] = [link.tag_id for link in item.tag_links]
    # 所属分组名称列表（#1332 排序用，避免前端再映射 group_ids）
    out['group_names'] = [link.watchlist_group.name for link in item.group_links if link.watchlist_group]

    # 投顾组合补充信息（#1167 / #1392 投顾品类差异化指标）：平台 / 主理人 / 策略类型 +
    # 区间收益 / 回撤 / 超额 / 业绩基准 / 持仓集中度。普通标的字段一律 None，
    # 前端 product 列按需渲染第二行元信息，品类列按 appliesTo=["portfolio"] 显示。
    _apply_advisor_fields(out, item.symbol, db)

    # 基金经理补充信息（#1286）：所属基金公司名。经理行没有对外有意义的交易代码，
    # 第二行元信息由公司承担，否则只剩一个「基金经理」标签、信息量为零
    # （2026-09-10 用户反馈）。
    mgr = lookup_manager(item.symbol, db)
    out['manager_company'] = mgr.company.name if mgr and mgr.company else None

    # 可转债条款（#1285 消费侧 / #1393）：仅转债命中 convertible_bond_terms 时填充
    _apply_bond_fields(out, item.symbol, db)

    # 指数估值（#1285 消费侧 / #1394）：仅指数命中 index_valuations 时填充
    _apply_index_valuation_fields(out, item.symbol, db)

    # 基金最大回撤（#1285 消费侧 / §3.10）：仅场外基金，口径元数据随值下发
    _apply_fund_drawdown_fields(out, item.symbol, item.asset_type, db)

    # 跨渠道关联（#1285 §3.8）：指数↔ETF（本期主流宽基）
    _apply_channel_link_fields(out, item.symbol, db)

    # 补充价格与市值信息（从持仓表计算静态值）
    position_value = _compute_position_market_value(item.symbol, db)
    current_price = _compute_avg_current_price(item.symbol, db)
    out['current_price'] = round(current_price, 2) if current_price else None
    out['change_pct'] = None  # 暂不提供，后续可通过元数据同步填充
    out['position_market_value'] = round(position_value, 2)

    # 真实持仓统计（自选页信息密度扩充，watchlist-table-redesign-2026-08-13.md P0/P1）
    # positions 表 quantity 存最小单位(0.0001 份)、avg_price/current_price 存分，
    # 对外一律换算为「份 / 元」（禁止裸乘除 float，换算走 Money）。
    # 注意：WatchlistItemOut.quantity/cost_price 是探市迁移透传的观察参考值，
    # 与本处真实持仓严格区分，前端不得混用。
    stats = _compute_holding_stats(item.symbol, db)
    if stats:
        out['holding_quantity'] = stats['quantity']
        out['holding_cost_price'] = round(stats['cost_price'], 4)
        out['holding_pnl'] = round(stats['pnl'], 2)
        out['holding_pnl_percent'] = round(stats['pnl_percent'], 2)
    else:
        out['holding_quantity'] = None
        out['holding_cost_price'] = None
        out['holding_pnl'] = None
        out['holding_pnl_percent'] = None
    # 添加自选日行情（price_history 最近交易日收盘价，缺数据 → None，前端降级显示 --）
    out['price_at_added'] = _compute_price_at_added(item, db)

    return out


def _compute_holding_stats(symbol, db) -> dict | None:
    """按 symbol 汇总真实持仓（positions，当前 family）：数量/加权成本/浮动盈亏。

    positions.quantity 以最小单位存储（0.0001 份），avg_price/current_price 以 0.0001元 存储，
    换算统一走 Money（min_unit_to_shares / price_units_to_yuan）。
    """
    row = (
        db.query(
            func.sum(Position.quantity).label('qty_units'),
            func.sum(Position.quantity * Position.avg_price).label('cost_raw'),
            func.sum(Position.quantity * Position.current_price).label('value_raw'),
        )
        .filter(Position.symbol == symbol, Position.family_id == get_family_id())
        .first()
    )
    if not row or not row.qty_units:
        return None
    quantity = Money.min_unit_to_shares(row.qty_units)  # 最小单位 → 份
    # quantity(×10000) × avg_price(×10000) = ×1e8，multiply_price_quantity ÷1e6 得 分，cents_to_yuan ÷100 得 元
    cost_yuan = Money.cents_to_yuan(Money.multiply_price_quantity(row.cost_raw, 1))
    value_yuan = Money.cents_to_yuan(Money.multiply_price_quantity(row.value_raw, 1))
    cost_price = cost_yuan / quantity if quantity else 0.0  # 加权成本均价（元/份）
    pnl = value_yuan - cost_yuan
    pnl_percent = (pnl / cost_yuan * 100) if cost_yuan else 0.0
    return {'quantity': quantity, 'cost_price': cost_price, 'pnl': pnl, 'pnl_percent': pnl_percent}


def _compute_price_at_added(item: WatchlistItem, db) -> float | None:
    """添加自选日行情：price_history 中 ≤ created_at 的最近一个交易日收盘价（元）。

    数据依赖 price_history 回填覆盖率；早于历史数据起始点或基金未覆盖时返回 None，
    前端对应「添加后涨幅/收益」列降级显示 --（见设计文档「局限」）。
    """
    created = item.created_at.date() if item.created_at else None
    if not created:
        return None
    row = (
        db.query(PriceHistory.close)
        .filter(PriceHistory.symbol == item.symbol, PriceHistory.trade_date <= created)
        .order_by(PriceHistory.trade_date.desc())
        .first()
    )
    return round(row[0], 4) if row and row[0] is not None else None


def _compute_position_market_value(symbol, db):
    """计算持仓市值（元）。

    positions.quantity 存最小单位（0.0001 份）、current_price 存 0.0001元，
    裸乘结果是最小单位·0.0001元，须经 Money.multiply_price_quantity 换算回元（÷1e6 转分、/100 转元）。
    """
    value = (
        db.query(func.sum(Position.quantity * Position.current_price))
        .filter(Position.symbol == symbol, Position.family_id == get_family_id())
        .scalar()
    )
    if not value:
        return 0.0
    return Money.cents_to_yuan(Money.multiply_price_quantity(value, 1))


def _compute_avg_current_price(symbol, db):
    """计算持仓平均市价（元），用于自选行展示。

    current_price 以 0.0001元 存储，对外换算回元（禁止裸除 float）。
    """
    avg_price_units = (
        db.query(func.avg(Position.current_price))
        .filter(Position.symbol == symbol, Position.family_id == get_family_id())
        .scalar()
    )
    return Money.price_units_to_yuan(avg_price_units) if avg_price_units else 0.0


def _list_holding_items(db, family_id, venue=None, search=None, asset_types=None):
    """持仓分组列表：返回 positions 表全部 active 持仓的虚拟行（按 symbol 聚合）。

    与 watchlist.status 快照解耦：一个 symbol 可能多账户多行，distinct 后按 symbol 聚合；
    每行 id=None 表示「无自选记录」，前端据此禁用置顶/关注/标签/移除等行操作。
    """
    rows = (
        db.query(Position.symbol, Position.asset_type, Position.market, Position.name)
        .filter(Position.family_id == family_id, Position.ownership_status == 'active')
        .distinct()
        .all()
    )
    # family 维度 symbol→venue 映射：优先取自选记录里的 venue，缺失时按资产类型推断
    venue_map = dict(
        db.query(WatchlistItem.symbol, WatchlistItem.venue).filter(WatchlistItem.family_id == family_id).all()
    )
    data = []
    seen = set()
    for symbol, asset_type, market, pos_name in rows:
        if symbol in seen:
            continue  # 同一 symbol 多账户行已聚合，跳过重复
        seen.add(symbol)
        row_venue = venue_map.get(symbol) or ('OTC' if asset_type == 'fund' else 'EXCHANGE')
        if venue and row_venue != venue:
            continue
        if search:
            s = search.lower()
            # 名称匹配：优先用持仓名称，缺失时回退到 securities/funds 展示名（与 _build_holding_row 同源）
            display = (pos_name or '') or resolve_display_name(symbol, db)
            if s not in symbol.lower() and s not in (display or '').lower():
                continue
        # 持仓虚拟行优先回填真实自选记录（若已入自选）→ 行内可打标签/备注；
        # 未入自选则保持 id=None，前端据此提示「一键加入」。
        holding_row = _build_holding_row(symbol, db, market=market, asset_type=asset_type, venue=row_venue)
        data.append(_enrich_holding_with_watchlist(holding_row, db, family_id))
    # 持仓分组支持类型筛选（#1449）：虚拟行已带小写 asset_type，按前端传来的
    # 逗号分隔类型集合过滤，与真实自选行的 asset_types 语义一致。
    if asset_types:
        type_set = {t.strip().lower() for t in asset_types.split(',') if t.strip()}
        if type_set:
            data = [r for r in data if (r.get('asset_type') or '').lower() in type_set]
    data.sort(key=lambda r: r['position_market_value'] or 0, reverse=True)
    return data


def _build_holding_row(symbol, db, market=None, asset_type=None, venue=None):
    """构造持仓虚拟行 dict，字段对齐 WatchlistItemOut/_enrich_item 输出（前端直接复用）。

    id=None 是虚拟行约定：该 symbol 可能不在自选表，行操作（置顶/关注/标签/移除）一律禁用。
    """
    pos = (
        db.query(Position)
        .filter(
            Position.symbol == symbol,
            Position.family_id == get_family_id(),
            Position.ownership_status == 'active',
        )
        .first()
    )
    market = market or (pos.market if pos else None)
    asset_type = asset_type or (pos.asset_type if pos else None)
    venue = venue or ('OTC' if asset_type == 'fund' else 'EXCHANGE')
    display_name = (pos.name if pos and pos.name else None) or resolve_display_name(symbol, db)
    # 投顾组合元信息：与 _enrich_item 同步，避免虚拟行（持仓聚合无 id 的行）漏字段
    advisor = db.query(AdvisorPortfolio).filter_by(code=symbol).first()
    mgr = lookup_manager(symbol, db)  # 经理行公司名：与 _enrich_item 同源

    current_price = _compute_avg_current_price(symbol, db)
    stats = _compute_holding_stats(symbol, db)
    row = {
        'id': None,
        'symbol': symbol,
        'market': market,
        'asset_type': (asset_type or '').lower() or None,
        'type_label': TYPE_LABELS.get((asset_type or '').lower()) or (asset_type or '').lower() or '',
        'venue': venue,
        'status': 'HOLDING',
        'favorite': False,
        'favorite_at': None,
        'is_pinned': False,
        'pinned_at': None,
        'add_reason': None,
        'notes': None,
        'cost_price': None,
        'quantity': None,
        'created_at': None,
        'updated_at': None,
        'display_name': display_name,
        'group_ids': [],
        'group_names': [],
        'tag_ids': [],
        'current_price': round(current_price, 2) if current_price else None,
        'change_pct': None,
        'position_market_value': round(_compute_position_market_value(symbol, db), 2),
        'holding_quantity': stats['quantity'] if stats else None,
        'holding_cost_price': round(stats['cost_price'], 4) if stats else None,
        'holding_pnl': round(stats['pnl'], 2) if stats else None,
        'holding_pnl_percent': round(stats['pnl_percent'], 2) if stats else None,
        'price_at_added': None,
        # 投顾组合补充信息（与 _enrich_item 同源；非投顾为 None）
        'advisor_platform': (advisor.platform if advisor else None),
        'advisor_host': (advisor.host if advisor else None),
        'advisor_strategy_type': (advisor.strategy_type if advisor else None),
        'advisor_org_name': (advisor.org_name if advisor else None),
        'return_1w': (_to_float(advisor.return_1w) if advisor else None),
        'return_1m': (_to_float(advisor.return_1m) if advisor else None),
        'return_1y': (_to_float(advisor.return_1y) if advisor else None),
        'return_ytd': (_to_float(advisor.return_ytd) if advisor else None),
        'return_since_incep': (_to_float(advisor.return_since_incep) if advisor else None),
        'max_drawdown': (_to_float(advisor.max_drawdown) if advisor else None),
        'excess_return': (_to_float(advisor.excess_return) if advisor else None),
        'advisor_benchmark': (advisor.benchmark if advisor else None),
        'advisor_holding_count': 0,
        'advisor_concentration': None,
    }
    # 持仓集中度（HHI）：与 _apply_advisor_fields 同源，避免虚拟行（持仓聚合无 id）漏字段
    if advisor is not None:
        _ratios = [
            float(r[0])
            for r in db.query(AdvisorHolding.after_ratio).filter_by(portfolio_id=advisor.id).all()
            if r[0] is not None
        ]
        if _ratios:
            row['advisor_holding_count'] = len(_ratios)
            row['advisor_concentration'] = round(sum(r * r for r in _ratios), 1)
    # 基金经理所属公司（与 _enrich_item 同源；非经理为 None）
    mgr = lookup_manager(symbol, db)
    row['manager_company'] = mgr.company.name if mgr and mgr.company else None
    # 可转债条款（#1285/#1393）：与 _enrich_item 同源，避免虚拟行（持仓聚合无 id）漏字段
    _apply_bond_fields(row, symbol, db)
    # 指数估值（#1285/#1394）：与 _enrich_item 同源
    _apply_index_valuation_fields(row, symbol, db)
    # 基金最大回撤（#1285/§3.10）：与 _enrich_item 同源，避免虚拟行漏字段
    _apply_fund_drawdown_fields(row, symbol, asset_type, db)
    # 跨渠道关联（#1285 §3.8）：与 _enrich_item 同源
    _apply_channel_link_fields(row, symbol, db)
    return row


def _enrich_holding_with_watchlist(row: dict, db, family_id: int) -> dict:
    """持仓虚拟行若存在真实自选记录，回填 id/分组/标签/备注等可编辑字段。

    使「持仓」分组内的产品也能打标签、加备注（#1458 后续：持仓即自选）。
    仅当无自选记录时保持 id=None——前端据此禁用行操作并提示「一键加入自选」。
    「全部」分组天然包含这些真实自选记录，无需在此处理，口径保持一致。
    """
    item = (
        db.query(WatchlistItem)
        .filter_by(symbol=row['symbol'], market=row['market'], venue=row['venue'], family_id=family_id)
        .first()
    )
    if item is None:
        item = db.query(WatchlistItem).filter_by(symbol=row['symbol'], family_id=family_id).first()
    if item is None:
        return row
    row = dict(row)
    row['id'] = item.id
    row['group_ids'] = [g.group_id for g in item.group_links]
    row['group_names'] = [g.watchlist_group.name for g in item.group_links]
    row['tag_ids'] = [t.tag_id for t in item.tag_links]
    row['notes'] = item.notes
    row['is_pinned'] = item.is_pinned
    row['pinned_at'] = item.pinned_at
    row['favorite'] = item.favorite
    row['favorite_at'] = item.favorite_at
    row['add_reason'] = item.add_reason
    row['cost_price'] = item.cost_price
    row['quantity'] = item.quantity
    row['status'] = 'HOLDING'  # 持仓分组恒为 HOLDING
    return row


def _build_all_items(db, family_id, venue=None, search=None, tag_ids_str=None, favorite=False, group_id=None):
    """「全部」分组数据：自选清单 ∪ 真实持仓补集（同一 symbol 自选记录优先，去重）。

    语义（与分组 count 口径一致，保证「全部 N 条」与分组数字吻合）：
    - 自选条目走 get_filtered_items_query（不传 status），保留置顶排序字段；
    - 补集虚拟行仅当无附加筛选（tag/关注/分组）时追加——附加筛选的语义是
      「自选内的资产」子集，与持仓全集无交集，补行会引入「筛选不到却展示」的条目；
    - 排序：置顶优先，其次持仓市值降序（自选行与虚拟行统一口径）。
    """
    params = {
        'status': None,
        'venue': venue,
        'market': None,
        'group_id': group_id,
        'search': search,
        'favorite': favorite,
        'symbol': None,
        'tag_ids_str': tag_ids_str,
        'tag_id': None,
    }
    query, _ = get_filtered_items_query(db, family_id, **params)
    items = query.order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.updated_at.desc()).all()
    data = [_enrich_item(item, db) for item in items]

    if not (tag_ids_str or favorite or group_id):
        holding_rows = _list_holding_items(db, family_id, venue=venue, search=search)
        watch_symbols = {item['symbol'] for item in data}
        for row in holding_rows:
            if row['symbol'] in watch_symbols:
                continue  # 同一 symbol 自选记录优先，虚拟行不重复展示
            data.append(row)

    # 混合排序：置顶优先（is_pinned 在前），再按持仓市值降序
    data.sort(key=lambda r: (not r['is_pinned'], -(r['position_market_value'] or 0)))
    return data


@watchlist_bp.get('/home-summary/')
def home_summary():
    """首页自选摘要"""
    with get_db() as db:
        data = build_home_summary(db, get_family_id())
    return jsonify({'data': data, 'message': 'ok'})


@watchlist_bp.get('/holding-gaps/')
def holding_gaps():
    """「有活跃持仓但未加入自选」的缺口列表（前端 banner 引导一键加入）。

    仅读取、幂等；不修改任何数据。缺口判定见 watchlist_service.get_holding_gaps。
    """
    with get_db() as db:
        gaps = get_holding_gaps(db, get_family_id())
    return jsonify({'data': gaps, 'count': len(gaps), 'message': 'ok'})


@watchlist_bp.post('/reconcile/')
def reconcile_watchlist():
    """一键补齐：为活跃持仓创建 HOLDING 自选记录（买入即入自选的批量版）。

    同时对齐卖出/清仓后的状态：无活跃持仓的 HOLDING 项降级为 WATCHING。
    单标的失败仅记录日志、不中断，返回汇总供前端提示（#1458 后续）。
    请求体可选：{"demote": true} 控制是否执行降级（默认 true）。
    """
    body = request.get_json(silent=True) or {}
    demote = body.get('demote', True)
    with get_db() as db:
        family_id = get_family_id()
        created = ensure_watchlist_for_positions(db, family_id)
        promoted = demoted = 0
        if demote:
            promoted, demoted = reconcile_watchlist_status(db, family_id)
    return jsonify(
        {
            'data': {'created': created, 'promoted': promoted, 'demoted': demoted},
            'message': 'ok',
        }
    )


@watchlist_bp.get('/trends/')
def list_trends():
    """批量获取标的近 N 日收盘价序列（迷你走势图数据源，#990）。

    ?symbols=SH600519,HK00700&days=60
    - 数据源：price_history 表（price_history_job 回填），与「添加后涨幅」同源同口径，
      纯历史日线无需实时性，不走前端 JSONP 行情通道（AGENTS.md 数据源收口约束）；
    - 紧凑返回：仅收盘价数组，无日期轴（迷你图不画坐标轴）；
    - 无数据的 symbol 不出现在返回字典中，前端降级显示 --；
    - symbols 上限 50 个、days 限幅 [5, 250]，防止单次请求过量。
    """
    symbols = [s.strip() for s in request.args.get('symbols', '').split(',') if s.strip()][:50]
    days = max(min(request.args.get('days', type=int, default=60) or 60, 250), 5)
    if not symbols:
        return jsonify({'data': {}, 'message': 'ok'})

    start = date.today() - timedelta(days=days)
    # 场外基金（OF. 开头）历史净值存于 daily_worth 表，需单独取数并入同一 trends 结构
    fund_symbols = [s for s in symbols if s.upper().startswith('OF.')]
    fund_codes = [s.split('.', 1)[1] for s in fund_symbols if '.' in s]

    with get_db() as db:
        rows = (
            db.query(PriceHistory.symbol, PriceHistory.close)
            .filter(
                PriceHistory.symbol.in_(symbols),
                PriceHistory.trade_date >= start,
            )
            .order_by(PriceHistory.symbol.asc(), PriceHistory.trade_date.asc())
            .all()
        )
        nav_rows = []
        if fund_codes:
            nav_rows = (
                db.query(DailyWorth.fund_code, DailyWorth.unit_nav)
                .filter(
                    DailyWorth.fund_code.in_(fund_codes),
                    DailyWorth.date >= start,
                )
                .order_by(DailyWorth.fund_code.asc(), DailyWorth.date.asc())
                .all()
            )

    trends: dict[str, list[float]] = {}
    for symbol, close in rows:
        if close is None:
            continue
        trends.setdefault(symbol, []).append(round(close, 4))
    # 基金净值并入 trends：键仍用前端符号 OF.xxxxxx，与 price_history 同口径（数值即单位净值）
    for fund_code, unit_nav in nav_rows:
        if unit_nav is None:
            continue
        trends.setdefault(f'OF.{fund_code}', []).append(round(unit_nav, 4))
    return jsonify({'data': trends, 'message': 'ok'})


# ─────────────── 自选资产 CRUD ───────────────

# 用户列内排序白名单（#991）：仅开放行字典中真实存在的数值/日期字段，
# 防止任意字段名注入排序。added_return 为派生值（前端「添加后涨幅」列），
# 由 _user_sort_metric 现算，不在本集合内。
_USER_SORTABLE_FIELDS = frozenset(
    {
        # #1331：前端「代码/名称」列（product）标了 sortable:custom 却未开放白名单，
        # 导致点击排序静默失效；映射为 symbol（代码）字典序，稳定且不耦合名称本地化。
        'product',
        'created_at',
        'current_price',
        'change_pct',
        'holding_quantity',
        'holding_cost_price',
        'position_market_value',
        'holding_pnl',
        'holding_pnl_percent',
        'price_at_added',
        # #1332：#993 引入的 4 个候选列放开排序；下列字段均已在 enrich 阶段下发（见 _enrich_item），
        # 排序键值由 _user_sort_metric 现算：
        # - holding_cost_price：数值，来自 positions 加权成本（_compute_holding_stats，L131 起）；
        # - type_label：资产类型中文标签（字符串），单一来源 app.core.constants.TYPE_LABELS（#1171）；
        # - updated_at：ISO 字符串，字典序即时间序；
        # - groups：多值（group_ids），按首个分组 id 字典序、无分组恒排末尾（语义见 _user_sort_metric）。
        'type_label',
        'updated_at',
        'groups',
    }
)


def _user_sort_metric(row: dict, sort_by: str):
    """取排序键值；缺失/不可比较返回 None（恒排末尾）。"""
    if sort_by == 'product':
        # 「代码/名称」列（#1331）：按 symbol（代码）字典序排序，稳定；symbol 缺失则排末尾
        return row.get('symbol')
    if sort_by == 'groups':
        # 所属分组（多值字段，#1332）：排序语义取「首个分组」——优先 group_ids 首个
        # 元素（分组 id）字典序；若无 group_ids 则退化为首个 group_names（分组名）；
        # 无分组恒排末尾。多分组整体顺序按首个分组定，与前端展示首个分组一致。
        ids = row.get('group_ids') or []
        if ids:
            return ids[0]
        names = row.get('group_names') or []
        return names[0] if names else None
    if sort_by == 'added_return':
        # 派生列：添加后收益金额 =（现价 - 添加日收盘价）× 持有数量，
        # 与前端 addedReturnAmount 同口径；三要素缺一则无意义
        cur = row.get('current_price')
        added = row.get('price_at_added')
        qty = row.get('holding_quantity')
        if cur is None or added is None or not qty:
            return None
        try:
            return (float(cur) - float(added)) * float(qty)
        except (TypeError, ValueError):
            return None
    v = row.get(sort_by)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def _apply_user_sort(data: list, sort_by, sort_order):
    """用户列内排序（#991）。

    - 未指定 sort_by：维持原顺序（置顶优先 + 更新时间倒序）；
    - 白名单外 sort_by：维持原顺序返回，但明确告警（#1331 消除「点击无反应」式静默失败），
      便于后续新增可排序列漏登记白名单时第一时间暴露，而非毫无提示；
    - 排序稳定且置顶行仍前置：用户排序只改变同优先级内的次序，
      不破坏「置顶恒在顶部」的既有心智；
    - 值缺失（None）的行无论升降序都排在末尾，避免空值干扰阅读。
    """
    if not sort_by:
        return data
    # 白名单外字段（含前端标了排序但后端未开放）：原序返回 + 告警，避免静默失效
    if sort_by not in _USER_SORTABLE_FIELDS and sort_by != 'added_return':
        logger.warning(
            'watchlist 排序忽略非白名单字段 sort_by={!r}（前端标了排序但后端未开放，'
            '如确属可排序列请在 _USER_SORTABLE_FIELDS 登记）',
            sort_by,
        )
        return data
    reverse = sort_order == 'desc'

    decorated = [(_user_sort_metric(r, sort_by), r) for r in data]
    known = [(m, r) for m, r in decorated if m is not None]
    unknown = [r for m, r in decorated if m is None]
    known.sort(key=lambda t: t[0], reverse=reverse)  # 主排序：用户选的指标
    known.sort(key=lambda t: 0 if t[1].get('is_pinned') else 1)  # 次排序：置顶前置（稳定）
    return [r for _, r in known] + unknown


@watchlist_bp.get('/items/')
def list_items():
    """获取自选列表，支持多种筛选、置顶优先排序与用户列内排序（sort_by/sort_order）"""
    params = {
        'status': request.args.get('status'),
        'venue': request.args.get('venue'),
        'market': request.args.get('market'),
        'group_id': request.args.get('group_id', type=int),
        'search': request.args.get('q'),
        'favorite': request.args.get('favorite', type=bool, default=False),
        'symbol': request.args.get('symbol'),
        'tag_ids_str': request.args.get('tag_ids'),
        'tag_id': request.args.get('tag_id', type=int),
        'asset_types': request.args.get('asset_types'),
        'page': request.args.get('page', type=int, default=1),
        'per_page': request.args.get('per_page', type=int, default=20),
        'sort_by': request.args.get('sort_by'),
        'sort_order': request.args.get('sort_order', 'asc'),
    }

    with get_db() as db:
        # 分页参数：page 从 1 开始；per_page 限幅 [1, 200] 避免一次性拉取全量
        page = max(params['page'] or 1, 1)
        per_page = max(min(params['per_page'] or 20, 200), 1)
        offset = (page - 1) * per_page
        if params['status'] == 'HOLDING':
            # 持仓分组 = 全部真实持仓（positions 表 active，按 symbol 聚合），
            # 不走 watchlist.status 快照查询；返回虚拟行（id=None，前端据此禁用行操作）
            data = _list_holding_items(
                db,
                get_family_id(),
                venue=params['venue'],
                search=params['search'],
                asset_types=params['asset_types'],
            )
            data = _apply_user_sort(data, params['sort_by'], params['sort_order'])
            total = len(data)
            page_data = data[offset : offset + per_page]
            return jsonify({'data': page_data, 'total': total, 'message': 'ok'})

        if not params['status'] and not (
            params['symbol'] or params['market'] or params['tag_id'] or params['asset_types']
        ):
            # 「全部」分组 = 自选清单 ∪ 真实持仓补集（同一 symbol 自选优先），
            # 前端「全部」分组不传 status 走此分支，解决「全部 < 持仓」口径矛盾。
            # 仅无查找型参数（symbol/market/tag_id/asset_types）时合并——
            # AddToWatchlistModal/OcrImportModal 的「symbol 查重」与「类型筛选」
            # 等调用依赖原过滤语义，不得在此被稀释。
            try:
                data = _build_all_items(
                    db,
                    get_family_id(),
                    venue=params['venue'],
                    search=params['search'],
                    tag_ids_str=params['tag_ids_str'],
                    favorite=params['favorite'],
                    group_id=params['group_id'],
                )
            except ValueError as e:
                abort(400, str(e))
            data = _apply_user_sort(data, params['sort_by'], params['sort_order'])
            total = len(data)
            page_data = data[offset : offset + per_page]
            return jsonify({'data': page_data, 'total': total, 'message': 'ok'})

        try:
            query, total = get_filtered_items_query(
                db,
                get_family_id(),
                status=params['status'],
                venue=params['venue'],
                market=params['market'],
                group_id=params['group_id'],
                search=params['search'],
                favorite=params['favorite'],
                symbol=params['symbol'],
                tag_ids_str=params['tag_ids_str'],
                tag_id=params['tag_id'],
                asset_types=params['asset_types'],
            )
        except ValueError as e:
            abort(400, str(e))

        items = query.order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.updated_at.desc()).all()
        data = [_enrich_item(item, db) for item in items]
        data = _apply_user_sort(data, params['sort_by'], params['sort_order'])

        total = len(data)
        page_data = data[offset : offset + per_page]
        return jsonify({'data': page_data, 'total': total, 'message': 'ok'})


@watchlist_bp.post('/items/')
def create_item():
    """添加自选资产"""
    json_data = parse_body(WatchlistItemCreate)
    data = json_data.model_dump()
    if not data['symbol'].strip():
        abort(400, '代码不能为空')

    with get_db() as db:
        try:
            item = create_watchlist_item(db, data, get_family_id())
            return jsonify({'data': _enrich_item(item, db), 'message': 'ok'})
        except ValueError as e:
            msg = str(e)
            if '已在自选' in msg:
                return jsonify({'data': None, 'message': msg}), 409
            else:
                return jsonify({'data': None, 'message': msg}), 400


@watchlist_bp.patch('/items/<int:item_id>/')
def update_item(item_id):
    """更新自选资产（置顶、状态、笔记等）"""
    json_data = parse_body(WatchlistItemUpdate)
    with get_db() as db:
        item = get_owned_or_404(db, WatchlistItem, item_id)
        if not item:
            abort(404, '自选记录不存在')
        update_data = json_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(item, field, value)
        db.commit()
        db.refresh(item)
        return jsonify({'data': _enrich_item(item, db), 'message': 'ok'})


@watchlist_bp.delete('/items/<int:item_id>/')
def delete_item(item_id):
    """删除自选资产（同时清理关联）"""
    with get_db() as db:
        item = get_owned_or_404(db, WatchlistItem, item_id)
        if not item:
            abort(404, '自选记录不存在')
        db.delete(item)
        db.commit()
        return jsonify({'message': 'ok', 'data': None})


# ─────────────── 分组 CRUD ───────────────
@watchlist_bp.get('/groups/')
def list_groups():
    with get_db() as db:
        data = build_groups_data(db, get_family_id())
    return jsonify({'data': data, 'message': 'ok'})


@watchlist_bp.post('/groups/')
def create_group():
    json_data = parse_body(WatchlistGroupCreate)
    with get_db() as db:
        name = json_data.name.strip()
        # 检查是否已存在同名分组（家庭维度），避免重名
        existing = (
            db.query(WatchlistGroup)
            .filter(WatchlistGroup.name == name, WatchlistGroup.family_id == get_family_id())
            .first()
        )
        if existing:
            abort(409, f'分组「{name}」已存在')

        data = json_data.model_dump()
        data['name'] = name
        group = WatchlistGroup(**data, family_id=get_family_id())
        group.is_system = False
        db.add(group)
        db.commit()
        db.refresh(group)
        return jsonify({'data': WatchlistGroupOut.model_validate(group).model_dump(), 'message': 'ok'})


@watchlist_bp.patch('/groups/<int:group_id>/')
def update_group(group_id):
    """更新分组"""
    json_data = parse_body(WatchlistGroupUpdate)
    with get_db() as db:
        group = get_owned_or_404(db, WatchlistGroup, group_id)
        if not group:
            abort(404, '分组不存在')
        # 重命名时校验是否与其他分组重名（排除自身）
        if json_data.name is not None:
            name = json_data.name.strip()
            name_conflict = (
                db.query(WatchlistGroup)
                .filter(
                    WatchlistGroup.name == name,
                    WatchlistGroup.family_id == get_family_id(),
                    WatchlistGroup.id != group_id,
                )
                .first()
            )
            if name_conflict:
                abort(409, f'分组「{name}」已存在')
            json_data.name = name
        update_data = json_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(group, field, value)
        db.commit()
        return jsonify({'data': WatchlistGroupOut.model_validate(group).model_dump(), 'message': 'ok'})


@watchlist_bp.delete('/groups/<int:group_id>/')
def delete_group(group_id):
    """删除分组（级联删除关联）"""
    with get_db() as db:
        group = get_owned_or_404(db, WatchlistGroup, group_id)
        if not group:
            abort(404, '分组不存在')
        db.delete(group)
        db.commit()
        return jsonify({'message': 'ok', 'data': None})


# ─────────────── 资产-分组关联 ───────────────
@watchlist_bp.post('/items/<int:item_id>/groups/<int:group_id>/')
def add_item_to_group(item_id, group_id):
    """将资产加入分组"""
    with get_db() as db:
        item = get_owned_or_404(db, WatchlistItem, item_id)
        if not item:
            abort(404, '自选记录不存在')
        group = get_owned_or_404(db, WatchlistGroup, group_id)
        if not group:
            abort(404, '分组不存在')

        existing = db.query(WatchlistItemGroup).filter_by(item_id=item_id, group_id=group_id).first()
        if existing:
            abort(409, '该资产已在此分组中')

        link = WatchlistItemGroup(item_id=item_id, group_id=group_id)
        db.add(link)
        db.commit()
        return jsonify({'message': 'ok'})


@watchlist_bp.delete('/items/<int:item_id>/groups/<int:group_id>/')
def remove_item_from_group(item_id, group_id):
    """从分组中移除资产"""
    with get_db() as db:
        # 先校验 item / group 均属当前家庭，避免越权操作关联表
        get_owned_or_404(db, WatchlistItem, item_id)
        get_owned_or_404(db, WatchlistGroup, group_id)
        link = db.query(WatchlistItemGroup).filter_by(item_id=item_id, group_id=group_id).first()
        if not link:
            abort(404, '未找到关联')
        db.delete(link)
        db.commit()
        return jsonify({'message': 'ok', 'data': None})


# ─────────────── 标签管理 ───────────────
@watchlist_bp.get('/tags/')
def list_tags():
    """获取所有标签，支持搜索和排序"""
    q = request.args.get('q')
    sort_by = request.args.get('sort_by', 'created_at')  # 默认按创建时间倒序

    with get_db() as db:
        query = db.query(WatchlistTagDef).filter(WatchlistTagDef.family_id == get_family_id())

        if q:
            query = query.filter(WatchlistTagDef.name.ilike(f'%{q}%'))

        if sort_by == 'frequency':
            # 按使用频率排序（关联的资产数量）

            count_sub_query = (
                db.query(WatchlistItemTag.tag_id, func.count(WatchlistItemTag.item_id).label('cnt'))
                .group_by(WatchlistItemTag.tag_id)
                .subquery()
            )
            query = query.outerjoin(count_sub_query, WatchlistTagDef.id == count_sub_query.c.tag_id).order_by(
                desc(func.coalesce(count_sub_query.c.cnt, 0))
            )
        else:
            query = query.order_by(WatchlistTagDef.created_at.desc())

        tags = query.limit(50).all()
        data = [WatchlistTagDefOut.model_validate(t).model_dump() for t in tags]
        return jsonify({'data': data, 'message': 'ok'})


@watchlist_bp.post('/tags/')
def create_tag():
    """创建标签"""
    json_data = parse_body(WatchlistTagDefCreate)
    with get_db() as db:
        name = json_data.name.strip()
        # 检查是否已存在同名标签（家庭维度）
        existing = (
            db.query(WatchlistTagDef)
            .filter(WatchlistTagDef.name == name, WatchlistTagDef.family_id == get_family_id())
            .first()
        )
        if existing:
            abort(409, f'标签「{name}」已存在')

        tag = WatchlistTagDef(name=name, color=json_data.color, family_id=get_family_id())
        db.add(tag)
        db.commit()
        db.refresh(tag)
        return jsonify({'data': WatchlistTagDefOut.model_validate(tag).model_dump(), 'message': 'ok'})


@watchlist_bp.delete('/tags/<int:tag_id>/')
def delete_tag(tag_id):
    with get_db() as db:
        tag = get_owned_or_404(db, WatchlistTagDef, tag_id)
        if not tag:
            abort(404, '标签不存在')

        # 检查标签是否已被使用
        usage_count = db.query(WatchlistItemTag).filter(WatchlistItemTag.tag_id == tag_id).count()
        if usage_count > 0:
            abort(409, f'标签「{tag.name}」已被 {usage_count} 个资产使用，无法删除')

        db.delete(tag)
        db.commit()
        return jsonify({'message': 'ok', 'data': None})


# ─────────────── 资产-标签关联 ───────────────
@watchlist_bp.post('/items/<int:item_id>/tags/<int:tag_id>/')
def add_tag_to_item(item_id, tag_id):
    with get_db() as db:
        item = get_owned_or_404(db, WatchlistItem, item_id)
        if not item:
            abort(404, '自选记录不存在')
        tag = get_owned_or_404(db, WatchlistTagDef, tag_id)
        if not tag:
            abort(404, '标签不存在')

        existing = db.query(WatchlistItemTag).filter_by(item_id=item_id, tag_id=tag_id).first()
        if existing:
            abort(409, '该资产已绑定此标签')

        link = WatchlistItemTag(item_id=item_id, tag_id=tag_id)
        db.add(link)
        db.commit()
        return jsonify({'message': 'ok'})


@watchlist_bp.delete('/items/<int:item_id>/tags/<int:tag_id>/')
def remove_tag_from_item(item_id, tag_id):
    with get_db() as db:
        # 先校验 item / tag 均属当前家庭，避免越权操作关联表
        get_owned_or_404(db, WatchlistItem, item_id)
        get_owned_or_404(db, WatchlistTagDef, tag_id)
        link = db.query(WatchlistItemTag).filter_by(item_id=item_id, tag_id=tag_id).first()
        if not link:
            abort(404, '未找到关联')
        db.delete(link)
        db.commit()
        return jsonify({'message': 'ok', 'data': None})


# ─────────────── 特别关注管理 ───────────────


@watchlist_bp.get('/favorites/')
@with_db
def list_favorites(db):
    items = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.favorite, WatchlistItem.family_id == get_family_id())
        .order_by(WatchlistItem.favorite_at.desc())
        .all()
    )
    data = []
    for item in items:
        d = _enrich_item(item, db)
        # 补充笔记摘要
        if item.notes:
            d['notes_summary'] = item.notes[:80] + ('...' if len(item.notes) > 80 else '')
        else:
            d['notes_summary'] = None
        data.append(d)
    return api_response(data=data)


@watchlist_bp.post('/items/<int:item_id>/favorite/')
@with_db
def toggle_favorite(db, item_id):
    item = get_owned_or_404(db, WatchlistItem, item_id)

    if not item:
        abort(404, '自选记录不存在')
    if item.favorite:
        item.favorite = False
        item.favorite_at = None
    else:
        item.favorite = True
        item.favorite_at = date.today()
    db.commit()
    db.refresh(item)
    data = _enrich_item(item, db)
    return api_response(data=data)


# ─────────────── 清仓智能提示条件检测 ───────────────
@watchlist_bp.get('/items/<int:item_id>/smart-prompt-conditions/')
def get_smart_prompt_conditions(item_id):
    """
    检查清仓时是否满足特别关注智能提示条件。
    返回条件是否触发及详细指标。
    """
    with get_db() as db:
        item = get_owned_or_404(db, WatchlistItem, item_id)
        if not item:
            abort(404, '自选记录不存在')

        # 关联交易记录（家庭维度）
        transactions = (
            db.query(Transaction)
            .filter(Transaction.position_name.ilike(f'%{item.symbol}%'), Transaction.family_id == get_family_id())
            .all()
        )

        buy_txns = [t for t in transactions if t.txn_type == 'buy']
        sell_txns = [t for t in transactions if t.txn_type == 'sell']
        trade_count = len(buy_txns) + len(sell_txns)

        holding_days = 0
        if buy_txns and sell_txns:
            first_buy = min(t.trade_date for t in buy_txns if t.trade_date)
            last_sell = max(t.trade_date for t in sell_txns if t.trade_date)
            holding_days = (last_sell - first_buy).days

        conditions = {
            'holding_days_gt_180': holding_days > 180,
            'trade_count_gt_6': trade_count > 6,
            'has_notes': bool(item.notes),
            'holding_days': holding_days,
            'trade_count': trade_count,
            'should_prompt': (holding_days > 180) or (trade_count > 6) or bool(item.notes),
        }
        return jsonify({'data': conditions, 'message': 'ok'})


@watchlist_bp.patch('/tags/<int:tag_id>/')
def update_tag(tag_id):
    json_data = parse_body(WatchlistTagDefUpdate)
    with get_db() as db:
        tag = get_owned_or_404(db, WatchlistTagDef, tag_id)
        if not tag:
            abort(404, '标签不存在')
        update_data = json_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(tag, field, value)
        db.commit()
        db.refresh(tag)
        return jsonify({'data': WatchlistTagDefOut.model_validate(tag).model_dump(), 'message': 'ok'})


@watchlist_bp.get('/items/export/')
def export_items():
    """导出当前筛选条件下的自选列表为 CSV"""
    params = {
        'status': request.args.get('status'),
        'venue': request.args.get('venue'),
        'market': request.args.get('market'),
        'group_id': request.args.get('group_id', type=int),
        'search': request.args.get('q'),
        'favorite': request.args.get('favorite', type=bool, default=False),
        'symbol': request.args.get('symbol'),
        'tag_ids_str': request.args.get('tag_ids'),
        'tag_id': request.args.get('tag_id', type=int),
        'asset_types': request.args.get('asset_types'),
    }

    with get_db() as db:
        if params['status'] == 'HOLDING':
            # 持仓分组导出：与列表一致，导出全部真实持仓（虚拟行，id=None）
            rows = _list_holding_items(db, get_family_id(), venue=params['venue'], search=params['search'])
        elif not params['status'] and not (
            params['symbol'] or params['market'] or params['tag_id'] or params['asset_types']
        ):
            # 「全部」导出与列表口径一致：自选 ∪ 持仓补集（复用同一合并逻辑；
            # 带 symbol/market/tag_id 查找参数时仍走原过滤语义，与列表分支对齐）
            try:
                rows = _build_all_items(
                    db,
                    get_family_id(),
                    venue=params['venue'],
                    search=params['search'],
                    tag_ids_str=params['tag_ids_str'],
                    favorite=params['favorite'],
                    group_id=params['group_id'],
                )
            except ValueError as e:
                abort(400, str(e))
        else:
            try:
                query, _ = get_filtered_items_query(db, get_family_id(), **params)
            except ValueError as e:
                abort(400, str(e))
            rows = [_enrich_item(item, db) for item in query.all()]  # 导出不分页

        output = io.StringIO()
        # UTF-8 BOM：Excel 打开 CSV 时按 BOM 识别 UTF-8，否则中文乱码
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow(['代码', '名称', '市场', '类型', '场内/场外', '状态', '置顶', '特别关注', '标签'])
        for item in rows:
            writer.writerow(
                [
                    item['symbol'],
                    item['display_name'] or item['symbol'],
                    item['market'] or '',
                    TYPE_LABELS.get(item['asset_type'], item['asset_type'] or ''),
                    _VENUE_LABELS.get(item['venue'], item['venue'] or ''),
                    _STATUS_LABELS.get(item['status'], item['status'] or ''),
                    '是' if item['is_pinned'] else '否',
                    '是' if item['favorite'] else '否',
                    ','.join(str(tid) for tid in (item['tag_ids'] or [])),
                ]
            )
        output.seek(0)
        return Response(
            output,
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': 'attachment; filename=watchlist.csv'},
        )
