# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/29 23:11
# File : views.py
from datetime import datetime

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.utils import get_confirm_date

utils_bp = APIBlueprint('utils', __name__, url_prefix='/api/utils')


@utils_bp.get('/trading-days/<date>/')
def get_trading_day(date: str):
    """
    查询指定日期是否为交易日。
    如果非交易日（周末或节假日），返回 false。
    """
    from chinese_calendar import is_workday

    try:
        d = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError:
        abort(400, '日期格式错误，应为 YYYY-MM-DD')

    try:
        is_trading = is_workday(d)
    except Exception:
        # 如果计算失败，保守返回 false（避免错误指引）
        is_trading = False

    return jsonify({'data': {'date': date, 'is_trading_day': is_trading}, 'message': 'ok'})


@utils_bp.get('/fund-confirm-dates/')
def calc_fund_confirm_date():
    """
    计算场外基金的确认日。
    参数：
        trade_date: 购买日期 (YYYY-MM-DD)
        fund_type: 基金类型 (domestic / qdii)，默认 domestic
        is_after_15: 是否在15:00之后 (true/false)，默认 false
    """
    trade_date_str = request.args.get('trade_date', '')
    fund_type = request.args.get('fund_type', 'domestic')
    is_after_15 = request.args.get('is_after_15', 'false').lower() == 'true'

    try:
        trade_date = datetime.strptime(trade_date_str, '%Y-%m-%d').date()
    except ValueError:
        abort(400, '购买日期格式错误，应为 YYYY-MM-DD')

    try:
        confirm_date = get_confirm_date(trade_date, fund_type=fund_type, is_after_15=is_after_15)
        return jsonify({'data': confirm_date.isoformat(), 'message': 'ok'})
    except Exception as e:
        abort(400, f'确认日计算失败: {str(e)}')
