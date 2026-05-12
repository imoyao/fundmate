# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/12 18:35
# File : sync_funds.py
# !/usr/bin/env python3
"""手动/定时任务：同步基金、证券、可转债数据到数据库"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.services.data_provider import DataProvider


def main():
    db = SessionLocal()
    try:
        # 首次同步基金列表（可注释，仅在需要时运行，数据量较大）
        # DataProvider.sync_fund_list(db)

        # 示例：同步几只重点关注的基金和证券
        fund_codes = ['000001', '000002', '110011']
        for code in fund_codes:
            DataProvider.sync_fund_daily_worth(code, db=db)

        DataProvider.sync_security_info('600519', db=db)  # 茅台
        DataProvider.sync_convertible_bond_info('110038', db=db)  # 示例可转债

    finally:
        db.close()


if __name__ == '__main__':
    main()
