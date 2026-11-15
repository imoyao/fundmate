# -*- coding: utf-8 -*-
"""持仓「按流水重算份额」入口（#3127）。

为什么单独一个模块：``positions/views.py`` 的行数已顶满 ``check_view_thickness.py`` 的
存量基线（只减不增），而悬空流水服务的 docstring 一直承诺「如需对齐份额，到持仓页手动
重算」——持仓域却从来没有这个路由，于是「回补后份额与流水不自洽」无路可修
（真库 2026-11-15 实测 104 条，95 条由重建 + 回补造出，虚增账面市值 ≈64 万元）。

本模块只做 HTTP 编排：归属校验 → 调服务 → jsonify。份额派生、清仓 / 删行判据全在
``services.position_recompute.recompute_from_transactions``（锚点唯一入口），审计在
``recompute_with_audit``。
"""

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.auth import get_family_id, get_owned_or_404
from app.core.database import get_db
from app.core.retry import retry_on_db_locked
from app.domains.positions.models import Position
from app.services.position_recompute_entry import recompute_with_audit

bp = APIBlueprint('positions_recompute', __name__, url_prefix='/api/positions/')


@bp.post('/<int:id>/recompute/')
@retry_on_db_locked()
def recompute_position(id: int):
    """按该持仓名下的流水重算份额与成本（body 可选：``{reason, operator}``）。

    返回改前 / 改后份额与 ``adjustment_logs`` 编号；``deleted=true`` 表示「无流水且无锚点，
    空壳行被删」，前端必须如实展示而不是只报成功。
    """
    body = request.get_json(silent=True)
    if body is None:
        body = {}
    elif not isinstance(body, dict):
        abort(400, description='请求体必须是 JSON 对象')
    with get_db() as db:
        get_owned_or_404(db, Position, id)  # 越权 / 不存在统一 404，不泄露存在性
        try:
            data = recompute_with_audit(
                db,
                get_family_id(),
                id,
                reason=body.get('reason'),
                operator=body.get('operator'),
            )
        except ValueError as e:
            abort(400, description=str(e))
        return jsonify({'data': data, 'message': 'ok'})
