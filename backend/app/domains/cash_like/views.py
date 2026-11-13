# -*- coding: utf-8 -*-
"""账外类现金流水管理 API（只读口径仍在 `GET /api/summary/cash-like/`）。

本蓝图只做 HTTP 编排：`family_id` 注入、参数解析、错误信封；业务逻辑全部在
`services/cash_like_manage.py`，视图层不直接查业务表（#1606 视图层职责边界）。

端点：

    GET    /api/summary/cash-like/flows/              逐笔列表 / 搜索
    POST   /api/summary/cash-like/flows/              补录（含「到期回款」）
    PATCH  /api/summary/cash-like/flows/<id>/         单笔编辑
    DELETE /api/summary/cash-like/flows/<id>/         单笔删除
    GET    /api/summary/cash-like/targets/            归置目标持仓候选
    POST   /api/summary/cash-like/reconcile/          归置 / 撤销归置

口径红线：写路径只碰 `transactions`，**不建 positions 行**、不改 TNA/XIRR 的
算法；归置只改 `position_id`，让 `summary_service` 的净额桶自动收敛。
"""

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.auth import get_family_id
from app.core.database import user_session
from app.services import cash_like_manage as svc

bp = APIBlueprint('cash_like', __name__, url_prefix='/api/summary/cash-like')


def _payload() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        abort(400, description='请求体必须是 JSON 对象')
    return data


def _flag(name: str) -> bool:
    return request.args.get(name, '').lower() in ('1', 'true', 'yes')


def _call(fn, *args):
    """统一事务边界与错误语义；业务校验失败必须 rollback，避免半改字段被提交。"""
    family_id = get_family_id()
    with user_session() as db:
        try:
            result = fn(db, family_id, *args)
        except ValueError as e:
            db.rollback()
            abort(400, description=str(e))
        return jsonify({'data': result, 'message': 'ok'})


@bp.get('/flows/')
def list_flows():
    """逐笔账外类现金流水（分页）。`q` 命中产品名 / 代码，供持仓页搜索使用。"""
    args = request.args
    return _call(
        lambda db, fid: svc.list_flows(
            db,
            fid,
            ledger_id=args.get('ledger_id', type=int),
            asset_type=args.get('asset_type') or None,
            q=args.get('q') or None,
            include_reconciled=_flag('include_reconciled'),
            page=args.get('page', default=1, type=int),
            per_page=args.get('per_page', default=50, type=int),
        )
    )


@bp.post('/flows/')
def create_flow():
    """补录一笔；`kind='repayment'` 为逆回购到期回款（本金 + 可选利息）。"""
    return _call(lambda db, fid: svc.create_flows(db, fid, _payload()))


@bp.patch('/flows/<int:txn_id>/')
def update_flow(txn_id: int):
    """单笔编辑；`trade_date` 只允许显式手填，留空＝不改，禁止系统派生回填。"""
    return _call(lambda db, fid: svc.update_flow(db, fid, txn_id, _payload()))


@bp.delete('/flows/<int:txn_id>/')
def delete_flow(txn_id: int):
    """删除单笔未归置流水（已归置的须先撤销）。"""
    return _call(lambda db, fid: svc.delete_flow(db, fid, txn_id))


@bp.get('/targets/')
def list_targets():
    """归置目标候选：同家庭 / 可收窄到同账户的活跃持仓。"""
    args = request.args
    return _call(
        lambda db, fid: {
            'items': svc.list_targets(
                db,
                fid,
                ledger_id=args.get('ledger_id', type=int),
                q=args.get('q') or None,
            )
        }
    )


@bp.post('/reconcile/')
def reconcile():
    """归置（`attach`）或撤销归置（`detach`）一批流水。"""
    return _call(lambda db, fid: svc.reconcile_flows(db, fid, _payload()))
