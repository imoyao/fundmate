# -*- coding: utf-8 -*-
"""为 market 域创建可转债**下修历史**表（#2585）。

- convertible_bond_adjust_logs：可转债下修事件流（股东大会日 / 下修前后转股价 /
  生效日 / 下修底价），唯一键 ``(symbol, 股东大会日)``。

该表为新建（无存量数据），``Base.metadata.create_all`` 建表即可，幂等：已存在则跳过。
``init_db()`` 的 ``market_meta.create_all`` 也会补建新表，本脚本是给「只想补这一张表」
与生产环境手动执行的路径，两者结果一致。

用法（在 backend 目录；用 -m 以便 cwd 进入 sys.path —— 部分环境下
`pdm run python scripts/xx.py` 会因找不到 app 包而 ImportError）：
    pdm run python -m scripts.migrate_convertible_bond_adjust_logs
"""

import sys

from sqlalchemy import inspect

from app.core.database import Base
from app.core.db_factory import DOMAIN_MARKET, DatabaseFactory
from app.domains.securities.models import ConvertibleBondAdjustLog  # noqa: F401  触发模型注册进 metadata

TABLE = 'convertible_bond_adjust_logs'


def main() -> None:
    # 属 market 域，必须建在 market 引擎（与 init_db / market_session 一致）
    engine = DatabaseFactory.create(DOMAIN_MARKET)
    print(f'目标引擎: {engine.url}')
    Base.metadata.create_all(bind=engine, tables=[Base.metadata.tables[TABLE]])
    insp = inspect(engine)
    if TABLE not in set(insp.get_table_names()):
        print(f'[ERROR] {TABLE} 未创建')
        sys.exit(1)

    cols = {c['name'] for c in insp.get_columns(TABLE)}
    expected = {
        'symbol',
        'bond_code',
        'name',
        'shareholder_meeting_date',
        'convert_price_before',
        'convert_price_after',
        'effective_date',
        'adjust_floor_price',
        'source',
    }
    missing = expected - cols
    if missing:
        print(f'[ERROR] {TABLE} 缺列: {sorted(missing)}')
        sys.exit(1)

    print(f'[OK] {TABLE} 已就绪（{len(cols)} 列）')


if __name__ == '__main__':
    main()
