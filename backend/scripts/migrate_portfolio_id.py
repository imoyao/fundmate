# -*- coding: utf-8 -*-
"""为 positions 表补充 portfolio_id 列（D20 持仓级组合），并回填存量数据。

背景：
- D20 决策「组合收敛为持仓级概念」：positions 增加可空 portfolio_id，
  空值 = 继承账户(ledger)的默认组合 ledger.portfolio_id。
- 关联键一律用 ledger_id / portfolio_id（FK），**不再用 account_name 字符串匹配**，
  避免账户改名断链 / 串仓。
- 启动期 _validate_schema 会拒绝缺列，因此存量库必须先跑本迁移再启动。

幂等：
- 列已存在则跳过 ALTER。
- 回填仅覆盖 portfolio_id IS NULL 的行（已显式改派的不会被覆盖）。
- 兼容双库：app 域引擎 + user 域引擎都跑一遍（user 域无独立库时二者为同一文件，重复跑无害）。

校验：
- 回填后若仍存在 ledger_id IS NULL 的持仓（异常数据），打印告警并汇总，
  但不阻断（此类持仓本就无法归属，需在业务侧修复）。
"""

from sqlalchemy import inspect, text

from app.core.db_factory import DOMAIN_APP, DOMAIN_USER, DatabaseFactory


def _migrate_on_engine(engine, label: str) -> None:
    """在单个引擎上执行 ALTER + 回填。"""
    inspector = inspect(engine)
    if 'positions' not in inspector.get_table_names():
        print(f'[{label}] 无 positions 表，跳过')
        return

    cols = {c['name'] for c in inspector.get_columns('positions')}
    if 'portfolio_id' not in cols:
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE positions ADD COLUMN portfolio_id INTEGER'))
        print(f'[{label}] 已添加 positions.portfolio_id 列')
    else:
        print(f'[{label}] positions.portfolio_id 列已存在，跳过 ALTER')

    # 回填：继承账户(ledger)的默认组合
    with engine.begin() as conn:
        conn.execute(
            text(
                'UPDATE positions '
                'SET portfolio_id = (SELECT l.portfolio_id FROM ledgers l WHERE l.id = positions.ledger_id) '
                'WHERE positions.portfolio_id IS NULL'
            )
        )

    # 校验：是否还有 ledger_id 为 NULL 的孤立持仓（无法归属）
    with engine.connect() as conn:
        orphan = conn.execute(text('SELECT COUNT(*) FROM positions WHERE ledger_id IS NULL')).scalar()
    if orphan:
        print(f'[WARN][{label}] 存在 {orphan} 条 ledger_id 为 NULL 的持仓，无法归属组合，请业务侧修复')

    # 校验：ledger_id 非空但指向不存在账户（悬空外键）的持仓
    # 这类持仓回填时子查询取不到 ledger.portfolio_id，会留下 portfolio_id 为 NULL 的空壳，
    # 需在业务侧清理无效 ledger_id 后再迁移。
    with engine.connect() as conn:
        dangling = conn.execute(
            text(
                'SELECT COUNT(*) FROM positions p '
                'WHERE p.ledger_id IS NOT NULL '
                'AND NOT EXISTS (SELECT 1 FROM ledgers l WHERE l.id = p.ledger_id)'
            )
        ).scalar()
    if dangling:
        print(f'[WARN][{label}] 存在 {dangling} 条 ledger_id 指向不存在账户的持仓（悬空外键），请业务侧修复')

    print(f'[{label}] 回填完成（组合归属已继承账户默认组合）')


def main() -> None:
    print('=== positions.portfolio_id 迁移（D20 持仓级组合）===')
    # app 域（单库模式下即主库）
    app_eng = DatabaseFactory.create(DOMAIN_APP)
    _migrate_on_engine(app_eng, label='app')

    # user 域（独立库时单独跑；回退同库时重复跑无害）
    user_eng = DatabaseFactory.create(DOMAIN_USER)
    if user_eng is not app_eng:
        _migrate_on_engine(user_eng, label='user')

    print('=== 迁移结束 ===')


if __name__ == '__main__':
    main()
