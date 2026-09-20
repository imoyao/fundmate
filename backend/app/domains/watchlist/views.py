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
from sqlalchemy import desc, func

from app.core.auth import get_family_id, get_owned_or_404
from app.core.constants import TYPE_LABELS
from app.core.database import get_db
from app.core.utils import api_response, with_db
from app.core.validation import parse_body
from app.domains.funds.models import DailyWorth
from app.domains.price_history.models import PriceHistory
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
    WatchlistItemUpdate,
    WatchlistTagDefCreate,
    WatchlistTagDefOut,
    WatchlistTagDefUpdate,
)
from app.services import watchlist_display as display
from app.services.watchlist_service import (
    build_groups_data,
    build_home_summary,
    create_watchlist_item,
    ensure_watchlist_for_positions,
    get_filtered_items_query,
    get_holding_gaps,
    reconcile_watchlist_status,
)

watchlist_bp = APIBlueprint('watchlist', __name__, url_prefix='/api/watchlist')

# CSV 导出字段值 → 中文 label 映射
_VENUE_LABELS = {'EXCHANGE': '场内', 'OTC': '场外'}
_STATUS_LABELS = {'HOLDING': '持仓中', 'WATCHING': '观察中'}

# 资产类型中文 label 统一取后端唯一来源 app.core.constants.TYPE_LABELS（收口自 asset_types），
# 不再在此私藏局部副本，避免与全局枚举漂移（#1171 枚举一致性）。
#
# ─────────────── 视图层边界（#1606）───────────────
# 本文件只做 HTTP 编排：解析入参 → 归属校验 → 调服务 → 组织响应信封。
# 自选域三层分工（判据见 `decisions.md` 2026-09-19「视图层职责边界」）：
#   - `services.watchlist_service`：查询 / 写入 / 状态机（筛选查询、买入即入自选、状态降级）；
#   - `services.watchlist_display`：展示行组装（enrich / 持仓虚拟行 / 页内补算 / 用户列内排序）；
#   - 本文件：路由与响应（不再持有 enrich、排序、DB 聚合等业务规则）。
# 展示名解析（resolve_display_name）与经理回查（lookup_manager）亦收口在 service：
# 首页自选摘要与列表页**共用同一实现**（此前两处各写一份，只有一边补了
# Manager/AdvisorPortfolio 分支，导致列表页正常而首页显示 MGR_xxx，2026-09-10 复盘）。


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
        db.commit()
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


@watchlist_bp.get('/items/')
def list_items():
    """获取自选列表，支持多种筛选、置顶优先排序与用户列内排序（sort_by/sort_order）。

    分页语义：**先在完整结果集上排序定序，只用页内行做完整 enrich**。
    展示专用字段（基金回撤 / 可转债条款 / 指数估值 / 跨渠道关联）一律延后到分页之后
    对本页补算——它们不参与排序，却按 symbol 逐行查库，是全接口最大的单点耗时。

    `?fields=lite`：只回基础字段，连页内行也跳过上述 enrich。供前端「全量拉取供估值
    汇总」使用（汇总只消费价格/持仓/市值），避免为一份汇总把每一行都算一遍回撤。
    """
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
        # fields=lite：只回基础字段，跳过展示专用 enrich（基金回撤/可转债条款/指数估值/
        # 跨渠道关联）。供前端「全量拉取供估值汇总」使用——汇总只消费 current_price /
        # holding_* / position_market_value，不需要展示专用字段。
        'fields': (request.args.get('fields') or 'full').strip().lower(),
    }

    with get_db() as db:
        lite = params['fields'] == 'lite'
        # 分页参数：page 从 1 开始；per_page 限幅 [1, 200] 避免一次性拉取全量
        page = max(params['page'] or 1, 1)
        per_page = max(min(params['per_page'] or 20, 200), 1)
        offset = (page - 1) * per_page
        if params['status'] == 'HOLDING':
            # 持仓分组 = 全部真实持仓（positions 表 active，按 symbol 聚合），
            # 不走 watchlist.status 快照查询；返回虚拟行（id=None，前端据此禁用行操作）
            data = display.list_holding_items(
                db,
                get_family_id(),
                venue=params['venue'],
                search=params['search'],
                asset_types=params['asset_types'],
                defer_display=True,  # 展示专用字段延后到分页之后（见 fill_page_display_fields）
            )
            data = display.apply_user_sort(data, params['sort_by'], params['sort_order'])
            total = len(data)
            page_data = display.fill_page_display_fields(data[offset : offset + per_page], db, lite)
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
                data = display.build_all_items(
                    db,
                    get_family_id(),
                    venue=params['venue'],
                    search=params['search'],
                    tag_ids_str=params['tag_ids_str'],
                    favorite=params['favorite'],
                    group_id=params['group_id'],
                    defer_display=True,  # 同上：分页后再补展示专用字段
                )
            except ValueError as e:
                abort(400, str(e))
            data = display.apply_user_sort(data, params['sort_by'], params['sort_order'])
            total = len(data)
            page_data = display.fill_page_display_fields(data[offset : offset + per_page], db, lite)
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
        data = [display.enrich_item(item, db, get_family_id(), defer_display=True) for item in items]
        data = display.apply_user_sort(data, params['sort_by'], params['sort_order'])

        total = len(data)
        page_data = display.fill_page_display_fields(data[offset : offset + per_page], db, lite)
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
            return jsonify({'data': display.enrich_item(item, db, get_family_id()), 'message': 'ok'})
        except ValueError as e:
            msg = str(e)
            if '已在自选' in msg:
                return jsonify({'data': None, 'message': msg, 'error_code': 1003}), 409
            else:
                return jsonify({'data': None, 'message': msg, 'error_code': 1001}), 400


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
        return jsonify({'data': display.enrich_item(item, db, get_family_id()), 'message': 'ok'})


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
        d = display.enrich_item(item, db, get_family_id())
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
    data = display.enrich_item(item, db, get_family_id())
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
            rows = display.list_holding_items(db, get_family_id(), venue=params['venue'], search=params['search'])
        elif not params['status'] and not (
            params['symbol'] or params['market'] or params['tag_id'] or params['asset_types']
        ):
            # 「全部」导出与列表口径一致：自选 ∪ 持仓补集（复用同一合并逻辑；
            # 带 symbol/market/tag_id 查找参数时仍走原过滤语义，与列表分支对齐）
            try:
                rows = display.build_all_items(
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
            rows = [display.enrich_item(item, db, get_family_id()) for item in query.all()]  # 导出不分页

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
