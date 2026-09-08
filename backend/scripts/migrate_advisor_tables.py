# -*- coding: utf-8 -*-
"""为 market 域创建投顾组合相关四表（#1167）。

- advisor_portfolios：投顾/基金组合公开参照（且慢/蛋卷/天天基金）
- advisor_holdings：投顾组合当前基金级持仓
- advisor_industry_allocs：投顾组合行业配置
- advisor_adjust_histories：投顾组合历史调仓明细

四表均为新建（无存量数据），经 SQLAlchemy Base.metadata.create_all 建表即可，
仅对新库（invest.db / Turso market 库）执行。幂等：已存在的表跳过。

用法（在 backend 目录）：
    pdm run python scripts/migrate_advisor_tables.py
"""

import sys

from app.core.database import Base
from app.core.db_factory import DOMAIN_APP, DatabaseFactory
from app.domains.funds.models import (  # noqa: F401  触发模型注册进 metadata
    AdvisorAdjustHistory,
    AdvisorHolding,
    AdvisorIndustryAlloc,
    AdvisorPortfolio,
)


def main() -> None:
    # 四表为 market 域，必须建在 market 引擎（与 init_db / market_session 一致），
    # 且仅建这四张表，避免误建其它域的表到 market 库。
    engine = DatabaseFactory.create(DOMAIN_APP)
    print(f'目标引擎: {engine.url}')
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Base.metadata.tables['advisor_portfolios'],
            Base.metadata.tables['advisor_holdings'],
            Base.metadata.tables['advisor_industry_allocs'],
            Base.metadata.tables['advisor_adjust_histories'],
        ],
    )
    from sqlalchemy import inspect

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    expected = {
        'advisor_portfolios',
        'advisor_holdings',
        'advisor_industry_allocs',
        'advisor_adjust_histories',
    }
    missing = expected - tables
    if missing:
        print(f'[ERROR] 以下表未创建: {missing}')
        sys.exit(1)
    print(f'[OK] 投顾组合相关表已就绪: {sorted(expected & tables)}')


if __name__ == '__main__':
    main()
