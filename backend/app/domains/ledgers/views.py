# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 10:56
# File : views.py
"""资金容器 API — 基本 CRUD"""

import json
from datetime import datetime

from apiflask import APIBlueprint
from flask import abort, jsonify, request
from sqlalchemy import func

from app.core.auth import get_family_id, get_owned_or_404
from app.core.constants import ALLOCATION_LABELS, LEDGER_TYPE_LABELS
from app.core.database import get_db
from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, SalesInstitution
from app.domains.transactions.models import Transaction
from app.services import ledger_migration_service as migration_svc
from app.services import ledger_write_service as ledger_write_svc

# #1132 场内证券聚合：与 #1101 基金聚合并列，纯 position 级聚合，零 schema 迁移。
from app.services.ledger_service import LedgerService  # noqa: E402
from app.services.position_aggregation import (
    DEFAULT_PAGE_SIZE,
)
from app.services.position_aggregation import (
    get_fund_aggregation as svc_get_fund_aggregation,
)
from app.services.position_aggregation import (  # noqa: E402
    get_securities_aggregation as svc_get_securities_aggregation,
)
from app.services.position_presenter import enrich_position_dict

ledgers_bp = APIBlueprint('ledgers', __name__, url_prefix='/api/ledgers')


def _ledger_to_dict(ledger: Ledger, last_used_at=None) -> dict:
    """将 Ledger 模型实例转为字典"""
    # 处理 fee_config：数据库中是字符串，需要反序列化
    fee_config = None
    if ledger.fee_config:
        try:
            fee_config = json.loads(ledger.fee_config)
        except (json.JSONDecodeError, TypeError):
            fee_config = None

    return {
        'id': ledger.id,
        'name': ledger.name,
        'ledger_type': ledger.ledger_type,
        'default_allocation': ledger.default_allocation,
        'default_allocation_label': ALLOCATION_LABELS.get(ledger.default_allocation, '未配置'),
        'fee_config': fee_config,
        'notes': ledger.notes,
        'portfolio_id': ledger.portfolio_id,
        'linked_cash_ledger_id': ledger.linked_cash_ledger_id,
        # 类现金产品绑定（#1137）：绑定 funds 标的（余额宝概念）。
        # 入参用基金代码（前端搜索结果即 code），存储用 funds.id；出参附带 code/name 便于回显。
        'linked_money_fund_id': ledger.linked_money_fund_id,
        'linked_money_fund_code': ledger.linked_money_fund.fund_code if ledger.linked_money_fund else None,
        'linked_money_fund_name': ledger.linked_money_fund.name if ledger.linked_money_fund else None,
        'auto_purchase_money_fund': bool(ledger.auto_purchase_money_fund),
        # 关联的销售机构（AMAC 名录），可选；前端回显与编辑依赖该字段
        'sales_institution_id': ledger.sales_institution_id,
        # 聚合/系统账本标记与交易前端标签（#1101，前端展示/编辑用）
        'is_aggregation': ledger.is_aggregation,
        'frontend_app': ledger.frontend_app,
        'is_active': ledger.is_active,
        # 渠道分类（#1101 重设计，铁律见设计文档 §2.3）：用户可见分组/类型标签，只读本字段做展示。
        'channel_category': ledger.channel_category,
        # 外部资金账户/凭证标识（#1100/#1101，物理隔离维度，默认 MAIN；导入取真实资金账号）。
        'external_account_code': ledger.external_account_code,
        # 组内手动排序序号；null 表示用户尚未手动排序（前端回退按持仓金额降序）。
        'display_order': ledger.display_order,
        'created_at': ledger.created_at.isoformat() if ledger.created_at else None,
        'updated_at': ledger.updated_at.isoformat() if ledger.updated_at else None,
        # 最近使用时间：取该账户最后一笔交易的确认日期（无交易则为 null），
        # 用于导入向导步骤一下拉的"最近使用优先"排序。
        'last_used_at': last_used_at.isoformat() if last_used_at else None,
    }


@ledgers_bp.get('/overview/')
def get_ledgers_overview():
    with get_db() as db:
        data = LedgerService.get_overview_stats(db, get_family_id())
        return jsonify({'data': data, 'message': 'ok'})


def _aggregation_args() -> dict:
    """解析聚合接口的公共查询参数（#1133）。

    - dimension：'product'（默认）| 'institution'。原 'app'（交易前端）维度已收敛去掉——
      其本质即销售机构、与 institution 重复；传入时静默降级为 institution，保证旧链接不报错。
    - sort：'market_value'（默认）| 'quantity' | 'name' | 'symbol' | 'return_pct'。
    - order：'desc'（默认）| 'asc'。
    - keyword：名称/代码模糊搜索。
    - fund_type：基金小类名精确筛选；'__none__' 表示筛选「未分类」。
    """
    dimension = request.args.get('dimension', 'product')
    if dimension == 'app':
        dimension = 'institution'
    if dimension not in ('product', 'institution'):
        dimension = 'product'
    return {
        'dimension': dimension,
        'sort': request.args.get('sort', 'market_value'),
        'order': request.args.get('order', 'desc'),
        'page': request.args.get('page', 1, type=int),
        'page_size': request.args.get('page_size', DEFAULT_PAGE_SIZE, type=int),
        'keyword': request.args.get('keyword', '').strip() or None,
        'fund_type': request.args.get('fund_type', '').strip() or None,
        'asset_type': request.args.get('asset_type', '').strip() or None,
    }


@ledgers_bp.get('/fund-aggregation/')
def get_fund_aggregation():
    """场外基金（含 E 账户）持仓跨账本聚合（#1101）：按产品/机构维度，供概览卡片与下钻页 /funds。"""
    with get_db() as db:
        data = svc_get_fund_aggregation(db, get_family_id(), **_aggregation_args())
        return jsonify({'data': data, 'message': 'ok'})


@ledgers_bp.get('/securities-aggregation/')
def get_securities_aggregation():
    """场内证券（股票/ETF/可转债）持仓跨账本聚合（#1132）：按产品/机构维度，供下钻页 /stocks。"""
    with get_db() as db:
        data = svc_get_securities_aggregation(db, get_family_id(), **_aggregation_args())
        return jsonify({'data': data, 'message': 'ok'})


def _ledger_type_label(ledger_type: str) -> str:
    """账户类型中文映射"""
    return LEDGER_TYPE_LABELS.get(ledger_type, ledger_type)


@ledgers_bp.get('/sales-institutions/')
def list_sales_institutions():
    """销售机构名录（AMAC 权威数据，全局共享，供账户表单下拉选择）

    只返回 is_active=True 的机构：与导入匹配逻辑一致，下架机构不可再新关联；
    已关联的历史账户不受影响（展示名仍由名录实时解析）。

    查询参数：
        org_types: 可选，逗号分隔的机构类型（原始 org_type 值），提供时仅返回命中
                   类型（#1082：按账户类型过滤可见机构，如证券账户只看券商）。

    排序：常用机构（is_common）按 common_sort 升序置顶，其余按名称字典序——
    前端据此拆「常用机构 / 全部机构」两个分组（#1081）。
    """
    # 兼容两种传参：逗号分隔（org_types=A,B）或重复参数（org_types=A&org_types=B）
    org_types: list[str] = []
    for raw in request.args.getlist('org_types'):
        for t in raw.split(','):
            t = t.strip()
            if t:
                org_types.append(t)

    with get_db() as db:
        query = db.query(SalesInstitution).filter(SalesInstitution.is_active.is_(True))
        if org_types:
            query = query.filter(SalesInstitution.org_type.in_(org_types))
        institutions = query.order_by(
            SalesInstitution.is_common.desc(),
            SalesInstitution.common_sort.asc().nullslast(),
            SalesInstitution.org_name.asc(),
        ).all()
        data = [
            {
                'id': institution.id,
                'org_name': institution.org_name,
                'display_name': institution.display_name,
                'org_type': institution.org_type,
                'is_common': institution.is_common,
                'common_sort': institution.common_sort,
                'pinyin_short': institution.pinyin_short,
            }
            for institution in institutions
        ]
        return jsonify({'data': data, 'message': 'ok'})


@ledgers_bp.post('/')
def create_ledger():
    """创建新账户（业务规则下沉至 ledger_write_service，#1642 A 块）"""
    data = request.get_json() or {}
    family_id = get_family_id()
    with get_db() as db:
        try:
            ledger = ledger_write_svc.create_ledger(db, family_id, data)
        except ledger_write_svc.LedgerWriteError as e:
            if e.error_code is None:
                abort(e.status_code, e.message)
            return jsonify({'data': None, 'message': e.message, 'error_code': e.error_code}), e.status_code
        return jsonify({'data': _ledger_to_dict(ledger), 'message': 'ok'})


@ledgers_bp.get('/')
def list_ledgers():
    """获取所有账户（含摘要统计）。

    include_archived=true 时一并返回已归档账户；默认仅返回活跃账户
    （归档账户保留全部数据、仍参与收益计算，仅从日常视图默认隐藏）。
    按类型的摘要统计下沉至 LedgerService.attach_ledger_summary（#1642 A 块）。
    """
    include_archived = request.args.get('include_archived', 'false').lower() == 'true'
    with get_db() as db:
        query = db.query(Ledger).filter(Ledger.family_id == get_family_id())
        if not include_archived:
            query = query.filter(Ledger.is_active.is_(True))
        # 隐藏聚合/系统账本（如基金E账户），不出现在用户账户列表（#1101）
        query = query.filter(Ledger.is_aggregation.is_(False))
        # 默认：手动排序序号在前（NULL 视为未排序排到后面），同组内再按创建时间稳定序。
        # 前端若检测到组内存在 display_order 则以它为准；否则按持仓金额降序。
        ledgers = query.order_by(
            Ledger.display_order.is_(None),
            Ledger.display_order.asc(),
            Ledger.created_at.asc(),
        ).all()
        # 派生"最近使用时间"：每个账户最近一笔交易的确认日期（单条聚合查询，避免 N+1）
        last_used_rows = (
            db.query(Transaction.ledger_id, func.max(Transaction.confirm_date).label('last_date'))
            .filter(Transaction.family_id == get_family_id())
            .group_by(Transaction.ledger_id)
            .all()
        )
        last_used_map = {row.ledger_id: row.last_date for row in last_used_rows}
        result = []
        for ledger in ledgers:
            item = _ledger_to_dict(ledger, last_used_map.get(ledger.id))
            item['total_market_value'] = 0.0
            item['pnl'] = 0.0
            item['position_count'] = 0
            item['cash_balance'] = 0.0  # 统一初始化 cash_balance
            LedgerService.attach_ledger_summary(db, ledger, item)
            result.append(item)
        return jsonify({'data': result, 'message': 'ok'})


@ledgers_bp.patch('/reorder/')
def reorder_ledgers():
    """对同一类型内的账户手动排序落库（#1083）。

    入参：{ ledger_type: str, ordered_ids: [int,...] }
    仅接受该家族下、且类型匹配、且属于 ordered_ids 的账户，赋 display_order = 序号(1-based)。
    客户端每次拖拽都发送该类型下的完整有序 id 列表，因此同类型要么全手动、要么全默认。
    """
    data = request.get_json(silent=True) or {}
    ledger_type = data.get('ledger_type')
    ordered_ids = data.get('ordered_ids')
    if not isinstance(ledger_type, str) or not isinstance(ordered_ids, list):
        return jsonify({'data': None, 'message': '参数错误：ledger_type 与 ordered_ids 必填', 'error_code': 1001}), 400

    with get_db() as db:
        fam = get_family_id()
        ledgers = (
            db.query(Ledger)
            .filter(
                Ledger.family_id == fam,
                Ledger.ledger_type == ledger_type,
                Ledger.id.in_(ordered_ids),
            )
            .all()
        )
        owned = {led.id: led for led in ledgers}
        for idx, lid in enumerate(ordered_ids):
            matched = owned.get(lid)
            if matched is not None:
                matched.display_order = idx + 1
        db.flush()
    return jsonify({'data': None, 'message': 'ok'})


@ledgers_bp.get('/<int:ledger_id>/')
def get_ledger(ledger_id: int):
    """获取单个账户详情"""
    with get_db() as db:
        ledger = get_owned_or_404(db, Ledger, ledger_id)
        if not ledger:
            abort(404, '账户不存在')
        return jsonify({'data': _ledger_to_dict(ledger), 'message': 'ok'})


@ledgers_bp.patch('/<int:ledger_id>/')
def update_ledger(ledger_id: int):
    """更新账户信息（业务规则下沉至 ledger_write_service，#1642 A 块）"""
    data = request.get_json() or {}
    family_id = get_family_id()
    with get_db() as db:
        ledger = get_owned_or_404(db, Ledger, ledger_id)
        if not ledger:
            abort(404, '账户不存在')
        try:
            ledger = ledger_write_svc.update_ledger(db, ledger, data, family_id)
        except ledger_write_svc.LedgerWriteError as e:
            if e.error_code is None:
                abort(e.status_code, e.message)
            return jsonify({'data': None, 'message': e.message, 'error_code': e.error_code}), e.status_code
        return jsonify({'data': _ledger_to_dict(ledger), 'message': 'ok'})


@ledgers_bp.delete('/<int:ledger_id>/')
def delete_ledger(ledger_id: int):
    """删除账户，可选择同时删除关联持仓"""
    delete_positions = request.args.get('delete_positions', 'false').lower() == 'true'

    with get_db() as db:
        ledger = get_owned_or_404(db, Ledger, ledger_id)
        if not ledger:
            abort(404, '账户不存在')

        if delete_positions:
            # 级联删除关联数据（基于 ledger_id）：先删交易，再删持仓/资产，最后删账户
            db.query(Transaction).filter(
                Transaction.ledger_id == ledger_id, Transaction.family_id == get_family_id()
            ).delete()
            db.query(Position).filter(Position.ledger_id == ledger_id).delete()
            db.query(Asset).filter(Asset.ledger_id == ledger_id, Asset.family_id == get_family_id()).delete()
        else:
            # 检查是否存在关联持仓/资产/交易（任一存在即拒绝，防止产生孤儿数据）
            position_count = db.query(Position).filter(Position.ledger_id == ledger_id).count()
            asset_count = (
                db.query(Asset).filter(Asset.ledger_id == ledger_id, Asset.family_id == get_family_id()).count()
            )
            transaction_count = (
                db.query(Transaction)
                .filter(Transaction.ledger_id == ledger_id, Transaction.family_id == get_family_id())
                .count()
            )
            if position_count > 0 or asset_count > 0 or transaction_count > 0:
                return jsonify(
                    {
                        'data': None,
                        'message': f'无法删除：账户「{ledger.name}」下还有 {position_count} 笔持仓、{asset_count} 项资产、{transaction_count} 笔交易，请先迁移或勾选"同时删除"',
                        'error_code': 1001,
                    }
                ), 400

        db.delete(ledger)
        db.flush()
        return jsonify({'data': {}, 'message': 'ok'})


@ledgers_bp.post('/<int:ledger_id>/archive/')
def archive_ledger(ledger_id: int):
    """归档账户：保留全部交易/持仓/资产数据，仅置 is_active=False 从日常视图默认隐藏。

    归档后数据仍参与收益计算（计算服务默认不过滤 is_active）。与删除不同——
    有数据的账户不可删除，只能归档。无"当前账本"全局指针，归档不影响其他状态。
    """
    with get_db() as db:
        ledger = get_owned_or_404(db, Ledger, ledger_id)
        if not ledger:
            abort(404, '账户不存在')
        ledger.is_active = False
        db.flush()
        db.refresh(ledger)
        return jsonify({'data': _ledger_to_dict(ledger), 'message': 'ok'})


@ledgers_bp.post('/<int:ledger_id>/unarchive/')
def unarchive_ledger(ledger_id: int):
    """激活账户：is_active=True，重新出现在日常视图。"""
    with get_db() as db:
        ledger = get_owned_or_404(db, Ledger, ledger_id)
        if not ledger:
            abort(404, '账户不存在')
        ledger.is_active = True
        db.flush()
        db.refresh(ledger)
        return jsonify({'data': _ledger_to_dict(ledger), 'message': 'ok'})


# ────────────────────────── 账本批量迁移（两段式：预览 → 提交） ──────────────────────────
# 业务规则（三分类 / 决议 / 守恒校验 / 单事务回滚）已下沉 services.ledger_migration_service（#1606），
# 视图只保留入参解析、归属校验与响应组织；错误经 MigrationError 转统一信封。


@ledgers_bp.post('/<int:ledger_id>/migrations/preview/')
def preview_migration(ledger_id: int):
    """迁移预览（只读，不写库）：对源账本全部持仓/资产做三分类并给出守恒预估。

    用户关闭预览即无任何副作用——「回滚」由「不提交」自然实现（设计文档 §4.1）。
    """
    data = request.get_json() or {}
    target_id = data.get('target_ledger_id')
    if not target_id:
        return jsonify({'data': None, 'message': '缺少 target_ledger_id', 'error_code': 1001}), 400

    with get_db() as db:
        source = get_owned_or_404(db, Ledger, ledger_id)
        target = db.query(Ledger).get(target_id)
        if not source or not target:
            return jsonify({'data': None, 'message': '账户不存在', 'error_code': 1002}), 404
        try:
            migration_svc.check_migration_target(source, target)
            payload = migration_svc.preview_migration(db, source, target, get_family_id())
        except migration_svc.MigrationError as e:
            return jsonify({'data': None, 'message': e.message}), e.status_code
        return jsonify({'data': payload, 'message': 'ok'})


@ledgers_bp.post('/<int:ledger_id>/migrations/commit/')
def commit_migration(ledger_id: int):
    """迁移提交（单事务 + 整体回滚）：按预览分类与用户决议执行写入。

    - conflict 行必须有 resolution（keep_source/keep_target/merge），缺任一条 → 400 且不写任何数据；
    - 任一异常（含守恒校验不过）→ rollback，返回 500，源数据原样（设计文档 §4.2/§6）。
    """
    data = request.get_json() or {}
    target_id = data.get('target_ledger_id')
    if not target_id:
        return jsonify({'data': None, 'message': '缺少 target_ledger_id', 'error_code': 1001}), 400

    with get_db() as db:
        source = get_owned_or_404(db, Ledger, ledger_id)
        target = db.query(Ledger).get(target_id)
        if not source or not target:
            return jsonify({'data': None, 'message': '账户不存在', 'error_code': 1002}), 404
        try:
            migration_svc.check_migration_target(source, target)
            counts = migration_svc.commit_migration(
                db,
                source,
                target,
                get_family_id(),
                resolutions=data.get('resolutions') or [],
                # 跨销售机构软闸门：仅显式 true 放行（与下沉前 `is not True` 判定等价）
                allow_cross_institution=data.get('allow_cross_institution') is True,
            )
        except migration_svc.MigrationError as e:
            return jsonify({'data': None, 'message': e.message}), e.status_code

        # 响应文案属「响应组织」职责，留在视图层（计数来自服务层）
        message = (
            f'已迁移至「{target.name}」：{counts["position_count"]} 项持仓迁入、{counts["dedup_count"]} 项去重、'
            f'{counts["merged_count"]} 项合并、{counts["keep_source_count"]} 项冲突留源、{counts["asset_count"]} 项资产'
        )
        if counts['transaction_count']:
            message += f'；另归并 {counts["transaction_count"]} 笔交易'
        return jsonify({'data': counts, 'message': message})


# ────────────────────────────── 账户详情页专用接口 ──────────────────────────────


@ledgers_bp.get('/<int:ledger_id>/pending-estimate/')
def get_ledger_pending_estimate(ledger_id: int):
    """#863 2-A：账户「确认中」货基申购预估（UI 标注过渡，非账本口径）。

    二期 B1 在途状态机上线后数据源切 pending 表，路径/字段不变。
    """
    with get_db() as db:
        ledger = get_owned_or_404(db, Ledger, ledger_id)
        data = LedgerService.get_pending_money_fund_estimate(db, ledger.id, get_family_id())
    return jsonify({'data': data, 'message': 'ok', 'error_code': 0})


@ledgers_bp.get('/<int:ledger_id>/summary/')
def get_ledger_summary(ledger_id: int):
    """获取单账户概览卡片数据，根据账户类型返回不同指标"""
    with get_db() as db:
        ledger = get_owned_or_404(db, Ledger, ledger_id)
        if not ledger:
            abort(404, '账户不存在')

        data = {'ledger_type': ledger.ledger_type, 'ledger_name': ledger.name, 'daily_pnl': None}

        if ledger.ledger_type in ('stock', 'fund', 'e_account'):
            stats = LedgerService.get_portfolio_stats(db, ledger.id)
            data.update(stats)
            data['cumulative_return'] = LedgerService.get_cumulative_return(db, ledger.id)

            if ledger.ledger_type == 'stock':
                data['cash_balance'] = LedgerService.get_cash_balance(db, ledger)
            elif ledger.ledger_type in ('fund', 'e_account'):
                # FIX-3: 传入 ledger.id 而非 ledger.name
                money_fund = LedgerService.get_money_fund_stats(db, ledger.id)
                data.update(money_fund)

            # 类现金统计（#1137）：货基 + 逆回购 + 账户现金，口径与 XIRR 的
            # EXCLUDED_ASSET_TYPES 一致；中高风险 = 总市值 - 类现金，供前端主次展示。
            data.update(LedgerService.get_cash_like_stats(db, ledger.id, get_family_id()))
            total_mv = data.get('total_market_value') or 0.0
            data['investment_amount'] = round(total_mv - (data.get('cash_like_amount') or 0.0), 2)

        elif ledger.ledger_type == 'bank':
            data.update(LedgerService.get_bank_stats(db, ledger.id))

        elif ledger.ledger_type == 'property':
            data.update(LedgerService.get_property_stats(db, ledger.id))

        return jsonify({'data': data, 'message': 'ok'})


@ledgers_bp.get('/<int:ledger_id>/positions/')
def get_ledger_positions(ledger_id: int):
    """获取账户持仓明细，支持分页与名称/代码搜索（#982）"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search') or None

    with get_db() as db:
        ledger = get_owned_or_404(db, Ledger, ledger_id)
        if not ledger:
            return jsonify({'data': None, 'message': '账户不存在', 'error_code': 1002}), 404
        items, total = LedgerService.get_positions_paginated(db, ledger.id, page, per_page, search=search)
        return jsonify(
            {
                'data': {
                    'items': items,
                    'total': total,
                    'page': page,
                    'per_page': per_page,
                },
                'message': 'ok',
            }
        )


@ledgers_bp.get('/<int:ledger_id>/transactions/')
def get_ledger_transactions(ledger_id: int):
    """获取账户交易记录，支持分页与名称/代码搜索（#982）"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search') or None

    with get_db() as db:
        ledger = get_owned_or_404(db, Ledger, ledger_id)
        if not ledger:
            return jsonify({'data': None, 'message': '账户不存在', 'error_code': 1002}), 404
        items, total = LedgerService.get_transactions_paginated(db, ledger.id, page, per_page, search=search)
        return jsonify(
            {
                'data': {
                    'items': items,
                    'total': total,
                    'page': page,
                    'per_page': per_page,
                },
                'message': 'ok',
            }
        )


@ledgers_bp.patch('/<int:ledger_id>/positions/<int:position_id>/')
def update_ledger_position(ledger_id: int, position_id: int):
    """编辑账户内持仓（仅允许修改配置目标、现价、备注等）"""
    data = request.get_json() or {}
    with get_db() as db:
        ledger = get_owned_or_404(db, Ledger, ledger_id)
        if not ledger:
            abort(404, '账户不存在')
        pos = (
            db.query(Position)
            .filter(
                Position.id == position_id,
                Position.ledger_id == ledger_id,  # 外键过滤
            )
            .first()
        )
        if not pos:
            abort(404, '持仓不存在或不属于该账户')

        if 'allocation' in data:
            pos.allocation = data['allocation']
        if 'current_price' in data:
            pos.current_price = Money.yuan_to_price_units(data['current_price'])
        if 'notes' in data:
            pos.notes = data['notes']
        db.flush()
        db.refresh(pos)
        return jsonify({'data': enrich_position_dict(pos), 'message': 'ok'})


@ledgers_bp.delete('/<int:ledger_id>/positions/<int:position_id>/')
def delete_ledger_position(ledger_id: int, position_id: int):
    """删除账户内持仓"""
    delete_txns = request.args.get('delete_transactions', 'false').lower() == 'true'
    with get_db() as db:
        ledger = get_owned_or_404(db, Ledger, ledger_id)
        if not ledger:
            abort(404, '账户不存在')
        pos = (
            db.query(Position)
            .filter(
                Position.id == position_id,
                Position.ledger_id == ledger.id,
            )
            .first()
        )
        if not pos:
            abort(404, '持仓不存在或不属于该账户')

        if delete_txns:
            db.query(Transaction).filter(
                Transaction.position_id == position_id,
                Transaction.ledger_id == ledger.id,
            ).delete()
        db.delete(pos)
        db.flush()
        return jsonify({'message': 'ok', 'data': None})


@ledgers_bp.patch('/<int:ledger_id>/transactions/<int:transaction_id>/')
def update_ledger_transaction(ledger_id: int, transaction_id: int):
    """编辑账户内交易（金额/数量/价格/日期/备注，见 issue #1112，#1642 A 块）。

    - 归属类字段（ledger_id/symbol/account 等）由本入口拦截；
    - 金额类/日期/备注字段的改写、金额重算、import_hash 清空下沉至 ledger_write_service；
    - 响应体（含 Money 反算）在此组装，保持展示职责在视图。
    """
    data = request.get_json() or {}
    forbidden = {'id', 'ledger_id', 'symbol', 'account', 'family_id', 'created_at', 'updated_at'}
    bad = [k for k in data if k in forbidden]
    if bad:
        abort(400, f'禁止修改字段: {", ".join(sorted(bad))}')

    with get_db() as db:
        ledger = get_owned_or_404(db, Ledger, ledger_id)
        if not ledger:
            abort(404, '账户不存在')
        txn = (
            db.query(Transaction)
            .filter(
                Transaction.id == transaction_id,
                Transaction.ledger_id == ledger.id,
            )
            .first()
        )
        if not txn:
            abort(404, '交易不存在或不属于该账户')

        try:
            ledger_write_svc.update_ledger_transaction(db, ledger, txn, data)
        except ledger_write_svc.LedgerWriteError as e:
            if e.error_code is None:
                abort(e.status_code, e.message)
            return jsonify({'data': None, 'message': e.message, 'error_code': e.error_code}), e.status_code

        def _ymd(value):
            # trade_date 为 DateTime 列（读回为 datetime），confirm_date 为 Date 列（date）；
            # 若本次仅赋过 .date() 则为 date。统一输出 YYYY-MM-DD。
            if not value:
                return None
            if isinstance(value, datetime):
                value = value.date()
            return value.isoformat()

        return jsonify(
            {
                'data': {
                    'id': txn.id,
                    'quantity': Money.min_unit_to_shares(txn.quantity),
                    'price': Money.price_units_to_yuan(txn.price),
                    'amount': Money.cents_to_yuan(txn.amount),
                    'fee': Money.cents_to_yuan(txn.fee),
                    'trade_date': _ymd(txn.trade_date),
                    'confirm_date': _ymd(txn.confirm_date),
                    'notes': txn.notes,
                    'import_hash': txn.import_hash,
                },
                'message': 'ok',
            }
        )


# ────────────────────────────── 未归置数据（orphan）归入/清理 ──────────────────────────────


@ledgers_bp.get('/orphan/detail/')
def get_orphan_detail():
    """查询未归置数据（孤儿）明细：孤儿持仓/资产/交易清单 + 汇总（业务规则见 service）。

    前端此前只能看到汇总数字（N 个持仓、合计 ¥X），无法定位具体是哪些数据；
    本接口补齐明细，孤儿判定与归入/清理完全一致（ledger_id 为空或不在当前家庭
    有效账户 id 集合内），保证「明细展示 → 归入/清理」所见即所得。
    """
    with get_db() as db:
        payload = migration_svc.build_orphan_detail(db, get_family_id())
    return jsonify({'data': payload, 'message': 'ok'})


@ledgers_bp.post('/orphan/migrations/')
def migrate_orphan_data():
    """将未归置数据（孤儿持仓/资产/交易）归入指定账户"""
    data = request.get_json() or {}
    target_id = data.get('target_ledger_id')
    if not target_id:
        return jsonify({'data': None, 'message': '缺少 target_ledger_id', 'error_code': 1001}), 400

    with get_db() as db:
        target = get_owned_or_404(db, Ledger, target_id)
        try:
            counts = migration_svc.migrate_orphan_data(db, target, get_family_id())
        except migration_svc.MigrationError as e:
            return jsonify({'data': None, 'message': e.message}), e.status_code
        # 文案在会话内取 target.name（服务层已提交，对象过期后需会话存活才能懒加载）
        return jsonify(
            {
                'data': counts,
                'message': f'已将 {counts["total"]} 项未归置数据归入「{target.name}」',
            }
        )


@ledgers_bp.delete('/orphan/')
def delete_orphan_data():
    """清理所有未归置数据（孤儿持仓/资产/交易）"""
    with get_db() as db:
        counts = migration_svc.delete_orphan_data(db, get_family_id())
    total = counts['position_count'] + counts['asset_count'] + counts['transaction_count']
    return jsonify(
        {
            'data': counts,
            'message': f'已清理 {total} 项未归置数据',
        }
    )
