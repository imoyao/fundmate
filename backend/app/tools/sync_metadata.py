# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:27
# File : sync_metadata.py
# !/usr/bin/env python
"""
多多贝 元数据同步脚本

用法:
    # 日常增量更新（推荐每天运行）
    python app/tools/sync_metadata.py --all

    # 通过 CSV 文件指定要同步的基金/股票代码
    python app/tools/sync_metadata.py --all --target-file codes.csv

    # 单独执行某个任务
    python app/tools/sync_metadata.py --job fund_nav
    python app/tools/sync_metadata.py --job fund_detail_enrich --target-file codes.csv

    # 强制全量同步（拉取全部历史数据，耗时长，仅首次或需要修复时使用）
    python app/tools/sync_metadata.py --all --full-sync

任务说明:
    stock_list         - 刷新 A 股股票列表（全量，约 5000 只）
    fund_list          - 刷新公募基金列表（全量，约 27000 只）
    fund_detail_enrich - 补充基金的分类、公司、费率等信息（核心池，约 200 只）
    fund_nav           - 更新基金净值（增量，仅核心池）
    price_history      - 更新股票行情（增量，仅核心池）

    核心池 = 持仓标的 + 自选标的 + CSV文件指定标的
"""

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from app.core.database import get_db, init_db
from app.services.sync.orchestrator import DataSyncOrchestrator

# 将项目根目录添加到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))
# ✅ 在入口文件顶部加载 .env（相对于 backend/ 目录）
# 当前文件在 backend/app/tools/，需要向上两级到 backend/
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


def ensure_fund_sync_fields(db_session):
    """
    确保 funds 表包含同步所需的三个字段：is_active、last_nav_check、nav_fail_count。

    这是一个幂等操作：如果字段已存在，不会重复添加或报错。
    在引入正式的数据库迁移工具（如 Alembic）之前，此函数作为运行时安全网。

    Args:
        db_session: SQLAlchemy Session 实例
    """
    from sqlalchemy import inspect, text

    inspector = inspect(db_session.get_bind())
    existing_columns = {col['name'] for col in inspector.get_columns('funds')}

    # 需要添加的字段及其 SQL 定义
    required_columns = {
        'is_active': 'BOOLEAN DEFAULT TRUE',
        'last_nav_check': 'DATETIME',
        'nav_fail_count': 'INTEGER DEFAULT 0',
    }

    for col_name, col_def in required_columns.items():
        if col_name not in existing_columns:
            db_session.execute(text(f'ALTER TABLE funds ADD COLUMN {col_name} {col_def}'))
            logger.info(f'已添加字段 {col_name} 到 funds 表')

    db_session.commit()


def main():
    parser = argparse.ArgumentParser(description='元数据同步工具')
    parser.add_argument('--all', action='store_true', help='同步所有数据')
    parser.add_argument('--job', type=str, help='单独同步某个 Job')
    parser.add_argument('--full-sync', action='store_true', help='全量同步（默认增量）')
    parser.add_argument('--target-file', type=str, help='通过CSV文件指定待同步的代码列表')
    parser.add_argument('--targets', type=str, help='直接指定基金/股票代码列表，逗号分隔')
    args = parser.parse_args()

    if not args.all and not args.job:
        parser.print_help()
        return

    # 初始化数据库（创建表）
    # 域模型必须先于 init_db 全量导入：部分表存在跨模块外键（如 position_import_meta
    # → ledgers.id），缺导入会让 Base.metadata 解析 FK 时抛 NoReferencedTableError
    # （E账户对账上线后 sync CLI 首跑即暴露，2026-08-24）。
    import app.domains.assets.models  # noqa: F401
    import app.domains.families.models  # noqa: F401
    import app.domains.funds.models  # noqa: F401
    import app.domains.indices.models  # noqa: F401
    import app.domains.ledgers.models  # noqa: F401
    import app.domains.portfolios.models  # noqa: F401
    import app.domains.positions.models  # noqa: F401
    import app.domains.price_history.models  # noqa: F401
    import app.domains.securities.models  # noqa: F401
    import app.domains.strategy.models  # noqa: F401
    import app.domains.summary.models  # noqa: F401
    import app.domains.transactions.models  # noqa: F401
    import app.domains.users.models  # noqa: F401
    import app.domains.watchlist.models  # noqa: F401
    import app.models.sync_log  # noqa: F401

    init_db()

    with get_db() as db:
        # 确保同步相关字段存在
        ensure_fund_sync_fields(db)
        orchestrator = DataSyncOrchestrator(db)

        try:
            if args.all:
                start = time.time()
                results = orchestrator.run_all_jobs(full_sync=args.full_sync, target_file=args.target_file)
                elapsed = time.time() - start

                # 输出人类可读的摘要
                summary = format_summary(results, elapsed)
                print(summary)

                # 同时保留 JSON 日志供调试
                logger.debug(f'详细结果: {results}')
            elif args.job:
                targets = None
                if args.targets:
                    # 直接指定代码列表（逗号分隔）
                    targets = [code.strip() for code in args.targets.split(',') if code.strip()]
                elif args.target_file:
                    all_targets = orchestrator.resolve_targets(target_file=args.target_file)
                    if args.job in ('fund_nav', 'fund_detail_enrich', 'fund_manager'):
                        targets = all_targets.get('fund', [])
                    elif args.job == 'price_history':
                        targets = all_targets.get('stock', [])

                result = orchestrator.run_job(args.job, full_sync=args.full_sync, targets=targets)
                logger.info(f'任务 {args.job} 执行完成: {result}')
                # 打印逐数据源成功/失败明细（若有）
                detail = format_source_results(result)
                if detail:
                    print(detail)
        except KeyboardInterrupt:
            logger.warning('用户中断同步')
            sys.exit(130)
        except Exception as e:
            logger.error(f'同步失败: {e}')
            sys.exit(1)


def format_summary(results: dict, elapsed: float) -> str:
    """
    将同步结果字典格式化为人类可读的摘要文本。

    Args:
        results: Orchestrator.run_all_jobs() 返回的结果字典
        elapsed: 总耗时（秒）

    Returns:
        格式化的多行文本
    """
    lines = list()
    lines.append('=' * 60)
    lines.append('  多多贝 元数据同步报告')
    lines.append(f'  耗时: {elapsed:.1f}s')
    lines.append('=' * 60)

    # 汇总统计
    total_success = 0
    total_failed = 0
    total_new = 0
    total_skipped = 0

    # 任务名 → 中文描述映射
    job_labels = {
        'stock_list': 'A股股票列表',
        'fund_list': '公募基金列表',
        'fund_detail_enrich': '基金详情补充',
        'fund_manager': '基金经理信息',
        'fund_nav': '基金净值',
        'price_history': '股票行情',
    }

    for job_name, job_result in results.items():
        label = job_labels.get(job_name, job_name)
        status = job_result.get('status', 'unknown')

        if status == 'success':
            total_success += 1
            stats = job_result.get('stats', {})

            # 不同 Job 的统计字段名可能不同
            new_count = stats.get('success', stats.get('enriched', 0))
            skip_count = stats.get('skipped', stats.get('skipped_inactive', 0))
            total_count = stats.get('total', 0)
            error_count = len(stats.get('errors', []))

            total_new += new_count
            total_skipped += skip_count

            if total_count == 0 and new_count == 0:
                lines.append(f'\n  [成功] {label}: 无新数据')
            else:
                lines.append(f'\n  [成功] {label}:')
                if total_count:
                    lines.append(f'     - 检查了 {total_count} 个标的')
                if new_count:
                    lines.append(f'     - 新增 {new_count} 条记录')
                if skip_count:
                    lines.append(f'     - 跳过 {skip_count} 条（已存在或无数据）')
                if error_count:
                    lines.append(f'     - 有 {error_count} 个标的获取失败')

                # 逐数据源明细（如市场温度任务）
                src_detail = format_source_results(job_result)
                if src_detail:
                    lines.append(src_detail)

        elif status == 'failed':
            total_failed += 1
            error_msg = job_result.get('stats', {}).get('error', job_result.get('error', '未知错误'))
            lines.append(f'\n  [失败] {label}: 失败 — {error_msg}')

        elif status == 'manual_intervention':
            total_failed += 1
            error_msg = job_result.get('stats', {}).get('error', job_result.get('error', '未知'))
            lines.append(f'\n  [人工] {label}: 需人工介入 — {error_msg}')

        else:
            lines.append(f'\n  [未知] {label}: 状态未知 ({status})')

    # 汇总
    lines.append('\n' + '-' * 60)
    lines.append(f'  总结: {total_success} 个任务成功, {total_failed} 个失败')
    if total_new or total_skipped:
        lines.append(f'  数据变更: 新增 {total_new} 条, 跳过 {total_skipped} 条')
    lines.append('=' * 60)

    return '\n'.join(lines)


def format_source_results(result: dict) -> str:
    """
    将单个任务返回的逐数据源明细（stats.source_results）格式化为可读文本。

    仅当结果中包含 source_results 时返回非空字符串，否则返回 ''。
    """
    stats = result.get('stats', {})
    source_results = stats.get('source_results')
    if not source_results:
        return ''

    icon = {'success': '[成功]', 'failed': '[失败]', 'skipped': '[复用]'}
    lines = []
    lines.append('  ' + '-' * 46)
    lines.append('  数据源更新明细:')
    for r in source_results:
        mark = icon.get(r.get('status'), '[未知]')
        name = r.get('name') or r.get('source')
        source = r.get('source')
        if r.get('status') == 'failed':
            lines.append(f'    {mark} {name} ({source}): 失败 - {r.get("error")}')
        elif r.get('status') == 'skipped':
            val = r.get('value')
            val_str = f' = {val}' if val is not None else ''
            lines.append(f'    {mark} {name} ({source}): 复用今日数据{val_str}')
        else:
            val = r.get('value')
            val_str = f' = {val}' if val is not None else ''
            lines.append(f'    {mark} {name} ({source}): 成功{val_str}')

    s = sum(1 for r in source_results if r['status'] == 'success')
    k = sum(1 for r in source_results if r['status'] == 'skipped')
    f = sum(1 for r in source_results if r['status'] == 'failed')
    lines.append('  ' + '-' * 46)
    lines.append(f'  成功 {s} / 复用 {k} / 失败 {f}')
    return '\n'.join(lines)


if __name__ == '__main__':
    main()
