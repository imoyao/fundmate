# -*- coding: utf-8 -*-
"""个股估值分位只读端点（#2944）。

只做 HTTP 编排（``conventions.md`` §2.2）：解析 ``?codes=`` → 服务层取数 → 统一信封。
``codes`` 省略时由服务层按「当前持仓 ∪ 自选」的股票取，禁止全市场扫描。
"""

from apiflask import APIBlueprint
from flask import jsonify, request

from app.core.auth import get_family_id
from app.core.database import get_db
from app.services.stock_valuation_service import get_stock_valuations

bp = APIBlueprint('stocks', __name__, url_prefix='/api/stocks')


@bp.get('/valuation/')
def get_stock_valuation():
    """个股 PE/PB 当前值与近 5 年历史分位（Wind 股票域只读，不落库）。

    ``?codes=600519.SH,000858.SZ`` 显式指定；省略则取用户触达范围内的股票。
    无数据 / 上游不可用时 ``data.items`` 为 ``[]`` 且 ``degraded=true``，
    前端据此显示「暂无数据」，不显示 0（「没数」与「0 分位」是两件事）。
    """
    try:
        with get_db() as db:
            data = get_stock_valuations(db, get_family_id(), request.args.get('codes'))
    except ValueError as exc:
        return jsonify({'data': {}, 'message': str(exc), 'error_code': 1001}), 400
    return jsonify({'data': data, 'message': 'ok'})
