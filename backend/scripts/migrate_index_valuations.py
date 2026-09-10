# -*- coding: utf-8 -*-
"""为 market 域创建指数估值表（#1285 消费侧「指数」品类 / #1394）。

- index_valuations：指数估值（市盈率1/2、股息率1/2，来源中证官方）

新建表（无存量数据），经 Base.metadata.create_all 建表即可；幂等。

用法（在 backend 目录；用 -m 以便 cwd 进入 sys.path）：
    pdm run python -m scripts.migrate_index_valuations
"""

import sys

from sqlalchemy import inspect

from app.core.database import Base
from app.core.db_factory import DOMAIN_MARKET, DatabaseFactory
from app.domains.indices.models import IndexValuation  # noqa: F401  触发模型注册进 metadata


def main() -> None:
    engine = DatabaseFactory.create(DOMAIN_MARKET)
    print(f'目标引擎: {engine.url}')
    Base.metadata.create_all(
        bind=engine,
        tables=[Base.metadata.tables['index_valuations']],
    )
    insp = inspect(engine)
    if 'index_valuations' not in set(insp.get_table_names()):
        print('[ERROR] index_valuations 未创建')
        sys.exit(1)
    print('[OK] index_valuations 已就绪')


if __name__ == '__main__':
    main()
