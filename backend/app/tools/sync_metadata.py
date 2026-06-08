# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:27
# File : sync_metadata.py
# !/usr/bin/env python
"""
ShowBuy 元数据同步脚本

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

# 将项目根目录添加到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from app.core.database import get_db, init_db
from app.services.sync.orchestrator import DataSyncOrchestrator


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
    lines.append('  ShowBuy 元数据同步报告')
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
                lines.append(f'\n  ✅ {label}: 无新数据')
            else:
                lines.append(f'\n  ✅ {label}:')
                if total_count:
                    lines.append(f'     - 检查了 {total_count} 个标的')
                if new_count:
                    lines.append(f'     - 新增 {new_count} 条记录')
                if skip_count:
                    lines.append(f'     - 跳过 {skip_count} 条（已存在或无数据）')
                if error_count:
                    lines.append(f'     - 有 {error_count} 个标的获取失败')

        elif status == 'failed':
            total_failed += 1
            error_msg = job_result.get('stats', {}).get('error', job_result.get('error', '未知错误'))
            lines.append(f'\n  ❌ {label}: 失败 — {error_msg}')

        elif status == 'manual_intervention':
            total_failed += 1
            error_msg = job_result.get('stats', {}).get('error', job_result.get('error', '未知'))
            lines.append(f'\n  ⚠️ {label}: 需人工介入 — {error_msg}')

        else:
            lines.append(f'\n  ❓ {label}: 状态未知 ({status})')

    # 汇总
    lines.append('\n' + '-' * 60)
    lines.append(f'  总结: {total_success} 个任务成功, {total_failed} 个失败')
    if total_new or total_skipped:
        lines.append(f'  数据变更: 新增 {total_new} 条, 跳过 {total_skipped} 条')
    lines.append('=' * 60)

    return '\n'.join(lines)


if __name__ == '__main__':
    main()
