import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import random
import time

from app.core.database import SessionLocal
from app.services.data_provider import DataProvider


def main():
    db = SessionLocal()
    try:
        # 基金净值同步（从持仓中获取需更新的基金代码）
        from app.domains.positions.models import Position

        fund_codes = db.query(Position.symbol).filter(Position.asset_type == 'fund').distinct().all()
        fund_codes = [c[0] for c in fund_codes] if fund_codes else ['000001', '000002']

        for code in fund_codes:
            DataProvider.sync_fund_daily_worth(code, days_back=1, db=db)
            time.sleep(random.uniform(0.5, 1.5))

        # 证券行情同步
        sec_symbols = (
            db.query(Position.symbol).filter(Position.asset_type.in_(['stock', 'bond', 'crypto'])).distinct().all()
        )
        sec_symbols = [s[0] for s in sec_symbols] if sec_symbols else ['600519', '00700.HK']

        for sym in sec_symbols:
            DataProvider.sync_security_daily_quote(sym, days_back=1, db=db)
            time.sleep(random.uniform(0.3, 1.0))

    finally:
        db.close()


if __name__ == '__main__':
    main()
