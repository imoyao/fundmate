# -*- coding: utf-8 -*-
"""建探市大类资产日频快照表（#1460 P1）：market_asset_daily / market_bond_yield_daily。

新库由 init_db（Base.metadata.create_all）自动建表；本脚本用于**已有库补表**，
幂等执行——表已存在则跳过，可安全重复运行。

用法（在 backend/ 目录下）：
    pdm run python scripts/migrate_market_asset_daily.py
"""

from sqlalchemy import inspect

from app.core.db_factory import DOMAIN_MARKET, DatabaseFactory
from app.domains.market.models import MarketAssetDaily, MarketBondYieldDaily


def main() -> None:
    engine = DatabaseFactory.create(DOMAIN_MARKET)
    insp = inspect(engine)
    existing = set(insp.get_table_names())

    for model in (MarketAssetDaily, MarketBondYieldDaily):
        table = model.__table__
        if table.name in existing:
            print(f'[SKIP] {table.name} 表已存在，无需迁移')
            continue
        table.create(engine, checkfirst=True)
        print(f'[OK] 已建表 {table.name}')


if __name__ == '__main__':
    main()
