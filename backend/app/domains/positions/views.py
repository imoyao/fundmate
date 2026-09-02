# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/7 21:19
# File : views.py
"""持仓相关 API."""

from apiflask import APIBlueprint
from flask import abort, jsonify, request
from loguru import logger
from sqlalchemy.exc import IntegrityError

from app.core.auth import get_family_id, get_owned_or_404
from app.core.constants import ALLOCATION_LABELS, MARKET_LABELS, TYPE_LABELS
from app.core.database import get_db
from app.core.money import Money
from app.core.utils import paginate
from app.core.validation import parse_body
from app.domains.portfolios.models import Portfolio
from app.domains.positions.models import Position
from app.domains.positions.schemas import PositionCreate, PositionOut, PositionUpdate
from app.domains.transactions.models import Transaction
from app.services.position_service import PositionService
from app.services.position_valuation import market_value_cents
from app.services.price_range_service import resolve_security_price_range
from app.services.trade_rules import TradeService
from app.services.value_allocation_service import allocate_value

bp = APIBlueprint('positions', __name__, url_prefix='/api/positions/')


def enrich_position_dict(p: Position) -> dict:
    if not p.market:
        p.market = 'UNKNOWN'
    d = PositionOut.model_validate(p).model_dump()
    d['type_label'] = TYPE_LABELS.get(p.asset_type, p.asset_type)
    d['market_label'] = MARKET_LABELS.get(p.market, p.market)
    d['allocation_label'] = ALLOCATION_LABELS.get(p.allocation, p.allocation or '未分类')
    # 转换内部单位到展示单位
    d['quantity'] = Money.min_unit_to_shares(p.quantity)
    d['avg_price'] = Money.price_units_to_yuan(p.avg_price)
    d['current_price'] = Money.price_units_to_yuan(p.current_price)
    d['market_value_override'] = (
        Money.cents_to_yuan(p.market_value_override) if p.market_value_override is not None else None
    )
    # 市值/盈亏（#1174 收口）：委托唯一口径 position_valuation.market_value_cents。
    # 本币直算——汇率折算仅存在于 summary 聚合口径（total_*_cny）；单条明细与 current_price 保持本币一致。
    d['market_value'] = Money.cents_to_yuan(market_value_cents(p))
    d['pnl'] = (
        Money.cents_to_yuan(Money.multiply_price_quantity(p.current_price - p.avg_price, p.quantity))
        if p.avg_price
        else 0.0
    )
    return d


@bp.get('/')
def list_positions():
    """获取所有持仓记录，支持分页和按账户分组.

    过滤参数:
      ledger_id: 按关联账户ID精确过滤；传字符串 'null' 表示仅查未归档持仓(ledger_id IS NULL)。
    """
    group_by = request.args.get('group_by', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    ledger_id_raw = request.args.get('ledger_id', '')

    with get_db() as db:
        query = db.query(Position).filter(Position.family_id == get_family_id())
        # 未归档过滤：ledger_id 显式传 'null' 时仅返回未绑定账户的持仓
        if ledger_id_raw == 'null':
            query = query.filter(Position.ledger_id.is_(None))
        elif ledger_id_raw:
            query = query.filter(Position.ledger_id == int(ledger_id_raw))
        query = query.order_by(Position.updated_at.desc())

        if group_by == 'account':
            positions = query.all()
            result = {}

            # 一次性查询所有持仓的首次买入确认日（性能优化）
            pos_ids = [p.id for p in positions]
            first_buy_dates = {}
            if pos_ids:
                from sqlalchemy import func

                buy_dates_query = (
                    db.query(Transaction.position_id, func.min(Transaction.confirm_date).label('confirm_date'))
                    .filter(
                        Transaction.position_id.in_(pos_ids),
                        Transaction.txn_type.in_(['buy', 'deposit']),
                    )
                    .group_by(Transaction.position_id)
                    .all()
                )
                first_buy_dates = {row.position_id: row.confirm_date for row in buy_dates_query}

            for p in positions:
                account = p.account_name
                if account not in result:
                    result[account] = []

                # 获取首次买入确认日
                buy_confirm = first_buy_dates.get(p.id)
                if buy_confirm is None:
                    buy_confirm = p.confirm_date  # 兼容无交易记录的回退

                result[account].append(
                    {
                        'id': p.id,
                        'symbol': p.symbol,
                        'name': p.name,
                        'type': p.asset_type,
                        'type_label': TYPE_LABELS.get(p.asset_type, p.asset_type),
                        'market': p.market,
                        'market_label': MARKET_LABELS.get(p.market, p.market),
                        'allocation': p.allocation,
                        'allocation_label': ALLOCATION_LABELS.get(p.allocation, p.allocation or '未分类'),
                        'quantity': Money.min_unit_to_shares(p.quantity),
                        'avg_price': Money.price_units_to_yuan(p.avg_price),
                        'currency': p.currency,
                        'current_price': Money.price_units_to_yuan(p.current_price),
                        'confirm_date': buy_confirm.isoformat() if buy_confirm else None,
                        'ledger_id': p.ledger_id,
                    }
                )
            return jsonify({'data': result, 'message': 'ok'})

        # 分页模式保持不变
        items, total = paginate(query, page=page, per_page=per_page)
        data = [enrich_position_dict(p) for p in items]
        return jsonify({'data': data, 'total': total, 'page': page, 'per_page': per_page, 'message': 'ok'})


@bp.get('/<int:id>/transactions/')
def get_position_transactions(id: int):
    with get_db() as db:
        position = get_owned_or_404(db, Position, id)
        if not position:
            abort(404, '持仓不存在')

        # 优先用 position_id，若为空则用 symbol + account_name。
        # 排序：确认日倒序（NULL 沉底）+ 创建时间倒序——用户最关注最近交易（#982 排查修正，
        # 原 asc() 让最早的 2023 年记录排在最前）
        if position.id and db.query(Transaction).filter(Transaction.position_id == position.id).first() is not None:
            transactions = (
                db.query(Transaction)
                .filter(Transaction.position_id == position.id)
                .order_by(
                    Transaction.confirm_date.desc().nullslast(),
                    Transaction.created_at.desc(),
                    Transaction.id.desc(),  # 同刻插入的最终 tie-breaker，保证排序确定
                )
                .all()
            )
        else:
            transactions = (
                db.query(Transaction)
                .filter(Transaction.symbol == position.symbol, Transaction.account_name == position.account_name)
                .order_by(
                    Transaction.confirm_date.desc().nullslast(),
                    Transaction.created_at.desc(),
                    Transaction.id.desc(),  # 同刻插入的最终 tie-breaker，保证排序确定
                )
                .all()
            )

        data = []
        for t in transactions:
            # 优先使用 confirm_date，为空时回退 trade_date
            display_date = t.confirm_date or t.trade_date
            data.append(
                {
                    'id': t.id,
                    'ledger_id': t.ledger_id,
                    'symbol': t.symbol,
                    'trade_date': display_date.isoformat() if display_date else None,
                    'txn_type': t.txn_type,
                    'quantity': Money.min_unit_to_shares(t.quantity),
                    'price': Money.price_units_to_yuan(t.price),
                    'amount': Money.cents_to_yuan(t.amount),
                    'fee': Money.cents_to_yuan(t.fee),
                    'notes': t.notes,
                    'asset_type': t.asset_type,
                }
            )
        return jsonify({'data': data, 'message': 'ok'})


_PRICE_RANGE_OP_TYPES = {'buy', 'sell', 'deposit', 'withdraw'}


def _validate_price_within_range(data: dict) -> None:
    """后端成交价区间拦截（#948 续）：证券类成交价须落在交易日 [low, high] 内。

    作为权威拦截（前端校验之外的最终防线）：本地 PriceHistory 优先，缺失时启用
    实时兜底（腾讯财经当日 / akshare 历史日）取真实区间，确保缺少本地行情的标的
    （如隆基）也能拦住明显异常的成交价。任一来源不可达则降级为放行，不会误拦。
    与前端 getSecurityPriceRange + SellForm/BuyForm 的区间校验保持一致。
    """
    op_type = data.get('op_type')
    if op_type not in _PRICE_RANGE_OP_TYPES:
        return
    symbol = data.get('symbol')
    avg_price = data.get('avg_price')
    trade_date = data.get('trade_date')
    if not symbol or avg_price is None or not trade_date:
        return
    rng = resolve_security_price_range(symbol, trade_date, use_live_fallback=True)
    if not rng:
        return
    low, high = rng['low'], rng['high']
    if avg_price < low or avg_price > high:
        raise ValueError(f'价格 {avg_price} 超出 {rng["date"]} 交易日区间（{low} ~ {high}），请核对后重新提交')


@bp.post('/')
def create_position():
    """新增/修改持仓，并写入交易流水.

    支持的操作类型:
    - buy: 买入（创建新持仓 + 买入流水）
    - sell: 卖出（减少持仓数量 + 卖出流水）
    - dividend: 分红（不改变持仓数量 + 分红流水）
    - dividend_reinvest: 红利再投资（分红现金流水 + 按净值申购流水，份额增加）
    - deposit: 存入（增加持仓 + 存入流水）
    - withdraw: 取出（减少持仓 + 取出流水）
    """
    json_data = parse_body(PositionCreate)
    data = json_data.model_dump()
    _validate_price_within_range(data)
    data['family_id'] = get_family_id()
    op_type = data.get('op_type', 'buy')
    # #863 P0-3：手动记账 type 归一——货基代码被误标普通 fund 时自动修正为 money_fund
    # （前端 resolveFundAssetType 已兜底；后端归一防绕过前端直接调 API 的脏数据）
    if op_type in ('buy', 'deposit') and data.get('asset_type') == 'fund' and data.get('symbol'):
        try:
            from app.services.fund_utils import is_money_fund_symbol

            if is_money_fund_symbol(str(data['symbol'])):
                logger.info('货基 type 归一：symbol=%s asset_type fund -> money_fund', data['symbol'])
                data['asset_type'] = 'money_fund'
        except Exception:
            logger.warning('货基 type 归一查询失败（market 名录不可达），保留原类型', exc_info=True)
    with get_db() as db:
        try:
            if op_type in ('sell', 'withdraw'):
                position = PositionService.process_sell_or_withdraw(db, data)
            elif op_type == 'dividend':
                data['dividend_amount'] = data.get('avg_price', 0)
                position = PositionService.process_dividend(db, data)
            elif op_type == 'dividend_reinvest':
                data['dividend_amount'] = data.get('dividend_amount', data.get('amount', data.get('avg_price', 0)))
                data['nav'] = data.get('nav', data.get('avg_price', 0))
                position = PositionService.process_dividend_reinvest(db, data)
            elif op_type == 'split':
                position = PositionService.process_orphan_split(db, data)
            elif op_type in ('buy', 'deposit'):
                try:
                    # #1233 决策 5：记一笔（手动记账）对货基/逆回购也建持仓，流水关联持仓；
                    # 交易导入路径不传该参数，保持「只记孤儿资金流水」的既有行为。
                    position = PositionService.process_buy_or_deposit(db, data, force_create_position=True)
                except IntegrityError:
                    # 唯一约束冲突（幂等键重复）→ 上抛给外层 except IntegrityError → 409 幂等拦截
                    raise
                except Exception as e:
                    logger.exception('买入/加仓处理失败: %s', e)
                    return jsonify({'message': str(e), 'data': None}), 400
            else:
                abort(400, description=f'不支持的操作类型: {op_type}')
        except ValueError as e:
            logger.exception('持仓操作业务校验失败: %s', e)
            # 业务逻辑错误，返回明确提示
            return jsonify({'message': str(e), 'data': None}), 400
        except IntegrityError as e:
            # 唯一约束冲突：幂等键(import_hash)重复 → 视为「请勿重复提交 / 已迁移」。
            # 典型场景：
            #   - 手动记账：网络超时后客户端用同一幂等键重发，服务端已落库，重发被唯一约束拦截；
            #   - 探市迁移：重跑迁移同一持有命中唯一约束 → 跳过，避免重复持仓。
            # 用 409 Conflict 而非 400，便于调用方（迁移逻辑）按状态码识别「已存在」并跳过。
            db.rollback()
            logger.warning('持仓操作唯一约束冲突（疑似重复提交/重复迁移）: %s', e)
            return jsonify({'message': '该笔交易已记录，请勿重复提交', 'data': None}), 409
        except Exception:
            # ⭐ 捕获所有未预期的异常，打印完整堆栈
            logger.exception('持仓操作未预期异常')
            db.rollback()
            abort(500, description='服务器内部错误，请稍后重试')

        if position is None:
            db.commit()  # 清仓时需要提交交易流水
            return jsonify({'message': '持仓已清空', 'data': None})
        wrap_position = enrich_position_dict(position)
        db.commit()  # ⭐ 显式提交事务
        return jsonify({'data': wrap_position, 'message': 'ok'})


@bp.patch('/<int:id>/')
def update_position(id):
    json_data = parse_body(PositionUpdate)
    with get_db() as db:
        position = get_owned_or_404(db, Position, id)
        if not position:
            abort(404, description='Position not found')

        update_data = json_data.model_dump(exclude_unset=True)

        # 持仓所属组合改派：校验目标组合存在且归属本家庭（禁止跨家庭串仓）
        if 'portfolio_id' in update_data and update_data['portfolio_id'] is not None:
            target = (
                db.query(Portfolio)
                .filter(Portfolio.id == update_data['portfolio_id'], Portfolio.family_id == get_family_id())
                .first()
            )
            if not target:
                abort(404, description='目标组合不存在或无权访问')

        for field, value in update_data.items():
            # 金额/份额字段转换为内部单位
            if field in ('current_price', 'avg_price'):
                value = Money.yuan_to_price_units(value)
            elif field == 'quantity':
                value = Money.shares_to_min_unit(value)
            setattr(position, field, value)

        db.commit()
        db.refresh(position)
        return jsonify({'data': enrich_position_dict(position), 'message': 'ok'})


@bp.delete('/<int:id>/')
def delete_position(id):
    """删除某条持仓记录."""
    delete_txns = request.args.get('delete_transactions', 'false').lower() == 'true'
    with get_db() as db:
        position = get_owned_or_404(db, Position, id)
        if not position:
            abort(404, description='Position not found')

        if delete_txns:
            # 优先使用 position_id 删除
            deleted = db.query(Transaction).filter(Transaction.position_id == id).delete()
            if deleted == 0:
                # 兜底：无 position_id 时用 symbol + account_name 匹配
                db.query(Transaction).filter(
                    Transaction.symbol == position.symbol, Transaction.account_name == position.account_name
                ).delete()

        db.delete(position)
        db.commit()
        return jsonify({'message': 'ok', 'data': None})


@bp.post('/validate/')
def validate_trade_order():
    data = request.get_json()
    symbol = data.get('symbol')
    market = data.get('market', 'CN_A')
    asset_type = data.get('type')
    current_hold = data.get('current_hold', 0)
    order_qty = data.get('order_qty', 0)
    op_type = data.get('op_type', 'buy')

    # 🔥 核心：一行代码调用你封装好的 TradeService
    result = TradeService.validate_transaction(symbol, market, asset_type, current_hold, order_qty, op_type)

    return jsonify(result)


@bp.post('/allocate-value/')
def allocate_position_value():
    """按占比批量更新某产品跨账户总价（P1-4）。

    同一产品分散在多个账户时，只需录入一次产品维度总价，系统按各账户当前市值占比
    自动分摊写入每笔持仓的 ``market_value_override``（整数分，尾差归占比最大一笔）。
    典型场景：投顾组合 / 银行理财只有组合级估值、无逐笔净值。
    """
    from app.domains.positions.schemas import AllocateValueRequest

    data = parse_body(AllocateValueRequest).model_dump()
    with get_db() as db:
        try:
            result = allocate_value(
                db,
                get_family_id(),
                data['symbol'],
                data['total_value'],
                as_of=data.get('as_of'),
                ledger_id=data.get('ledger_id'),
            )
        except ValueError as e:
            logger.warning('按占比分摊失败: %s', e)
            return jsonify({'message': str(e), 'data': None}), 400
        db.commit()
        return jsonify({'data': result, 'message': 'ok'})
