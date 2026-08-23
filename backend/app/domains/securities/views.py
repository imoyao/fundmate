from apiflask import APIBlueprint
from flask import jsonify, request
from sqlalchemy import or_

from app.core.database import get_db
from app.core.symbol_utils import get_normalizer
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security

bp = APIBlueprint('securities', __name__, url_prefix='/api/securities')


@bp.get('/<symbol>/price-range/')
def get_price_range(symbol: str):
    """指定交易日价格区间（#948）：供手动记账回填默认价与区间校验。

    ?date=YYYY-MM-DD 缺省取最近一个有行情的交易日（≤该日）。
    无行情数据返回 data=null，前端保持手输不阻塞。
    """
    raw = request.args.get('date')
    target = None
    if raw:
        try:
            from datetime import date as _date

            target = _date.fromisoformat(raw)
        except ValueError:
            return jsonify({'data': None, 'message': '日期格式错误，应为 YYYY-MM-DD'}), 400

    with get_db() as db:
        q = db.query(
            PriceHistory.trade_date,
            PriceHistory.low,
            PriceHistory.high,
            PriceHistory.close,
        ).filter(PriceHistory.symbol == symbol)
        if target is not None:
            q = q.filter(PriceHistory.trade_date <= target)
        row = q.order_by(PriceHistory.trade_date.desc()).first()
        if not row or row.low is None or row.high is None:
            return jsonify({'data': None, 'message': 'ok'})
        return jsonify(
            {
                'data': {
                    'symbol': symbol,
                    'date': row.trade_date.isoformat(),
                    'low': float(row.low),
                    'high': float(row.high),
                    'close': float(row.close) if row.close is not None else None,
                },
                'message': 'ok',
            }
        )


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
