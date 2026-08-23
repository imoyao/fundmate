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
    get_snapshots,
    get_summary_data,
    scan_cross_ledger_duplicates,
    write_asset_snapshot,
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


@bp.post('/summary/snapshots/')
def create_snapshot():
    """记录当日资产快照（幂等 upsert，同 natural 日覆盖）。

    请求体可选 `snapshot_date`（YYYY-MM-DD）用于历史回填；默认上海时区当日。
    金额自动聚合当前家庭总资产/负债/净资产，无请求体依赖。
    """
    try:
        body = request.get_json(silent=True) or {}
        snapshot_date = body.get('snapshot_date')
        with get_db() as db:
            data = write_asset_snapshot(db, get_family_id(), snapshot_date)
        return jsonify({'data': data, 'message': 'ok'})
    except ValueError as e:
        return jsonify({'data': None, 'message': str(e), 'error_code': 'INVALID_PARAMS'}), 400
    except Exception as e:
        return jsonify({'data': None, 'message': f'服务器内部错误: {str(e)}'}), 500


@bp.get('/summary/snapshots/')
def list_snapshots():
    """返回资产快照列表（升序），附 monthly_change_pct / yearly_change_pct 同比。

    支持 `start_date` / `end_date`（含）筛选。同比基准取基准日当天或之前最近
    一条快照；积累期无历史返回 null（前端降级展示）。分页为纯数据列表，量极小。
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        with get_db() as db:
            data = get_snapshots(db, get_family_id(), start_date, end_date)
        return jsonify({'data': data, 'message': 'ok'})
    except ValueError as e:
        return jsonify({'data': [], 'message': str(e), 'error_code': 'INVALID_PARAMS'}), 400
    except Exception as e:
        return jsonify({'data': [], 'message': f'服务器内部错误: {str(e)}'}), 500


@bp.get('/summary/ghost-duplicates/')
def ghost_duplicates():
    """#1066 / #1020：family 级「幽灵重复」扫描（跨账本疑似重复交易预警）。

    识别同一笔交易疑似出现在多个账本（跨账本重复导入），供前端非阻断软提示
    横幅指名来源账本。不阻断任何操作，仅预警。
    """
    try:
        with get_db() as db:
            data = scan_cross_ledger_duplicates(db, get_family_id())
        return jsonify({'code': 200, 'data': data, 'message': 'ok'})
    except Exception as e:
        return jsonify({'code': 500, 'data': [], 'message': f'服务器内部错误: {str(e)}'}), 500
