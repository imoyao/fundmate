# -*- coding: utf-8 -*-
"""证券 asset_type 回填 CLI（#1264 / #1266 数据修正）。

用法：
    pdm run python backend/scripts/backfill_securities_asset_type.py          # 预览（dry-run）
    pdm run python backend/scripts/backfill_securities_asset_type.py --apply  # 真正写入
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services.securities_type_backfill import backfill_securities_asset_type


def main():
    parser = argparse.ArgumentParser(description='证券 asset_type 回填（stock/etf/bond）')
    parser.add_argument('--apply', action='store_true', help='真正写入；默认仅预览')
    args = parser.parse_args()

    db = SessionLocal()
    try:
        summary = backfill_securities_asset_type(db, apply=args.apply)
    finally:
        db.close()

    mode = 'APPLY' if args.apply else 'DRY-RUN'
    print(f'[{mode}] 证券 asset_type 回填')
    print(f'  持仓检查 {summary["positions_checked"]} 条，更新 {summary["positions_updated"]} 条')
    print(f'  元数据检查 {summary["securities_checked"]} 条，更新 {summary["securities_updated"]} 条')
    for c in summary['changes']:
        print(f'  - {c["kind"]} {c["symbol"]}: {c["from"]} -> {c["to"]}')


if __name__ == '__main__':
    main()
