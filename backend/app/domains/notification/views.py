# -*- coding: utf-8 -*-
"""站内通知 API。

端点（一律尾斜杠，见 `docs/spec/conventions.md` §2.2）：

- ``GET   /api/notifications/``              通知列表（含未读数与首页横栏候选）
- ``GET   /api/notifications/unread-count/``  仅未读条数（前端轮询红点用，更轻）
- ``PATCH /api/notifications/<id>/read/``     标记单条已读
- ``POST  /api/notifications/read-all/``      全部标记已读

视图只做参数校验与编排，读写口径全在 `services/notification_service.py`。

**本域不生产消息**：消息由各业务域（策略提醒 / 自选异动）调用
`notification_service.emit_many` 写入，本域只负责存取。这样通知表不会
反过来依赖业务，业务新增一种提醒也不必改这里。
"""

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.auth import get_family_id
from app.core.database import get_db
from app.domains.notification.schemas import NotificationListOut
from app.services import notification_service

notification_bp = APIBlueprint('notification', __name__, url_prefix='/api/notifications')


def _as_bool(value: str | None) -> bool:
    """查询参数转布尔：'1'/'true'/'yes' 为真，其余为假。"""
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


@notification_bp.get('/')
def list_notifications():
    """通知列表。

    query:
        unread_only: 只看未读（默认否）。
        limit:       单页条数（1~200，默认 50）。

    响应同时给出 `unread_count` 与 `banner`，省去前端为红点和首页横栏再发两次请求。
    """
    unread_only = _as_bool(request.args.get('unread_only'))
    limit = request.args.get('limit', type=int) or notification_service.DEFAULT_LIMIT
    with get_db() as db:
        family_id = get_family_id()
        rows = notification_service.list_notifications(db, family_id, unread_only=unread_only, limit=limit)
        items = [notification_service.to_dict(r) for r in rows]
        banner = notification_service.banner_notification(db, family_id)
        payload = NotificationListOut(
            items=items,
            total=notification_service.total_count(db, family_id),
            unread_count=notification_service.unread_count(db, family_id),
            banner=notification_service.to_dict(banner) if banner else None,
        )
        return jsonify({'data': payload.model_dump(), 'message': 'ok'})


@notification_bp.get('/unread-count/')
def get_unread_count():
    """未读条数。铃铛红点每开一次页面都要问，故独立成最轻的一个端点。"""
    with get_db() as db:
        return jsonify(
            {'data': {'unread_count': notification_service.unread_count(db, get_family_id())}, 'message': 'ok'}
        )


@notification_bp.patch('/<int:notification_id>/read/')
def mark_notification_read(notification_id: int):
    """标记单条已读。

    幂等：重复点已读仍返回 200。找不到（或不属于本家庭）返回 404——
    越权与不存在对调用方无差别，一律 404 避免泄漏「这条消息存在但不属于你」。
    """
    with get_db() as db:
        if not notification_service.mark_read(db, get_family_id(), notification_id):
            abort(404, description='通知不存在')
        return jsonify({'data': {'id': notification_id, 'is_read': True}, 'message': 'ok'})


@notification_bp.post('/read-all/')
def mark_all_read():
    """全部标记已读，返回本次被标记条数（可能为 0，非错误）。"""
    with get_db() as db:
        count = notification_service.mark_all_read(db, get_family_id())
        return jsonify({'data': {'marked': count}, 'message': 'ok'})
