# app/tools/scheduler.py
"""每日定时调度入口（#1182）。

不引入常驻调度器（符合部署决策）：由外部定时器（GitHub Actions schedule /
SCF cron / 系统 cron）每日触发本脚本，复用 DataSyncOrchestrator 跑全量增量同步
（含资产快照落账 job）。

抓取礼仪（#1400）：外部 cron 只能触发**固定时刻**（如每天 00:00），对数据源而言
就是机器人指纹。故本入口默认在开工前做**随机起跑延迟**（jitter，默认窗口 10 分钟，
可用 --jitter / --no-jitter / SYNC_JITTER_SECONDS 调整）；配置了 JSL_COOKIE 时还会
先跑一次集思录会话保活检查，并在两者之间加随机间隔。

用法:
    pdm run scheduler                 # 跑全量增量同步（fund_nav 刷新净值 + asset_snapshot 落账）
    pdm run scheduler --job asset_snapshot   # 仅落资产快照（净值已新鲜时，轻量）
    pdm run scheduler --full          # 全量同步
    pdm run scheduler --jitter 1800   # 起跑前在 0~1800s 内随机延迟
    pdm run scheduler --no-jitter     # 关闭随机延迟（本地调试用）
    pdm run scheduler --check-jsl     # 只做集思录 cookie 自检/保活
    pdm run scheduler --status        # 只读：本机调度开关 / 单实例锁 / 各任务上次成功时间

依赖：外部定时触发设施（CI schedule / SCF cron / 系统 cron），属运维部署项。

本机常驻（无外部定时器）见 `app/services/daily_scheduler.py`：`.env` 置
`SCHEDULER_ENABLED=1` 由应用启动时进程内调度，或 `pdm run scheduler-daemon`
以独立守护进程常驻（#1467）。
"""

import argparse
import json
import os
import socket
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from loguru import logger

# 将项目根目录（backend，即 app 包的父目录）加入 Python 路径，
# 否则 `pdm run scheduler` 直接执行时 `import app.*` 会因找不到 app 包而 ImportError
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# 必须先导入全部域模型再 init_db()：否则跨域外键（如 ledgers.portfolio_id → portfolios.id）
# 解析失败并抛 NoReferencedTableError —— 本脚本此前漏了这段，`pdm run scheduler` 直接跑不起来
# （2026-09-11 实测）。约定与 tests/conftest.py、app/tools/sync_metadata.py 一致。
import app.domains.assets.models  # noqa: E402,F401
import app.domains.families.models  # noqa: E402,F401
import app.domains.funds.models  # noqa: E402,F401
import app.domains.indices.models  # noqa: E402,F401
import app.domains.ledgers.models  # noqa: E402,F401
import app.domains.market.models  # noqa: E402,F401
import app.domains.portfolios.models  # noqa: E402,F401
import app.domains.positions.models  # noqa: E402,F401
import app.domains.price_history.models  # noqa: E402,F401
import app.domains.securities.models  # noqa: E402,F401
import app.domains.strategy.models  # noqa: E402,F401
import app.domains.summary.models  # noqa: E402,F401
import app.domains.transactions.models  # noqa: E402,F401
import app.domains.users.models  # noqa: E402,F401
import app.domains.watchlist.models  # noqa: E402,F401
from app.core.database import get_db, init_db  # noqa: E402
from app.core.db_factory import (  # noqa: E402
    DOMAIN_APP,
    DOMAIN_USER,
    DatabaseConfig,
    DatabaseFactory,
    get_app_env,
    normalized_app_db_url_preview,
    turso_auth_token,
)
from app.core.jitter import (  # noqa: E402
    apply_jitter,
    random_gap,
    resolve_jitter_seconds,
)
from app.core.time_utils import now_shanghai  # noqa: E402
from app.services.jsl_session import keepalive_jsl_session  # noqa: E402
from app.services.sync.orchestrator import DataSyncOrchestrator  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='多多贝每日定时调度')
    parser.add_argument('--job', help='只跑单个 job（如 asset_snapshot）')
    parser.add_argument('--full', action='store_true', help='全量同步（默认增量）')
    parser.add_argument(
        '--jitter',
        type=int,
        default=None,
        help='起跑前随机延迟窗口（秒）；默认取 SYNC_JITTER_SECONDS，否则 600',
    )
    parser.add_argument('--no-jitter', action='store_true', help='关闭随机延迟（本地调试）')
    parser.add_argument('--check-jsl', action='store_true', help='只做集思录 cookie 自检/保活')
    parser.add_argument('--status', action='store_true', help='只读打印本机调度状态（不动数据）')
    return parser.parse_args()


def _resolve_ip_families(host: str, port: int) -> set:
    """解析 host 的地址族集合（{'IPv4', 'IPv6'}）；解析失败返回空集。

    用途：判断「这个 host 只有 IPv6 记录」——那是「无 IPv6 出口的环境连不上」
    的判据（#2462）。
    """
    if not host:
        return set()
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return set()
    return {'IPv6' if info[0] == socket.AF_INET6 else 'IPv4' for info in infos}


def _user_domain_failure_message(parsed: 'urllib.parse.ParseResult', exc: Exception) -> str:
    """把 user 域连接失败翻译成**可操作**的结论（纯函数，便于单测钉住）。

    #2462：Supabase 的直连端口 5432 **只提供 IPv6**，而 CI runner 没有 IPv6 出口
    ⇒ libpq 报 `Network is unreachable`。这句话看不出
    「该换 pooler 端点」或「该把调度换到有 IPv6 的机器上」，于是排查只能靠猜。
    """
    msg = ' '.join(str(exc).split())
    families = _resolve_ip_families(parsed.hostname or '', parsed.port or 5432)
    if 'unreachable' in msg.lower() and families == {'IPv6'}:
        return (
            f'[DB诊断] user 域连接失败：{parsed.hostname} **只有 IPv6 记录**（无 IPv4）——'
            'Supabase 直连端口 5432 是 IPv6-only，而本机（GitHub Actions runner）没有 IPv6 出口，'
            'libpq 因此报 Network is unreachable。两条出路：'
            '(1) 把 SUPABASE_DATABASE_URL 换成 Supavisor pooler 端点（IPv4，形如 '
            'postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres）；'
            '(2) 把每日调度放到有 IPv6 出口的机器上跑（见 daily-snapshot.yml 头部「部署说明」b 项）。'
            f'原始错误：{msg}'
        )
    return f'[DB诊断] user 域连接失败：{msg}'


def _probe_user_domain(parsed: 'urllib.parse.ParseResult') -> None:
    """user 域（Postgres）连通性探测；失败时给出**可操作**的结论（见 _user_domain_failure_message）。"""
    from sqlalchemy import create_engine, text

    url = parsed.geturl()
    engine = create_engine(url, connect_args={'connect_timeout': 10})
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        logger.info('[DB诊断] user 域 连接 OK')
    except Exception as e:  # noqa: BLE001 - 诊断失败要重新抛出，由调用方统一上抛
        logger.error(_user_domain_failure_message(parsed, e))
        raise


def _diagnose_db() -> None:
    """启动期 DB 连接诊断（#1490 根因排查）。

    在真正 init_db 之前打印各数据域连接 URL 的 scheme + host（脱敏，不含 query/token），
    并对走 sqlalchemy-libsql 的 Hrana(HTTP) 协议的 market 域做一次轻量 SELECT 1 探测。
    若连接收到 Hrana 308 永久重定向，直接给出指向 secret 配置的清晰指引并重新抛出，
    使 CI 在下一次失败时即可从打印的 host 定位根因，无需再翻源码。
    """
    from sqlalchemy import text

    env = get_app_env()
    logger.info(f'[DB诊断] APP_ENV={env}')

    app_url = DatabaseConfig.for_app(env).url
    app_parsed = urllib.parse.urlparse(app_url)
    user_parsed = urllib.parse.urlparse(DatabaseConfig.for_user(env).url)

    def _describe(label: str, parsed: 'urllib.parse.ParseResult') -> bool:
        logger.info(f'[DB诊断] 域={label} scheme={parsed.scheme} host={parsed.netloc}')
        is_turso = parsed.scheme in ('turso', 'libsql') or (
            parsed.scheme == 'https' and 'turso' in parsed.netloc.lower()
        )
        if is_turso:
            logger.info(f'[DB诊断] 域={label} 将经 sqlalchemy-libsql 的 Hrana(HTTP) 协议连接')
        return is_turso

    is_app_turso = _describe(DOMAIN_APP, app_parsed)
    _describe(DOMAIN_USER, user_parsed)

    # 两域**各自独立**探测、**各自报结论**，全部探完再抛第一个错——
    # 撞上哪一域就停在哪一域，排查就得多跑一轮（#2462）。
    failures = []

    # ── market 域（Turso / Hrana）──
    if is_app_turso:
        # 缺 authToken 的 Turso 连接串**必然连不上**（服务端回 308 / 401），
        # 而这两种状态码都看不出「压根没配 token」——#1490 实测：每日调度连续 25 天全红，
        # 根因就是注入的 secret 里的连接串只有 host、没有 ?authToken=。
        # **先查这一条**：它比「host 被服务端重定向」常见得多，修法也只是补一个 query 参数。
        if turso_auth_token(app_url) is None:
            logger.error(
                '[DB诊断] market 域的 Turso 连接串里**没有 authToken**，必然连不上。'
                '生产下生效的变量是 TURSO_DATABASE_URL（优先）或 DATABASE_URL，'
                '请确认注入的 secret 是 Turso 控制台给出的**完整**连接串'
                '（形如 turso://<host>?authToken=<token>），而不是只有 host。'
            )
            raise RuntimeError('Turso 连接串缺少 authToken（详见上一行日志）')

        # 实际会用哪条 URL 连（token 已打码）：`secure=true` 决定走 https 还是明文 http，
        # 明文 http 会被 Turso 边缘 308 跳 https 而失败（#1490 根因之一）。
        logger.info(f'[DB诊断] 归一后的 market 域连接串: {normalized_app_db_url_preview(env)}')

        try:
            engine = DatabaseFactory.create(DOMAIN_APP)
            with engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            logger.info('[DB诊断] market 域(Turso/Hrana) 连接 OK')
        except Exception as e:  # noqa: BLE001 - 连接层异常要继续探另一域，最后统一抛出
            msg = str(e)
            if '308' in msg or 'Hrana' in msg or 'Permanent Redirect' in msg:
                logger.error(
                    '[DB诊断] market 域 Hrana 连接收到 HTTP 308 永久重定向。'
                    '两种可能，**先查前者**（成本最低、修法最简单）：'
                    '(1) 连接串缺 authToken——上面已单独检查过，若补了 token 仍 308 请重跑；'
                    '(2) Turso 侧 host 确实变更（区域 / 组织后缀）——'
                    '到 Turso 控制台取当前地址后更新注入的 secret。'
                    '原始错误：' + msg
                )
            else:
                logger.error(f'[DB诊断] market 域连接失败：{msg}')
            failures.append(e)

    # ── user 域（Postgres）──
    if user_parsed.scheme.startswith('postgres'):
        try:
            _probe_user_domain(user_parsed)
        except Exception as e:  # noqa: BLE001
            failures.append(e)

    if failures:
        raise failures[0]


# ── 每日调度的退出码与运行摘要（#2457）────────────────────────────────────
#
# 0 = 全部 job 成功；1 = 调度过程崩溃（未捕获异常）；2 = 跑完了，但有 job 失败。
# 区分 1 与 2，是为了让看日志的人一眼分清「调度本身炸了」与「某个任务/数据源坏了」。
EXIT_OK = 0
EXIT_CRASH = 1
EXIT_JOB_FAILED = 2

#: 逐 job 结果摘要的落盘位置（`backend/data/` 已被 .gitignore 忽略，不会脏工作区）。
RUN_SUMMARY_PATH = Path(__file__).resolve().parents[2] / 'data' / 'last_run_summary.json'


def build_run_summary(
    results: Dict[str, Any],
    elapsed: float,
    started_at: Optional[str] = None,
) -> Dict[str, Any]:
    """把逐 job 结果整理成机器可读的摘要。

    为什么要有它：告警卡正文要**指名道姓**说出哪几个 job 坏了——
    只写「运行失败」等于把排查成本推给读日志的人（#2457）。
    """
    jobs = {name: (res or {}).get('status', 'unknown') for name, res in (results or {}).items()}
    failed = sorted(name for name, status in jobs.items() if status != 'success')
    return {
        'started_at': started_at or now_shanghai().isoformat(),
        'elapsed_seconds': round(float(elapsed), 1),
        'total': len(jobs),
        'failed': failed,
        'jobs': jobs,
    }


def write_run_summary(summary: Dict[str, Any], path: Path = RUN_SUMMARY_PATH) -> Path:
    """原子写摘要：先写临时文件再 replace，避免读到半截 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)
    return path


def scheduler_exit_code(results: Dict[str, Any]) -> int:
    """有 job 失败 ⇒ 退出码非 0。

    #2457：旧行为把失败降级成日志里的一行、进程照样退 0，于是 workflow 判绿、
    末尾的「失败告警」步骤不触发 ⇒ 半个链路坏了却没有任何告警。
    """
    failed = [name for name, res in (results or {}).items() if (res or {}).get('status') != 'success']
    return EXIT_JOB_FAILED if failed else EXIT_OK


def main() -> None:
    # 显式指定 backend/.env，避免从 cron 等非项目根目录执行时加载不到
    load_dotenv(Path(__file__).resolve().parents[2] / '.env')
    args = _parse_args()

    # 只读状态：先于 jitter / init_db，做到「查状态」不扰动任何东西。
    # 惰性导入：describe_status 在 daily_scheduler 里，正常抓取路径不需要它。
    if args.status:
        from app.services.daily_scheduler import describe_status

        for line in describe_status():
            print(line)
        return

    # 只做集思录 cookie 自检/保活：可在 cron 里单挂一条（带 --jitter）
    # 手工自检要即时反馈，故仅在**显式**传 --jitter 时才抖动。
    if args.check_jsl:
        if args.jitter and not args.no_jitter:
            apply_jitter(resolve_jitter_seconds(args.jitter), label='JSL 保活')
        status = keepalive_jsl_session()
        sys.exit(0 if status.ok else 2)

    # 抓取礼仪（#1400）：随机起跑延迟，避免每天准点抓取形成指纹
    window = 0 if args.no_jitter else resolve_jitter_seconds(args.jitter)
    apply_jitter(window, label='每日调度起跑')

    # 启动期 DB 连接诊断（#1490 根因排查）：打印归一 URL + 探测 market 域，遇 Hrana 308 快速失败
    _diagnose_db()
    init_db()
    with get_db() as db:
        orch = DataSyncOrchestrator(db)
        try:
            # 集思录会话保活（配置了 cookie 才做）：与同步之间加随机间隔，避免同时打两个源
            if os.getenv('JSL_COOKIE'):
                keepalive_jsl_session()
                random_gap(label='JSL 保活后间隔')

            if args.job:
                result = orch.run_job(args.job, full_sync=args.full)
                logger.info(f'{args.job} 执行完成: {result.get("status")}')
            else:
                start = time.time()
                results = orch.run_all_jobs(full_sync=args.full)
                elapsed = time.time() - start
                summary = build_run_summary(results, elapsed)
                write_run_summary(summary)
                failed = summary['failed']
                for name, res in results.items():
                    logger.info(f'  {name}: {res.get("status")}')
                logger.info(f'每日调度完成，耗时 {elapsed:.1f}s，失败: {failed or "无"}')
                # 机器可读的一行：告警卡正文与人工排查都直接用它
                logger.info('DAILY_RUN_SUMMARY ' + json.dumps(summary, ensure_ascii=False))
                if failed:
                    # 有 job 失败 ⇒ 退出码非 0（#2457）。
                    # 旧行为是「失败只打进日志、进程照样退 0」，于是 workflow 判绿、
                    # 末尾的「失败告警」步骤（if: failure()）不触发 ⇒
                    # 半个链路坏了却没有任何告警，只能靠人翻日志发现。
                    logger.error(
                        f'有 {len(failed)} 个 job 失败：{", ".join(failed)}'
                        '——退出码非 0，使 workflow 的失败告警生效（#2457）'
                    )
                    sys.exit(EXIT_JOB_FAILED)
        except KeyboardInterrupt:
            logger.warning('用户中断调度')
            sys.exit(130)
        except Exception as e:  # noqa: BLE001
            logger.exception('调度失败: %s', e)
            sys.exit(1)


if __name__ == '__main__':
    main()
