# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/19 19:27
# File : sync_security_basics.py
"""同步全量A股股票基础信息到 securities 表"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import akshare as ak
from loguru import logger

from app.core.database import SessionLocal
from app.core.symbol_utils import derive_security_type
from app.domains.securities.models import Security


def sync_all_stocks():
    db = SessionLocal()
    count = 0
    try:
        logger.info('开始同步全量A股基础信息...')
        df = ak.stock_info_a_code_name()
        for _, row in df.iterrows():
            symbol = str(row['code']).strip()
            if not symbol:
                continue

            sec = db.query(Security).filter_by(symbol=symbol).first()
            if not sec:
                # 按 A 股代码前缀推断证券细类（stock/etf/bond），不再硬编码 'stock'
                mkt = 'SH' if symbol[:2] == '11' else None
                sec_type = derive_security_type(symbol, mkt) or 'stock'
                sec = Security(symbol=symbol, market='CN_A', type=sec_type)
                db.add(sec)

            sec.name = str(row.get('name', ''))[:100] or symbol

            count += 1
            if count % 1000 == 0:
                db.commit()
                logger.info(f'已处理 {count} 只股票...')

        db.commit()
        logger.info(f'✅ A股基础信息同步完成，共 {count} 只')
    except Exception as e:
        db.rollback()
        logger.error(f'❌ 同步A股信息失败: {e}')
    finally:
        db.close()


if __name__ == '__main__':
    sync_all_stocks()
