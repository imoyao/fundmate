# -*- coding: utf-8 -*-
"""健康检查蓝图：验证服务启动，并暴露关键组件健康（维护者 / 监控系统视角，非终端页面）。

#1720：将本机每日调度的健康状态纳入 health 端点。调度健康以 `sync_logs` 最近一次
成功运行为准（编排器每跑完一个 job 写一行），无需新增心跳表。普通探市页不调用本端点，
故「调度未运行」这类运维细节只在此对维护者可见，符合分层（终端页仅展示数据延迟提示）。
"""

import os

from apiflask import APIBlueprint
from loguru import logger
from sqlalchemy import func

from app.core.database import get_db
from app.core.time_utils import now_shanghai
from app.models.sync_log import SyncLog

bp = APIBlueprint('health', __name__, url_prefix='/api')

# 调度健康判定：开启但超过该自然日数无任何成功运行即视为异常（容纳周末 + 单个短假期）。
_SCHEDULER_STALE_DAYS = 3


@bp.get('/health')
def health_check():
    """返回服务与关键组件健康状态（供监控系统 / 维护者，非终端页面）。

    - 应用进程存活 -> status=ok；
    - 调度已开启却长时间无成功运行 -> status=degraded（便于外部监控捕获）；
    - 调度默认关闭属预期 -> scheduler.status=disabled，不告警。
    """
    components: dict = {}

    # ── 调度组件 ──
    scheduler_enabled = os.getenv('SCHEDULER_ENABLED', '').lower() in ('1', 'true', 'yes', 'on')
    last_success = None
    try:
        with get_db() as db:
            last_success = db.query(func.max(SyncLog.started_at)).filter(
                SyncLog.status == 'success'
            ).scalar()
    except Exception as exc:  # 健康端点本身绝不应因 DB 抖动而 500
        logger.warning(f'health: 查询 sync_logs 失败：{exc}')

    if not scheduler_enabled:
        sched_status = 'disabled'
        sched_message = (
            '本机每日调度未开启（默认），温度/净值等不会自动更新；'
            '需手动抓取或开启 SCHEDULER_ENABLED'
        )
    elif last_success is None:
        sched_status = 'unhealthy'
        sched_message = '调度已开启但无任何成功运行记录，请检查调度进程是否启动'
    elif (now_shanghai() - last_success).days > _SCHEDULER_STALE_DAYS:
        sched_status = 'unhealthy'
        sched_message = (
            f'调度已开启但最近一次成功运行在 {last_success.date()}'
            f'（超过 {_SCHEDULER_STALE_DAYS} 天），可能已停止'
        )
    else:
        sched_status = 'healthy'
        sched_message = f'调度正常，最近成功运行 {last_success.date()}'
    components['scheduler'] = {
        'enabled': scheduler_enabled,
        'last_success_run': last_success.isoformat() if last_success else None,
        'status': sched_status,
        'message': sched_message,
    }

    # 整体状态：应用进程存活为 ok；调度明确异常（开启却长时间无运行）降级为 degraded
    overall = 'ok' if sched_status != 'unhealthy' else 'degraded'
    return {
        'status': overall,
        'message': '多多贝 is running',
        'components': components,
    }
