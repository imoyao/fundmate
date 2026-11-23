# -*- coding: utf-8 -*-
"""ledgers 表结构迁移（账户可见性，#3246 / D125）.

为什么单独成模块：``core/migrations.py`` 已 3000+ 行、被 ``scripts/guard_service_size.py``
冻结在基线，新增函数必然顶破行数闸门；本文件只服务 ledgers 一张表的可见性两列。

## 为什么加列不带 DEFAULT、回填走 UPDATE

``ALTER TABLE ... ADD COLUMN visibility VARCHAR(10) DEFAULT 'private'`` 会把**存量行**
一并变成 private——升级后同一 family 的其它账号立刻看不见账户，用户会以为数据丢了
（本机 16 个账户、4 个同家庭账号）。所以 DDL 不带默认值（存量行取到 NULL），再用
``UPDATE ... WHERE visibility IS NULL`` 回填 shared；**新行**由 ORM 的
``default='private'`` 决定。这样「存量 shared + 新行 private」同时成立，且幂等
（重复跑只补 NULL 行，不会把用户后来改回的 private 再翻成 shared）。

加列一律走 ``migrations._add_columns_if_missing``（PG 用 ``ADD COLUMN IF NOT EXISTS``），
不重写方言分支——本仓没有 Alembic、``create_all()`` 又不给存量表加列。
"""

from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.migrations import _add_columns_if_missing, _table_exists

# 不带 NOT NULL / DEFAULT：存量行的值必须由下面的 UPDATE 决定，而不是 DDL 默认值
VISIBILITY_DDL = 'VARCHAR(10)'
OWNER_USER_ID_DDL = 'INTEGER'
BACKFILL_VISIBILITY = 'shared'
# 加列清单提成模块常量：迁移函数要压进 NEW_FILE_LIMITS 的单函数 14 行上限
_COLUMNS = [('visibility', VISIBILITY_DDL), ('owner_user_id', OWNER_USER_ID_DDL)]


def _backfill_visibility(engine: Engine) -> int:
    """把 visibility 为 NULL 的存量行回填 shared（幂等）；返回写入行数."""
    with engine.connect() as conn:
        result = conn.execute(
            text('UPDATE ledgers SET visibility = :v WHERE visibility IS NULL'),
            {'v': BACKFILL_VISIBILITY},
        )
        conn.commit()
        return result.rowcount or 0


def migrate_ledger_visibility(engine: Engine) -> str:
    """ledgers 补 visibility / owner_user_id 两列并回填存量行（#3246）."""
    if not _table_exists(engine, 'ledgers'):
        return '[SKIP] ledgers 表不存在（空库，init_db 将按新模型建表）'

    added = _add_columns_if_missing(engine, 'ledgers', _COLUMNS)
    filled = _backfill_visibility(engine)
    if added or filled:
        logger.info(f'[OK] ledgers 增加列 {added}，回填可见性 {filled} 行')
        return f'[OK] 增加列 {added}，回填可见性 {filled} 行'
    return '[SKIP] ledgers.visibility / owner_user_id 已存在且无待回填行'
