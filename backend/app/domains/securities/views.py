# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/11 19:32
# File : views.py
from apiflask import APIBlueprint
from flask import jsonify, request

from app.core.database import get_db
from app.domains.securities.models import Security

bp = APIBlueprint('securities', __name__, url_prefix='/api/securities')


@bp.get('/search/')
def search_securities():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'data': [], 'message': 'ok'})
    with get_db() as db:
        secs = (
            db.query(Security)
            .filter((Security.symbol.ilike(f'%{q}%')) | (Security.name.ilike(f'%{q}%')))
            .limit(20)
            .all()
        )
        result = [{'symbol': s.symbol, 'name': s.name, 'market': s.market, 'type': s.type} for s in secs]
        return jsonify({'data': result, 'message': 'ok'})
