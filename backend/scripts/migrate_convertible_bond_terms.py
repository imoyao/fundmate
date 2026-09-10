# -*- coding: utf-8 -*-
"""为 market 域创建可转债条款表（#1285 消费侧 / #1393）。

- convertible_bond_terms：可转债静态条款（强赎触发价 / 转股价值 / 溢价率 /
  评级 / 到期日 / 规模 / 强赎天计数等）

该表为新建（无存量数据），经 Base.metadata.create_all 建表即可，幂等：已存在则跳过。

用法（在 backend 目录）：
    pdm run python scripts/migrate_convertible_bond_terms.py
"""

import sys

from sqlalchemy import inspect

from app.core.database import Base
from app.core.db_factory import DOMAIN_MARKET, DatabaseFactory
from app.domains.securities.models import ConvertibleBondTerm  # noqa: F401  触发模型注册进 metadata


def main() -> None:
    # 属 market 域，必须建在 market 引擎（与 init_db / market_session 一致）
    engine = DatabaseFactory.create(DOMAIN_MARKET)
    print(f'目标引擎: {engine.url}')
    Base.metadata.create_all(
        bind=engine,
        tables=[Base.metadata.tables['convertible_bond_terms']],
    )
    insp = inspect(engine)
    if 'convertible_bond_terms' not in set(insp.get_table_names()):
        print('[ERROR] convertible_bond_terms 未创建')
        sys.exit(1)
    print('[OK] convertible_bond_terms 已就绪')


if __name__ == '__main__':
    main()
