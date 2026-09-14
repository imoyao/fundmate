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
import sys
from pathlib import Path

# 将项目根目录（backend/）加入 Python 路径 —— 必须在 import app 之前（同
# sync_metadata.py，#1366：原插入层级差一级且位于 import app 之后）。
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
from loguru import logger  # noqa: E402

from app.core.database import get_db, init_db  # noqa: E402

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
    init_db()
    with get_db() as db:
        orch = _build_orchestrator(db)
        results = orch.run_all_jobs(full_sync=args.full_sync)
        failed = [k for k, v in results.items() if v.get('status') != 'success']
        for name, res in results.items():
            logger.info(f'  {name}: {res.get("status")}')
        if failed:
            logger.warning(f'有 {len(failed)} 个任务未成功: {failed}')
            return 1
        logger.info('全部同步任务成功')
        return 0


def cmd_job(args):
    """透传跑单个 Job。"""
    init_db()
    with get_db() as db:
        orch = _build_orchestrator(db)
        result = orch.run_job(args.job, full_sync=args.full_sync)
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
    p_all.add_argument('--full-sync', action='store_true', help='全量同步')
    p_all.set_defaults(func=cmd_all)

    p_job = sub.add_parser('job', help='透传跑单个 Job')
    p_job.add_argument('job', type=str, help='Job 名称，如 fund_nav / temperature')
    p_job.add_argument('--full-sync', action='store_true', help='全量同步')
    p_job.set_defaults(func=cmd_job)

    p_verify = sub.add_parser('verify-jisilu', help='验证 jisilu_indicator 是否已含 level 字段')
    p_verify.set_defaults(func=cmd_verify_jisilu)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == '__main__':
    main()
