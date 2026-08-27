# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/7 21:19
# File : views.py
"""持仓相关 API."""

from apiflask import APIBlueprint
from flask import abort, jsonify, request
from loguru import logger

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
from app.services.trade_rules import TradeService

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
    d['avg_price'] = Money.cents_to_yuan(p.avg_price)
    d['current_price'] = Money.cents_to_yuan(p.current_price)
    # 市值/盈亏：复用 Money.multiply_price_quantity（与 portfolios/ledger_service 同口径，本币直算）。
    # 汇率折算仅存在于 summary 聚合口径（total_*_cny）；单条明细与 current_price 保持本币一致。
    d['market_value'] = Money.cents_to_yuan(Money.multiply_price_quantity(p.current_price, p.quantity))
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
                        'avg_price': Money.cents_to_yuan(p.avg_price),
                        'currency': p.currency,
                        'current_price': Money.cents_to_yuan(p.current_price),
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
                    'trade_date': display_date.isoformat() if display_date else None,
                    'txn_type': t.txn_type,
                    'quantity': Money.min_unit_to_shares(t.quantity),
                    'price': Money.cents_to_yuan(t.price),
                    'amount': Money.cents_to_yuan(t.amount),
                    'fee': Money.cents_to_yuan(t.fee),
                    'notes': t.notes,
                    'asset_type': t.asset_type,
                }
            )
        return jsonify({'data': data, 'message': 'ok'})


@bp.post('/')
def create_position():
    """新增/修改持仓，并写入交易流水.

    支持的操作类型:
    - buy: 买入（创建新持仓 + 买入流水）
    - sell: 卖出（减少持仓数量 + 卖出流水）
    - dividend: 分红（不改变持仓数量 + 分红流水）
    - deposit: 存入（增加持仓 + 存入流水）
    - withdraw: 取出（减少持仓 + 取出流水）
    """
    json_data = parse_body(PositionCreate)
    data = json_data.model_dump()
    data['family_id'] = get_family_id()
    op_type = data.get('op_type', 'buy')
    with get_db() as db:
        try:
            if op_type in ('sell', 'withdraw'):
                position = PositionService.process_sell_or_withdraw(db, data)
            elif op_type == 'dividend':
                data['dividend_amount'] = data.get('avg_price', 0)
                position = PositionService.process_dividend(db, data)
            elif op_type in ('buy', 'deposit'):
                try:
                    position = PositionService.process_buy_or_deposit(db, data)
                except Exception as e:
                    logger.exception('买入/加仓处理失败: %s', e)
                    return jsonify({'message': str(e), 'data': None}), 400
            else:
                abort(400, description=f'不支持的操作类型: {op_type}')
        except ValueError as e:
            logger.exception('持仓操作业务校验失败: %s', e)
            # 业务逻辑错误，返回明确提示
            return jsonify({'message': str(e), 'data': None}), 400
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
                value = Money.yuan_to_cents(value)
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
