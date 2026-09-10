# -*- coding: utf-8 -*-
"""为 market 域创建可转债条款表（#1285 消费侧 / #1393）。

- convertible_bond_terms：可转债静态条款（强赎触发价 / 转股价值 / 溢价率 /
  评级 / 到期日 / 规模 / 强赎天计数等）

该表为新建（无存量数据），经 Base.metadata.create_all 建表即可，幂等：已存在则跳过。

用法（在 backend 目录；用 -m 以便 cwd 进入 sys.path —— 部分环境下
`pdm run python scripts/xx.py` 会因找不到 app 包而 ImportError）：
    pdm run python -m scripts.migrate_convertible_bond_terms
"""

import sys

from sqlalchemy import inspect, text

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

    # create_all 不会 ALTER 既有表；早期版本落库过本表（缺强赎状态/触发比）时幂等补列，
    # 避免「no such column」以及 init_db 的 schema 漂移守卫拒绝启动。
    existing_cols = {c['name'] for c in insp.get_columns('convertible_bond_terms')}
    for col, ddl in (
        ('redeem_trigger_ratio', 'ALTER TABLE convertible_bond_terms ADD COLUMN redeem_trigger_ratio NUMERIC(6, 2)'),
        ('redeem_status', 'ALTER TABLE convertible_bond_terms ADD COLUMN redeem_status VARCHAR(20)'),
    ):
        if col not in existing_cols:
            with engine.begin() as conn:
                conn.execute(text(ddl))
            print(f'[OK] 补充列 {col}')

    print('[OK] convertible_bond_terms 已就绪')


if __name__ == '__main__':
    main()
