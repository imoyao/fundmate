# -*- coding: utf-8 -*-
"""为 market 域创建跨渠道关联表（#1285 设计 §3.8）。

- channel_links：指数↔ETF / ETF↔联接（裸代码存储，名称冗余）

新建表（无存量数据），经 Base.metadata.create_all 建表即可；幂等。

用法（在 backend 目录；用 -m 以便 cwd 进入 sys.path）：
    pdm run python -m scripts.migrate_channel_links
"""

import sys

from sqlalchemy import inspect

from app.core.database import Base
from app.core.db_factory import DOMAIN_MARKET, DatabaseFactory
from app.domains.funds.models import ChannelLink  # noqa: F401  触发模型注册进 metadata


def main() -> None:
    engine = DatabaseFactory.create(DOMAIN_MARKET)
    print(f'目标引擎: {engine.url}')
    Base.metadata.create_all(
        bind=engine,
        tables=[Base.metadata.tables['channel_links']],
    )
    insp = inspect(engine)
    if 'channel_links' not in set(insp.get_table_names()):
        print('[ERROR] channel_links 未创建')
        sys.exit(1)
    print('[OK] channel_links 已就绪')


if __name__ == '__main__':
    main()
