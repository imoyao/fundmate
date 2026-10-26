# -*- coding: utf-8 -*-
"""定投计划 API（#2138）。

端点（一律尾斜杠，见 `docs/spec/conventions.md` §2.2）：

- ``GET   /api/recurring-plans/``               列表（``?status=``），含派生状态
- ``POST  /api/recurring-plans/``               新建
- ``GET   /api/recurring-plans/<id>/``          详情
- ``PATCH /api/recurring-plans/<id>/``          编辑（部分字段）
- ``POST  /api/recurring-plans/<id>/pause/``    暂停
- ``POST  /api/recurring-plans/<id>/resume/``   恢复
- ``POST  /api/recurring-plans/<id>/end/``      结束

读口径全在 ``services/recurring_service.py``：计划表**不落**执行状态，
「下次扣款 / 累计投入 / 断投」都按流水现算，避免第二份事实源。

视图只做参数校验、家庭隔离与编排；事务边界由请求 teardown 统一收
（``get_db()`` 不提交，见其 docstring）。
"""

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.auth import get_family_id
from app.core.database import get_db
from app.core.retry import retry_on_db_locked
from app.core.validation import parse_body
from app.domains.recurring.models import RECURRING_STATUSES
from app.domains.recurring.schemas import RecurringPlanCreate, RecurringPlanUpdate
from app.services import recurring_service

recurring_bp = APIBlueprint('recurring', __name__, url_prefix='/api/recurring-plans')


def _get_or_404(db, plan_id: int):
    """家庭内取计划：越权与不存在同判 404（不泄露他人计划是否存在）。"""
    plan = recurring_service.get_plan(db, get_family_id(), plan_id)
    if plan is None:
        abort(404, f'定投计划不存在: {plan_id}')
    return plan


def _summarize(db, plan) -> dict:
    """单条计划 + 流水派生状态。"""
    return recurring_service.summarize_one(db, get_family_id(), plan)


@recurring_bp.get('/')
def list_plans():
    """计划列表。``status`` 过滤：active（在投）/ paused（暂停）/ ended（已结束）。"""
    status = (request.args.get('status') or '').strip() or None
    if status and status not in RECURRING_STATUSES:
        abort(422, f'status 必须是 {list(RECURRING_STATUSES)} 之一，收到 {status!r}')
    with get_db() as db:
        items = recurring_service.list_plans(db, get_family_id(), status)
        return jsonify({'data': items, 'total': len(items), 'message': 'ok'})


@recurring_bp.get('/<int:plan_id>/')
def get_plan(plan_id: int):
    with get_db() as db:
        plan = _get_or_404(db, plan_id)
        return jsonify({'data': _summarize(db, plan), 'message': 'ok'})


@recurring_bp.post('/')
@retry_on_db_locked()
def create_plan():
    payload = parse_body(RecurringPlanCreate)
    with get_db() as db:
        plan = recurring_service.create_plan(db, get_family_id(), payload.model_dump())
        return jsonify({'data': _summarize(db, plan), 'message': 'ok'}), 201


@recurring_bp.patch('/<int:plan_id>/')
@retry_on_db_locked()
def update_plan(plan_id: int):
    payload = parse_body(RecurringPlanUpdate)
    patch = payload.model_dump(exclude_unset=True)
    if not patch:
        abort(422, '没有需要修改的字段')
    with get_db() as db:
        plan = _get_or_404(db, plan_id)
        try:
            recurring_service.update_plan(db, plan, patch)
        except ValueError as exc:
            abort(422, str(exc))
        return jsonify({'data': _summarize(db, plan), 'message': 'ok'})


@recurring_bp.post('/<int:plan_id>/pause/')
@retry_on_db_locked()
def pause_plan(plan_id: int):
    """暂停：不再推进下次扣款日，也不参与断投提示；已产生的流水不动。"""
    with get_db() as db:
        plan = _get_or_404(db, plan_id)
        recurring_service.set_status(db, plan, 'paused')
        return jsonify({'data': _summarize(db, plan), 'message': 'ok'})


@recurring_bp.post('/<int:plan_id>/resume/')
@retry_on_db_locked()
def resume_plan(plan_id: int):
    """恢复：从 active 重新开始推进（下次扣款日按原频率从今天之后推算）。"""
    with get_db() as db:
        plan = _get_or_404(db, plan_id)
        recurring_service.set_status(db, plan, 'active')
        return jsonify({'data': _summarize(db, plan), 'message': 'ok'})


@recurring_bp.post('/<int:plan_id>/end/')
@retry_on_db_locked()
def end_plan(plan_id: int):
    """结束：终态（可再 resume 启用）。不删除历史流水。"""
    with get_db() as db:
        plan = _get_or_404(db, plan_id)
        recurring_service.set_status(db, plan, 'ended')
        return jsonify({'data': _summarize(db, plan), 'message': 'ok'})
