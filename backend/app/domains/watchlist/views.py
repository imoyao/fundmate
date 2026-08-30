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
from sqlalchemy import desc, func

from app.core.auth import get_family_id, get_owned_or_404
from app.core.constants import TYPE_LABELS
from app.core.database import get_db
from app.core.money import Money
from app.core.utils import api_response, with_db
from app.core.validation import parse_body
from app.domains.funds.models import DailyWorth, Fund
from app.domains.positions.models import Position
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
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
from app.services.watchlist_service import (
    build_groups_data,
    build_home_summary,
    create_watchlist_item,
    get_filtered_items_query,
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
def _get_display_info(symbol: str, db) -> str:
    """根据标准化代码查询资产展示名称，优先取 Security.name，其次 Fund.name，兜底 symbol."""
    sec = db.query(Security).filter_by(symbol=symbol).first()
    if sec and sec.name:
        return sec.name
    fund = db.query(Fund).filter_by(fund_code=symbol).first()
    if fund and fund.name:
        return fund.name
    return symbol


def _enrich_item(item: WatchlistItem, db) -> dict:
    out = WatchlistItemOut.model_validate(item).model_dump()
    # watchlist.asset_type 历史存放大写（STOCK/ETF/...），对外统一归一为小写，
    # 与后端 asset_types 单一来源（stock/etf/fund/bond/index）及 positions 域保持一致（#1171）。
    out['asset_type'] = item.asset_type.lower() if item.asset_type else None
    out['display_name'] = _get_display_info(item.symbol, db)
    out['group_ids'] = [link.group_id for link in item.group_links]
    out['tag_ids'] = [link.tag_id for link in item.tag_links]

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


def _list_holding_items(db, family_id, venue=None, search=None):
    """持仓分组列表：返回 positions 表全部 active 持仓的虚拟行（按 symbol 聚合）。

    与 watchlist.status 快照解耦：一个 symbol 可能多账户多行，distinct 后按 symbol 聚合；
    每行 id=None 表示「无自选记录」，前端据此禁用置顶/关注/标签/移除等行操作。
    """
    rows = (
        db.query(Position.symbol, Position.asset_type, Position.market)
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
    for symbol, asset_type, market in rows:
        if symbol in seen:
            continue  # 同一 symbol 多账户行已聚合，跳过重复
        seen.add(symbol)
        row_venue = venue_map.get(symbol) or ('OTC' if asset_type == 'fund' else 'EXCHANGE')
        if venue and row_venue != venue:
            continue
        if search and search.lower() not in symbol.lower():
            continue
        data.append(_build_holding_row(symbol, db, market=market, asset_type=asset_type, venue=row_venue))
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
    display_name = (pos.name if pos and pos.name else None) or _get_display_info(symbol, db)

    current_price = _compute_avg_current_price(symbol, db)
    stats = _compute_holding_stats(symbol, db)
    return {
        'id': None,
        'symbol': symbol,
        'market': market,
        'asset_type': (asset_type or '').lower() or None,
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
        'tag_ids': [],
        'current_price': round(current_price, 2) if current_price else None,
        'change_pct': None,
        'position_market_value': round(_compute_position_market_value(symbol, db), 2),
        'holding_quantity': stats['quantity'] if stats else None,
        'holding_cost_price': round(stats['cost_price'], 4) if stats else None,
        'holding_pnl': round(stats['pnl'], 2) if stats else None,
        'holding_pnl_percent': round(stats['pnl_percent'], 2) if stats else None,
        'price_at_added': None,
    }


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
        'created_at',
        'current_price',
        'change_pct',
        'holding_quantity',
        'position_market_value',
        'holding_pnl',
        'holding_pnl_percent',
        'price_at_added',
    }
)


def _user_sort_metric(row: dict, sort_by: str):
    """取排序键值；缺失/不可比较返回 None（恒排末尾）。"""
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

    - 白名单外/未指定：维持原顺序（置顶优先 + 更新时间倒序）；
    - 排序稳定且置顶行仍前置：用户排序只改变同优先级内的次序，
      不破坏「置顶恒在顶部」的既有心智；
    - 值缺失（None）的行无论升降序都排在末尾，避免空值干扰阅读。
    """
    if not sort_by or sort_by not in _USER_SORTABLE_FIELDS and sort_by != 'added_return':
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
            data = _list_holding_items(db, get_family_id(), venue=params['venue'], search=params['search'])
            data = _apply_user_sort(data, params['sort_by'], params['sort_order'])
            total = len(data)
            page_data = data[offset : offset + per_page]
            return jsonify({'data': page_data, 'total': total, 'message': 'ok'})

        if not params['status'] and not (params['symbol'] or params['market'] or params['tag_id']):
            # 「全部」分组 = 自选清单 ∪ 真实持仓补集（同一 symbol 自选优先），
            # 前端「全部」分组不传 status 走此分支，解决「全部 < 持仓」口径矛盾。
            # 仅无查找型参数（symbol/market/tag_id）时合并——AddToWatchlistModal/OcrImportModal
            # 的「symbol 查重」等调用依赖原过滤语义，不得在此被稀释。
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
            print(f'--------MSG--1111111111111----{msg}')
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

        logger.info(f'============{json_data.color}===')

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
    }

    with get_db() as db:
        if params['status'] == 'HOLDING':
            # 持仓分组导出：与列表一致，导出全部真实持仓（虚拟行，id=None）
            rows = _list_holding_items(db, get_family_id(), venue=params['venue'], search=params['search'])
        elif not params['status'] and not (params['symbol'] or params['market'] or params['tag_id']):
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
