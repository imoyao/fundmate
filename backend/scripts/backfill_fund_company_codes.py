# -*- coding: utf-8 -*-
# backend/scripts/backfill_fund_company_codes.py
"""
回填 fund_companies 表中 code==name 的占位行（#1168 P1 修复脚本）。

为什么需要：akshare 全链路只给公司"名"不给"code"，导致 fund_companies 表大量
行 code==name 占位。本脚本调用 company_resolver.backfill_fund_company_codes，
按天天基金权威列表把真值 code 回填进去。

安全模型（与 cleanup_temp.py 同源）：默认 DRY-RUN，只打印待变更清单；必须显式
传 --apply 才写库。回填逻辑本身幂等（只处理 code==name 的占位行）。
"""

import argparse
import sys

from loguru import logger

from app.core.database import market_session
from app.services.sync.company_resolver import backfill_fund_company_codes


def main(argv=None):
    ap = argparse.ArgumentParser(description='回填基金公司 code（默认 dry-run，需 --apply 才写库）')
    ap.add_argument('--apply', action='store_true', help='真正写库（默认仅打印待变更清单）')
    args = ap.parse_args(argv)

    with market_session() as db:
        changes = backfill_fund_company_codes(db, dry_run=not args.apply)

    if not changes:
        print('[backfill] 没有需要回填的基金公司 code（无 code==name 占位，或均未匹配到权威 code）。')
        return

    print(f'[backfill] 共 {len(changes)} 条待回填：')
    for c in changes:
        print(f'  id={c["id"]} name={c["name"]} {c["old_code"]} -> {c["new_code"]}')

    if not args.apply:
        print('\n[backfill] DRY-RUN 模式：未写入任何数据。确认清单无误后加 --apply 执行。')
        return

    print(f'\n[backfill] 已回填 {len(changes)} 条基金公司 code。')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.exception(f'回填失败: {e}')
        sys.exit(1)
