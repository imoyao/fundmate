# -*- coding: utf-8 -*-
"""健康检查蓝图：验证服务启动，并暴露关键组件健康（维护者 / 监控系统视角，非终端页面）。

#1720：将本机每日调度的健康状态纳入 health 端点。调度健康以 `sync_logs` 最近一次
成功运行为准（编排器每跑完一个 job 写一行），无需新建心跳表。普通探市页不调用本端点，
故「调度未运行」这类运维细节只在此对维护者可见，符合分层（终端页仅展示数据延迟提示）。

本端点为免登录公开（监控/探活用），因此**不做任何实时外部调用**（如 LLM 连通性探测、
第三方适配器 ping），避免被匿名请求滥用触发外部费用或 SSRF。组件仅暴露：
- database：内部 DB 连通性（SELECT 1）+ 方言，安全；
- scheduler：调度是否开启 + 最近成功运行（取自内部 sync_logs），安全；
- llm：仅配置就绪状态（provider/model/endpoint，不含 key），不做实时探测。
"""

import os

from apiflask import APIBlueprint
from loguru import logger
from sqlalchemy import func, text

from app.core.database import get_db, get_engine
from app.core.time_utils import now_shanghai
from app.models.sync_log import SyncLog

bp = APIBlueprint('health', __name__, url_prefix='/api')

# 调度健康判定：开启但超过该自然日数无任何成功运行即视为异常（容纳周末 + 单个短假期）。
_SCHEDULER_STALE_DAYS = 3


@bp.get('/health')
def health_check():
    """返回服务与关键组件健康状态（供监控系统 / 维护者，非终端页面）。

    - 应用进程存活 -> status=ok；
    - 数据库不可达 / 调度已开启却长时间无成功运行 -> status=degraded；
    - LLM 未配置为可选组件，不影响整体状态（仅功能不可用）。
    """
    components: dict = {}

    # ── 数据库组件 ──
    try:
        with get_db() as db:
            db.execute(text('SELECT 1'))
        dialect = 'unknown'
        try:
            eng = get_engine()
            dialect = eng.dialect.name if eng is not None else 'unknown'
        except Exception:
            pass
        components['database'] = {
            'status': 'healthy',
            'dialect': dialect,
            'message': '数据库连接正常',
        }
    except Exception as exc:  # 数据库不可达是严重故障，必须暴露
        logger.warning(f'health: 数据库探活失败：{exc}')
        components['database'] = {
            'status': 'unhealthy',
            'dialect': 'unknown',
            'message': f'数据库不可达：{exc}',
        }

    # ── 调度组件 ──
    scheduler_enabled = os.getenv('SCHEDULER_ENABLED', '').lower() in ('1', 'true', 'yes', 'on')
    last_success = None
    try:
        with get_db() as db:
            last_success = db.query(func.max(SyncLog.started_at)).filter(SyncLog.status == 'success').scalar()
    except Exception as exc:  # 健康端点本身绝不应因 DB 抖动而 500
        logger.warning(f'health: 查询 sync_logs 失败：{exc}')

    if not scheduler_enabled:
        sched_status = 'disabled'
        sched_message = '本机每日调度未开启（默认），温度/净值等不会自动更新；需手动抓取或开启 SCHEDULER_ENABLED'
    elif last_success is None:
        sched_status = 'unhealthy'
        sched_message = '调度已开启但无任何成功运行记录，请检查调度进程是否启动'
    elif (now_shanghai() - last_success).days > _SCHEDULER_STALE_DAYS:
        sched_status = 'unhealthy'
        sched_message = (
            f'调度已开启但最近一次成功运行在 {last_success.date()}（超过 {_SCHEDULER_STALE_DAYS} 天），可能已停止'
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

    # ── LLM 组件（仅配置就绪状态；免登录端点不做实时连通性探测，避免被滥用触发外部调用）──
    try:
        from app.services.ai_recognizer.llm import (
            ARK_API_KEY,
            ARK_ENDPOINT,
            ARK_MODEL,
        )
    except Exception:  # 极端情况下 AI 域不可导入，视为未配置
        ARK_API_KEY, ARK_MODEL, ARK_ENDPOINT = '', 'unknown', 'unknown'
    llm_configured = bool(ARK_API_KEY)
    if not llm_configured:
        llm_status = 'disabled'
        llm_message = '未配置 ARK_API_KEY，AI 识别功能不可用（可选组件，不影响主流程）'
    else:
        # 仅配置就绪：免登录端点不发起实时 LLM 请求（防止匿名请求刷额度/SSRF），
        # 连通性由实际调用链路与监控告警覆盖。
        llm_status = 'healthy'
        llm_message = f'已配置火山方舟 LLM（model={ARK_MODEL}）；连通性由实际调用与监控告警覆盖，本端点不做实时探测'
    components['llm'] = {
        'status': llm_status,
        'configured': llm_configured,
        'provider': 'volcano-ark',
        'model': ARK_MODEL,
        'endpoint': ARK_ENDPOINT,
        'message': llm_message,
    }

    # 整体状态：数据库不可达或调度明确异常（开启却长时间无运行）降级为 degraded
    critical = (components['database'], components['scheduler'])
    overall = 'degraded' if any(c['status'] == 'unhealthy' for c in critical) else 'ok'
    return {
        'status': overall,
        'message': '多多贝 is running',
        'components': components,
    }
