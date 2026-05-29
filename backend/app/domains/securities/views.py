from apiflask import APIBlueprint
from flask import jsonify, request
from sqlalchemy import or_

from app.core.database import get_db
from app.core.symbol_utils import get_normalizer
from app.domains.securities.models import Security

bp = APIBlueprint('securities', __name__, url_prefix='/api/securities')


@bp.get('/search/')
def search_securities():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'data': [], 'message': 'ok'})

    normalizer = get_normalizer()
    # 尝试标准化为精确代码
    normalized_q, _, _ = normalizer.normalize(q)

    with get_db() as db:
        query = db.query(Security)
        conditions = []

        # 如果有标准化后的精确代码，加入精确匹配
        if normalized_q:
            conditions.append(Security.symbol == normalized_q)

        # 始终加入模糊匹配（代码和名称）
        conditions.append(Security.symbol.ilike(f'%{q}%'))
        conditions.append(Security.name.ilike(f'%{q}%'))

        secs = query.filter(or_(*conditions)).limit(20).all()

        result = []
        for s in secs:
            result.append(
                {
                    'symbol': s.symbol,
                    'display_symbol': normalizer.to_display_code(s.symbol),
                    'name': s.name,
                    'market': s.market,
                    'type': s.type,
                }
            )
        return jsonify({'data': result, 'message': 'ok'})
