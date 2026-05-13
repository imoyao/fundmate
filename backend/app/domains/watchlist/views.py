# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/13 21:57
# File : views.py
# 自选模块 API

from datetime import date

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.database import get_db
from app.core.symbol_utils import get_normalizer
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
)

watchlist_bp = APIBlueprint('watchlist', __name__, url_prefix='/api/watchlist')


# ─────────────── 辅助函数 ───────────────
def _get_display_info(symbol: str, db):
    """根据标准化代码查询展示名称"""
    sec = db.query(Security).filter_by(symbol=symbol).first()
    if sec:
        return sec.name or symbol
    fund = db.query(Fund).filter_by(fund_code=symbol).first()
    if fund:
        return fund.name or symbol
    return symbol


def _enrich_item(item: WatchlistItem, db) -> dict:
    """将 WatchlistItem 转为前端需要的字典，补充展示名称和关联ID"""
    out = WatchlistItemOut.model_validate(item).model_dump()
    out['display_name'] = _get_display_info(item.symbol, db)
    out['group_ids'] = [link.group_id for link in item.group_links]
    out['tag_ids'] = [link.tag_id for link in item.tag_links]
    return out


# ─────────────── 自选资产 CRUD ───────────────
@watchlist_bp.get('/items/')
def list_items():
    """获取自选列表，支持多种筛选和置顶优先排序"""
    status = request.args.get('status')
    venue = request.args.get('venue')
    market = request.args.get('market')
    group_id = request.args.get('group_id', type=int)
    tag_id = request.args.get('tag_id', type=int)
    search = request.args.get('q')
    bookmarked = request.args.get('bookmarked', type=bool, default=False)

    with get_db() as db:
        query = db.query(WatchlistItem)

        if status:
            query = query.filter(WatchlistItem.status == status)
        if venue:
            query = query.filter(WatchlistItem.venue == venue)
        if market:
            query = query.filter(WatchlistItem.market == market)
        if bookmarked:
            query = query.filter(WatchlistItem.bookmarked)
        if group_id:
            query = query.join(WatchlistItem.group_links).filter(WatchlistItemGroup.group_id == group_id)
        if tag_id:
            query = query.join(WatchlistItem.tag_links).filter(WatchlistItemTag.tag_id == tag_id)
        if search:
            query = query.filter(WatchlistItem.symbol.ilike(f'%{search}%'))

        items = query.order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.updated_at.desc()).all()

        data = [_enrich_item(item, db) for item in items]
        return jsonify({'data': data, 'total': len(data), 'message': 'ok'})


@watchlist_bp.post('/items/')
@watchlist_bp.input(WatchlistItemCreate)
def create_item(json_data):
    """添加自选资产"""
    data = json_data.model_dump()
    symbol = data['symbol'].strip().upper()
    if not symbol:
        abort(400, '代码不能为空')

    normalizer = get_normalizer()
    normalized, market = normalizer.normalize(symbol)
    if normalized:
        data['symbol'] = normalized
        data['market'] = data.get('market') or market
    else:
        data['symbol'] = symbol
        data['market'] = data.get('market') or 'UNKNOWN'

    with get_db() as db:
        existing = (
            db.query(WatchlistItem)
            .filter_by(symbol=data['symbol'], market=data['market'], venue=data.get('venue', 'EXCHANGE'))
            .first()
        )
        if existing:
            abort(409, '该资产已在自选列表中')

        # 判断持仓状态
        has_position = db.query(Position).filter(Position.symbol == data['symbol']).first()
        status = 'HOLDING' if has_position else 'WATCHING'

        item = WatchlistItem(
            symbol=data['symbol'],
            market=data['market'],
            asset_type=data.get('asset_type'),
            venue=data.get('venue', 'EXCHANGE'),
            status=status,
            add_reason=data.get('add_reason'),
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        return jsonify({'data': _enrich_item(item, db), 'message': 'ok'})


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
    """获取所有分组（系统分组由前端动态渲染，这里只返回用户自定义分组）"""
    with get_db() as db:
        groups = db.query(WatchlistGroup).order_by(WatchlistGroup.sort_order).all()
        data = [WatchlistGroupOut.model_validate(g).model_dump() for g in groups]
        return jsonify({'data': data, 'message': 'ok'})


@watchlist_bp.post('/groups/')
@watchlist_bp.input(WatchlistGroupCreate)
def create_group(json_data):
    """创建自定义分组"""
    with get_db() as db:
        group = WatchlistGroup(**json_data.model_dump())
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
    with get_db() as db:
        tags = db.query(WatchlistTagDef).all()
        data = [WatchlistTagDefOut.model_validate(t).model_dump() for t in tags]
        return jsonify({'data': data, 'message': 'ok'})


@watchlist_bp.post('/tags/')
@watchlist_bp.input(WatchlistTagDefCreate)
def create_tag(json_data):
    with get_db() as db:
        tag = WatchlistTagDef(**json_data.model_dump())
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
@watchlist_bp.post('/items/<int:item_id>/bookmark/')
def toggle_bookmark(item_id):
    """切换特别关注状态"""
    with get_db() as db:
        item = db.query(WatchlistItem).get(item_id)
        if not item:
            abort(404, '自选记录不存在')
        if item.bookmarked:
            item.bookmarked = False
            item.bookmarked_at = None
        else:
            item.bookmarked = True
            item.bookmarked_at = date.today()
        db.commit()
        db.refresh(item)
        return jsonify({'data': _enrich_item(item, db), 'message': 'ok'})


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
