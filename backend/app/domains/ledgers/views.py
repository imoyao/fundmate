# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 10:56
# File : views.py
"""资金容器 API — 基本 CRUD"""

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.database import get_db
from app.domains.ledgers.models import Ledger

ledgers_bp = APIBlueprint('ledgers', __name__, url_prefix='/api/ledgers')


@ledgers_bp.get('/')
def list_ledgers():
    with get_db() as db:
        ledgers = db.query(Ledger).order_by(Ledger.name).all()
        data = list()
        for leg in ledgers:
            ledger = {
                'id': leg.id,
                'name': leg.name,
                'ledger_type': leg.ledger_type,
                'currency': leg.currency,
                'notes': leg.notes,
                'default_allocation': leg.default_allocation,
            }
            data.append(ledger)

        return jsonify({'data': data, 'message': 'ok'})


@ledgers_bp.post('/')
def create_ledger():
    data = request.get_json()
    if not data or 'name' not in data or not data['name'].strip():
        abort(400, '名称不能为空')
    with get_db() as db:
        ledger = Ledger(
            name=data['name'],
            ledger_type=data.get('ledger_type', 'general'),
            currency=data.get('currency', 'CNY'),
            notes=data.get('notes', ''),
            default_allocation=data.get('default_allocation', 'longterm'),
        )
        db.add(ledger)
        db.commit()
        db.refresh(ledger)
        return jsonify(
            {
                'data': {
                    'id': ledger.id,
                    'name': ledger.name,
                    'ledger_type': ledger.ledger_type,
                    'default_allocation': ledger.default_allocation,
                },
                'message': 'ok',
            }
        )


@ledgers_bp.delete('/<int:id>/')
def delete_ledger(id):
    with get_db() as db:
        ledger = db.query(Ledger).get(id)
        if not ledger:
            abort(404, '账本不存在')
        db.delete(ledger)
        db.commit()
        return jsonify({'message': 'ok', 'data': None})
