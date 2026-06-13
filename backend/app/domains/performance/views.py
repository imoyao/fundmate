# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/12 19:29
# File : views.py
# app/domains/performance/views.py

from apiflask import APIBlueprint
from flask import abort, jsonify
from loguru import logger

from app.core.database import get_db
from app.domains.performance.schemas import XirrRequest
from app.services.performance import calculate_portfolio_xirr, calculate_position_xirr

bp = APIBlueprint('performance', __name__, url_prefix='/api/performance')


@bp.get('/xirr/')
@bp.input(XirrRequest, location='query')
def get_xirr(query_data: XirrRequest):
    """查询年化收益率"""
    scope = query_data.scope
    position_id = query_data.position_id

    with get_db() as db:
        try:
            if scope == 'position':
                if not position_id:
                    abort(400, '缺少 position_id 参数')
                result = calculate_position_xirr(db, position_id)
            else:
                result = calculate_portfolio_xirr(db)
                logger.info(f'组合 XIRR 计算完成: {result}')
        except ValueError as e:
            abort(404, str(e))
        except Exception as e:
            logger.exception('年化收益率计算异常')
            abort(500, f'年化收益率计算失败，请稍后重试: {str(e)}')

    return jsonify({'data': result, 'message': 'ok'})
