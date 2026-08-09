# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/7 21:52
# File : views.py
# backend/app/api/views.py

"""首页仪表盘聚合数据 API."""

from apiflask import APIBlueprint
from flask import jsonify, request

from app.core.auth import get_family_id
from app.core.database import get_db
from app.services.summary_service import (
    get_account_groups,
    get_distributions,
    get_position_groups,
    get_sankey_data,
    get_summary_data,
)

bp = APIBlueprint('summary', __name__, url_prefix='/api')


@bp.get('/summary/')
def summary():
    """返回首页仪表盘聚合数据"""
    try:
        with get_db() as db:
            family_id = get_family_id()
            data = get_summary_data(db, family_id)
            account_groups = get_account_groups(db, family_id)
            data['account_groups'] = account_groups
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        return jsonify({'data': {}, 'message': f'服务器内部错误: {str(e)}'}), 500


@bp.get('/summary/sankey/')
def sankey():
    """返回桑基图数据"""
    try:
        with get_db() as db:
            data = get_sankey_data(db, get_family_id())
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        return jsonify({'data': {'nodes': [], 'links': []}, 'message': f'服务器内部错误: {str(e)}'}), 500


@bp.get('/summary/distributions/')
def distributions():
    """返回家庭级多维市值分布（Overview/AssetPanorama 分布图表消费）"""
    try:
        with get_db() as db:
            data = get_distributions(db, get_family_id())
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        return jsonify({'data': {}, 'message': f'服务器内部错误: {str(e)}'}), 500


@bp.get('/summary/groups/')
def position_groups():
    """返回持仓/资产按维度分组汇总（type/account/allocation，含 items 明细）"""
    dimension = request.args.get('dimension', 'type')
    if dimension not in ('type', 'account', 'allocation'):
        return jsonify({'data': [], 'message': f'不支持的维度: {dimension}'}), 400
    try:
        with get_db() as db:
            data = get_position_groups(db, get_family_id(), dimension)
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        return jsonify({'data': [], 'message': f'服务器内部错误: {str(e)}'}), 500
