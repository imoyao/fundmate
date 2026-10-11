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
from app.services.penetration import SCHEME_LABELS, build_penetration
from app.services.pnl_calendar import GRANULARITY_DAY, build_pnl_series
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
        return jsonify({'data': {}, 'message': f'服务器内部错误: {str(e)}', 'error_code': 5004}), 500


@bp.get('/summary/sankey/')
def sankey():
    """返回桑基图数据"""
    try:
        with get_db() as db:
            data = get_sankey_data(db, get_family_id())
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        return jsonify(
            {'data': {'nodes': [], 'links': []}, 'message': f'服务器内部错误: {str(e)}', 'error_code': 5004}
        ), 500


@bp.get('/summary/distributions/')
def distributions():
    """返回家庭级多维市值分布（Overview/AssetPanorama 分布图表消费）"""
    try:
        with get_db() as db:
            data = get_distributions(db, get_family_id())
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        return jsonify({'data': {}, 'message': f'服务器内部错误: {str(e)}', 'error_code': 5004}), 500


@bp.get('/summary/penetration/')
def penetration():
    """返回基金持仓穿透（行业 / 个股真实暴露，#870 Step 2）。

    查询参数：
    - `scheme`：主聚合口径，`csrc`（默认，证监会门类）/ `gics`（GICS 板块）。
      两套体系**不可相加**，非主口径的结果在 `other_schemes` 单列返回。
    - `top_n`：个股分布截断条数，默认 20；`<=0` 表示不截断（超出部分合并为「其他」）。

    覆盖率有硬上限（本机实测约 53%）：直持股票无「个股→行业」映射、场内 ETF 无
    底层持仓数据、货基债基本身无股票敞口。`unpenetrated` 逐条带 `reason`，区分
    「真缺口」与「本质无敞口」，前端不得把两者混为一谈。
    """
    scheme = (request.args.get('scheme') or 'csrc').strip().lower()
    if scheme not in SCHEME_LABELS:
        return jsonify(
            {'data': {}, 'message': f'scheme 仅支持 {"/".join(sorted(SCHEME_LABELS))}', 'error_code': 1001}
        ), 400

    raw_top_n = request.args.get('top_n')
    try:
        top_n = int(raw_top_n) if raw_top_n not in (None, '') else 20
    except (TypeError, ValueError):
        return jsonify({'data': {}, 'message': f'top_n 必须为整数: {raw_top_n!r}', 'error_code': 1001}), 400

    try:
        with get_db() as db:
            data = build_penetration(db, get_family_id(), scheme=scheme, top_n=top_n)
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        # 标准错误信封 {data, message, error_code}（AGENTS.md 接口契约）
        return jsonify({'data': {}, 'message': f'服务器内部错误: {str(e)}', 'error_code': 5004}), 500


@bp.get('/summary/groups/')
def position_groups():
    """返回持仓/资产按维度分组汇总（type/account/allocation，含 items 明细）"""
    dimension = request.args.get('dimension', 'type')
    if dimension not in ('type', 'account', 'allocation'):
        return jsonify({'data': [], 'message': f'不支持的维度: {dimension}', 'error_code': 1001}), 400
    try:
        with get_db() as db:
            data = get_position_groups(db, get_family_id(), dimension)
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        return jsonify({'data': [], 'message': f'服务器内部错误: {str(e)}', 'error_code': 5004}), 500


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
        return jsonify({'data': None, 'message': str(e), 'error_code': 1001}), 400
    except Exception as e:
        return jsonify({'data': None, 'message': f'服务器内部错误: {str(e)}', 'error_code': 5004}), 500


@bp.get('/summary/snapshots/')
def list_snapshots():
    """返回资产快照列表（升序），附 monthly_change_pct / yearly_change_pct 同比。

    支持 `start_date` / `end_date`（含）筛选。同比基准取基准日当天或之前最近
    一条快照；积累期无历史返回 null（前端降级展示）。分页为纯数据列表，量极小。

    #1181：支持 `ledger_id` 筛选——传入返回该账户的**账户级**快照序列，
    不传返回**家庭级**序列（既有行为不变）。
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        ledger_id = request.args.get('ledger_id', type=int)
        with get_db() as db:
            data = get_snapshots(db, get_family_id(), start_date, end_date, ledger_id)
        return jsonify({'data': data, 'message': 'ok'})
    except ValueError as e:
        return jsonify({'data': [], 'message': str(e), 'error_code': 1001}), 400
    except Exception as e:
        return jsonify({'data': [], 'message': f'服务器内部错误: {str(e)}', 'error_code': 5004}), 500


@bp.get('/summary/pnl-calendar/')
def pnl_calendar():
    """#1812 每日收益日历（as-of 派生逐日盈亏；口径与六态定义见 services/pnl_calendar.py）。
    与 snapshots 的区别：快照记的是落库当时的状态，改持仓后历史不更新、回填还会把今天
    的值贴到历史日期上；本接口现算。`ledger_id` 同 snapshots（不传=家庭级）；#1925 加
    `granularity`（day 缺省回 `days`，month/year 回 `periods`，聚合下推），非法值回 400。
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        ledger_id = request.args.get('ledger_id', type=int)
        granularity = request.args.get('granularity', GRANULARITY_DAY)
        with get_db() as db:
            data = build_pnl_series(db, get_family_id(), start_date, end_date, ledger_id, granularity)
        return jsonify({'data': data, 'message': 'ok'})
    except ValueError as e:
        return jsonify({'data': None, 'message': str(e), 'error_code': 1001}), 400
    except Exception as e:
        return jsonify({'data': None, 'message': f'服务器内部错误: {str(e)}', 'error_code': 5004}), 500


@bp.get('/summary/ghost-duplicates/')
def ghost_duplicates():
    """#1066 / #1020：family 级「幽灵重复」扫描（跨账本疑似重复交易预警）。

    识别同一笔交易疑似出现在多个账本（跨账本重复导入），供前端非阻断软提示
    横幅指名来源账本。不阻断任何操作，仅预警。
    """
    try:
        with get_db() as db:
            data = scan_cross_ledger_duplicates(db, get_family_id())
        return jsonify({'data': data, 'message': 'ok'})
    except Exception as e:
        # 标准错误信封 {data, message, error_code}（AGENTS.md 接口契约）
        return jsonify(
            {
                'data': [],
                'message': f'服务器内部错误: {str(e)}',
                'error_code': 5004,
            }
        ), 500
