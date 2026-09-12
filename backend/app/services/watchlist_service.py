# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/13 13:41
# File : watchlist_service.py
# -*- coding: utf-8 -*-
"""自选模块服务层：分组数据构建"""

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Query, Session

from app.core.constants import MANAGER_SYMBOL_PREFIX
from app.core.money import Money
from app.core.symbol_utils import get_normalizer
from app.domains.funds.models import AdvisorPortfolio, Fund, Manager
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

    # 1. 全部（自选清单 ∪ 真实持仓，同一 symbol 自选记录优先去重——
    # 与「全部」分组列表返回条数保持一致，避免出现「全部 < 持仓」的口径矛盾）
    watchlist_symbols = {
        sym for (sym,) in db.query(WatchlistItem.symbol).filter(WatchlistItem.family_id == family_id).all()
    }
    pos_q = db.query(Position.symbol).filter(
        Position.family_id == family_id,
        Position.ownership_status == 'active',
    )
    if watchlist_symbols:
        pos_q = pos_q.filter(Position.symbol.notin_(watchlist_symbols))
    all_count = _item_base().count() + pos_q.distinct().count()
    groups_data.append(
        {
            'key': 'all',
            'label': '全部',
            'color': GROUP_COLORS['all'],
            'count': all_count,
            'is_system': True,
        }
    )

    # 2. 持仓（真实持仓口径：positions 表 active 持仓按 symbol 去重，
    # 不再依赖 watchlist.status 快照——自选页「持仓」分组 = 全部真实持仓）
    holding_count = (
        db.query(Position.symbol)
        .filter(Position.family_id == family_id, Position.ownership_status == 'active')
        .distinct()
        .count()
    )
    groups_data.append(
        {
            'key': 'holding',
            'label': '持仓',
            'color': GROUP_COLORS['holding'],
            'count': holding_count,
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


def lookup_manager(symbol: str, db: Session):
    """按 watchlist symbol（`MGR_<mgr_code>`）回查 managers 表；非经理符号返回 None。

    mgr_code 大小写不敏感——搜索侧（asset_search）原样输出、历史行存在大小写混存，
    等值匹配会漏查（2026-09-10 用户反馈：经理名显示为 sha256 派生码）。
    """
    if not symbol or not symbol.startswith(MANAGER_SYMBOL_PREFIX):
        return None
    code = symbol[len(MANAGER_SYMBOL_PREFIX) :]
    if not code:
        return None
    return db.query(Manager).filter(func.lower(Manager.mgr_code) == code.lower()).first()


def resolve_display_name(symbol: str, db: Session) -> str:
    """资产展示名**唯一**解析链（自选列表页与首页自选摘要共用，禁止再各写一份）。

    优先级：Manager.name（MGR_ 前缀）→ Security.name → Fund.name →
    AdvisorPortfolio.name → symbol 兜底。

    投顾组合（#1167，且慢 ZHxxxx / 蛋卷 / 天天基金 combo）既不在 Securities 也不在
    Funds；基金经理（#1286）只在 managers 表。不补这两层，界面会把原始代码 /
    sha256 派生码甩给用户，编号对用户毫无意义。

    历史教训（本函数即为此收口）：views._get_display_info 与
    services._get_display_name 曾是两份实现，前者补了 Manager/AdvisorPortfolio、
    后者没补 → 自选列表页正常、首页自选组件仍显示 MGR_xxx。同一展示需求两处实现
    必然漂移，故收口为单一实现，改一处即两处生效。
    """
    mgr = lookup_manager(symbol, db)
    if mgr and mgr.name:
        return mgr.name
    sec = db.query(Security).filter_by(symbol=symbol).first()
    if sec and sec.name:
        return sec.name
    fund = db.query(Fund).filter_by(fund_code=symbol).first()
    if fund and fund.name:
        return fund.name
    advisor = db.query(AdvisorPortfolio).filter_by(code=symbol).first()
    if advisor and advisor.name:
        return advisor.name
    return symbol


def normalize_and_infer_venue(
    symbol: str,
    venue: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> Dict[str, Any]:
    symbol = symbol.strip().upper()

    # #1286 品种差异化维度：经理/组合为非交易实体，无市场与交易场所属性，
    # market/venue 存空串（SQLite UNIQUE 中 NULL 互不相等，存 NULL 会使唯一性失效）。
    # symbol 保留平台原生码（经理 MGR_ 前缀 + 权威外部 id；组合 tgcode/ZHxxxx 等）。
    if asset_type in ('manager', 'portfolio'):
        return {'symbol': symbol, 'market': '', 'venue': ''}

    # 指数（index）：symbol 已是聚合搜索归一化的命名空间码（SH000300 / CSI930950 / CNIxxxx），
    # 不能落入下方 EXCHANGE 分支——normalizer 会把它改写成 SH/SZ（market 失真），
    # 且 CSI/CNI 的空 venue 既不是 OTC 也不是 EXCHANGE，会直接抛 ValueError（#1362 评审：指数无法加入自选）。
    # market 由命名空间前缀推断，venue 原样透传搜索返回的值（EXCHANGE / 空串）。
    if asset_type == 'index':
        if symbol[:2] in ('SH', 'SZ'):
            idx_market = 'CN_A'
        elif symbol[:3] in ('CSI', 'CNI'):
            idx_market = symbol[:3]
        else:
            idx_market = ''
        return {'symbol': symbol, 'market': idx_market, 'venue': venue or ''}

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
    # 写入前归一为小写，与后端 asset_types 单一来源（stock/etf/fund/bond/index）及 positions 域一致，
    # 并修正历史大写（STOCK/ETF/...）导致 venue 推断（asset_type=='fund'）失效的问题（#1171）。
    raw_asset_type = (data.get('asset_type') or '').strip().lower() or None
    normalized = normalize_and_infer_venue(
        data['symbol'],
        data.get('venue'),
        raw_asset_type,
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
        asset_type=raw_asset_type,
        venue=normalized['venue'],
        status=status,
        add_reason=data.get('add_reason'),
        is_pinned=data.get('is_pinned', False),
        pinned_at=date.today() if data.get('is_pinned') else None,
        cost_price=data.get('cost_price'),
        quantity=data.get('quantity'),
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


def _infer_venue_for_asset_type(asset_type: Optional[str]) -> Optional[str]:
    """持仓无 venue 列，按资产类型推断与 watchlist 一致的 venue（与 _list_holding_items 同源）。

    - 经理/组合/指数：无交易场所，存空串；
    - 基金/货基：OTC；其余（股票/ETF/可转债）：EXCHANGE。
    normalize_and_infer_venue 对经理/组合/指数会忽略传入 venue，故空串安全。
    """
    at = (asset_type or '').strip().lower()
    if at in ('manager', 'portfolio', 'index'):
        return ''
    if at in ('fund', 'money_fund'):
        return 'OTC'
    return 'EXCHANGE'


def _normalize_for_position(symbol: str, asset_type: Optional[str]) -> Dict[str, Any]:
    """把持仓 (symbol, asset_type) 归一到与 watchlist 唯一键一致的 (symbol, market, venue)。"""
    venue = _infer_venue_for_asset_type(asset_type)
    return normalize_and_infer_venue(symbol, venue, asset_type)


def _find_watchlist_item_for_position(
    db: Session, family_id: int, symbol: str, asset_type: Optional[str]
) -> Optional[WatchlistItem]:
    """按 symbol 定位持仓对应的自选记录（优先精确市场/venue 匹配，否则仅 symbol）。"""
    norm = _normalize_for_position(symbol, asset_type)
    item = (
        db.query(WatchlistItem)
        .filter_by(
            symbol=norm['symbol'],
            market=norm['market'],
            venue=norm['venue'],
            family_id=family_id,
        )
        .first()
    )
    if item is None:
        item = db.query(WatchlistItem).filter_by(symbol=norm['symbol'], family_id=family_id).first()
    return item


def ensure_watchlist_for_positions(db: Session, family_id: int, symbols: Optional[List[str]] = None) -> int:
    """为活跃持仓补齐 HOLDING 自选记录（买入即入自选 / 一键加入）。

    - 已存在 → 升级为 HOLDING（缺失时创建）；
    - 单标的失败仅记录日志、不中断整批（持仓写入路径要求静默，#1458 后续）。
    返回新建数量（已存在升级不计入，避免一次买入多次计数）。

    **不在此处提交事务**：本函数常被持仓写入链路（import/orchestrator 的
    `with db.begin()` 上下文）调用，提前 commit 会关闭外层事务导致后续操作
    报 "closed transaction"。改由各调用方在自身事务内统一提交（视图端点显式
    commit）。
    """
    active_q = db.query(Position).filter(Position.family_id == family_id, Position.ownership_status == 'active')
    if symbols is not None:
        active_q = active_q.filter(Position.symbol.in_(symbols))
    positions = active_q.all()

    seen: set = set()
    created = 0
    for pos in positions:
        if pos.symbol in seen:
            continue  # 同一 symbol 多账户行已聚合
        seen.add(pos.symbol)
        try:
            item = _find_watchlist_item_for_position(db, family_id, pos.symbol, pos.asset_type)
            if item is None:
                norm = _normalize_for_position(pos.symbol, pos.asset_type)
                item = WatchlistItem(
                    symbol=norm['symbol'],
                    market=norm['market'],
                    asset_type=(pos.asset_type or '').strip().lower() or None,
                    venue=norm['venue'],
                    status='HOLDING',
                    family_id=family_id,
                )
                db.add(item)
                created += 1
            elif item.status != 'HOLDING':
                item.status = 'HOLDING'
        except Exception:
            logger.exception('ensure_watchlist_for_positions 单标的失败: family=%s symbol=%s', family_id, pos.symbol)
    return created


def reconcile_watchlist_status(db: Session, family_id: int, symbols: Optional[List[str]] = None) -> Tuple[int, int]:
    """卖出/重算后对齐自选状态：有活跃持仓→确保 HOLDING；无活跃持仓但状态 HOLDING→降级 WATCHING。

    返回 (promoted, demoted)。单标的失败仅记录日志、不中断整批。

    **不在此处提交事务**：同 ensure_watchlist_for_positions（见其 docstring），
    由调用方在自身事务内统一提交。
    """
    active_q = db.query(Position.symbol).filter(Position.family_id == family_id, Position.ownership_status == 'active')
    if symbols is not None:
        active_q = active_q.filter(Position.symbol.in_(symbols))
    active_symbols = {s for (s,) in active_q.distinct().all()}

    items_q = db.query(WatchlistItem).filter(WatchlistItem.family_id == family_id)
    if symbols is not None:
        items_q = items_q.filter(WatchlistItem.symbol.in_(symbols))

    promoted = 0
    demoted = 0
    for item in items_q.all():
        try:
            if item.symbol in active_symbols:
                if item.status != 'HOLDING':
                    item.status = 'HOLDING'
                    promoted += 1
            else:
                if item.status == 'HOLDING':
                    item.status = 'WATCHING'
                    demoted += 1
        except Exception:
            logger.exception('reconcile_watchlist_status 单标的失败: family=%s symbol=%s', family_id, item.symbol)
    return promoted, demoted


def get_holding_gaps(db: Session, family_id: int) -> List[Dict[str, Any]]:
    """返回「有活跃持仓但未加入自选」的标的列表（前端 banner 引导一键加入）。

    判定：活跃持仓 symbol 在 watchlist 中不存在记录即为缺口。
    """
    watchlist_symbols = {
        sym for (sym,) in db.query(WatchlistItem.symbol).filter(WatchlistItem.family_id == family_id).all()
    }
    rows = (
        db.query(Position.symbol, Position.name, Position.asset_type)
        .filter(Position.family_id == family_id, Position.ownership_status == 'active')
        .distinct()
        .all()
    )
    gaps: List[Dict[str, Any]] = []
    seen: set = set()
    for symbol, name, asset_type in rows:
        if symbol in seen:
            continue
        seen.add(symbol)
        norm = _normalize_for_position(symbol, asset_type)
        if norm['symbol'] in watchlist_symbols:
            continue
        gaps.append(
            {
                'symbol': norm['symbol'],
                'name': name or resolve_display_name(symbol, db),
                'asset_type': (asset_type or '').strip().lower() or None,
            }
        )
    return gaps


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
        display_name = resolve_display_name(item.symbol, db)
        position_value_units = (
            db.query(func.sum(Position.quantity * Position.current_price))
            .filter(Position.symbol == item.symbol, Position.family_id == family_id)
            .scalar()
            or 0.0
        )
        # quantity 最小单位(0.0001份) × current_price(0.0001元) = ×1e8 → multiply_price_quantity ÷1e6 得 分 → 元
        position_value = Money.cents_to_yuan(Money.multiply_price_quantity(position_value_units, 1))
        avg_price_units = (
            db.query(func.avg(Position.current_price))
            .filter(Position.symbol == item.symbol, Position.family_id == family_id)
            .scalar()
        )
        current_price = Money.price_units_to_yuan(avg_price_units) if avg_price_units else None
        data.append(
            {
                'id': item.id,
                'symbol': item.symbol,
                'display_name': display_name,
                'is_pinned': item.is_pinned,
                'current_price': round(current_price, 4) if current_price else None,
                'change_pct': None,
                'position_market_value': round(position_value, 2),
                'status': item.status,
                'asset_type': item.asset_type,
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
    asset_types: Optional[str] = None,
) -> Tuple[Query, int]:
    """
    根据筛选条件构建查询对象并返回总条数。
    返回 (query, total)
    """
    query = db.query(WatchlistItem).filter(WatchlistItem.family_id == family_id)

    if symbol:
        query = query.filter(WatchlistItem.symbol == symbol)

    # 资产类型多选（前端「类型」弹层，逗号分隔小写）。历史行 asset_type 可能
    # 残留大写（STOCK/ETF，#1171 前），统一 lower 后比较，避免筛选漏行。
    if asset_types:
        type_list = [t.strip().lower() for t in asset_types.split(',') if t.strip()]
        if type_list:
            query = query.filter(func.lower(WatchlistItem.asset_type).in_(type_list))

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
            item_ids_sub_query = select(distinct(WatchlistItemTag.item_id)).filter(
                WatchlistItemTag.tag_id.in_(tag_id_list)
            )
            query = query.filter(WatchlistItem.id.in_(item_ids_sub_query))
    elif tag_id:
        query = query.join(WatchlistItem.tag_links).filter(WatchlistItemTag.tag_id == tag_id)

    if search:
        like = f'%{search}%'
        # 搜索同时匹配「代码」与「名称」：名称散落在 securities / funds / positions
        # 三张表的 name 字段，先收集名称命中的标准化代码，再并入 symbol 过滤
        # （自选以 symbol 唯一标识，无法直接对 WatchlistItem 做名称 like）。
        conditions = [WatchlistItem.symbol.ilike(like)]
        name_symbols: set = set()
        name_symbols.update(s for (s,) in db.query(Security.symbol).filter(Security.name.ilike(like)).all())
        name_symbols.update(s for (s,) in db.query(Fund.fund_code).filter(Fund.name.ilike(like)).all())
        name_symbols.update(s for (s,) in db.query(Position.symbol).filter(Position.name.ilike(like)).all())
        if name_symbols:
            conditions.append(WatchlistItem.symbol.in_(name_symbols))
        query = query.filter(or_(*conditions))

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
