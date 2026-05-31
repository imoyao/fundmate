# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:27
# File : sync_metadata.py
# !/usr/bin/env python
# -*- coding: utf-8 -*-
"""
元数据同步脚本

用法:
    python scripts/sync_metadata.py --all                # 全量同步所有数据
    python scripts/sync_metadata.py --all --full-sync    # 强制全量同步
    python scripts/sync_metadata.py --job stock_list     # 单独同步某个 Job
"""

import argparse
import csv
import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from app.core.database import get_db, init_db
from app.services.sync.orchestrator import DataSyncOrchestrator


def load_codes_from_csv(filepath):
    codes = []
    with open(filepath, encoding='utf-8-sig') as f:  # utf-8-sig 自动去掉 BOM
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            code = row[0].strip().strip('"')  # 去掉可能的引号
            if not code:
                continue
            # 跳过表头
            if code in ('code', '代码', 'symbol'):
                continue
            codes.append(code)
    return codes


def main():
    parser = argparse.ArgumentParser(description='元数据同步工具')
    parser.add_argument('--all', action='store_true', help='同步所有数据')
    parser.add_argument('--job', type=str, help='单独同步某个 Job')
    parser.add_argument('--full-sync', action='store_true', help='全量同步（默认增量）')
    parser.add_argument('--target-file', type=str, help='通过CSV文件指定待同步的代码列表')
    args = parser.parse_args()

    if not args.all and not args.job:
        parser.print_help()
        return

    if args.target_file:
        target_codes = load_codes_from_csv(args.target_file)
        print(target_codes, '-------000000000000------------')
    else:
        target_codes = None

    init_db()

    with get_db() as db:
        orchestrator = DataSyncOrchestrator(db, target_file_codes=target_codes)
        try:
            if args.all:
                results = orchestrator.run_all_jobs(full_sync=args.full_sync)
                logger.info(f'所有任务执行完成: {results}')
            elif args.job:
                result = orchestrator.run_job(args.job, full_sync=args.full_sync)
                logger.info(f'任务 {args.job} 执行完成: {result}')
        except Exception as e:
            logger.error(f'同步失败: {e}')
            sys.exit(1)


if __name__ == '__main__':
    main()
