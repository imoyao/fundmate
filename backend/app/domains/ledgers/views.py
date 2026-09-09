# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 10:56
# File : views.py
"""资金容器 API — 基本 CRUD"""

import json
from datetime import date, datetime

from apiflask import APIBlueprint
from flask import abort, jsonify, request
from loguru import logger
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from app.core.auth import get_family_id, get_owned_or_404
from app.core.constants import ALLOCATION_LABELS, LEDGER_TYPE_LABELS
from app.core.database import get_db
from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.funds.models import Fund, MoneyFundDailyWorth
from app.domains.ledgers.constants import (
    map_channel_category_to_ledger_type,
    map_ledger_type_to_channel_category,
    map_org_type_to_channel_category,
)
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, PositionImportMeta, SalesInstitution
from app.domains.positions.views import enrich_position_dict
from app.domains.transactions.models import Transaction
from app.services.fund_service import FundService
from app.services.position_aggregation import (
    DEFAULT_PAGE_SIZE,
)
from app.services.position_aggregation import (
    get_fund_aggregation as svc_get_fund_aggregation,
)
from app.services.trading import TransactionService

# 外部基金列表缓存（进程级，基金列表极少变动）：用于「本地库无此货基时」补建 Fund 行
_FUND_NAME_EM_CACHE: dict = {'ts': 0.0, 'data': None}
_FUND_NAME_EM_TTL = 86400


def _resolve_money_fund(db, fund_code: str):
    """按代码解析类现金产品（货基）对应的 Fund 行。

    本地缺失时，用 akshare fund_name_em 兜底补建（仅填代码/名称/类型等最小字段），
    使「本地库尚未同步的货基」也能被绑定（#交互修复：按名称搜得到也要绑得上）。
    补建失败（网络/解析异常）返回 None，由调用方回退 400。
    """
    fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
    if fund:
        return fund
    try:
        import time

        cache = _FUND_NAME_EM_CACHE
        now = time.time()
        if cache['data'] is None or now - cache['ts'] > _FUND_NAME_EM_TTL:
            from app.services.sync.adapters.akshare_adapter import AKShareAdapter

            cache['data'] = AKShareAdapter().fetch_fund_list()
            cache['ts'] = now
        for item in cache['data'] or []:
            if item.get('fund_code') == fund_code:
                fund = Fund(
                    fund_code=fund_code,
                    name=item.get('name') or fund_code,
                    fund_type_id=6 if item.get('fund_type') == '货币型' else None,
                )
                db.add(fund)
                db.flush()
                return fund
    except Exception as e:  # 外部失败不阻塞，回退 400
        logger.warning(f'补建货基 Fund 行失败({fund_code}): {e}')
    return None


def _check_money_fund_bindable(db, fund: Fund, ledger_type: str) -> str | None:
    """校验基金是否可作为「活期+」绑定标的，并按账户渠道约束可绑范围（#1156/#1154）。

    复用 FundService._judge_money_fund 三态判定（与前端 disabled 策略一致）：
      - True  → 允许（进入渠道约束）
      - None  → 类型未知，允许但记 warning（避免 fund_type_id 缺失误拒）
      - False → 明确非货基，拒绝
    渠道约束（#1154，方案 B：按账户 ledger_type 约束，不加 Fund 字段）：
      - 场内货币ETF（511/519/159）→ 属投资范畴，任何账户均不可绑
      - 券商渠道现金管理（026/970）→ 仅证券账户(stock)可绑
      - 场外货基 → 仅基金平台账户(fund)可绑
    返回 None 表示可绑定；返回字符串为 400 拒绝原因。
    """
    has_worth = (
        db.query(MoneyFundDailyWorth.fund_code).filter(MoneyFundDailyWorth.fund_code == fund.fund_code).first()
        is not None
    )
    is_mf = FundService._judge_money_fund(fund.fund_type_id, fund.name, has_worth)
    if is_mf is False:
        return '活期+ 仅支持货币基金类产品'
    if is_mf is None:
        logger.warning(f'绑定活期+ 的基金类型未知（{fund.fund_code} {fund.name}），按前端策略放行')
    # 渠道约束（#1154，方案 B）：按账户类型约束可绑范围，不加 Fund 字段
    channel = FundService._classify_money_fund_channel(fund.fund_code)
    if channel == 'exchange_traded':
        return '场内货币ETF（如华宝添益/银华日利）属投资范畴，不可绑定活期+'
    if channel == 'broker_channel' and ledger_type != 'stock':
        return '证券账户活期+ 仅支持券商渠道现金管理产品（如银河水星现金添利）'
    if channel == 'off_exchange' and ledger_type != 'fund':
        return '基金平台账户活期+ 仅支持场外货币基金'
    return None


def _swap_linked_money_fund(db, ledger: Ledger, old_fund: Fund, new_fund: Fund) -> None:
    """#1137 换绑活期+：将账户内原绑定货基 A 的净额持仓赎回，并申购新绑定货基 B。

    货基以孤儿流水记账（不建持仓），故「持仓」= 该账户下 A 的 money_fund 流水净额。
    净额<=0 表示无实际持仓，跳过（避免凭空造流水）。仅生成两条孤儿流水（赎回 A /
    申购 B），资产中性、不影响其他账户；失败仅记录告警不抛出，避免阻断换绑主流程。
    """
    family_id = get_family_id()
    # 货基以孤儿流水记账（不建持仓），净额口径与 summary_service.orphan_money_fund_net_by_ledger
    # 一致：buy/deposit 加、sell/withdraw 减，且仅计 position_id IS NULL 的孤儿流水，全程整数分。
    positive = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.ledger_id == ledger.id,
            Transaction.family_id == family_id,
            Transaction.asset_type == 'money_fund',
            Transaction.symbol == old_fund.fund_code,
            Transaction.position_id.is_(None),
            Transaction.txn_type.in_(('buy', 'deposit')),
        )
        .scalar()
        or 0
    )
    negative = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.ledger_id == ledger.id,
            Transaction.family_id == family_id,
            Transaction.asset_type == 'money_fund',
            Transaction.symbol == old_fund.fund_code,
            Transaction.position_id.is_(None),
            Transaction.txn_type.in_(('sell', 'withdraw')),
        )
        .scalar()
        or 0
    )
    net_cents = int(positive) - int(negative)
    if net_cents <= 0:
        return
    today = date.today()
    # 赎回原绑定货基 A
    TransactionService.create(
        db=db,
        position_id=None,
        symbol=old_fund.fund_code,
        txn_type='sell',
        trade_date=today,
        confirm_date=today,
        asset_type='money_fund',
        quantity=0,
        price=0,
        fee=0,
        amount=net_cents,
        status='success',
        position_name=old_fund.name,
        ledger_id=ledger.id,
        account_name=ledger.name,
        notes='更换活期+，赎回原绑定产品',
        entry_status='orphan',
        family_id=family_id,
    )
    # 申购新绑定货基 B（活期+内迁移，保持资产中性）
    TransactionService.create(
        db=db,
        position_id=None,
        symbol=new_fund.fund_code,
        txn_type='buy',
        trade_date=today,
        confirm_date=today,
        asset_type='money_fund',
        quantity=0,
        price=0,
        fee=0,
        amount=net_cents,
        status='success',
        position_name=new_fund.name,
        ledger_id=ledger.id,
        account_name=ledger.name,
        notes='更换活期+，申购新绑定产品',
        entry_status='orphan',
        family_id=family_id,
    )
    logger.info(
        f'账户 {ledger.id} 换绑活期+：{old_fund.fund_code} → {new_fund.fund_code}，'
        f'净额 {net_cents} 分已迁移（赎回 A / 申购 B）'
    )


# #1132 场内证券聚合：与 #1101 基金聚合并列，纯 position 级聚合，零 schema 迁移。
from app.services.ledger_service import LedgerService  # noqa: E402
from app.services.position_aggregation import (  # noqa: E402
    get_securities_aggregation as svc_get_securities_aggregation,
)

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
    """创建新账户"""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        abort(400, '账户名称不能为空')

    ledger_type = data.get('ledger_type', 'bank')
    channel_category = data.get('channel_category')
    linked_cash_id = data.get('linked_cash_ledger_id')
    sales_institution_id = data.get('sales_institution_id')

    # 校验关联的销售机构（可选）：机构是全局 AMAC 名录，无 family 归属
    institution_org_type = None
    if sales_institution_id is not None:
        with get_db() as db:
            institution = db.query(SalesInstitution).filter_by(id=sales_institution_id).first()
            if not institution:
                return jsonify({'data': None, 'message': '关联的销售机构不存在'}), 400
            institution_org_type = institution.org_type

    # 校验关联的现金账户
    if linked_cash_id is not None:
        if ledger_type not in ('stock', 'fund'):
            return jsonify({'data': None, 'message': '只有证券账户或基金可以关联现金账户'}), 400
        with get_db() as db:
            cash_ledger = db.query(Ledger).filter_by(id=linked_cash_id, ledger_type='bank').first()
            if not cash_ledger or cash_ledger.family_id != get_family_id():
                return jsonify({'data': None, 'message': '关联的现金账户不存在或类型不是现金账户'}), 400

    # 派生 channel_category / ledger_type（#1101 渠道分类重设计，铁律见设计文档 §2.3）：
    #   - 显式给了 channel_category → 以它为准，并据其反推 ledger_type（手动账本路径）；
    #   - 否则有销售机构 → 以 org_type 映射为准（权威，覆盖 ledger_type 的展示语义）；
    #   - 否则按 ledger_type 反推 channel_category（向后兼容旧调用方）。
    # 注意：ledger_type 仍保留作计算口径键，channel_category 才是用户可见分组/标签。
    if channel_category:
        ledger_type = map_channel_category_to_ledger_type(channel_category)
    elif institution_org_type:
        channel_category = map_org_type_to_channel_category(institution_org_type)
    elif ledger_type:
        channel_category = map_ledger_type_to_channel_category(ledger_type)

    # 类现金产品绑定（#1137）：入参用基金代码（前端搜索结果即 code），存储 funds.id。
    # 仅证券/基金平台可绑；开关默认关闭，未绑定时不允许开启。
    linked_money_fund_code = (data.get('linked_money_fund_code') or '').strip() or None
    auto_purchase_money_fund = bool(data.get('auto_purchase_money_fund', False))
    linked_money_fund_id = None
    if linked_money_fund_code:
        if ledger_type not in ('stock', 'fund'):
            return jsonify({'data': None, 'message': '只有证券账户或基金可以绑定活期+'}), 400
        with get_db() as db:
            fund = _resolve_money_fund(db, linked_money_fund_code)
            if not fund:
                return jsonify({'data': None, 'message': '绑定的活期+不存在'}), 400
            reject = _check_money_fund_bindable(db, fund, ledger_type)
            if reject:
                return jsonify({'data': None, 'message': reject}), 400
            linked_money_fund_id = fund.id
    elif auto_purchase_money_fund:
        return jsonify({'data': None, 'message': '请先绑定活期+，再开启自动申购'}), 400

    with get_db() as db:
        ledger = Ledger(
            name=name,
            ledger_type=ledger_type,
            channel_category=channel_category,
            default_allocation=data.get('default_allocation', 'longterm'),
            notes=data.get('notes', ''),
            portfolio_id=data.get('portfolio_id'),
            linked_cash_ledger_id=linked_cash_id,
            linked_money_fund_id=linked_money_fund_id,
            auto_purchase_money_fund=auto_purchase_money_fund,
            sales_institution_id=sales_institution_id,
            family_id=get_family_id(),
        )

        # 处理 fee_config JSON 字段
        fee_config = data.get('fee_config')
        if fee_config is not None:
            # 前端传入的可能是一个 dict，直接序列化；也可以是字符串
            if isinstance(fee_config, dict):
                ledger.fee_config = json.dumps(fee_config, ensure_ascii=False)
            elif isinstance(fee_config, str):
                ledger.fee_config = fee_config  # 信任前端传的 JSON 字符串
            else:
                abort(400, 'fee_config 格式无效')

        db.add(ledger)
        db.commit()
        db.refresh(ledger)
        return jsonify({'data': _ledger_to_dict(ledger), 'message': 'ok'})


@ledgers_bp.get('/')
def list_ledgers():
    """获取所有账户（含摘要统计）。

    include_archived=true 时一并返回已归档账户；默认仅返回活跃账户
    （归档账户保留全部数据、仍参与收益计算，仅从日常视图默认隐藏）。
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
        # 派生"最近使用时间"：每个账户最近一笔交易的确认日期。
        # 单条聚合查询，避免 N+1；供前端下拉按最近使用排序。
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
            # 附加摘要数据
            item['total_market_value'] = 0.0
            item['pnl'] = 0.0
            item['position_count'] = 0
            item['cash_balance'] = 0.0  # 统一初始化 cash_balance

            if ledger.ledger_type in ('stock', 'fund', 'e_account'):
                stats = LedgerService.get_portfolio_stats(db, ledger.id)
                item['total_market_value'] = stats['total_market_value']
                item['pnl'] = stats['position_pnl']
                item['position_count'] = stats['position_count']
                if ledger.ledger_type == 'stock':
                    item['cash_balance'] = LedgerService.get_cash_balance(db, ledger)

            elif ledger.ledger_type == 'bank':
                stats = LedgerService.get_bank_stats(db, ledger.id)
                item['total_market_value'] = stats['total_market_value']
                item['pnl'] = 0  # bank 不直接显示盈亏
                item['position_count'] = stats.get('position_count', 0)
                item['cash_balance'] = stats['current_balance']
                # 🔥 负债必须从 stats 拿，视图层不做 SQL 聚合
                item['linked_liability'] = stats.get('linked_liability', 0.0)

                # 🔥 货基统计必须在这里写上
                money_fund_stats = LedgerService.get_money_fund_stats(db, ledger.id)
                item['money_fund_amount'] = money_fund_stats.get('money_fund_amount', 0.0)
                item['money_fund_ratio'] = money_fund_stats.get('money_fund_ratio', 0.0)

            elif ledger.ledger_type == 'property':
                stats = LedgerService.get_property_stats(db, ledger.id)
                item['total_market_value'] = stats['total_market_value']
                item['position_count'] = stats['asset_count']
                item['asset_count'] = stats['asset_count']
                item['cash_balance'] = 0.0

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
        return jsonify({'data': None, 'message': '参数错误：ledger_type 与 ordered_ids 必填'}), 400

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
        db.commit()
    return jsonify({'data': None, 'message': 'ok'})


@ledgers_bp.get('/<int:ledger_id>/')
def get_ledger(ledger_id: int):
    """获取单个账户详情"""
    with get_db() as db:
        ledger = get_owned_or_404(db, Ledger, ledger_id)
        if not ledger:
            abort(404, '账户不存在')
        return jsonify({'data': _ledger_to_dict(ledger), 'message': 'ok'})


def _sync_account_name_snapshots(db, ledger_id: int, account_name: str) -> dict[str, int]:
    """把账户新名称刷到所有下游 account_name 冗余快照（#1354）。

    account_name 是 ledgers.name 的冗余列，散落在 assets / positions / transactions
    三张表。账户改名时只改 ledgers.name 会让明细页、按账户分组的分布图继续显示旧名字
    （改名看着成功了，数据里还是旧的）。此处按 ledger_id 命中范围统一刷新；
    ledger_id 为空的孤儿数据不处理——它本就没有账户可对齐。

    Returns:
        {表名: 受影响行数}，便于接口回执与测试断言。
    """
    family_id = get_family_id()
    return {
        'assets': db.query(Asset)
        .filter(Asset.ledger_id == ledger_id, Asset.family_id == family_id)
        .update({Asset.account_name: account_name}, synchronize_session=False),
        'positions': db.query(Position)
        .filter(Position.ledger_id == ledger_id, Position.family_id == family_id)
        .update({Position.account_name: account_name}, synchronize_session=False),
        'transactions': db.query(Transaction)
        .filter(Transaction.ledger_id == ledger_id, Transaction.family_id == family_id)
        .update({Transaction.account_name: account_name}, synchronize_session=False),
    }


@ledgers_bp.patch('/<int:ledger_id>/')
def update_ledger(ledger_id: int):
    """更新账户信息"""
    data = request.get_json() or {}
    with get_db() as db:
        ledger = get_owned_or_404(db, Ledger, ledger_id)
        if not ledger:
            abort(404, '账户不存在')

        # 更新基本字段
        name = data.get('name')
        renamed_to: str | None = None
        if name is not None:
            name = name.strip()
            if not name:
                return jsonify({'data': None, 'message': '账户名称不能为空'}), 400
            if name != ledger.name:
                renamed_to = name
            ledger.name = name

        ledger_type = data.get('ledger_type')
        if ledger_type is not None and ledger_type != ledger.ledger_type:
            # 类型决定计算口径（费率/税费/分红再投资/XIRR 处理不同），已有数据的账户
            # 禁止改类型，否则历史交易的计算口径会瞬间错乱。空白账户（零交易/零持仓/
            # 零资产）允许改类型。详见归档账户设计决策。
            has_data = (
                db.query(Transaction).filter(Transaction.ledger_id == ledger_id).count() > 0
                or db.query(Position).filter(Position.ledger_id == ledger_id).count() > 0
                or db.query(Asset).filter(Asset.ledger_id == ledger_id, Asset.family_id == get_family_id()).count() > 0
            )
            if has_data:
                return jsonify(
                    {'data': None, 'message': '账户已有交易/持仓/资产数据，类型不可更改；如需调整请先归档后新建'}
                ), 409
            ledger.ledger_type = ledger_type

        # 归档状态：活跃/归档切换。归档仅隐藏于日常视图，保留全部数据并仍参与收益计算。
        if 'is_active' in data:
            is_active = data['is_active']
            if not isinstance(is_active, bool):
                return jsonify({'data': None, 'message': 'is_active 必须为布尔值'}), 400
            ledger.is_active = is_active

        default_allocation = data.get('default_allocation')
        if default_allocation is not None:
            ledger.default_allocation = default_allocation

        notes = data.get('notes')
        if notes is not None:
            ledger.notes = notes

        # 更新 portfolio_id（允许设置为 None）
        if 'portfolio_id' in data:
            ledger.portfolio_id = data['portfolio_id']

        # 更新 linked_cash_ledger_id（允许设置为 None）
        if 'linked_cash_ledger_id' in data:
            linked_cash_id = data['linked_cash_ledger_id']
            # 如果是设置非空值，必须校验
            if linked_cash_id is not None:
                current_type = ledger_type if ledger_type is not None else ledger.ledger_type
                if current_type not in ('stock', 'fund'):
                    return jsonify({'data': None, 'message': '只有证券账户或基金可以关联现金账户'}), 400
                cash_ledger = db.query(Ledger).filter_by(id=linked_cash_id, ledger_type='bank').first()
                if not cash_ledger or cash_ledger.family_id != get_family_id():
                    return jsonify({'data': None, 'message': '关联的现金账户不存在或类型不是现金账户'}), 400
            # 无论值是否为 None，均更新
            ledger.linked_cash_ledger_id = linked_cash_id

        # 更新类现金产品绑定（#1137，允许设置为 None 解绑）
        # 入参用基金代码，存储 funds.id；未绑定时不允许开启自动申购。
        if 'linked_money_fund_code' in data:
            fund_code = (data.get('linked_money_fund_code') or '').strip() or None
            old_linked_id = ledger.linked_money_fund_id
            if fund_code is None:
                ledger.linked_money_fund_id = None
                # 解绑时自动关闭开关，避免残留一个无法生效的开关
                ledger.auto_purchase_money_fund = False
            else:
                if ledger.ledger_type not in ('stock', 'fund'):
                    return jsonify({'data': None, 'message': '只有证券账户或基金可以绑定活期+'}), 400
                fund = _resolve_money_fund(db, fund_code)
                if not fund:
                    return jsonify({'data': None, 'message': '绑定的活期+不存在'}), 400
                reject = _check_money_fund_bindable(db, fund, ledger.ledger_type)
                if reject:
                    return jsonify({'data': None, 'message': reject}), 400
                ledger.linked_money_fund_id = fund.id
                # #1137 换绑活期+：原绑定货基仍有净额持仓时，赎回 A 并申购 B（资产中性）。
                # 仅当从 A 换到 B（ID 不同）才触发，首次绑定 / 解绑重绑不触发。
                if old_linked_id and old_linked_id != fund.id:
                    old_fund = db.get(Fund, old_linked_id)
                    if old_fund:
                        _swap_linked_money_fund(db, ledger, old_fund, fund)

        # 更新自动申购开关（#1137）
        if 'auto_purchase_money_fund' in data:
            auto_purchase = data['auto_purchase_money_fund']
            if not isinstance(auto_purchase, bool):
                return jsonify({'data': None, 'message': 'auto_purchase_money_fund 必须为布尔值'}), 400
            if auto_purchase and not ledger.linked_money_fund_id:
                return jsonify({'data': None, 'message': '请先绑定活期+，再开启自动申购'}), 400
            ledger.auto_purchase_money_fund = auto_purchase

        # 更新 sales_institution_id（允许设置为 None）
        if 'sales_institution_id' in data:
            sales_institution_id = data['sales_institution_id']
            if sales_institution_id is not None:
                institution = db.query(SalesInstitution).filter_by(id=sales_institution_id).first()
                if not institution:
                    return jsonify({'data': None, 'message': '关联的销售机构不存在'}), 400
            # 无论值是否为 None，均更新
            ledger.sales_institution_id = sales_institution_id

        # 更新 channel_category（用户可见分组/类型标签，#1101 重设计）。
        # 注：本字段通常由系统维护（建账/导入时由 org_type 或用户选分组推导），
        # 此处允许显式写入以兼容前端直接设置分组；不反向改写 ledger_type（计算口径键）。
        if 'channel_category' in data:
            ledger.channel_category = data['channel_category']

        # 更新 fee_config
        if 'fee_config' in data:
            fee_config = data['fee_config']
            if fee_config is None:
                ledger.fee_config = None
            elif isinstance(fee_config, dict):
                ledger.fee_config = json.dumps(fee_config, ensure_ascii=False)
            elif isinstance(fee_config, str):
                ledger.fee_config = fee_config
            else:
                return jsonify({'data': None, 'message': 'fee_config 格式无效'}), 400

        # #1354：改名后级联刷新下游快照，否则明细页仍显示旧账户名
        if renamed_to:
            _sync_account_name_snapshots(db, ledger_id, renamed_to)

        db.commit()
        db.refresh(ledger)
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
                    }
                ), 400

        db.delete(ledger)
        db.commit()
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
        db.commit()
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
        db.commit()
        db.refresh(ledger)
        return jsonify({'data': _ledger_to_dict(ledger), 'message': 'ok'})


def _migrate_transactions(
    db,
    src_ledger_id,
    tgt_ledger_id,
    tgt_account_name,
    src_position_id=None,
    tgt_position_id=None,
):
    """把来源账户下的交易记录一并归并到目标账户，保持与持仓的 ledger 一致。

    - src_position_id 给定时只处理该持仓下的交易；为 None 时处理账户级
      （position_id 为空，如存取/费用）交易。
    - 交易改挂目标账户的 ledger_id / account_name；合并到目标持仓时同步改 position_id。
    - 若目标账户已存在相同 import_hash 的交易（重复导入），丢弃来源这份以归一，
      避免触发 uq_txn_import_hash(ledger_id, import_hash) 唯一约束冲突。
    """
    q = db.query(Transaction).filter(Transaction.ledger_id == src_ledger_id)
    if src_position_id is None:
        q = q.filter(Transaction.position_id.is_(None))
    else:
        q = q.filter(Transaction.position_id == src_position_id)
    txns = q.all()
    if not txns:
        return 0
    count = 0
    for t in txns:
        if t.import_hash:
            exists = (
                db.query(Transaction)
                .filter(
                    Transaction.ledger_id == tgt_ledger_id,
                    Transaction.import_hash == t.import_hash,
                )
                .first()
            )
            if exists is not None:
                db.delete(t)  # 重复交易：保留目标账户那份
                count += 1
                continue
        t.ledger_id = tgt_ledger_id
        t.account_name = tgt_account_name
        if src_position_id is not None:
            t.position_id = tgt_position_id
        count += 1
    return count


# ────────────────────────── 账本批量迁移（两段式：预览 → 提交） ──────────────────────────


def _find_target_position(db, target_ledger_id, symbol, family_id):
    """在目标账本中找同 symbol 持仓（uq_positions_ledger_symbol 业务键）。"""
    return (
        db.query(Position)
        .filter(
            Position.ledger_id == target_ledger_id,
            Position.symbol == symbol,
            Position.family_id == family_id,
        )
        .first()
    )


def _find_target_asset(db, target_ledger_id, asset, family_id):
    """在目标账本中按 (name, major_category, minor_category) 定位同类资产。"""
    return (
        db.query(Asset)
        .filter(
            Asset.ledger_id == target_ledger_id,
            Asset.name == asset.name,
            Asset.major_category == asset.major_category,
            Asset.minor_category == asset.minor_category,
            Asset.family_id == family_id,
        )
        .first()
    )


def _position_read_view(pos):
    """持仓可读视图：份额（份）/确认净值（元）/ISO 日期，供前端直接展示比对。"""
    return {
        'quantity': Money.min_unit_to_shares(pos.quantity),
        'avg_price': Money.price_units_to_yuan(pos.avg_price) if pos.avg_price else None,
        'confirm_date': pos.confirm_date.isoformat() if pos.confirm_date else None,
    }


def _asset_read_view(asset):
    """资产可读视图：金额（元）。"""
    return {'amount': Money.cents_to_yuan(asset.amount) if asset.amount else None}


def _classify_position(src_pos, dup):
    """持仓三分类：keep / duplicate / conflict（conflict 附系统建议 suggestion）。

    判定口径（设计文档 §5.1/§5.2）：份额+确认日期+确认净值全等 → 精确重复；
    任一不一致 → 冲突。仅确认日期不同（份额与确认净值全等）大概率是同一笔被写两遍、
    日期为手填噪声，建议保留目标；其余冲突建议加权合并。
    """
    if dup is None:
        return 'keep', None, []
    if (
        src_pos.quantity == dup.quantity
        and src_pos.confirm_date == dup.confirm_date
        and src_pos.avg_price == dup.avg_price
    ):
        return 'duplicate', None, []
    src_view, tgt_view = _position_read_view(src_pos), _position_read_view(dup)
    conflict_fields = [k for k in ('quantity', 'avg_price', 'confirm_date') if src_view[k] != tgt_view[k]]
    if src_pos.quantity == dup.quantity and src_pos.avg_price == dup.avg_price:
        suggestion = 'keep_target'
    else:
        suggestion = 'merge'
    return 'conflict', suggestion, conflict_fields


def _classify_asset(src_asset, dup):
    """资产二分类判定（无 merge）：金额一致 → duplicate，否则 conflict。

    返回与 _classify_position 相同的三元组形状（suggestion 恒为 None），便于调用方统一解包。
    """
    if dup is None:
        return 'keep', None, []
    if src_asset.amount == dup.amount:
        return 'duplicate', None, []
    return 'conflict', None, ['amount']


def _check_migration_target(source, target):
    """迁移目标合法性校验：同家庭（防 IDOR）、同类型（计算口径一致）。返回错误信封或 None。"""
    if source.family_id != target.family_id:
        return {'data': None, 'message': '只能迁移到同家庭账户'}, 403
    if source.ledger_type != target.ledger_type:
        return {'data': None, 'message': '只能迁移到同类型账户'}, 400
    return None


def _institution_view(db, ledger):
    """账本绑定机构的展示视图：{id, name}；未绑定（或名录机构已不存在）返回 None。

    name 取 display_name（常用别名如「支付宝」），缺省回退 AMAC 权威全称 org_name。
    """
    if not ledger.sales_institution_id:
        return None
    inst = db.query(SalesInstitution).filter_by(id=ledger.sales_institution_id).first()
    if inst is None:
        return None
    return {'id': inst.id, 'name': inst.display_name or inst.org_name}


def _cross_institution(source, target, src_inst, tgt_inst):
    """跨机构判定：双方都已绑定机构且 id 不同才为 True；任一未绑定 → False。"""
    return src_inst is not None and tgt_inst is not None and src_inst['id'] != tgt_inst['id']


@ledgers_bp.post('/<int:ledger_id>/migrations/preview/')
def preview_migration(ledger_id: int):
    """迁移预览（只读，不写库）：对源账本全部持仓/资产做三分类并给出守恒预估。

    用户关闭预览即无任何副作用——「回滚」由「不提交」自然实现（设计文档 §4.1）。
    """
    data = request.get_json() or {}
    target_id = data.get('target_ledger_id')
    if not target_id:
        return jsonify({'data': None, 'message': '缺少 target_ledger_id'}), 400

    with get_db() as db:
        source = get_owned_or_404(db, Ledger, ledger_id)
        target = db.query(Ledger).get(target_id)
        if not source or not target:
            return jsonify({'data': None, 'message': '账户不存在'}), 404
        err = _check_migration_target(source, target)
        if err:
            return jsonify(err[0]), err[1]

        family_id = get_family_id()
        items = []
        # 守恒预估一律用最小单位整数（份×10000），避免 float 误差；
        # 冲突行按系统建议计入（前端可改决议，故仅为预估，真正守恒校验在 commit 后置执行）。
        source_out_min = 0
        target_in_min = 0
        for p in db.query(Position).filter(Position.ledger_id == source.id).all():
            dup = _find_target_position(db, target.id, p.symbol, family_id)
            classification, suggestion, conflict_fields = _classify_position(p, dup)
            items.append(
                {
                    'kind': 'position',
                    'symbol': p.symbol,
                    'name': p.name,
                    # 资产类型：前端据此切换展示术语（基金用「确认净值」，股票用「成本价」）
                    'asset_type': p.asset_type,
                    'classification': classification,
                    'suggestion': suggestion,
                    'source': _position_read_view(p),
                    'target': _position_read_view(dup) if dup is not None else None,
                    'conflict_fields': conflict_fields,
                }
            )
            qty = p.quantity or 0
            source_out_min += qty
            if classification == 'keep' or classification == 'duplicate':
                # keep：源份额并入目标；duplicate：目标已有同额一份，净增 0
                if classification == 'keep':
                    target_in_min += qty
            elif suggestion == 'merge':
                target_in_min += qty
            elif suggestion == 'keep_source':
                # 整条覆盖：目标净增 = 源份额 − 被覆盖的目标份额（可能为负）
                target_in_min += qty - (dup.quantity or 0)

        for a in db.query(Asset).filter(Asset.ledger_id == source.id, Asset.family_id == family_id).all():
            dup = _find_target_asset(db, target.id, a, family_id)
            classification, _, conflict_fields = _classify_asset(a, dup)
            items.append(
                {
                    'kind': 'asset',
                    'symbol': None,
                    'name': a.name,
                    # 决议定位键：commit 按 (name, major_category, minor_category) 匹配资产决议，
                    # preview 必须带出分类键，否则前端无法组装合法决议
                    'major_category': a.major_category,
                    'minor_category': a.minor_category,
                    'classification': classification,
                    'suggestion': None,  # 资产无 merge，不给建议
                    'source': _asset_read_view(a),
                    'target': _asset_read_view(dup) if dup is not None else None,
                    'conflict_fields': conflict_fields,
                }
            )

        # 账户级交易（position_id 为空，如存取/费用）在 commit 时无条件归并，预览只报数
        account_txn_count = (
            db.query(Transaction).filter(Transaction.ledger_id == source.id, Transaction.position_id.is_(None)).count()
        )

        # 销售机构软优先：跨机构不禁止迁移，但前端须提示，commit 需用户显式确认
        src_inst = _institution_view(db, source)
        tgt_inst = _institution_view(db, target)

        return jsonify(
            {
                'data': {
                    'items': items,
                    'conservation': {
                        'source_out_positions': source_out_min,
                        'target_in_positions': target_in_min,
                        'account_level_transactions': account_txn_count,
                    },
                    'institution': {
                        'source': src_inst,
                        'target': tgt_inst,
                        'cross_institution': _cross_institution(source, target, src_inst, tgt_inst),
                    },
                },
                'message': 'ok',
            }
        )


def _delete_position_with_meta(db, position):
    """删除持仓及其导入溯源元数据。

    不依赖数据库层 CASCADE：SQLite 需 PRAGMA foreign_keys=ON 才会触发外键级联，
    各环境（测试内存库/本地开发库）未必开启，应用层显式删除保证 meta 不残留。
    """
    db.query(PositionImportMeta).filter(PositionImportMeta.position_id == position.id).delete()
    db.delete(position)


def _verify_migration_conservation(db, expectations, source_id, target_id):
    """守恒后置校验（写库后、commit 前）：任何不符立即抛异常触发整体回滚。

    - 逐行核对目标持仓数量/确认净值与动作语义期望值；
    - 源账本不应残留任何持仓/资产（conflict 未决议已在入口 400 拦截，走到这里即应清空）。
    """
    # 会话为 autoflush=False：先把挂起的 UPDATE/DELETE 刷库，否则下面的 SQL 校验读到旧值
    db.flush()
    for pid, exp_quantity, exp_avg_price in expectations:
        row = db.query(Position).filter(Position.id == pid, Position.ledger_id == target_id).first()
        if row is None:
            raise RuntimeError(f'守恒校验失败：持仓 {pid} 未落在目标账本')
        if row.quantity != exp_quantity or (row.avg_price or 0) != exp_avg_price:
            raise RuntimeError(f'守恒校验失败：持仓 {pid} 数量/确认净值与动作语义期望值不符')
    if db.query(Position).filter(Position.ledger_id == source_id).count() > 0:
        raise RuntimeError('守恒校验失败：源账本仍残留持仓')
    if db.query(Asset).filter(Asset.ledger_id == source_id).count() > 0:
        raise RuntimeError('守恒校验失败：源账本仍残留资产')


@ledgers_bp.post('/<int:ledger_id>/migrations/commit/')
def commit_migration(ledger_id: int):
    """迁移提交（单事务 + 整体回滚）：按预览分类与用户决议执行写入。

    - conflict 行必须有 resolution（keep_source/keep_target/merge），缺任一条 → 400 且不写任何数据；
    - 任一异常（含守恒校验不过）→ rollback，返回 500，源数据原样（设计文档 §4.2/§6）。
    """
    data = request.get_json() or {}
    target_id = data.get('target_ledger_id')
    if not target_id:
        return jsonify({'data': None, 'message': '缺少 target_ledger_id'}), 400

    with get_db() as db:
        source = get_owned_or_404(db, Ledger, ledger_id)
        target = db.query(Ledger).get(target_id)
        if not source or not target:
            return jsonify({'data': None, 'message': '账户不存在'}), 404
        err = _check_migration_target(source, target)
        if err:
            return jsonify(err[0]), err[1]

        # 跨销售机构软闸门：双方均已绑定且机构不同时，须用户显式确认才放行；
        # 任一方未绑定或同机构 → 直接放行。校验在任何写库动作之前。
        src_inst = _institution_view(db, source)
        tgt_inst = _institution_view(db, target)
        if _cross_institution(source, target, src_inst, tgt_inst) and data.get('allow_cross_institution') is not True:
            return jsonify(
                {
                    'data': None,
                    'message': '跨销售机构迁移需显式确认，可能造成交易归属混乱；'
                    '请携带 allow_cross_institution=true 重试',
                }
            ), 400

        # 解析用户决议表：持仓按 symbol、资产按 (name, major, minor) 定位
        pos_resolutions = {}
        asset_resolutions = {}
        for r in data.get('resolutions') or []:
            action = r.get('action')
            if r.get('kind') == 'position':
                pos_resolutions[r.get('symbol')] = action
            elif r.get('kind') == 'asset':
                asset_resolutions[(r.get('name'), r.get('major_category'), r.get('minor_category'))] = action

        family_id = get_family_id()

        # ── 第一步：纯读分类 + 决议完整性检查（此时不写任何数据）──
        plan = []  # (kind, 源对象, 目标对象或 None, 动作)
        unresolved = []
        for p in db.query(Position).filter(Position.ledger_id == source.id).all():
            dup = _find_target_position(db, target.id, p.symbol, family_id)
            classification, _, _ = _classify_position(p, dup)
            if classification == 'keep':
                plan.append(('position', p, None, 'keep'))
            elif classification == 'duplicate':
                plan.append(('position', p, dup, 'duplicate'))
            else:
                action = pos_resolutions.get(p.symbol)
                if action not in ('keep_source', 'keep_target', 'merge'):
                    unresolved.append(p.symbol)
                else:
                    plan.append(('position', p, dup, action))

        for a in db.query(Asset).filter(Asset.ledger_id == source.id, Asset.family_id == family_id).all():
            dup = _find_target_asset(db, target.id, a, family_id)
            classification, _, _ = _classify_asset(a, dup)
            if classification == 'keep':
                plan.append(('asset', a, None, 'keep'))
            elif classification == 'duplicate':
                plan.append(('asset', a, dup, 'duplicate'))
            else:
                action = asset_resolutions.get((a.name, a.major_category, a.minor_category))
                if action not in ('keep_source', 'keep_target'):
                    unresolved.append(a.name)
                else:
                    plan.append(('asset', a, dup, action))

        if unresolved:
            # 缺决议直接拒绝：列明未决议项，保证「未确认不写库」
            return jsonify(
                {
                    'data': None,
                    'message': '以下冲突项未决议，请逐条选择保留源/保留目标/合并后再提交：' + '、'.join(unresolved),
                }
            ), 400

        # ── 第二步：单事务执行 + 守恒校验 + 提交；任一异常整体回滚 ──
        try:
            migrated = deduped = merged = keep_source_cnt = asset_cnt = txn_cnt = 0
            expectations = []  # (目标持仓 id, 期望数量最小单位, 期望确认净值分)
            for kind, src_obj, dup, action in plan:
                if kind == 'position':
                    if action == 'keep':
                        # 无同名冲突：源行整条改挂目标账本，交易随行归并
                        src_obj.ledger_id = target.id
                        src_obj.account_name = target.name
                        src_obj.updated_at = func.now()
                        txn_cnt += _migrate_transactions(
                            db,
                            source.id,
                            target.id,
                            target.name,
                            src_position_id=src_obj.id,
                            tgt_position_id=src_obj.id,
                        )
                        expectations.append((src_obj.id, src_obj.quantity or 0, src_obj.avg_price or 0))
                        migrated += 1
                    elif action in ('duplicate', 'keep_target'):
                        # 精确重复/用户弃源：源交易并入目标持仓（import_hash 去重）后删源行
                        txn_cnt += _migrate_transactions(
                            db,
                            source.id,
                            target.id,
                            target.name,
                            src_position_id=src_obj.id,
                            tgt_position_id=dup.id,
                        )
                        expectations.append((dup.id, dup.quantity or 0, dup.avg_price or 0))
                        _delete_position_with_meta(db, src_obj)
                        deduped += 1
                    elif action == 'keep_source':
                        # 源整条覆盖目标：先把目标持仓名下交易改挂到源持仓
                        # （复用 _migrate_transactions 去重逻辑、方向相反），删目标行后源行改挂目标账本。
                        # 删除必须先 flush 落库，否则源行改挂会撞 uq_positions_ledger_symbol。
                        txn_cnt += _migrate_transactions(
                            db,
                            target.id,
                            source.id,
                            source.name,
                            src_position_id=dup.id,
                            tgt_position_id=src_obj.id,
                        )
                        _delete_position_with_meta(db, dup)
                        db.flush()
                        src_obj.ledger_id = target.id
                        src_obj.account_name = target.name
                        src_obj.updated_at = func.now()
                        # 源行名下交易（含刚从目标并入的）统一对齐目标账本
                        txn_cnt += _migrate_transactions(
                            db,
                            source.id,
                            target.id,
                            target.name,
                            src_position_id=src_obj.id,
                            tgt_position_id=src_obj.id,
                        )
                        expectations.append((src_obj.id, src_obj.quantity or 0, src_obj.avg_price or 0))
                        keep_source_cnt += 1
                    elif action == 'merge':
                        # 加权平均合并（全程最小单位整数，四舍五入到分；份额和为 0 取 0）
                        q1, q2 = dup.quantity or 0, src_obj.quantity or 0
                        p1, p2 = dup.avg_price or 0, src_obj.avg_price or 0
                        total_q = q1 + q2
                        merged_price = ((q1 * p1 + q2 * p2 + total_q // 2) // total_q) if total_q else 0
                        dates = [d for d in (dup.confirm_date, src_obj.confirm_date) if d is not None]
                        dup.quantity = total_q
                        dup.avg_price = merged_price
                        if dates:
                            dup.confirm_date = max(dates)  # 确认日期取较新（仅展示口径，不参与计算）
                        # 其余字段（name/market/portfolio_id 等）保留目标原值
                        txn_cnt += _migrate_transactions(
                            db,
                            source.id,
                            target.id,
                            target.name,
                            src_position_id=src_obj.id,
                            tgt_position_id=dup.id,
                        )
                        expectations.append((dup.id, total_q, merged_price))
                        _delete_position_with_meta(db, src_obj)  # 源行及其导入溯源一并清除
                        merged += 1
                else:
                    if action == 'keep':
                        src_obj.ledger_id = target.id
                        src_obj.account_name = target.name
                        src_obj.updated_at = func.now()
                    elif action in ('duplicate', 'keep_target'):
                        db.delete(src_obj)  # 弃源保目标
                    elif action == 'keep_source':
                        # 源覆盖目标：先删目标行（flush 避免唯一键冲突），源行改挂目标账本
                        db.delete(dup)
                        db.flush()
                        src_obj.ledger_id = target.id
                        src_obj.account_name = target.name
                        src_obj.updated_at = func.now()
                    asset_cnt += 1

            # 账户级交易（position_id 为空，如存取/费用）无条件归并到目标账户
            txn_cnt += _migrate_transactions(db, source.id, target.id, target.name)

            # 守恒后置校验：不过即抛异常 → 整体回滚，源数据原样
            _verify_migration_conservation(db, expectations, source.id, target.id)

            db.commit()
        except Exception:
            db.rollback()
            # 记录完整堆栈便于排查；对外只返回统一信封，不泄露内部细节
            logger.exception('账本迁移提交失败，已整体回滚：src={} tgt={}', ledger_id, target_id)
            return jsonify({'data': None, 'message': '迁移失败，已整体回滚，源数据未变动'}), 500

        message = (
            f'已迁移至「{target.name}」：{migrated} 项持仓迁入、{deduped} 项去重、'
            f'{merged} 项合并、{keep_source_cnt} 项冲突留源、{asset_cnt} 项资产'
        )
        if txn_cnt:
            message += f'；另归并 {txn_cnt} 笔交易'
        return jsonify(
            {
                'data': {
                    'position_count': migrated,
                    'dedup_count': deduped,
                    'merged_count': merged,
                    'keep_source_count': keep_source_cnt,
                    'asset_count': asset_cnt,
                    'transaction_count': txn_cnt,
                },
                'message': message,
            }
        )


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
            return jsonify({'data': None, 'message': '账户不存在'}), 404
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
            return jsonify({'data': None, 'message': '账户不存在'}), 404
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
        db.commit()
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
        db.commit()
        return jsonify({'message': 'ok', 'data': None})


@ledgers_bp.patch('/<int:ledger_id>/transactions/<int:transaction_id>/')
def update_ledger_transaction(ledger_id: int, transaction_id: int):
    """编辑账户内交易（金额/数量/价格/日期/备注，见 issue #1112）。

    设计要点：
    - 允许修改 quantity/price/amount/fee/trade_date/confirm_date/notes；
    - 归属类字段（ledger_id/symbol/account 等）禁止修改；
    - 修改金额类或日期/备注字段后清空 import_hash：手工编辑已破坏"内容哈希去重"
      不变式，后续重新导入需按新内容重新匹配/对账（不自动重算持仓，避免冲销算法风险）；
    - 未显式给出 amount 时，按 价格×数量 重算毛额以保持一致。
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

        def _non_negative(field, value):
            if value is not None and (not isinstance(value, (int, float)) or value < 0):
                abort(400, f'{field} 必须为非负数字')
            return value

        touched = False
        recompute_amount = False
        if 'quantity' in data:
            txn.quantity = Money.shares_to_min_unit(_non_negative('quantity', data['quantity']))
            touched = True
            recompute_amount = True
        if 'price' in data:
            txn.price = Money.yuan_to_price_units(_non_negative('price', data['price']))
            touched = True
            recompute_amount = True
        if 'fee' in data:
            txn.fee = Money.yuan_to_cents(_non_negative('fee', data['fee']))
            touched = True
        if 'amount' in data:
            txn.amount = Money.yuan_to_cents(_non_negative('amount', data['amount']))
            touched = True
        elif recompute_amount:
            # 改了价格/数量但未显式给金额时，按 价格×数量 重算毛额，保持一致性
            txn.amount = Money.multiply_price_quantity(txn.price, txn.quantity)

        if 'trade_date' in data and data['trade_date'] is not None:
            try:
                txn.trade_date = datetime.strptime(data['trade_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                abort(400, 'trade_date 格式应为 YYYY-MM-DD')
            touched = True
        if 'confirm_date' in data:
            if data['confirm_date'] is None:
                txn.confirm_date = None
            else:
                try:
                    txn.confirm_date = datetime.strptime(data['confirm_date'], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    abort(400, 'confirm_date 格式应为 YYYY-MM-DD')
            touched = True
        if 'notes' in data:
            txn.notes = data['notes']
            touched = True

        # 手工编辑破坏内容哈希去重不变式，清空以便重新导入按新内容对账
        if touched and txn.import_hash:
            txn.import_hash = None

        db.commit()

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


def _orphan_ledger_condition(ledger_id_col, valid_ledger_ids):
    """孤儿判定条件：ledger_id 为空或指向已删除账户（与 ledger_service 语义一致）"""
    return or_(ledger_id_col.is_(None), ~ledger_id_col.in_(valid_ledger_ids))


@ledgers_bp.get('/orphan/detail/')
def get_orphan_detail():
    """查询未归置数据（孤儿）明细：孤儿持仓/资产/交易清单 + 汇总。

    前端此前只能看到汇总数字（N 个持仓、合计 ¥X），无法定位具体是哪些数据；
    本接口补齐明细，孤儿判定与 migrate/delete 完全一致（ledger_id 为空或不在
    当前家庭有效账户 id 集合内），保证「明细展示 → 归入/清理」所见即所得。
    """
    with get_db() as db:
        family_id = get_family_id()
        # 当前家庭全部账户 id 集合（孤儿判定基准，与 migrate/delete 相同）
        valid_ledger_ids = [lid for (lid,) in db.query(Ledger.id).filter(Ledger.family_id == family_id).all()]

        # ── 孤儿持仓：逐行算市值/盈亏，复用 Money.multiply_price_quantity 的
        #    ROUND_HALF_UP 语义（与 ledger_service.get_positions_paginated 一致，
        #    避免 SQL 聚合与逐行四舍五入的分位差异）
        orphan_positions = (
            db.query(Position)
            .filter(Position.family_id == family_id, _orphan_ledger_condition(Position.ledger_id, valid_ledger_ids))
            .all()
        )
        positions = []
        position_mv_cents = 0
        for p in orphan_positions:
            mv_cents = Money.multiply_price_quantity(p.current_price, p.quantity)
            # 盈亏 = (现价 - 成本) × 数量；无成本价时盈亏记 0（与持仓列表语义一致）
            pnl_cents = Money.multiply_price_quantity(p.current_price - p.avg_price, p.quantity) if p.avg_price else 0
            position_mv_cents += mv_cents
            positions.append(
                {
                    'id': p.id,
                    'symbol': p.symbol,
                    'name': p.name,
                    'quantity': Money.min_unit_to_shares(p.quantity),
                    'avg_price': Money.price_units_to_yuan(p.avg_price),
                    'market_value': Money.cents_to_yuan(mv_cents),
                    'pnl': Money.cents_to_yuan(pnl_cents),
                }
            )

        # ── 孤儿资产：金额为存量价值，直接计入汇总
        orphan_assets = (
            db.query(Asset)
            .filter(Asset.family_id == family_id, _orphan_ledger_condition(Asset.ledger_id, valid_ledger_ids))
            .all()
        )
        assets = []
        asset_amount_cents = 0
        for a in orphan_assets:
            asset_amount_cents += a.amount or 0
            assets.append(
                {
                    'id': a.id,
                    'name': a.name,
                    'amount': Money.cents_to_yuan(a.amount),
                    'major_category': a.major_category,
                }
            )

        # ── 孤儿交易：ledger_id 悬空（与 migrate 归入交易的判定一致）。
        #    交易是流水而非存量，金额不计入 total_market_value，避免与持仓/资产重复计算
        orphan_txns = (
            db.query(Transaction)
            .filter(
                Transaction.family_id == family_id,
                _orphan_ledger_condition(Transaction.ledger_id, valid_ledger_ids),
            )
            .all()
        )
        transactions = []
        for t in orphan_txns:
            transactions.append(
                {
                    'id': t.id,
                    'position_name': t.position_name or '未知资产',
                    # txn_type 保持后端原始枚举值（buy/sell/dividend…），翻译交给前端
                    'txn_type': t.txn_type,
                    'amount': Money.cents_to_yuan(t.amount),
                    # 纯日期（YYYY-MM-DD），不带时间
                    'confirm_date': t.confirm_date.isoformat()[:10] if t.confirm_date else None,
                }
            )

        return jsonify(
            {
                'data': {
                    'positions': positions,
                    'assets': assets,
                    'transactions': transactions,
                    'summary': {
                        'position_count': len(positions),
                        'asset_count': len(assets),
                        'transaction_count': len(transactions),
                        'total_market_value': Money.cents_to_yuan(position_mv_cents + asset_amount_cents),
                    },
                },
                'message': 'ok',
            }
        )


@ledgers_bp.post('/orphan/migrations/')
def migrate_orphan_data():
    """将未归置数据（孤儿持仓/资产/交易）归入指定账户"""
    data = request.get_json() or {}
    target_id = data.get('target_ledger_id')
    if not target_id:
        return jsonify({'data': None, 'message': '缺少 target_ledger_id'}), 400

    with get_db() as db:
        target = get_owned_or_404(db, Ledger, target_id)
        family_id = get_family_id()
        # 当前家庭全部账户 id 集合（孤儿判定基准）
        valid_ledger_ids = [lid for (lid,) in db.query(Ledger.id).filter(Ledger.family_id == family_id).all()]
        orphan_cond = _orphan_ledger_condition(Position.ledger_id, valid_ledger_ids)

        # 孤儿持仓 id 集合（供对应悬空交易归入使用）
        orphan_position_ids = [
            pid for (pid,) in db.query(Position.id).filter(Position.family_id == family_id, orphan_cond).all()
        ]

        try:
            # 归入孤儿持仓：更新 ledger_id 与 account_name 快照
            position_count = (
                db.query(Position)
                .filter(Position.family_id == family_id, orphan_cond)
                .update(
                    {Position.ledger_id: target.id, Position.account_name: target.name},
                    synchronize_session=False,
                )
            )
            # 归入孤儿持仓对应的悬空交易（position_id 命中孤儿持仓，且 ledger_id 悬空）
            transaction_count = (
                db.query(Transaction)
                .filter(
                    Transaction.family_id == family_id,
                    Transaction.position_id.in_(orphan_position_ids),
                    _orphan_ledger_condition(Transaction.ledger_id, valid_ledger_ids),
                )
                .update(
                    {Transaction.ledger_id: target.id, Transaction.account_name: target.name},
                    synchronize_session=False,
                )
            )
            # 归入孤儿资产
            asset_count = (
                db.query(Asset)
                .filter(Asset.family_id == family_id, _orphan_ledger_condition(Asset.ledger_id, valid_ledger_ids))
                .update(
                    {Asset.ledger_id: target.id, Asset.account_name: target.name},
                    synchronize_session=False,
                )
            )
            db.commit()
        except IntegrityError:
            # uq_positions_ledger_symbol 唯一约束冲突：归入导致目标账户出现同名持仓
            db.rollback()
            return jsonify({'data': None, 'message': '归入失败：目标账户已存在同名持仓，请选择其他账户'}), 400

        total = position_count + asset_count + transaction_count
        return jsonify(
            {
                'data': {
                    'position_count': position_count,
                    'asset_count': asset_count,
                    'transaction_count': transaction_count,
                    'total': total,
                },
                'message': f'已将 {total} 项未归置数据归入「{target.name}」',
            }
        )


@ledgers_bp.delete('/orphan/')
def delete_orphan_data():
    """清理所有未归置数据（孤儿持仓/资产/交易）"""
    with get_db() as db:
        family_id = get_family_id()
        valid_ledger_ids = [lid for (lid,) in db.query(Ledger.id).filter(Ledger.family_id == family_id).all()]
        orphan_cond = _orphan_ledger_condition(Position.ledger_id, valid_ledger_ids)

        orphan_position_ids = [
            pid for (pid,) in db.query(Position.id).filter(Position.family_id == family_id, orphan_cond).all()
        ]

        # 先删交易：position 命中孤儿持仓 或 ledger_id 悬空
        transaction_count = (
            db.query(Transaction)
            .filter(
                Transaction.family_id == family_id,
                or_(
                    Transaction.position_id.in_(orphan_position_ids),
                    _orphan_ledger_condition(Transaction.ledger_id, valid_ledger_ids),
                ),
            )
            .delete(synchronize_session=False)
        )
        # 再删孤儿持仓
        position_count = (
            db.query(Position).filter(Position.family_id == family_id, orphan_cond).delete(synchronize_session=False)
        )
        # 最后删孤儿资产
        asset_count = (
            db.query(Asset)
            .filter(Asset.family_id == family_id, _orphan_ledger_condition(Asset.ledger_id, valid_ledger_ids))
            .delete(synchronize_session=False)
        )
        db.commit()

        return jsonify(
            {
                'data': {
                    'position_count': position_count,
                    'asset_count': asset_count,
                    'transaction_count': transaction_count,
                },
                'message': f'已清理 {position_count + asset_count + transaction_count} 项未归置数据',
            }
        )
