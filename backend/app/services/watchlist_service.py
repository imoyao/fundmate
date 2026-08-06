# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/13 13:41
# File : watchlist_service.py
# -*- coding: utf-8 -*-
"""自选模块服务层：分组数据构建"""

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Query, Session

from app.core.symbol_utils import get_normalizer
from app.domains.funds.models import Fund
from app.domains.positions.models import Position
from app.domains.securities.models import Security
from app.domains.watchlist.models import WatchlistGroup, WatchlistItem, WatchlistItemGroup, WatchlistItemTag
from app.services.async_backfill import trigger_backfill

GROUP_COLORS = {
    'all': '#999',
    'holding': '#ff4d4f',
    'watching': '#52c41a',
    'cleared': '#fa8c16',
    'exchange': '#1890ff',
    'otc': '#722ed1',
    'favorite': '#a6a6d2',
}


def build_groups_data(db: Session, family_id: int) -> list[dict]:
    """构建分组列表数据（系统分组 + 自定义分组），包含资产数量"""
    groups_data = list()

    def _item_base():
        return db.query(WatchlistItem).filter(WatchlistItem.family_id == family_id)

    # 1. 全部
    groups_data.append(
        {
            'key': 'all',
            'label': '全部',
            'color': GROUP_COLORS['all'],
            'count': _item_base().count(),
            'is_system': True,
        }
    )

    # 2. 持仓
    groups_data.append(
        {
            'key': 'holding',
            'label': '持仓',
            'color': GROUP_COLORS['holding'],
            'count': _item_base().filter(WatchlistItem.status == 'HOLDING').count(),
            'is_system': True,
        }
    )

    # 3. 观察中
    groups_data.append(
        {
            'key': 'watching',
            'label': '观察中',
            'color': GROUP_COLORS['watching'],
            'count': _item_base().filter(WatchlistItem.status == 'WATCHING').count(),
            'is_system': True,
        }
    )

    # 4. 已清仓（构建子查询，并显式 select 消除警告）
    position_sum = (
        db.query(Position.symbol, func.sum(Position.quantity).label('total_qty'))
        .filter(Position.family_id == family_id)
        .group_by(Position.symbol)
        .subquery()
    )
    cleared_symbols = db.query(position_sum.c.symbol).filter(position_sum.c.total_qty == 0).subquery()
    groups_data.append(
        {
            'key': 'cleared',
            'label': '已清仓',
            'color': GROUP_COLORS['cleared'],
            'count': _item_base().filter(WatchlistItem.symbol.in_(select(cleared_symbols))).count(),
            'is_system': True,
        }
    )

    # 5. 场内资产
    groups_data.append(
        {
            'key': 'exchange',
            'label': '场内资产',
            'color': GROUP_COLORS['exchange'],
            'count': _item_base().filter(WatchlistItem.venue == 'EXCHANGE').count(),
            'is_system': True,
        }
    )

    # 6. 场外基金
    groups_data.append(
        {
            'key': 'otc',
            'label': '场外基金',
            'color': GROUP_COLORS['otc'],
            'count': _item_base().filter(WatchlistItem.venue == 'OTC').count(),
            'is_system': True,
        }
    )

    # 7. 特别关注
    groups_data.append(
        {
            'key': 'favorite',
            'label': '特别关注',
            'color': GROUP_COLORS['favorite'],
            'count': _item_base().filter(WatchlistItem.favorite).count(),
            'is_system': True,
        }
    )

    # 8. 自定义分组
    custom_groups = (
        db.query(WatchlistGroup)
        .filter(WatchlistGroup.is_system.is_(False), WatchlistGroup.family_id == family_id)
        .order_by(WatchlistGroup.sort_order)
        .all()
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

    return groups_data


def _get_display_name(symbol: str, db: Session) -> str:
    """根据标准化代码查询资产展示名称"""
    sec = db.query(Security).filter_by(symbol=symbol).first()
    if sec and sec.name:
        return sec.name
    fund = db.query(Fund).filter_by(fund_code=symbol).first()
    if fund and fund.name:
        return fund.name
    return symbol


def normalize_and_infer_venue(
    symbol: str,
    venue: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> Dict[str, Any]:
    symbol = symbol.strip().upper()

    # 如果没有 venue，必须根据 asset_type 推断，否则报错
    if venue is None:
        if asset_type == 'fund':
            venue = 'OTC'
        else:
            raise ValueError('缺少 asset_type 或 venue，无法判断资产类型')

    # 场外基金直接返回原始代码
    if venue == 'OTC':
        return {'symbol': symbol, 'market': 'CN_A', 'venue': 'OTC'}

    # 场内资产标准化
    if venue == 'EXCHANGE':
        normalizer = get_normalizer()
        normalized, market, _ = normalizer.normalize(symbol)
        return {'symbol': normalized or symbol, 'market': market or 'UNKNOWN', 'venue': 'EXCHANGE'}

    # 其他未知 venue 也报错
    raise ValueError(f'无效的 venue 值: {venue}')


def create_watchlist_item(db: Session, data: Dict[str, Any], family_id: int) -> WatchlistItem:
    """创建自选资产并触发异步回填"""
    normalized = normalize_and_infer_venue(
        data['symbol'],
        data.get('venue'),
        data.get('asset_type'),
    )
    symbol = normalized['symbol']

    # 查重（家庭维度）
    existing = (
        db.query(WatchlistItem)
        .filter_by(symbol=symbol, market=normalized['market'], venue=normalized['venue'], family_id=family_id)
        .first()
    )
    if existing:
        raise ValueError('该资产已在自选列表中')

    # 持仓状态判断（家庭维度）
    has_position = db.query(Position).filter(Position.symbol == symbol, Position.family_id == family_id).first()
    status = 'HOLDING' if has_position else 'WATCHING'

    item = WatchlistItem(
        symbol=symbol,
        market=normalized['market'],
        asset_type=data.get('asset_type'),
        venue=normalized['venue'],
        status=status,
        add_reason=data.get('add_reason'),
        is_pinned=data.get('is_pinned', False),
        pinned_at=date.today() if data.get('is_pinned') else None,
        family_id=family_id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    # 异步回填
    try:
        backfill_type = 'fund' if (data['symbol'].isdigit() and len(data['symbol']) == 6) else 'stock'
        trigger_backfill(backfill_type, data['symbol'])
    except Exception:
        pass

    return item


def build_home_summary(db: Session, family_id: int) -> List[Dict[str, Any]]:
    """构建首页自选摘要数据"""
    pinned = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.is_pinned, WatchlistItem.family_id == family_id)
        .order_by(WatchlistItem.pinned_at.desc())
        .limit(6)
        .all()
    )
    result_items = list(pinned)
    pinned_ids = {item.id for item in pinned}

    if len(result_items) < 5:
        needed = 5 - len(result_items)
        market_value_subq = (
            db.query(Position.symbol, func.sum(Position.quantity * Position.current_price).label('market_value'))
            .filter(Position.family_id == family_id)
            .group_by(Position.symbol)
            .subquery()
        )
        holding_items = (
            db.query(WatchlistItem, market_value_subq.c.market_value)
            .filter(
                WatchlistItem.status == 'HOLDING',
                WatchlistItem.family_id == family_id,
                ~WatchlistItem.id.in_(pinned_ids) if pinned_ids else True,
            )
            .outerjoin(market_value_subq, WatchlistItem.symbol == market_value_subq.c.symbol)
            .order_by(market_value_subq.c.market_value.desc().nullslast())
            .limit(needed)
            .all()
        )
        for item, _ in holding_items:
            result_items.append(item)

    result_items = result_items[:5]

    data = []
    for item in result_items:
        display_name = _get_display_name(item.symbol, db)
        position_value = (
            db.query(func.sum(Position.quantity * Position.current_price))
            .filter(Position.symbol == item.symbol, Position.family_id == family_id)
            .scalar()
            or 0.0
        )
        current_price = (
            db.query(func.avg(Position.current_price))
            .filter(Position.symbol == item.symbol, Position.family_id == family_id)
            .scalar()
        )
        data.append(
            {
                'id': item.id,
                'symbol': item.symbol,
                'display_name': display_name,
                'is_pinned': item.is_pinned,
                'current_price': round(current_price, 2) if current_price else None,
                'change_pct': None,
                'position_market_value': round(position_value, 2),
                'status': item.status,
                'venue': item.venue,
            }
        )

    return data


def get_filtered_items_query(
    db: Session,
    family_id: int,
    status: Optional[str] = None,
    venue: Optional[str] = None,
    market: Optional[str] = None,
    group_id: Optional[int] = None,
    search: Optional[str] = None,
    favorite: bool = False,
    symbol: Optional[str] = None,
    tag_ids_str: Optional[str] = None,
    tag_id: Optional[int] = None,
) -> Tuple[Query, int]:
    """
    根据筛选条件构建查询对象并返回总条数。
    返回 (query, total)
    """
    query = db.query(WatchlistItem).filter(WatchlistItem.family_id == family_id)

    if symbol:
        query = query.filter(WatchlistItem.symbol == symbol)

    if group_id:
        query = query.join(WatchlistItem.group_links).filter(WatchlistItemGroup.group_id == group_id)

    cleared_symbols = None
    if status and status == 'cleared':
        position_sum = (
            select(Position.symbol, func.sum(Position.quantity).label('total_qty'))
            .where(Position.family_id == family_id)
            .group_by(Position.symbol)
            .subquery()
        )
        cleared_symbols = select(position_sum.c.symbol).where(position_sum.c.total_qty == 0).subquery()

    if status:
        if status in ('HOLDING', 'WATCHING'):
            query = query.filter(WatchlistItem.status == status)
        elif status == 'cleared':
            query = query.filter(WatchlistItem.symbol.in_(select(cleared_symbols)))

    if venue:
        query = query.filter(WatchlistItem.venue == venue)
    if market:
        query = query.filter(WatchlistItem.market == market)
    if favorite:
        query = query.filter(WatchlistItem.favorite)

    if tag_ids_str:
        try:
            tag_id_list = [int(tid.strip()) for tid in tag_ids_str.split(',') if tid.strip()]
        except ValueError:
            raise ValueError('tag_ids 参数格式错误')
        if tag_id_list:
            item_ids_sub_query = (
                db.query(distinct(WatchlistItemTag.item_id)).filter(WatchlistItemTag.tag_id.in_(tag_id_list)).subquery()
            )
            query = query.filter(WatchlistItem.id.in_(item_ids_sub_query))
    elif tag_id:
        query = query.join(WatchlistItem.tag_links).filter(WatchlistItemTag.tag_id == tag_id)

    if search:
        query = query.filter(WatchlistItem.symbol.ilike(f'%{search}%'))

    # 计算总数（清仓状态特殊处理）
    if status == 'cleared' and cleared_symbols is not None:
        total = (
            db.query(WatchlistItem)
            .filter(WatchlistItem.symbol.in_(cleared_symbols), WatchlistItem.family_id == family_id)
            .count()
        )
    else:
        total = query.count()

    return query, total
