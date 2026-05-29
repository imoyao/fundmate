# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11 19:33
# File : views.py
from apiflask import APIBlueprint
from flask import jsonify, request

from app.core.database import get_db
from app.domains.funds.models import Fund, Manager

bp = APIBlueprint('funds', __name__, url_prefix='/api/funds')


@bp.get('/search/')
def search_funds():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'data': [], 'message': 'ok'})
    with get_db() as db:
        funds = (
            db.query(Fund)
            .filter((Fund.fund_code.ilike(f'%{q}%')) | (Fund.name.ilike(f'%{q}%')) | (Fund.pinyin_abbr.ilike(f'%{q}%')))
            .limit(20)
            .all()
        )
        result = [
            {
                'code': f.fund_code,
                'name': f.name,
                'type': 'fund',
                'subscription_rate': 0.015,
            }
            for f in funds
        ]
        return jsonify({'data': result, 'message': 'ok'})


@bp.get('/managers/search/')
def search_managers():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'data': [], 'message': 'ok'})
    with get_db() as db:
        mgrs = db.query(Manager).filter(Manager.name.ilike(f'%{q}%')).limit(20).all()
        result = [{'code': m.mgr_code, 'name': m.name, 'type': m.mgr_type} for m in mgrs]
        return jsonify({'data': result, 'message': 'ok'})
