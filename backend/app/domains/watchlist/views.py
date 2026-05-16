# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/13 21:57
# File : views.py
# 自选模块 API

from datetime import date

from apiflask import APIBlueprint
from flask import abort, jsonify, request
from loguru import logger
from sqlalchemy import func, select

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


@watchlist_bp.get('/home-summary/')
def home_summary():
    """首页自选摘要：置顶优先，无置顶时按持仓市值降序，最多5条"""
    with get_db() as db:
        # 1. 获取置顶资产（按置顶时间倒序，最多6个，后续截断）
        pinned = (
            db.query(WatchlistItem)
            .filter(WatchlistItem.is_pinned)
            .order_by(WatchlistItem.pinned_at.desc())
            .limit(6)
            .all()
        )

        result_items = list(pinned)
        pinned_ids = {item.id for item in pinned}

        # 2. 如果不足5个，补充持仓资产
        if len(result_items) < 5:
            needed = 5 - len(result_items)
            # 子查询：持仓市值汇总
            market_value_subq = (
                db.query(Position.symbol, func.sum(Position.quantity * Position.current_price).label('market_value'))
                .group_by(Position.symbol)
                .subquery()
            )

            # 查询状态为HOLDING的watchlist资产，并关联持仓市值
            holding_items = (
                db.query(WatchlistItem, market_value_subq.c.market_value)
                .filter(WatchlistItem.status == 'HOLDING', ~WatchlistItem.id.in_(pinned_ids) if pinned_ids else True)
                .outerjoin(market_value_subq, WatchlistItem.symbol == market_value_subq.c.symbol)
                .order_by(market_value_subq.c.market_value.desc().nullslast())
                .limit(needed)
                .all()
            )

            for item, market_val in holding_items:
                result_items.append(item)

        # 3. 截取前5个
        result_items = result_items[:5]

        # 4. 组装返回数据
        data = []
        for item in result_items:
            # 展示名称
            display_name = item.symbol
            sec = db.query(Security).filter_by(symbol=item.symbol).first()
            if sec:
                display_name = sec.name or item.symbol
            else:
                fund = db.query(Fund).filter_by(fund_code=item.symbol).first()
                if fund:
                    display_name = fund.name or item.symbol

            # 持仓市值（重新计算，确保一致）
            position_value = (
                db.query(func.sum(Position.quantity * Position.current_price))
                .filter(Position.symbol == item.symbol)
                .scalar()
            ) or 0.0

            # 当前价格（取持仓表中该symbol的平均最新价）
            current_price = db.query(func.avg(Position.current_price)).filter(Position.symbol == item.symbol).scalar()

            data.append(
                {
                    'id': item.id,
                    'symbol': item.symbol,
                    'display_name': display_name,
                    'is_pinned': item.is_pinned,
                    'current_price': round(current_price, 2) if current_price else None,
                    'change_pct': None,  # 暂无历史行情
                    'position_market_value': round(position_value, 2),
                    'status': item.status,
                    'venue': item.venue,
                }
            )

        return jsonify({'data': data, 'message': 'ok'})


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
    symbol = request.args.get('symbol')

    with get_db() as db:
        query = db.query(WatchlistItem)

        # 精确符号查询
        if symbol:
            query = query.filter(WatchlistItem.symbol == symbol)

        # 分组筛选（仅自定义分组）
        if group_id:
            query = query.join(WatchlistItem.group_links).filter(WatchlistItemGroup.group_id == group_id)

        # 定义清仓symbol的select构造（提前定义，两处复用）
        cleared_symbols = None
        if status and status == 'cleared':
            # 1. 先构建子查询（计算持仓总数）
            position_sum = (
                select(Position.symbol, func.sum(Position.quantity).label('total_qty'))
                .group_by(Position.symbol)
                .subquery()
            )
            cleared_symbols = select(position_sum.c.symbol).where(position_sum.c.total_qty == 0).subquery()
        # 状态筛选
        if status:
            if status in ('HOLDING', 'WATCHING'):
                query = query.filter(WatchlistItem.status == status)
            elif status == 'cleared':
                # 3. 筛选条件用显式的select构造
                query = query.filter(WatchlistItem.symbol.in_(cleared_symbols))

        # 其他筛选
        if venue:
            query = query.filter(WatchlistItem.venue == venue)
        if market:
            query = query.filter(WatchlistItem.market == market)
        if bookmarked:
            query = query.filter(WatchlistItem.bookmarked)
        if tag_id:
            query = query.join(WatchlistItem.tag_links).filter(WatchlistItemTag.tag_id == tag_id)
        if search:
            query = query.filter(WatchlistItem.symbol.ilike(f'%{search}%'))

        # 排序查询结果
        items = query.order_by(WatchlistItem.is_pinned.desc(), WatchlistItem.updated_at.desc()).all()
        data = [_enrich_item(item, db) for item in items]

        # 计算总数（清仓状态下也用同一个select构造）
        if status == 'cleared' and cleared_symbols is not None:
            # 4. 计数时也传入显式的select构造，彻底消除警告
            total = db.query(WatchlistItem).filter(WatchlistItem.symbol.in_(cleared_symbols)).count()
        else:
            total = len(data)

        return jsonify({'data': data, 'total': total, 'message': 'ok'})


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
            is_pinned=data.get('is_pinned', False),
            pinned_at=date.today() if data.get('is_pinned') else None,
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
    """获取所有分组（系统 + 自定义），并附带资产数量"""
    with get_db() as db:
        groups_data = list()

        # 1. 全部
        groups_data.append(
            {
                'key': 'all',
                'label': '全部',
                'color': '#999',
                'count': db.query(WatchlistItem).count(),
                'is_system': True,
            }
        )

        # 2. 持仓
        groups_data.append(
            {
                'key': 'holding',
                'label': '持仓',
                'color': '#ff4d4f',
                'count': db.query(WatchlistItem).filter(WatchlistItem.status == 'HOLDING').count(),
                'is_system': True,
            }
        )

        # 3. 观察中
        groups_data.append(
            {
                'key': 'watching',
                'label': '观察中',
                'color': '#52c41a',
                'count': db.query(WatchlistItem).filter(WatchlistItem.status == 'WATCHING').count(),
                'is_system': True,
            }
        )

        # 4. 已清仓
        position_sum = (
            db.query(Position.symbol, func.sum(Position.quantity).label('total_qty'))
            .group_by(Position.symbol)
            .subquery()
        )
        cleared_symbols = db.query(position_sum.c.symbol).filter(position_sum.c.total_qty == 0).subquery()
        groups_data.append(
            {
                'key': 'cleared',
                'label': '已清仓',
                'color': '#fa8c16',
                'count': db.query(WatchlistItem).filter(WatchlistItem.symbol.in_(cleared_symbols)).count(),
                'is_system': True,
            }
        )

        # 5. 场内资产
        groups_data.append(
            {
                'key': 'exchange',
                'label': '场内资产',
                'color': '#1890ff',
                'count': db.query(WatchlistItem).filter(WatchlistItem.venue == 'EXCHANGE').count(),
                'is_system': True,
            }
        )

        # 6. 场外基金
        groups_data.append(
            {
                'key': 'otc',
                'label': '场外基金',
                'color': '#722ed1',
                'count': db.query(WatchlistItem).filter(WatchlistItem.venue == 'OTC').count(),
                'is_system': True,
            }
        )

        # 7. 特别关注
        groups_data.append(
            {
                'key': 'bookmarked',
                'label': '特别关注',
                'color': '#a6a6d2',
                'count': db.query(WatchlistItem).filter(WatchlistItem.bookmarked).count(),
                'is_system': True,
            }
        )

        # 8. 自定义分组
        custom_groups = (
            db.query(WatchlistGroup).filter(not WatchlistGroup.is_system).order_by(WatchlistGroup.sort_order).all()
        )
        for g in custom_groups:
            groups_data.append(
                {
                    'id': g.id,
                    'name': g.name,
                    'color': g.color or '#C5C9B8',
                    'sort_order': g.sort_order,
                    'is_system': False,
                    'entity_type': g.entity_type,
                    'count': db.query(WatchlistItemGroup).filter(WatchlistItemGroup.group_id == g.id).count(),
                }
            )

        return jsonify({'data': groups_data, 'message': 'ok'})


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
    """获取所有标签，支持搜索和排序"""
    q = request.args.get('q')
    sort_by = request.args.get('sort_by', 'created_at')  # 默认按创建时间倒序

    with get_db() as db:
        query = db.query(WatchlistTagDef)

        if q:
            query = query.filter(WatchlistTagDef.name.ilike(f'%{q}%'))

        if sort_by == 'frequency':
            # 按使用频率排序（关联的资产数量）
            from sqlalchemy import desc, func

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
