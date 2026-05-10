# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/7 21:19
# File : views.py
"""持仓相关 API."""

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.database import get_db
from app.domains.positions.models import Position
from app.domains.positions.schemas import PositionCreate, PositionOut, PositionUpdate
from app.domains.transactions.models import Transaction
from backend.app.core.enums import ALLOCATION_LABELS, MARKET_LABELS, TYPE_LABELS

bp = APIBlueprint('positions', __name__, url_prefix='/api/positions')


@bp.get('/')
def list_positions():
    """获取所有持仓记录，支持分页和按账户分组."""
    group_by = request.args.get('group_by', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    with get_db() as db:
        query = db.query(Position).order_by(Position.updated_at.desc())

        if group_by == 'account':
            positions = query.all()
            result = {}
            for p in positions:
                account = p.account_name
                if account not in result:
                    result[account] = []
                result[account].append(
                    {
                        'id': p.id,
                        'symbol': p.symbol,
                        'name': p.name,
                        'type': p.type,
                        'type_label': TYPE_LABELS.get(p.type, p.type),
                        'market': p.market,
                        'market_label': MARKET_LABELS.get(p.market, p.market),
                        'allocation': p.allocation,
                        'allocation_label': ALLOCATION_LABELS.get(p.allocation, p.allocation or '未分类'),
                        'quantity': p.quantity,
                        'avg_price': p.avg_price,
                        'currency': p.currency,
                        'current_price': p.current_price,
                    }
                )
            return jsonify({'data': result, 'message': 'ok'})

        total = query.count()

        items = query.offset((page - 1) * per_page).limit(per_page).all()
        data = []
        for p in items:
            pd = PositionOut.model_validate(p).model_dump()
            pd['type_label'] = TYPE_LABELS.get(p.type, p.type)
            pd['market_label'] = MARKET_LABELS.get(p.market, p.market)
            pd['allocation_label'] = ALLOCATION_LABELS.get(p.allocation, p.allocation or '未分类')
            data.append(pd)
        return jsonify({'data': data, 'total': total, 'page': page, 'per_page': per_page, 'message': 'ok'})


@bp.post('/')
@bp.input(PositionCreate)
def create_position(json_data):
    """新增/修改持仓，并写入交易流水.

    支持的操作类型:
    - buy: 买入（创建新持仓 + 买入流水）
    - sell: 卖出（减少持仓数量 + 卖出流水）
    - dividend: 分红（不改变持仓数量 + 分红流水）
    - deposit: 存入（增加持仓 + 存入流水）
    - withdraw: 取出（减少持仓 + 取出流水）
    """
    with get_db() as db:
        op_type = getattr(json_data, 'op_type', 'buy') or 'buy'

        # --- 卖出 / 分红 / 取出：必须提供 position_id ---
        if op_type in ('sell', 'dividend', 'withdraw'):
            position_id = getattr(json_data, 'position_id', None)
            if not position_id:
                abort(400, description=f'{op_type} 操作必须提供 position_id')

            existing = db.query(Position).filter_by(id=position_id).first()
            if not existing:
                abort(404, description='指定的持仓不存在，无法操作')

            # --- 卖出 ---
            if op_type == 'sell':
                sell_qty = json_data.quantity
                if sell_qty <= 0:
                    abort(400, description='卖出数量必须大于 0')
                if existing.quantity < sell_qty:
                    abort(400, description=f'持仓数量不足：当前持有 {existing.quantity}，拟卖出 {sell_qty}')
                # 更新持仓数量
                existing.quantity -= sell_qty
                if existing.quantity == 0:
                    db.delete(existing)
                    db.flush()
                    db.add(
                        Transaction(
                            position_id=position_id,
                            type='sell',
                            trade_date=json_data.purchase_date,
                            quantity=sell_qty,
                            price=json_data.avg_price,
                            fee=json_data.fee or 0.0,
                            amount=sell_qty * json_data.avg_price,
                            status='success',
                            position_name=existing.name,
                            account_name=existing.account_name,
                            notes=json_data.notes or '卖出',
                        )
                    )
                    db.commit()
                    return jsonify({'message': '持仓已清空', 'data': None})
                db.flush()

                # 写流水
                txn = Transaction(
                    position_id=position_id,
                    type='sell',
                    trade_date=json_data.purchase_date,
                    quantity=sell_qty,
                    price=json_data.avg_price,
                    fee=json_data.fee or 0.0,
                    amount=sell_qty * json_data.avg_price,
                    status='success',
                    position_name=existing.name,
                    account_name=existing.account_name,
                    notes=json_data.notes or '卖出',
                )
                db.add(txn)
                db.commit()
                return jsonify({'data': PositionOut.model_validate(existing).model_dump(), 'message': 'ok'})

            # --- 分红 ---
            elif op_type == 'dividend':
                txn = Transaction(
                    position_id=position_id,
                    type='dividend',
                    trade_date=json_data.purchase_date,
                    quantity=0,
                    price=0,
                    fee=0,
                    amount=json_data.avg_price,  # 分红金额暂存 avg_price
                    status='success',
                    position_name=existing.name,
                    account_name=existing.account_name,
                    notes=json_data.notes or '现金分红',
                )
                db.add(txn)
                db.commit()
                return jsonify({'data': PositionOut.model_validate(existing).model_dump(), 'message': 'ok'})

            # --- 取出 ---
            elif op_type == 'withdraw':
                withdraw_qty = json_data.quantity
                if withdraw_qty <= 0:
                    abort(400, description='取出数量必须大于 0')
                if existing.quantity < withdraw_qty:
                    abort(400, description=f'持仓数量不足：当前持有 {existing.quantity}，拟取出 {withdraw_qty}')

                existing.quantity -= withdraw_qty
                if existing.quantity == 0:
                    db.delete(existing)
                    db.flush()
                    db.add(
                        Transaction(
                            position_id=position_id,
                            type='withdraw',
                            trade_date=json_data.purchase_date,
                            quantity=withdraw_qty,
                            price=json_data.avg_price,
                            fee=json_data.fee or 0.0,
                            amount=withdraw_qty * json_data.avg_price,
                            status='success',
                            position_name=existing.name,
                            account_name=existing.account_name,
                            notes=json_data.notes or '取出',
                        )
                    )
                    db.commit()
                    return jsonify({'message': '持仓已清空', 'data': None})
                db.flush()

                txn = Transaction(
                    position_id=position_id,
                    type='withdraw',
                    trade_date=json_data.purchase_date,
                    quantity=withdraw_qty,
                    price=json_data.avg_price,
                    fee=json_data.fee or 0.0,
                    amount=withdraw_qty * json_data.avg_price,
                    status='success',
                    position_name=existing.name,
                    account_name=existing.account_name,
                    notes=json_data.notes or '取出',
                )
                db.add(txn)
                db.commit()
                return jsonify({'data': PositionOut.model_validate(existing).model_dump(), 'message': 'ok'})

        # --- 买入 / 存入（创建或追加）---
        # 同账户同 symbol 的买入/存入，自动合并
        if op_type in ('buy', 'deposit'):
            symbol = json_data.symbol
            account = json_data.account_name
            same = db.query(Position).filter_by(symbol=symbol, account_name=account).first()
            if same:
                # 累加数量，重算均价
                total_qty = same.quantity + json_data.quantity
                same.avg_price = (same.avg_price * same.quantity + json_data.avg_price * json_data.quantity) / total_qty
                same.quantity = total_qty
                same.current_price = json_data.avg_price
                db.flush()

                txn = Transaction(
                    position_id=same.id,
                    type=op_type,
                    trade_date=json_data.purchase_date,
                    quantity=json_data.quantity,
                    price=json_data.avg_price,
                    fee=json_data.fee or 0.0,
                    amount=json_data.quantity * json_data.avg_price,
                    status='success',
                    position_name=same.name,
                    account_name=same.account_name,
                    notes=json_data.notes or ('追加买入' if op_type == 'buy' else '追加存入'),
                )
                db.add(txn)
                db.commit()
                return jsonify({'data': PositionOut.model_validate(same).model_dump(), 'message': 'ok'})

        # 新买入或新存入（没有同账户同 symbol 的持仓）
        position_fields = json_data.model_dump(
            exclude={'fee', 'confirm_date', 'notes', 'op_type', 'position_id', 'isAfter15', 'interestRate'}
        )
        position = Position(**position_fields)
        position.current_price = position.avg_price
        db.add(position)
        # 先刷新，拿到 position.id
        db.flush()

        # 自动创建初始交易流水
        init_txn = Transaction(
            position_id=position.id,
            type=op_type if op_type in ('buy', 'deposit') else 'buy',
            trade_date=position.purchase_date,
            quantity=position.quantity,
            price=position.avg_price,
            fee=json_data.fee or 0.0,
            amount=position.quantity * position.avg_price,
            status='success',
            position_name=position.name,
            account_name=position.account_name,
            confirm_date=json_data.confirm_date,
            notes=json_data.notes or ('初始买入' if op_type == 'buy' else '存入'),
        )
        db.add(init_txn)
        db.commit()
        db.refresh(position)
        return jsonify({'data': PositionOut.model_validate(position).model_dump(), 'message': 'ok'})


@bp.patch('/<int:id>')
@bp.input(PositionUpdate)
@bp.output(PositionOut, status_code=200)
def update_position(p_id, json_data):
    """使用 PATCH 语义仅更新修改过的字段 (例如 current_price)."""
    with get_db() as db:
        position = db.query(Position).filter_by(id=p_id).first()
        if not position:
            abort(404, description='Position not found')

        # model_dump(exclude_unset=True) 仅返回用户实际发送的字段
        # 例如，用户仅提供 {"current_price": 160.5}，则返回 {"current_price": 160.5}
        update_data = json_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(position, field, value)

        db.commit()
        db.refresh(position)
        return position


@bp.delete('/<int:id>')
@bp.output({}, status_code=204)
def delete_position(id):
    """删除某条持仓记录."""
    with get_db() as db:
        position = db.query(Position).filter_by(id=id).first()
        if not position:
            abort(404, description='Position not found')
        db.delete(position)
        db.commit()
        return ''
