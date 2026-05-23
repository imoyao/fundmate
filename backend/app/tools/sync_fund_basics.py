# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/19 19:27
# File : sync_fund_basics.py
# tools/sync_fund_basics.py
"""同步全量基金基础信息到 funds 表"""

import akshare as ak
from loguru import logger

from app.core.database import SessionLocal
from app.domains.funds.models import Fund


def sync_all_funds():
    db = SessionLocal()
    count = 0
    try:
        logger.info('开始同步全量基金基础信息...')
        df = ak.fund_name_em()
        for _, row in df.iterrows():
            fund_code = str(row['基金代码']).strip()
            if not fund_code:
                continue

            fund = db.query(Fund).filter_by(fund_code=fund_code).first()
            if not fund:
                fund = Fund(fund_code=fund_code)
                db.add(fund)

            fund.name = str(row.get('基金简称', ''))[:80] or fund_code
            fund.pinyin_abbr = str(row.get('拼音缩写', ''))[:30] if row.get('拼音缩写') else None
            fund.pinyin_full = str(row.get('拼音全称', ''))[:80] if row.get('拼音全称') else None
            fund.full_name = str(row.get('基金全称', ''))[:100] or fund.name
            count += 1
            if count % 1000 == 0:
                db.commit()
                logger.info(f'已处理 {count} 只基金...')

        db.commit()
        logger.info(f'✅ 基金基础信息同步完成，共 {count} 只')
    except Exception as e:
        db.rollback()
        logger.error(f'❌ 同步基金信息失败: {e}')
    finally:
        db.close()


if __name__ == '__main__':
    sync_all_funds()
