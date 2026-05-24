# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/7 21:19
# File : views.py
"""持仓相关 API."""

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.database import get_db
from app.core.enums import ALLOCATION_LABELS, MARKET_LABELS, TYPE_LABELS
from app.core.utils import paginate
from app.domains.positions.models import Position
from app.domains.positions.schemas import PositionCreate, PositionOut, PositionUpdate
from app.services.position_service import PositionService

bp = APIBlueprint('positions', __name__, url_prefix='/api/positions')


def _enrich_position_dict(p: Position) -> dict:
    """为持仓对象生成附带标签的字典."""
    if not p.market:
        p.market = 'UNKNOWN'  # 兜底，防止验证错误
    d = PositionOut.model_validate(p).model_dump()
    d['type_label'] = TYPE_LABELS.get(p.asset_type, p.asset_type)
    d['market_label'] = MARKET_LABELS.get(p.market, p.market)
    d['allocation_label'] = ALLOCATION_LABELS.get(p.allocation, p.allocation or '未分类')
    return d


@bp.get('/')
def list_positions():
    """获取所有持仓记录，支持分页和按账户分组."""
    group_by = request.args.get('group_by', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    with get_db() as db:
        query = db.query(Position).order_by(Position.updated_at.desc())

        # 分组模式
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
                        'type': p.asset_type,
                        'type_label': TYPE_LABELS.get(p.asset_type, p.asset_type),
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

        # 分页模式
        items, total = paginate(query, page=page, per_page=per_page)
        data = [_enrich_position_dict(p) for p in items]
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
    data = json_data.model_dump()
    op_type = data.get('op_type', 'buy')

    with get_db() as db:
        try:
            if op_type in ('sell', 'withdraw'):
                position = PositionService.process_sell_or_withdraw(db, data)
            elif op_type == 'dividend':
                data['dividend_amount'] = data.get('avg_price', 0)
                position = PositionService.process_dividend(db, data)
            elif op_type in ('buy', 'deposit'):
                position = PositionService.process_buy_or_deposit(db, data)
            else:
                abort(400, description=f'不支持的操作类型: {op_type}')
        except ValueError as e:
            abort(400, description=str(e))

        if position is None:
            return jsonify({'message': '持仓已清空', 'data': None})
        wrap_position = _enrich_position_dict(position)
        return jsonify({'data': wrap_position, 'message': 'ok'})


@bp.patch('/<int:id>/')
@bp.input(PositionUpdate)
def update_position(id, json_data):
    """使用 PATCH 语义仅更新修改过的字段 (例如 current_price)."""
    with get_db() as db:
        position = db.query(Position).filter_by(id=id).first()
        if not position:
            abort(404, description='Position not found')

        # model_dump(exclude_unset=True) 仅返回用户实际发送的字段
        # 例如，用户仅提供 {"current_price": 160.5}，则返回 {"current_price": 160.5}
        update_data = json_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(position, field, value)

        db.commit()
        db.refresh(position)
        return jsonify({'data': _enrich_position_dict(position), 'message': 'ok'})


@bp.delete('/<int:id>/')
def delete_position(id):
    """删除某条持仓记录."""
    with get_db() as db:
        position = db.query(Position).filter_by(id=id).first()
        if not position:
            abort(404, description='Position not found')
        db.delete(position)
        db.commit()
        return jsonify({'message': 'ok', 'data': None})
