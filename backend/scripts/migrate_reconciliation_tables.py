# -*- coding: utf-8 -*-
"""为既有 SQLite 数据库创建统一对账框架三表（#1232 §8.1 / P1）。

- discrepancies：活跃对账差异（按业务键 upsert）
- reconciliation_runs：对账运行记录
- adjustment_logs：审计日志

三表均为新建（无存量数据），通过 SQLAlchemy Base.metadata.create_all 建表即可，
仅对新库（invest.db）执行。幂等：已存在的表跳过。

用法（在 backend 目录）：
    pdm run python scripts/migrate_reconciliation_tables.py
"""

import sys


def main() -> None:
    # 导入 Base 与全部模型（确保 reconciliation models 注册进 metadata）
    import app.domains.reconciliation.models  # noqa: F401
    from app.core.database import Base
    from app.core.db_factory import DOMAIN_USER, DatabaseFactory

    # 三表为 user 域，必须建在 user 引擎（与 init_db / user_session 一致），
    # 且仅建这三张表，避免误建其它域的表到 user 库。
    engine = DatabaseFactory.create(DOMAIN_USER)
    print(f'目标引擎: {engine.url}')
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Base.metadata.tables['discrepancies'],
            Base.metadata.tables['reconciliation_runs'],
            Base.metadata.tables['adjustment_logs'],
        ],
    )
    # 校验三表已建
    from sqlalchemy import inspect

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    expected = {'discrepancies', 'reconciliation_runs', 'adjustment_logs'}
    missing = expected - tables
    if missing:
        print(f'[ERROR] 以下表未创建: {missing}')
        sys.exit(1)
    print(f'[OK] 统一对账三表已就绪: {sorted(expected & tables)}')


if __name__ == '__main__':
    main()
