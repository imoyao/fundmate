# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/13 13:41
# File : watchlist_service.py
# -*- coding: utf-8 -*-
"""自选模块服务层：分组数据构建"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.positions.models import Position
from app.domains.watchlist.models import WatchlistGroup, WatchlistItem, WatchlistItemGroup

GROUP_COLORS = {
    'all': '#999',
    'holding': '#ff4d4f',
    'watching': '#52c41a',
    'cleared': '#fa8c16',
    'exchange': '#1890ff',
    'otc': '#722ed1',
    'favorite': '#a6a6d2',
}


def build_groups_data(db: Session) -> list[dict]:
    """构建分组列表数据（系统分组 + 自定义分组），包含资产数量"""
    groups_data = []

    # 1. 全部
    groups_data.append(
        {
            'key': 'all',
            'label': '全部',
            'color': GROUP_COLORS['all'],
            'count': db.query(WatchlistItem).count(),
            'is_system': True,
        }
    )

    # 2. 持仓
    groups_data.append(
        {
            'key': 'holding',
            'label': '持仓',
            'color': GROUP_COLORS['holding'],
            'count': db.query(WatchlistItem).filter(WatchlistItem.status == 'HOLDING').count(),
            'is_system': True,
        }
    )

    # 3. 观察中
    groups_data.append(
        {
            'key': 'watching',
            'label': '观察中',
            'color': GROUP_COLORS['watching'],
            'count': db.query(WatchlistItem).filter(WatchlistItem.status == 'WATCHING').count(),
            'is_system': True,
        }
    )

    # 4. 已清仓（构建子查询，并显式 select 消除警告）
    position_sum = (
        db.query(Position.symbol, func.sum(Position.quantity).label('total_qty')).group_by(Position.symbol).subquery()
    )
    cleared_symbols = db.query(position_sum.c.symbol).filter(position_sum.c.total_qty == 0).subquery()
    groups_data.append(
        {
            'key': 'cleared',
            'label': '已清仓',
            'color': GROUP_COLORS['cleared'],
            'count': db.query(WatchlistItem).filter(WatchlistItem.symbol.in_(select(cleared_symbols))).count(),
            'is_system': True,
        }
    )

    # 5. 场内资产
    groups_data.append(
        {
            'key': 'exchange',
            'label': '场内资产',
            'color': GROUP_COLORS['exchange'],
            'count': db.query(WatchlistItem).filter(WatchlistItem.venue == 'EXCHANGE').count(),
            'is_system': True,
        }
    )

    # 6. 场外基金
    groups_data.append(
        {
            'key': 'otc',
            'label': '场外基金',
            'color': GROUP_COLORS['otc'],
            'count': db.query(WatchlistItem).filter(WatchlistItem.venue == 'OTC').count(),
            'is_system': True,
        }
    )

    # 7. 特别关注
    groups_data.append(
        {
            'key': 'favorite',
            'label': '特别关注',
            'color': GROUP_COLORS['favorite'],
            'count': db.query(WatchlistItem).filter(WatchlistItem.favorite).count(),
            'is_system': True,
        }
    )

    # 8. 自定义分组
    custom_groups = (
        db.query(WatchlistGroup).filter(WatchlistGroup.is_system.is_(False)).order_by(WatchlistGroup.sort_order).all()
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
