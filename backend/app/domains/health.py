# -*- coding: utf-8 -*-
"""健康检查蓝图：验证服务启动，并暴露关键组件健康（维护者 / 监控系统视角，非终端页面）。

#1720：将本机每日调度的健康状态纳入 health 端点。调度健康以 `sync_logs` 最近一次
成功运行为准（编排器每跑完一个 job 写一行），无需新建心跳表。普通探市页不调用本端点，
故「调度未运行」这类运维细节只在此对维护者可见，符合分层（终端页仅展示数据延迟提示）。

#3085：上述口径有两处漏判，已改为**心跳 job + 形态无关**：① 只有 `asset_snapshot`
（每日 23:45 落账）的成功才算「调度在跑」——手动单跑任意 job 也写 success，
旧口径下「每日调度停了 5 天、只手动跑过一次 nav_backfill」会显示成正常；
② `SCHEDULER_ENABLED` 不再决定「该不该判」，只回答「本机常驻开没开」——
部署库由 GitHub Actions 的外部 cron 驱动、从不设该 env，旧口径下它停摆多久都只报
`disabled`，而 `disabled` 不拉低整体 ⇒ 生产侧停摆永远绿。

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

# 调度健康判定：心跳 job 超过该自然日数无成功运行即视为异常（容纳周末 + 单个短假期）。
# 不能收到 2 天：`SCHEDULER_SKIP_NON_TRADING_DAY` 默认开启，周末两天本就不跑，
# 周一早上必然是「3 天前」——判据会把每个周一都判成红。
_SCHEDULER_STALE_DAYS = 3

#: 心跳 job（#3085）：每日 23:45 的资产快照落账，纯本地、不依赖上游开不开门，
#: 「它没跑成」等价于「整条每日调度链没跑成」。改动它必须同步改
#: `tests/domains/test_health.py::test_heartbeat_job_is_daily_scheduled`（会核对
#: `daily_scheduler._JOB_TEMPLATES` 里确有此 job 且 cron 是日频）。
_SCHEDULER_HEARTBEAT_JOB = 'asset_snapshot'

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
    # #3085（D113）：停摆判定改看**心跳 job**，不再用「任意一条 success 行」。
    # 旧口径三处失效，每一处都会把「每日调度已停」显示成正常：
    #   ① 手动单跑一个 job（`pdm run scheduler --job nav_backfill`）也写 success；
    #   ② 不区分是哪个 job 成功了——「只有 nav_backfill 在跑」与「19 个 job 都在跑」一样绿；
    #   ③ 巡检落的是 `ok`/`bloated`（D110），本来就不在 success 里。
    # 心跳取 `asset_snapshot`（每日 23:45 落账，纯本地、不依赖上游是否开门），
    # 它没跑成就说明整条调度链没跑成。
    scheduler_enabled = os.getenv('SCHEDULER_ENABLED', '').lower() in ('1', 'true', 'yes', 'on')
    last_success = None
    heartbeat = None
    try:
        with get_db() as db:
            # SQLite 不保留时区偏移，读回的 started_at 是 naive 的东八区墙钟时间，
            # 必须归一为 aware 后才能与 now_shanghai() 相减（否则 TypeError → 端点 500，见 #1793）
            last_success = as_shanghai(
                db.query(func.max(SyncLog.started_at)).filter(SyncLog.status == 'success').scalar()
            )
            heartbeat = as_shanghai(
                db.query(func.max(SyncLog.started_at))
                .filter(SyncLog.job_name == _SCHEDULER_HEARTBEAT_JOB, SyncLog.status == 'success')
                .scalar()
            )
    except Exception as exc:  # 健康端点本身绝不应因 DB 抖动而 500
        logger.warning(f'health: 查询 sync_logs 失败：{exc}')

    # 形态无关（#3085）：本仓有两条调度通道（D111）——本机常驻与部署侧外部 cron。
    # 旧实现把 `SCHEDULER_ENABLED` 当成「调度该不该在跑」的唯一开关，于是**部署库**
    # （由 GitHub Actions 驱动、从不设该 env）无论停摆多久都只报 `disabled`，
    # 而 `disabled` 不拉低整体状态 ⇒ 生产侧停摆永远绿。现在「有没有心跳」才是事实来源，
    # 开关只回答「本机常驻开没开」。
    stale = heartbeat is not None and (now_shanghai() - heartbeat).days > _SCHEDULER_STALE_DAYS
    stale_msg = (
        f'心跳 job `{_SCHEDULER_HEARTBEAT_JOB}` 最后成功在 {heartbeat.date()}（超过 {_SCHEDULER_STALE_DAYS} 天）'
        if stale
        else ''
    )
    if heartbeat is None:
        if scheduler_enabled:
            sched_status = 'unhealthy'
            sched_message = f'调度已开启但心跳 job `{_SCHEDULER_HEARTBEAT_JOB}` 从未成功运行，请检查调度进程是否启动'
        else:
            sched_status = 'disabled'
            sched_message = (
                '本机每日调度未开启（默认），且这份库没有任何日更成功记录；需手动抓取或开启 SCHEDULER_ENABLED'
            )
    elif stale:
        # 本机常驻没开、但这份库曾经在日更 ⇒ 大概率是部署侧的外部定时器停了。
        # 报 `degraded` 而非 `unhealthy`：本进程看不到那个定时器，不能替它下定论；
        # 但**必须显示出来**，否则「进程全停」这件事依旧只能靠人想起来。
        sched_status = 'unhealthy' if scheduler_enabled else 'degraded'
        sched_message = (
            f'每日调度已停止：{stale_msg}'
            if scheduler_enabled
            else f'本机常驻调度未开启，且这份库的日更记录已陈旧：{stale_msg}——若这是部署库，外部定时器可能已停'
        )
    else:
        sched_status = 'healthy'
        sched_message = (
            f'调度正常，最近日更成功 {heartbeat.date()}'
            if scheduler_enabled
            else f'本机常驻调度未开启，但 {heartbeat.date()} 有日更成功记录（由外部定时器驱动）'
        )
    components['scheduler'] = {
        'enabled': scheduler_enabled,
        'last_success_run': last_success.isoformat() if last_success else None,
        'heartbeat_job': _SCHEDULER_HEARTBEAT_JOB,
        'last_heartbeat_run': heartbeat.isoformat() if heartbeat else None,
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
