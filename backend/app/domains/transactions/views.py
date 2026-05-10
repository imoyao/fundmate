# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/10 8:22
# File : views.py

"""交易流水相关 API."""

from datetime import date, timedelta

from apiflask import APIBlueprint
from flask import jsonify, request

from app.core.database import get_db
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction

bp = APIBlueprint('transactions', __name__, url_prefix='/api/transactions')


@bp.get('/')
def list_transactions():
    """获取交易流水列表，支持多维筛选与分页."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    with get_db() as db:
        query = db.query(Transaction)

        # 筛选：操作类型
        op_type = request.args.get('type')
        if op_type:
            query = query.filter(Transaction.type == op_type)

        # 筛选：时间范围
        time_range = request.args.get('time_range')
        if time_range == '1m':
            query = query.filter(Transaction.trade_date >= date.today() - timedelta(days=30))
        elif time_range == '3m':
            query = query.filter(Transaction.trade_date >= date.today() - timedelta(days=90))
        elif time_range == '6m':
            query = query.filter(Transaction.trade_date >= date.today() - timedelta(days=180))
        elif time_range == '1y':
            query = query.filter(Transaction.trade_date >= date.today() - timedelta(days=365))
        elif time_range == 'custom':
            start = request.args.get('start_date')
            end = request.args.get('end_date')
            if start:
                query = query.filter(Transaction.trade_date >= start)
            if end:
                query = query.filter(Transaction.trade_date <= end)

        # 筛选：交易状态
        status = request.args.get('status')
        if status:
            query = query.filter(Transaction.status == status)

        # 筛选：资产类型（通过 positions 表关联）
        asset_type = request.args.get('asset_type')
        if asset_type:
            position_ids = db.query(Position.id).filter(Position.type == asset_type).all()
            pids = [p.id for p in position_ids]
            query = query.filter(Transaction.position_id.in_(pids))

        # 排序与分页
        query = query.order_by(Transaction.created_at.desc())
        total = query.count()
        transactions = query.offset((page - 1) * per_page).limit(per_page).all()

        results = []
        for t in transactions:
            results.append(
                {
                    'id': t.id,
                    'position_id': t.position_id,
                    'position_name': t.position_name or '未知资产',
                    'type': t.type,
                    'trade_date': t.trade_date.isoformat() if t.trade_date else None,
                    'quantity': t.quantity,
                    'price': t.price,
                    'fee': t.fee,
                    'amount': t.amount,
                    'status': t.status,
                    'account_name': t.account_name or '未知账户',
                    'notes': t.notes,
                    'created_at': t.created_at.isoformat() if t.created_at else None,
                }
            )

        return jsonify({'data': results, 'total': total, 'page': page, 'per_page': per_page, 'message': 'ok'})
