# -*- coding: utf-8 -*-
"""目标配比 API（#2237）。

端点（一律尾斜杠，见 `docs/spec/conventions.md` §2.2）：

- ``GET    /api/strategy/allocation/``  当前占比 vs 目标占比（含偏离与越线判定）
- ``PUT    /api/strategy/allocation/``  整体覆盖式保存目标配比
- ``DELETE /api/strategy/allocation/``  清空目标配比

视图只做参数校验与编排，市值与占比口径全在 `services/strategy_engine/allocation.py`。

**本文件不产生提醒**：生成提醒是 `POST /api/strategy/engine/reminders/refresh/`
（策略引擎视图）。查询与写入分离，避免「看一眼配比」就顺手往消息表里写东西。
"""

from apiflask import APIBlueprint
from flask import jsonify, request

from app.core.auth import get_family_id
from app.core.database import get_db
from app.core.validation import parse_body
from app.domains.strategy.allocation.schemas import AllocationUpdate
from app.services.strategy_engine import allocation as allocation_service

allocation_bp = APIBlueprint('allocation', __name__, url_prefix='/api/strategy/allocation')


def _threshold_arg() -> float:
    """偏离阈值（百分点，0~100）。用户可临时调宽/收窄来看不同容忍带下的结果。"""
    raw = request.args.get('threshold', type=float)
    if raw is None:
        return allocation_service.DEFAULT_THRESHOLD_PCT
    return min(max(raw, 0.0), 100.0)


@allocation_bp.get('/')
def get_allocation():
    """当前占比 vs 目标占比。

    query:
        threshold: 偏离阈值（百分点，默认 5）。

    未设目标的标的 `target_pct` / `deviation_pct` 为 null 且不参与越线判定——
    「没定规矩」不该被判成「违反规矩」。
    """
    with get_db() as db:
        data = allocation_service.compute_deviation(db, get_family_id(), threshold_pct=_threshold_arg())
        return jsonify({'data': data, 'message': 'ok'})


@allocation_bp.put('/')
def put_allocation():
    """整体覆盖式保存目标配比。

    提交列表即最终状态，未提交的历史目标会被移除；空列表等价清空。
    保存后回读偏离，让用户立刻看到「按这个目标现在是什么情况」。
    """
    payload: AllocationUpdate = parse_body(AllocationUpdate)
    with get_db() as db:
        family_id = get_family_id()
        saved = allocation_service.save_targets(db, family_id, [item.model_dump() for item in payload.items])
        data = allocation_service.compute_deviation(db, family_id, threshold_pct=_threshold_arg())
        data['saved_count'] = saved
        return jsonify({'data': data, 'message': 'ok'})


@allocation_bp.delete('/')
def delete_allocation():
    """清空目标配比。幂等：本来就没设目标也返回 200。"""
    with get_db() as db:
        cleared = allocation_service.clear_targets(db, get_family_id())
        return jsonify({'data': {'cleared_count': cleared}, 'message': 'ok'})
