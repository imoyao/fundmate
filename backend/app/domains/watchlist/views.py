# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/13 21:57
# File : views.py
# 自选模块 API

import csv
import io
from datetime import date

from apiflask import APIBlueprint
from flask import Response, abort, jsonify, request
from loguru import logger
from sqlalchemy import desc, func

from app.core.auth import get_family_id, get_owned_or_404
from app.core.database import get_db
from app.core.money import Money
from app.core.utils import api_response, with_db
from app.core.validation import parse_body
from app.domains.funds.models import Fund
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
_ASSET_TYPE_LABELS = {'fund': '基金', 'stock': '股票', 'etf': 'ETF', 'bond': '可转债'}

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

    positions.quantity 以最小单位存储（0.0001 份），avg_price/current_price 以分存储，
    换算统一走 Money（min_unit_to_shares / cents_to_yuan）。
    """
    row = (
        db.query(
            func.sum(Position.quantity).label('qty_units'),
            func.sum(Position.quantity * Position.avg_price).label('cost_cents'),
            func.sum(Position.quantity * Position.current_price).label('value_cents'),
        )
        .filter(Position.symbol == symbol, Position.family_id == get_family_id())
        .first()
    )
    if not row or not row.qty_units:
        return None
    quantity = Money.min_unit_to_shares(row.qty_units)  # 最小单位 → 份
    cost_yuan = Money.cents_to_yuan(row.cost_cents / 10000)  # (最小单位×分)/10000 = 分 → 元
    value_yuan = Money.cents_to_yuan(row.value_cents / 10000)
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

    positions.quantity 存最小单位（0.0001 份）、current_price 存分，
    裸乘结果是最小单位·分，须经 Money 换算回元（/10000 转份、/100 转元）。
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

    current_price 以分存储，对外换算回元（禁止裸除 float）。
    """
    avg_price_cents = (
        db.query(func.avg(Position.current_price))
        .filter(Position.symbol == symbol, Position.family_id == get_family_id())
        .scalar()
    )
    return Money.cents_to_yuan(avg_price_cents) if avg_price_cents else 0.0


@watchlist_bp.get('/home-summary/')
def home_summary():
    """首页自选摘要"""
    with get_db() as db:
        data = build_home_summary(db, get_family_id())
    return jsonify({'data': data, 'message': 'ok'})


# ─────────────── 自选资产 CRUD ───────────────


@watchlist_bp.get('/items/')
def list_items():
    """获取自选列表，支持多种筛选和置顶优先排序"""
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
        try:
            query, total = get_filtered_items_query(db, get_family_id(), **params)
        except ValueError as e:
            abort(400, str(e))

        items = query.order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.updated_at.desc()).all()
        data = [_enrich_item(item, db) for item in items]

        return jsonify({'data': data, 'total': total, 'message': 'ok'})


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
        group = WatchlistGroup(**json_data.model_dump(), family_id=get_family_id())
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
        try:
            query, _ = get_filtered_items_query(db, get_family_id(), **params)
        except ValueError as e:
            abort(400, str(e))

        items = query.all()  # 导出不分页

        output = io.StringIO()
        # UTF-8 BOM：Excel 打开 CSV 时按 BOM 识别 UTF-8，否则中文乱码
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow(['代码', '名称', '市场', '类型', '场内/场外', '状态', '置顶', '特别关注', '标签'])
        for item in items:
            writer.writerow(
                [
                    item.symbol,
                    _get_display_info(item.symbol, db),
                    item.market,
                    _ASSET_TYPE_LABELS.get(item.asset_type, item.asset_type or ''),
                    _VENUE_LABELS.get(item.venue, item.venue or ''),
                    _STATUS_LABELS.get(item.status, item.status or ''),
                    '是' if item.is_pinned else '否',
                    '是' if item.favorite else '否',
                    ','.join([str(link.tag_id) for link in item.tag_links]),
                ]
            )
        output.seek(0)
        return Response(
            output,
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': 'attachment; filename=watchlist.csv'},
        )
