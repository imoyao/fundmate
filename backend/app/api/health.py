# -*- coding: utf-8 -*-
"""健康检查蓝图，用于验证项目骨架是否启动成功."""

from apiflask import APIBlueprint

bp = APIBlueprint('health', __name__, url_prefix='/api')


@bp.get('/health')
def health_check():
    """返回 ok 表示服务正常运行."""
    return {'status': 'ok', 'message': 'ShowBuy is running'}
