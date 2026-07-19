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

from app.core.database import get_db
from app.core.utils import api_response, with_db
from app.domains.funds.models import Fund
from app.domains.positions.models import Position
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

    return out


# 新增两个辅助函数在文件顶部
def _compute_position_market_value(symbol, db):
    return (
        db.query(func.sum(Position.quantity * Position.current_price)).filter(Position.symbol == symbol).scalar() or 0.0
    )


def _compute_avg_current_price(symbol, db):
    return db.query(func.avg(Position.current_price)).filter(Position.symbol == symbol).scalar()


@watchlist_bp.get('/home-summary/')
def home_summary():
    """首页自选摘要"""
    with get_db() as db:
        data = build_home_summary(db)
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
            query, total = get_filtered_items_query(db, **params)
        except ValueError as e:
            abort(400, str(e))

        items = query.order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.updated_at.desc()).all()
        data = [_enrich_item(item, db) for item in items]

        return jsonify({'data': data, 'total': total, 'message': 'ok'})


@watchlist_bp.post('/items/')
@watchlist_bp.input(WatchlistItemCreate)
def create_item(json_data):
    """添加自选资产"""
    data = json_data.model_dump()
    if not data['symbol'].strip():
        abort(400, '代码不能为空')

    with get_db() as db:
        try:
            item = create_watchlist_item(db, data)
            return jsonify({'data': _enrich_item(item, db), 'message': 'ok'})
        except ValueError as e:
            msg = str(e)
            print(f'--------MSG--1111111111111----{msg}')
            if '已在自选' in msg:
                return jsonify({'data': None, 'message': msg}), 409
            else:
                return jsonify({'data': None, 'message': msg}), 400


@watchlist_bp.patch('/items/<int:item_id>/')
@watchlist_bp.input(WatchlistItemUpdate)
def update_item(item_id, json_data):
    """更新自选资产（置顶、状态、笔记等）"""
    with get_db() as db:
        item = db.query(WatchlistItem).get(item_id)
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
        item = db.query(WatchlistItem).get(item_id)
        if not item:
            abort(404, '自选记录不存在')
        db.delete(item)
        db.commit()
        return jsonify({'message': 'ok', 'data': None})


# ─────────────── 分组 CRUD ───────────────
@watchlist_bp.get('/groups/')
def list_groups():
    with get_db() as db:
        data = build_groups_data(db)
    return jsonify({'data': data, 'message': 'ok'})


@watchlist_bp.post('/groups/')
@watchlist_bp.input(WatchlistGroupCreate)
def create_group(json_data):
    with get_db() as db:
        group = WatchlistGroup(**json_data.model_dump())
        group.is_system = False
        db.add(group)
        db.commit()
        db.refresh(group)
        return jsonify({'data': WatchlistGroupOut.model_validate(group).model_dump(), 'message': 'ok'})


@watchlist_bp.patch('/groups/<int:group_id>/')
@watchlist_bp.input(WatchlistGroupUpdate)
def update_group(group_id, json_data):
    """更新分组"""
    with get_db() as db:
        group = db.query(WatchlistGroup).get(group_id)
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
        group = db.query(WatchlistGroup).get(group_id)
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
        item = db.query(WatchlistItem).get(item_id)
        if not item:
            abort(404, '自选记录不存在')
        group = db.query(WatchlistGroup).get(group_id)
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
        query = db.query(WatchlistTagDef)

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
@watchlist_bp.input(WatchlistTagDefCreate)
def create_tag(json_data):
    """创建标签"""
    with get_db() as db:
        name = json_data.name.strip()
        # 检查是否已存在同名标签
        existing = db.query(WatchlistTagDef).filter(WatchlistTagDef.name == name).first()
        if existing:
            abort(409, f'标签「{name}」已存在')

        logger.info(f'============{json_data.color}===')

        tag = WatchlistTagDef(name=name, color=json_data.color)
        db.add(tag)
        db.commit()
        db.refresh(tag)
        return jsonify({'data': WatchlistTagDefOut.model_validate(tag).model_dump(), 'message': 'ok'})


@watchlist_bp.delete('/tags/<int:tag_id>/')
def delete_tag(tag_id):
    with get_db() as db:
        tag = db.query(WatchlistTagDef).get(tag_id)
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
        item = db.query(WatchlistItem).get(item_id)
        if not item:
            abort(404, '自选记录不存在')
        tag = db.query(WatchlistTagDef).get(tag_id)
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
    items = db.query(WatchlistItem).filter(WatchlistItem.favorite).order_by(WatchlistItem.favorite_at.desc()).all()
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
    item = db.query(WatchlistItem).get(item_id)

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
        item = db.query(WatchlistItem).get(item_id)
        if not item:
            abort(404, '自选记录不存在')

        # 关联交易记录
        transactions = db.query(Transaction).filter(Transaction.position_name.ilike(f'%{item.symbol}%')).all()

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
@watchlist_bp.input(WatchlistTagDefUpdate)  # 需要新增 Schema
def update_tag(tag_id, json_data):
    with get_db() as db:
        tag = db.query(WatchlistTagDef).get(tag_id)
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
            query, _ = get_filtered_items_query(db, **params)
        except ValueError as e:
            abort(400, str(e))

        items = query.all()  # 导出不分页

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['代码', '名称', '市场', '类型', '场内/场外', '状态', '置顶', '特别关注', '标签'])
        for item in items:
            writer.writerow(
                [
                    item.symbol,
                    _get_display_info(item.symbol, db),
                    item.market,
                    item.asset_type,
                    item.venue,
                    item.status,
                    item.is_pinned,
                    item.favorite,
                    ','.join([str(link.tag_id) for link in item.tag_links]),
                ]
            )
        output.seek(0)
        return Response(
            output, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=watchlist.csv'}
        )
