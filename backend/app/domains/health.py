# -*- coding: utf-8 -*-
"""健康检查蓝图：验证服务启动，并暴露关键组件健康（维护者 / 监控系统视角，非终端页面）。

#1720：将本机每日调度的健康状态纳入 health 端点。调度健康以 `sync_logs` 最近一次
成功运行为准（编排器每跑完一个 job 写一行），无需新建心跳表。普通探市页不调用本端点，
故「调度未运行」这类运维细节只在此对维护者可见，符合分层（终端页仅展示数据延迟提示）。

本端点为免登录公开（监控/探活用），因此**不做任何实时外部调用**（如 LLM 连通性探测、
第三方适配器 ping），避免被匿名请求滥用触发外部费用或 SSRF。组件仅暴露：
- database：内部 DB 连通性（SELECT 1）+ 方言，安全；
- scheduler：调度是否开启 + 最近成功运行（取自内部 sync_logs），安全；
- llm：仅配置就绪状态（provider/model/endpoint，不含 key），不做实时探测；
- mcp：各 MCP provider 的凭据就绪状态 + 最近一次失败种类（取自内部 mcp_call_logs），
  同样不做实时探测，也不回显任何 Token（#2490）。
"""

import os

from apiflask import APIBlueprint
from loguru import logger
from sqlalchemy import func, text

from app.core.database import get_db, get_engine
from app.core.time_utils import as_shanghai, now_shanghai
from app.models.sync_log import SyncLog
from app.services.mcp.call_log import provider_snapshot
from app.services.mcp.credentials import is_configured, token_env_name
from app.services.mcp.errors import display_name
from app.services.mcp.registry import provider_names

bp = APIBlueprint('health', __name__, url_prefix='/api')

# 调度健康判定：开启但超过该自然日数无任何成功运行即视为异常（容纳周末 + 单个短假期）。
_SCHEDULER_STALE_DAYS = 3

#: 24h 内出现这些失败 ⇒ **人必须处理**（换 Token / 等额度 / 联系服务商），拉低整体状态。
#: 其余失败（unavailable / rate_limit / bad_response）只算 ``degraded``，不拉低整体——
#: 与 index_daily_job 同口径（#2475）：偶发抖动常态化报红，真故障反而被淹没。
_MCP_UNHEALTHY_KINDS = frozenset({'auth', 'quota', 'billing'})


def _mcp_component() -> dict:
    """MCP 接入层健康（provider 维度；**只读内部审计表，无实时外部调用**）。

    数据来源只有两个：``credentials.is_configured``（env 有没有配 —— 只看有无、不读值）
    与 ``mcp_call_logs``（最近一次失败是哪一类、24h 错误数、当日调用数）。

    状态口径：

    ============  ==================================================
    ``disabled``  未配置 Token：可选组件关闭。可见但**不算故障**（#1720 同口径）
    ``unhealthy`` 24h 内有 auth / quota / billing 失败 —— 拉低整体状态
    ``degraded``  24h 内有其它失败（5xx / 频控 / 结构异常）
    ``healthy``   已配置且 24h 无失败
    ``unknown``   **读不到审计表** —— 不得退化成 healthy（#171：拿不到输入却说正常）
    ============  ==================================================

    为什么 ``unknown`` 也要拉低整体：本端点自己的读库都失败了，继续报 ``ok`` 就是
    「结论不可信但看着正常」，而那正是要被消灭的形态。
    """
    try:
        names = provider_names()
    except Exception as exc:  # noqa: BLE001 - provider 模块导入失败不能让免登录端点 500
        logger.warning(f'health: 加载 MCP provider 注册表失败：{exc}')
        return {'status': 'unknown', 'providers': {}, 'message': f'无法加载 MCP provider 注册表：{exc}'}

    providers: dict = {}
    for name in names:
        configured = is_configured(name)
        snapshot = provider_snapshot(name)
        entry = {
            'configured': configured,
            'status': 'healthy',
            'last_error_kind': None,
            'last_error_at': None,
            'last_ok_at': None,
            'calls_today': 0,
            'errors_24h': 0,
            'message': '',
        }
        if not snapshot.get('available'):
            # 读不到 ≠ 没错误：显式声明结论不可信，而不是当作「一切正常」
            entry['status'] = 'unknown'
            entry['message'] = f'读不到 mcp_call_logs，本次结论不可信：{snapshot.get("reason") or "未知原因"}'
            providers[name] = entry
            continue

        for key in ('last_error_kind', 'last_error_at', 'last_ok_at', 'calls_today', 'errors_24h'):
            entry[key] = snapshot.get(key)
        label = display_name(name)
        if not configured:
            try:
                env_hint = token_env_name(name)
            except ValueError:
                env_hint = f'{name} 的凭据环境变量'
            entry['status'] = 'disabled'
            entry['message'] = f'{label} 未配置 {env_hint}，该来源不更新（可选组件，不影响主流程）'
        elif entry['errors_24h'] and entry['last_error_kind'] in _MCP_UNHEALTHY_KINDS:
            entry['status'] = 'unhealthy'
            entry['message'] = snapshot.get('last_error_message') or f'{label} 最近调用失败：{entry["last_error_kind"]}'
        elif entry['errors_24h']:
            entry['status'] = 'degraded'
            entry['message'] = (
                f'{label} 24 小时内 {entry["errors_24h"]} 次调用失败（最近：{entry["last_error_kind"]}），已在同步任务中降级处理'
            )
        else:
            entry['message'] = f'{label} 近期调用无异常'
        providers[name] = entry

    statuses = {p['status'] for p in providers.values()}
    if statuses & {'unhealthy'}:
        overall = 'unhealthy'
    elif statuses & {'unknown'}:
        overall = 'unknown'
    elif statuses & {'degraded'}:
        overall = 'degraded'
    elif statuses and statuses <= {'disabled'}:
        # 全部 provider 都没配 Token ⇒ 整个接入层没启用。**不报 healthy**：
        # 「一个都没启用」与「都正常」是两件事，报 healthy 就是 #171 那类假绿
        # （拿不到输入却输出正常结论）。``disabled`` 同样不拉低整体，它是可选组件关闭。
        overall = 'disabled'
    else:
        overall = 'healthy'
    return {
        'status': overall,
        'providers': providers,
        'message': 'MCP 接入层状态（数据取自 mcp_call_logs，无实时探测）',
    }


@bp.get('/health')
def health_check():
    """返回服务与关键组件健康状态（供监控系统 / 维护者，非终端页面）。

    - 应用进程存活 -> status=ok；
    - 数据库不可达 / 调度已开启却长时间无成功运行 / MCP 需要人处理（auth / quota / billing）
      或读不到调用审计表 -> status=degraded；
    - LLM 未配置、MCP 未配置 Token 为可选组件，不影响整体状态（仅功能不可用）。
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
            # SQLite 不保留时区偏移，读回的 started_at 是 naive 的东八区墙钟时间，
            # 必须归一为 aware 后才能与 now_shanghai() 相减（否则 TypeError → 端点 500，见 #1793）
            last_success = as_shanghai(
                db.query(func.max(SyncLog.started_at)).filter(SyncLog.status == 'success').scalar()
            )
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
            ARK_MODEL_AGENT,
        )
    except Exception:  # 极端情况下 AI 域不可导入，视为未配置
        ARK_API_KEY, ARK_MODEL, ARK_MODEL_AGENT, ARK_ENDPOINT = '', 'unknown', 'unknown', 'unknown'
    llm_configured = bool(ARK_API_KEY)
    if not llm_configured:
        llm_status = 'disabled'
        llm_message = '未配置 ARK_API_KEY，AI 识别功能不可用（可选组件，不影响主流程）'
    else:
        # 仅配置就绪：免登录端点不发起实时 LLM 请求（防止匿名请求刷额度/SSRF），
        # 连通性由实际调用链路与监控告警覆盖。
        llm_status = 'healthy'
        llm_message = (
            f'已配置火山方舟 LLM（OCR model={ARK_MODEL}，agent model={ARK_MODEL_AGENT}）；'
            '连通性由实际调用与监控告警覆盖，本端点不做实时探测'
        )
    components['llm'] = {
        'status': llm_status,
        'configured': llm_configured,
        'provider': 'volcano-ark',
        'model': ARK_MODEL,
        'model_agent': ARK_MODEL_AGENT,
        'endpoint': ARK_ENDPOINT,
        'message': llm_message,
    }

    # ── MCP 组件（只读内部审计表；免登录端点禁止实时探测，与 llm 同口径）──
    components['mcp'] = _mcp_component()

    # 整体状态：数据库不可达 / 调度明确异常 / MCP 需要人处理（auth / quota / billing）
    # 或**读不到审计表**（结论不可信）→ degraded。MCP 的 degraded（5xx / 频控）不拉低整体，
    # 理由见 :func:`_mcp_component`。
    critical = (components['database'], components['scheduler'])
    overall = (
        'degraded'
        if any(c['status'] == 'unhealthy' for c in critical) or components['mcp']['status'] in ('unhealthy', 'unknown')
        else 'ok'
    )
    return {
        'status': overall,
        'message': '多多贝 is running',
        'components': components,
    }
