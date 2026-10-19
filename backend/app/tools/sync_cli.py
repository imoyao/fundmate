# -*- coding: utf-8 -*-
# File : sync_cli.py
"""
统一数据同步 CLI —— 把日常要跑的同步指令集中到一个入口。

用法:
    # 跑市场温度（含集思录估值温度、韭圈儿、自算估值分位；乖离率已临时跳过）
    pdm run python -m app.tools.sync_cli temperature

    # 跑全部同步任务（元数据 + 温度；乖离率跳过）
    pdm run python -m app.tools.sync_cli all

    # 单独跑某个 Job（透传到 DataSyncOrchestrator.run_job）
    pdm run python -m app.tools.sync_cli job fund_nav
    pdm run python -m app.tools.sync_cli job temperature --full-sync

    # 重抓并验证 jisilu_indicator 是否含 level（B2 端到端验证用）
    pdm run python -m app.tools.sync_cli verify-jisilu

说明:
    - temperature 任务目前跳过乖离率（SKIP_BIAS=True，见 thermometer/jobs.py），
      待后期修复后放开，放开不影响本 CLI 用法。
    - 所有命令均走 DataSyncOrchestrator，与 sync_metadata.py 同一套调度。
"""

import argparse
import os
import sys
from pathlib import Path

# 将项目根目录（backend/）加入 Python 路径 —— 必须在 import app 之前（同
# sync_metadata.py，#1366：原插入层级差一级且位于 import app 之后）。
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from loguru import logger  # noqa: E402

# 必须先导入全部域模型再 init_db()（#1607 约定，与 app/tools/scheduler.py、
# app/tools/sync_metadata.py、tests/conftest.py 一致）：init_db 的 create_all 只建
# 「已被 import 的模型」，漏掉哪个域，新建库就少建那个域的表，直到 job 跑起来写数据时才炸。
#
# ⚠️ 原注释写的「其余域模型由 _build_orchestrator 的惰性导入带来」**不成立**（2026-09-30 实证）：
#   orchestrator 顶层只导入 positions / watchlist 两域，而 fund_position_job 是在
#   `_save_data` 里才 `from app.domains.funds.models import ...` —— 那时 init_db() 早已跑完，
#   新增的 fund_holdings / fund_industry_allocs 根本没建，job 直接报 `no such table: fund_holdings`；
#   更糟的是该异常被基类当成「临时失败」重试 3 次，每次都**整批重抓**（117 只 × 2 请求/次）。
# 全量导入的启动开销可忽略（只是 SQLAlchemy 声明，不加载 akshare）。
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
import app.models.sync_log  # noqa: E402,F401
from app.core.database import get_db, init_db  # noqa: E402
from app.core.db_factory import app_db_startup_check, resolve_app_db  # noqa: E402

# 加载 .env（backend/ 目录）
env_path = BACKEND_DIR / '.env'
load_dotenv(dotenv_path=env_path)


def _build_orchestrator(db):
    # 惰性导入：orchestrator → akshare_adapter → akshare → pandas/numpy 的 C 扩展加载开销极大，
    # 仅在真正需要抓取的命令（temperature/all/job）才导入；只读诊断命令（verify-jisilu）不触碰此链路。
    from app.services.sync.orchestrator import DataSyncOrchestrator

    return DataSyncOrchestrator(db)


def cmd_temperature(args):
    """跑市场温度同步（集思录估值温度 / 韭圈儿 / 自算估值分位；乖离率跳过）。"""
    init_db()
    with get_db() as db:
        orch = _build_orchestrator(db)
        result = orch.run_job('temperature', full_sync=args.full_sync)
        logger.info(f'temperature 执行完成: {result.get("status")}')
        return 0 if result.get('status') == 'success' else 1


def cmd_all(args):
    """跑全部同步任务。"""
    # --all --full-sync 必须带 --target-file 范围，否则全市场逐标的全量回填
    # 会触发数据源封禁且耗时极长（#824 / #1776 ④）
    if args.full_sync and not args.target_file:
        logger.error(
            '--all --full-sync 必须配合 --target-file <csv> 限定范围，'
            '禁止裸调用（全市场逐标的全量回填会触发数据源封禁）。'
        )
        return 2
    init_db()
    with get_db() as db:
        orch = _build_orchestrator(db)
        results = orch.run_all_jobs(full_sync=args.full_sync, target_file=args.target_file)
        failed = [k for k, v in results.items() if v.get('status') != 'success']
        for name, res in results.items():
            logger.info(f'  {name}: {res.get("status")}')
        if failed:
            logger.warning(f'有 {len(failed)} 个任务未成功: {failed}')
            return 1
        logger.info('全部同步任务成功')
        return 0


def cmd_job(args):
    """透传跑单个 Job。

    #1983 遗留①：DB_POOL_JOBS 里的 job（fund_position）在无显式
    目标时，与 sync_metadata.main() 同源解析库内核心池（含 etf 池）；
    其他 job 仍透传 None，保持「子类自取核心池」语义。
    """
    # 逐标的回填型 Job 走 --full-sync 必须带 --targets / --target-file（#824 / #1776 ④）
    from app.services.sync.orchestrator import require_full_sync_scope
    from app.tools.sync_metadata import DB_POOL_JOBS, resolve_job_targets

    targets = None
    if args.targets:
        targets = [code.strip() for code in args.targets.split(',') if code.strip()]
    try:
        require_full_sync_scope(args.job, args.full_sync, bool(targets) or bool(args.target_file))
    except ValueError as e:
        logger.error(str(e))
        return 2
    init_db()
    with get_db() as db:
        orch = _build_orchestrator(db)
        # fund_position 对 targets=None 的语义是「目标池为空 → 显式跳过」
        # （grab.job 此前连 fund 池都不取，是 #870 修 sync_metadata 时
        # 遗漏的对称路径）。显式 --targets 优先（not targets 保证）；
        # --target-file 对 fund_position 从此生效（此前该 flag 在
        # grab.job 路径是死参数，只被门禁读了 bool）。
        if args.job in DB_POOL_JOBS and not targets:
            targets = resolve_job_targets(orch, args.job, None, args.target_file)
        result = orch.run_job(args.job, full_sync=args.full_sync, targets=targets)
        logger.info(f'{args.job} 执行完成: {result.get("status")}')
        return 0 if result.get('status') == 'success' else 1


def cmd_verify_jisilu(args):
    """只读诊断：确认 jisilu_indicator 是否已含 level 字段（B2 端到端验证）。"""
    from app.services.thermometer.service import TemperatureService

    data = TemperatureService.get_overview()
    ji = (data.get('composites') or {}).get('jisilu_indicator') or {}
    level_keys = [k for k in ji if 'level' in k]
    bands = (data.get('composites') or {}).get('temperature_bands')
    logger.info(f'jisilu level 字段: {level_keys or "无（B2 尚未生效，需先跑 temperature 抓取）"}')
    logger.info(f'median_pb_level={ji.get("median_pb_level")}  median_pe_level={ji.get("median_pe_level")}')
    logger.info(f'temperature_bands: {bands}')
    return 0 if level_keys else 1


def main():
    parser = argparse.ArgumentParser(description='统一数据同步 CLI')
    sub = parser.add_subparsers(dest='command', required=True)

    p_temp = sub.add_parser('temperature', help='跑市场温度同步（乖离率跳过）')
    p_temp.add_argument('--full-sync', action='store_true', help='全量同步')
    p_temp.set_defaults(func=cmd_temperature)

    p_all = sub.add_parser('all', help='跑全部同步任务')
    p_all.add_argument('--full-sync', action='store_true', help='全量同步（须配合 --target-file）')
    p_all.add_argument('--target-file', type=str, help='通过 CSV 文件指定待同步的代码列表（--full-sync 必须）')
    p_all.set_defaults(func=cmd_all)

    p_job = sub.add_parser('job', help='透传跑单个 Job')
    p_job.add_argument('job', type=str, help='Job 名称，如 fund_nav / temperature')
    p_job.add_argument('--full-sync', action='store_true', help='全量同步')
    p_job.add_argument('--targets', type=str, help='直接指定基金/股票代码列表，逗号分隔（--full-sync 必须）')
    p_job.add_argument('--target-file', type=str, help='通过 CSV 文件指定待同步的代码列表（--full-sync 必须）')
    p_job.set_defaults(func=cmd_job)

    p_verify = sub.add_parser('verify-jisilu', help='验证 jisilu_indicator 是否已含 level 字段')
    p_verify.set_defaults(func=cmd_verify_jisilu)

    args = parser.parse_args()

    # 预检（#2344，与 sync_metadata.main() 同源）：显式目标（--targets/--target-file）
    # 的批量修复场景对「解析出的库文件不存在」fail-closed；日常增量仅告警，
    # 不误伤 fresh clone 首跑就地建库。只接 sync_metadata 的话，`pdm run sync --job xxx`
    # 仍会静默连到空库/错库并报 success——正是 #2344 要防的形态。
    strict = bool(getattr(args, 'targets', None) or getattr(args, 'target_file', None))
    db_problem = app_db_startup_check(strict=strict)

    env = os.getenv('APP_ENV', 'development')
    url, source = resolve_app_db(env)
    print(f'运行库目标（APP_ENV={env}）: market 域: {url}（解析来源: {source}）')

    if db_problem:
        print(f'错误：{db_problem}', file=sys.stderr)
        sys.exit(2)

    sys.exit(args.func(args))


if __name__ == '__main__':
    main()
