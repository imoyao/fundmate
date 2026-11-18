# -*- coding: utf-8 -*-
"""自选提醒 API（独立蓝图，避免把 `watchlist/views.py` 撑厚）。

端点（一律尾斜杠，见 `docs/spec/conventions.md` §2.2）：

- ``GET   /api/watchlist/alerts/``                    全部规则 + 家庭默认（读时顺带扫描投递）
- ``GET   /api/watchlist/alerts/settings/``           家庭默认口径
- ``PUT   /api/watchlist/alerts/settings/``           更新家庭默认口径（阈值/开关/窗口）
- ``GET   /api/watchlist/items/<id>/alerts/``         单标的规则 + 生效口径 + 最新价（抽屉用）
- ``POST  /api/watchlist/items/<id>/alerts/``         新建/覆盖单标的规则
- ``PATCH /api/watchlist/alerts/<id>/``               改阈值 / 启停
- ``DELETE /api/watchlist/alerts/<id>/``              删除规则

视图只做入参校验与编排：规则口径、行情取数、通知投递全在
`services/alerts/{rules,quotes,service}.py`。

**为什么 GET 列表里顺带扫描**：站内通知是懒生成设计（见
`notification_service` 模块 docstring），用户打开自选页即最新，等价于定时任务
而省掉调度器；与 `strategy_engine.allocation.refresh_reminders` 同一取舍。
"""

from apiflask import APIBlueprint
from flask import abort, jsonify, request

from app.core.auth import get_family_id
from app.core.database import get_db
from app.core.validation import parse_body
from app.domains.watchlist.alert_schemas import (
    AlertSettingsUpdate,
    WatchlistAlertCreate,
    WatchlistAlertUpdate,
)
from app.services.alerts import rules
from app.services.alerts import service as alert_service

watchlist_alert_bp = APIBlueprint('watchlist_alerts', __name__, url_prefix='/api/watchlist')


def _defaults_payload() -> dict:
    """把代码默认值下发给前端做占位（用户没设过时输入框显示的就是它）。"""
    return {
        alert_type: {
            'threshold_value': cfg['threshold_value'],
            'window_days': cfg['window_days'],
            'level': cfg['level'],
        }
        for alert_type, cfg in rules.DEFAULT_SETTINGS.items()
    }


@watchlist_alert_bp.get('/alerts/settings/')
def get_alert_settings():
    """家庭默认口径（缺行由代码默认值补齐，`is_customized` 区分是否用户设过）。"""
    with get_db() as db:
        settings = alert_service.get_settings(db, get_family_id())
    return jsonify({'data': {'items': list(settings.values()), 'defaults': _defaults_payload()}, 'message': 'ok'})


@watchlist_alert_bp.put('/alerts/settings/')
def put_alert_settings():
    """更新家庭默认口径：只影响「没单独设过规则的标的」。"""
    body = parse_body(AlertSettingsUpdate)
    payload = [item.model_dump() for item in body.items]
    with get_db() as db:
        try:
            settings = alert_service.update_settings(db, get_family_id(), payload)
        except ValueError as exc:
            abort(422, str(exc))
        db.flush()
    return jsonify({'data': {'items': list(settings.values()), 'defaults': _defaults_payload()}, 'message': 'ok'})


@watchlist_alert_bp.get('/alerts/')
def list_alerts():
    """全部提醒规则（可选 `?item_id=` 过滤），并顺带跑一次幂等扫描。"""
    item_id = request.args.get('item_id', type=int)
    with get_db() as db:
        family_id = get_family_id()
        stats = alert_service.refresh_alerts(db, family_id)
        items = alert_service.list_alerts(db, family_id, item_id=item_id)
        settings = alert_service.get_settings(db, family_id)
    return jsonify(
        {
            'data': {
                'items': items,
                'settings': list(settings.values()),
                'defaults': _defaults_payload(),
                'refresh': stats,
            },
            'message': 'ok',
        }
    )


@watchlist_alert_bp.get('/items/<int:item_id>/alerts/')
def get_item_alerts(item_id: int):
    """单标的详情：规则、生效口径（含来源）、最新报价。"""
    with get_db() as db:
        data = alert_service.get_item_alerts(db, get_family_id(), item_id)
        if data is None:
            abort(404, '自选记录不存在')
    data['defaults'] = _defaults_payload()
    return jsonify({'data': data, 'message': 'ok'})


@watchlist_alert_bp.post('/items/<int:item_id>/alerts/')
def create_item_alert(item_id: int):
    """新建或覆盖某标的某类型的规则（同类型只留一行）。"""
    body = parse_body(WatchlistAlertCreate)
    with get_db() as db:
        try:
            data = alert_service.upsert_alert(
                db,
                get_family_id(),
                item_id,
                alert_type=body.alert_type,
                threshold_value=body.threshold_value,
                is_active=body.is_active,
            )
        except LookupError:
            abort(404, '自选记录不存在')
        except ValueError as exc:
            abort(422, str(exc))
        db.flush()
    return jsonify({'data': data, 'message': 'ok'})


@watchlist_alert_bp.patch('/alerts/<int:alert_id>/')
def patch_alert(alert_id: int):
    """改阈值 / 启停。找不到或不属于本家庭一律 404。"""
    body = parse_body(WatchlistAlertUpdate)
    with get_db() as db:
        try:
            data = alert_service.update_alert(
                db,
                get_family_id(),
                alert_id,
                threshold_value=body.threshold_value,
                is_active=body.is_active,
            )
        except ValueError as exc:
            abort(422, str(exc))
        if data is None:
            abort(404, '提醒规则不存在')
        db.flush()
    return jsonify({'data': data, 'message': 'ok'})


@watchlist_alert_bp.delete('/alerts/<int:alert_id>/')
def remove_alert(alert_id: int):
    with get_db() as db:
        if not alert_service.delete_alert(db, get_family_id(), alert_id):
            abort(404, '提醒规则不存在')
        db.flush()
    return jsonify({'data': {'id': alert_id, 'deleted': True}, 'message': 'ok'})
