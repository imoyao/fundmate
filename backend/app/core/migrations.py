# -*- coding: utf-8 -*-
"""启动期数据库迁移（在 init_db 中按数据域自动执行，幂等、可重复跑）。

背景：SQLite 不支持 ALTER 改约束/加列，存量库的结构演进只能靠「建新表→拷贝→删旧→改名」
的标准重建流程。这些迁移原本是 scripts/ 下的手动脚本，但存量库（含生产）若只靠手动跑，
会出现「代码已回归基线、库却仍是旧约束」的静默漂移（#1362 评审 #3：watchlist 唯一键）。
故统一收敛到本模块，由 init_db 按数据域在启动时自动执行，与「库内其他迁移一致」。

每个迁移函数约定：
- 入参 engine（对应数据域引擎）；
- 幂等：目标结构已存在则跳过；
- 失败显式抛错（不静默吞掉，避免带病启动）。

**全引擎覆盖（2026-10-23，#2534）**：迁移必须同时管 SQLite 与 Postgres
（生产 user 域是 Supabase PG、market 域是 Turso/libsql）。本仓没有 Alembic，
``create_all()`` 只建缺失的表、不给存量表加列/加索引——「非 SQLite 就跳过」
等于「生产的库永远不迁移」，而 ``init_db()`` 末尾的 ``_validate_schema`` 会因
结构漂移**拒绝启动**（#2469 / #2532 两次生产停摆的根因）。故：

- 加列一律走 ``_add_columns_if_missing``，建索引一律走 ``_ensure_index``
  （方言分支已在 helper 内收敛，迁移函数里禁止裸写 ALTER / CREATE INDEX）；
- 数据回填用标准 SQL（两种引擎通用）；确需方言差异时按 ``_is_postgres``
  显式分支并**两侧都写测试**；
- 静态守卫 ``scripts/guard_migrations_pg_aware.py`` 拦下新的「非 SQLite 就跳过」
  早退；存量按函数指纹基线冻结，改到一个函数就顺手收一个基线条目。
"""

import os
import re
from typing import List

from loguru import logger
from sqlalchemy import Engine, inspect, text

# ── user 域 watchlist 表补列（#2469）────────────────────────────────────────
#
# 生产 user 域（Supabase Postgres）上的 watchlist 三表是**旧结构**：
#   - watchlist_groups：缺 sort_order / is_visible / entity_type / family_id；
#   - watchlist_item_tags：缺 id（自增主键）。
# 后果：`_validate_schema` 判「库结构与模型不一致」→ init_db 直接拒绝启动
# → 每日调度（#1490）全线停摆（实测 run 39773356610，2026-10-22）。
#
# ⚠️ 与仓内既有 watchlist 迁移的关键区别：那些迁移都**只跑 SQLite**
# （「非 SQLite 引擎，列由 ORM 模型/迁移工具负责」）——而生产 user 域恰恰是 Postgres，
# 且没有任何工具会替它补列（Supabase 侧是手工建表）。**本条是第一条管 PG 侧的**
_WATCHLIST_GROUP_COLUMNS = (
    # (列名, 类型与默认值 DDL 片段)
    ('sort_order', 'INTEGER DEFAULT 0'),
    ('is_visible', 'BOOLEAN DEFAULT TRUE'),
    ('entity_type', "VARCHAR(20) DEFAULT 'ASSET'"),
    # family_id 来自 FamilyScopedMixin（default=1）：存量行按「默认家庭 1」收编，
    # 与该 mixin 的语义一致（默认家庭 1 兼容既有单用户数据）。
    ('family_id', 'INTEGER NOT NULL DEFAULT 1'),
)

#: watchlist_groups.family_id 的索引（模型声明 index=True → 默认名 ix_<表>_<列>）
_WATCHLIST_GROUP_FAMILY_INDEX = 'ix_watchlist_groups_family_id'


def _is_postgres(engine: Engine) -> bool:
    url = str(getattr(engine, 'url', '') or '')
    return url.startswith('postgres')


def _add_column_sql(table: str, name: str, ddl: str, is_pg: bool) -> str:
    """加列 SQL：PG 用 ``IF NOT EXISTS``（并发友好），SQLite 不支持该语法故不加。"""
    if is_pg:
        return f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {ddl}'
    return f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'


def _table_exists(engine: Engine, table: str) -> bool:
    """表是否存在（dialect 无关反射）。空库（create_all 尚未建表）时为 False。"""
    return table in set(inspect(engine).get_table_names())


def _add_columns_if_missing(engine: Engine, table: str, columns) -> List[str]:
    """给 ``table`` 补齐 ``columns``（(列名, DDL) 序列）中缺失的列，返回实际加上的列名。

    ## 为什么必须收敛到这个单一通道（#2534）

    加列迁移此前散落着两种死法：

    1. **SQLite-only 早退**（「非 SQLite 引擎，列由 ORM 模型/迁移工具负责」）——
       而本仓没有 Alembic、``create_all()`` 又不给存量表加列，生产 user 域
       （Supabase Postgres）的列**永远加不上**；``_validate_schema`` 再判
       「库结构与模型不一致」拒绝启动。#2469 与 #2532 两次生产停摆同此根因。
    2. **每个函数各写一遍** inspect→ALTER→commit：漏 commit、漏自校验的变体
       在本地全绿、在启动路径上炸。

    本函数是加列的唯一允许通道：

    - 方言分支收敛在 ``_add_column_sql``（PG 用 ``ADD COLUMN IF NOT EXISTS``）；
    - 幂等：列已存在则不发 DDL，可重复跑；
    - 收尾自校验：加完仍缺列 ⇒ 抛错（迁移失败必须显性，不留半截状态）；
    - 表不存在（空库）⇒ 返回 ``[]``（create_all 会按新模型建表，不替它兜底）。

    配套静态守卫 ``scripts/guard_migrations_pg_aware.py``：迁移里再出现
    「非 SQLite 就跳过」的新早退即报红（存量按函数指纹基线冻结，改一个收一个）。
    """
    if not _table_exists(engine, table):
        return []
    is_pg = _is_postgres(engine)
    existing = {c['name'] for c in inspect(engine).get_columns(table)}
    added: List[str] = []
    with engine.connect() as conn:
        for name, ddl in columns:
            if name not in existing:
                conn.execute(text(_add_column_sql(table, name, ddl, is_pg)))
                added.append(name)
        conn.commit()
    if added:
        # 自校验：DDL 若被引擎静默忽略（PG 上 IF NOT EXISTS 不会静默失败，但
        # 权限/只读副本会），这里必须让调用方看到，而不是返回「看起来 OK」。
        after = {c['name'] for c in inspect(engine).get_columns(table)}
        missing = [n for n in added if n not in after]
        if missing:
            raise RuntimeError(f'{table} 加列后仍缺列 {missing}（引擎 {"Postgres" if is_pg else "SQLite"}），迁移失败')
    return added


def _index_exists(engine: Engine, table: str, index_name: str) -> bool:
    """按**名**判断索引是否存在（表达式索引也能判）。

    方言差异是实测逼出来的：SQLAlchemy 对 SQLite 的反射**不曝露表达式索引**
    （``COALESCE(...)`` 的列清单解析不出来，``get_indexes()`` 直接跳过整条），
    费率三表的唯一索引正是表达式索引——按反射判会把「已建成」误判成「没建成」
    （#2534 首版即踩中，迁移每次启动都抛错）。故 SQLite 侧查 ``sqlite_master``
    （系统表按名列索引，与表达式无关），PG 侧反射曝露名字，用 ``get_indexes()``。
    """
    if _is_postgres(engine):
        return index_name in {i['name'] for i in inspect(engine).get_indexes(table)}
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND name=:n"),
            {'n': index_name},
        ).scalar()
    return row is not None


def _ensure_index(engine: Engine, index_name: str, ddl: str, *, table: str) -> bool:
    """建索引（幂等）：执行自带 ``IF NOT EXISTS`` 的 DDL，按**名**校验，缺了抛错。

    返回 True = 本次执行了 DDL，False = 已存在（无 DDL 发出）。

    PG 与 SQLite 都支持 ``CREATE [UNIQUE] INDEX IF NOT EXISTS``，故**无需方言分支**；
    校验按名走 ``_index_exists``（表达式索引的反射差异见其 docstring）。
    """
    if not _table_exists(engine, table):
        return False
    existed = _index_exists(engine, table, index_name)
    if not existed:
        with engine.connect() as conn:
            conn.execute(text(ddl))
            conn.commit()
    if not _index_exists(engine, table, index_name):
        raise RuntimeError(f'索引 {index_name} 创建后校验失败（表 {table}）')
    return not existed


def _add_id_serial_sql(table: str, is_pg: bool) -> str:
    """加自增主键列 SQL：PG 用 ``SERIAL``（自带序列默认值，新行自动取号）。"""
    if is_pg:
        return f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS id SERIAL'
    return f'ALTER TABLE {table} ADD COLUMN id INTEGER'


def _sqlite_rebuild_watchlist_item_tags(engine: Engine) -> str:
    """SQLite：给 watchlist_item_tags 补自增主键 id（SQLite 不许 ALTER 加主键列）。

    走标准重建流程：建新表 → 拷贝（id 取旧表 rowid，唯一且非空）→ 删旧 → 改名。
    旧 DDL 的其余部分（唯一约束、外键、列序）原样保留，只插入 id 列与主键。
    """
    with engine.connect() as conn:
        ddl = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='watchlist_item_tags'")
        ).scalar()
        if ddl is None:
            return '[SKIP] watchlist_item_tags 表不存在（空库，init_db 将按新模型建表）'
        # ⚠️ 不能用子串判断「id 是否已存在」：`item_id INTEGER NOT NULL` 里也含
        # `id INTEGER NOT NULL` —— 那会让「缺 id 的旧表」被误判成「已有 id」而跳过重建
        # （本迁移首版即如此，被收尾自校验当场抓住）。故按**列名**判断。
        if 'id' in {c['name'] for c in inspect(engine).get_columns('watchlist_item_tags')}:
            return '[SKIP] watchlist_item_tags.id 已存在'

        new_ddl = ddl.replace(
            'CREATE TABLE watchlist_item_tags',
            'CREATE TABLE watchlist_item_tags_new',
            1,
        )
        # 插入 id 列（紧跟表名后）与主键（追加在末尾括号前）
        new_ddl = new_ddl.replace(
            'CREATE TABLE watchlist_item_tags_new (',
            'CREATE TABLE watchlist_item_tags_new (id INTEGER NOT NULL, ',
            1,
        )
        if 'PRIMARY KEY' in new_ddl:
            # 旧表已有主键（可能是复合键）⇒ 只能追加 id，不能再加一个 PRIMARY KEY
            logger.warning('[watchlist_item_tags] 旧表已有主键，id 仅作为普通列补入（不覆盖既有主键）')
        else:
            new_ddl = re.sub(r'\)\s*$', ', PRIMARY KEY (id))', new_ddl, count=1)
        if not re.search(r'\bid\s+INTEGER\s+NOT\s+NULL', new_ddl):
            raise RuntimeError(f'watchlist_item_tags 重建 DDL 拼装失败：\n{ddl}')

        cols = [c['name'] for c in inspect(engine).get_columns('watchlist_item_tags')]
        if 'id' in cols:  # 竞态：别处已加
            return '[SKIP] watchlist_item_tags.id 已存在'
        col_list = ', '.join(cols)

        conn.execute(text('PRAGMA foreign_keys=OFF'))
        conn.execute(text(new_ddl))
        # id 取旧表 rowid：唯一且非空；SQLite 的 rowid 从 1 起
        conn.execute(
            text(
                f'INSERT INTO watchlist_item_tags_new (id, {col_list}) '
                f'SELECT rowid, {col_list} FROM watchlist_item_tags'
            )
        )
        conn.execute(text('DROP TABLE watchlist_item_tags'))
        conn.execute(text('ALTER TABLE watchlist_item_tags_new RENAME TO watchlist_item_tags'))
        conn.commit()
    return '[OK] watchlist_item_tags 已重建并补上 id 主键'


def migrate_watchlist_user_domain_columns(engine: Engine) -> str:
    """user 域 watchlist 三表补齐模型列（#2469）。

    ## 为什么需要

    生产 user 域（Supabase Postgres）上的 watchlist 表是**旧结构**：
    ``watchlist_groups`` 缺 ``sort_order`` / ``is_visible`` / ``entity_type`` / ``family_id``，
    ``watchlist_item_tags`` 缺 ``id``（自增主键）。
    于是 ``_validate_schema`` 判「库结构与模型不一致」并**拒绝启动**，
    每日调度（#1490）随之全线停摆——净值刷新、温度计、资产快照全部拿不到新数据。

    ## 与既有迁移的关键区别

    仓内既有的 watchlist 迁移都**只跑 SQLite**（注释写「非 SQLite 引擎，列由 ORM 模型 /
    迁移工具负责」）。但生产 user 域恰恰是 Postgres，而那套「迁移工具」在本仓并不存在
    （Supabase 侧是手工建表）——**这就是漂移一直没人补上的原因**。
    本迁移是**第一条管 PG 侧**的，故不能沿用「非 SQLite 就跳过」的写法。

    ## 做法

    - **只加列**：不改既有列、不删数据、不回填业务数据；
    - 已有列一律跳过（**幂等**，可重复跑）；
    - 新列带默认值，存量行按默认值收编（family_id=1 即「默认家庭」，与
      ``FamilyScopedMixin.default=1`` 一致）；
    - ``watchlist_item_tags.id``：PG 用 ``SERIAL``（自带序列默认值，新行自动取号）；
      SQLite 走「建新表→拷贝→删旧→改名」重建（SQLite 不许 ALTER 加主键列）；
    - **收尾自校验**：目标列必须在，缺了直接抛错——迁移失败必须显性，不留半截状态。
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    notes: List[str] = []

    # ── watchlist_groups：四列 + family_id 索引 ──
    if 'watchlist_groups' in tables:
        existing = {c['name'] for c in inspector.get_columns('watchlist_groups')}
        added: List[str] = []
        with engine.connect() as conn:
            for name, ddl in _WATCHLIST_GROUP_COLUMNS:
                if name in existing:
                    continue
                conn.execute(text(_add_column_sql('watchlist_groups', name, ddl, _is_postgres(engine))))
                added.append(name)
            conn.commit()
        if added:
            notes.append(f'watchlist_groups 加列 {added}')
    else:
        notes.append('watchlist_groups 表不存在（空库，交给 create_all 建表）')

    # ── watchlist_item_tags：id 主键 ──
    if 'watchlist_item_tags' in tables:
        existing = {c['name'] for c in inspector.get_columns('watchlist_item_tags')}
        if 'id' in existing:
            notes.append('watchlist_item_tags.id 已存在')
        elif _is_postgres(engine):
            with engine.connect() as conn:
                # SERIAL = INTEGER + 序列默认值 + NOT NULL：存量行按 nextval 补号，新行自动取号
                conn.execute(text(_add_id_serial_sql('watchlist_item_tags', True)))
                conn.commit()
            notes.append('watchlist_item_tags 加 id 列（SERIAL）')
        else:
            notes.append(_sqlite_rebuild_watchlist_item_tags(engine))
    else:
        notes.append('watchlist_item_tags 表不存在（空库，交给 create_all 建表）')

    # ── 自校验：目标列必须在（迁移失败必须显性）──
    inspector = inspect(engine)
    if 'watchlist_groups' in set(inspector.get_table_names()):
        cols = {c['name'] for c in inspector.get_columns('watchlist_groups')}
        missing = [name for name, _ in _WATCHLIST_GROUP_COLUMNS if name not in cols]
        if missing:
            raise RuntimeError(f'watchlist_groups 补列后仍缺列：{missing}')
    if 'watchlist_item_tags' in set(inspector.get_table_names()):
        cols = {c['name'] for c in inspector.get_columns('watchlist_item_tags')}
        if 'id' not in cols:
            raise RuntimeError('watchlist_item_tags 补列后仍缺 id 列')

    # ── family_id 索引：放在自校验**之后**建 ──
    # 顺序有讲究：列没补上时建索引会先炸一个「no such column」，
    # 报错误导（像是索引的问题），而真实原因是「列没加上」。自校验先跑，错误才说人话。
    if 'watchlist_groups' in set(inspector.get_table_names()):
        with engine.connect() as conn:
            conn.execute(
                text(f'CREATE INDEX IF NOT EXISTS {_WATCHLIST_GROUP_FAMILY_INDEX} ON watchlist_groups (family_id)')
            )
            conn.commit()

    summary = '；'.join(notes)
    logger.info(f'[watchlist 补列] {summary}')
    return f'[OK] {summary}'


def migrate_watchlist_unique_key(engine: Engine) -> str:
    """自选表唯一键回归基线：(symbol, venue) → (symbol, market, venue)（#1286 / #1362 评审 #3）。

    防 000001 上证指数 vs 平安银行跨市场同码冲突。SQLite 不支持直接改约束，
    走「建新表→拷贝→删旧→改名」标准重建流程。

    仅 SQLite 需要此重建（Postgres 等由 ORM 模型 / 迁移工具负责唯一键，无 sqlite_master
    概念）；非 SQLite 引擎直接跳过，避免 init_db 在 Supabase 路径上误跑 SQLite 专属 SQL。
    """
    url = str(getattr(engine, 'url', '') or '')
    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎（如 Supabase Postgres），唯一键由 ORM 模型/迁移工具负责，无需重建'

    with engine.connect() as conn:
        ddl = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='watchlist'")).scalar()
        if ddl is None:
            return '[SKIP] watchlist 表不存在（空库，init_db 将按新约束建表）'
        if 'uk_watchlist_family_symbol_market_venue' in ddl:
            # 已是家庭维度唯一键（由 migrate_watchlist_family_scoped_unique_key 升级而来）：
            # 本迁移的目标（纳入 market）已包含在其中，直接跳过，避免误判为「结构异常」。
            return '[SKIP] 新唯一键（含 family_id）已存在，无需迁移'
        if 'uk_watchlist_symbol_market_venue' in ddl:
            return '[SKIP] 新唯一键已存在，无需迁移'
        if 'uk_watchlist_symbol_venue' not in ddl:
            raise RuntimeError(f'未找到旧约束 uk_watchlist_symbol_venue，watchlist 表结构异常，请人工确认：\n{ddl}')

        new_ddl = ddl.replace(
            'CONSTRAINT uk_watchlist_symbol_venue UNIQUE (symbol, venue)',
            'CONSTRAINT uk_watchlist_symbol_market_venue UNIQUE (symbol, market, venue)',
        )
        if new_ddl == ddl:
            # 无名约束兜底：UNIQUE (symbol, venue) 形态
            new_ddl = re.sub(
                r'UNIQUE\s*\(\s*symbol\s*,\s*venue\s*\)',
                'CONSTRAINT uk_watchlist_symbol_market_venue UNIQUE (symbol, market, venue)',
                ddl,
                count=1,
            )
        if new_ddl == ddl:
            raise RuntimeError(f'约束替换失败，watchlist 表结构：\n{ddl}')

        # 用当前表的真实列动态构造拷贝 SQL，避免模型增删列后硬编码列清单失效
        cols = [c['name'] for c in inspect(engine).get_columns('watchlist')]
        col_list = ', '.join(cols)

        new_ddl = new_ddl.replace('CREATE TABLE watchlist', 'CREATE TABLE watchlist_new', 1)
        conn.execute(text('PRAGMA foreign_keys=OFF'))
        conn.execute(text(new_ddl))
        conn.execute(text(f'INSERT INTO watchlist_new SELECT {col_list} FROM watchlist'))
        conn.execute(text('DROP TABLE watchlist'))
        conn.execute(text('ALTER TABLE watchlist_new RENAME TO watchlist'))
        conn.commit()

    with engine.connect() as conn:
        ddl2 = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='watchlist'")).scalar()
    idx = [i['name'] for i in inspect(engine).get_indexes('watchlist') if i.get('unique')]
    if 'uk_watchlist_symbol_market_venue' in (ddl2 or ''):
        logger.info(f'[OK] watchlist 唯一键已迁移为 (symbol, market, venue)；当前唯一索引: {idx}')
        return f'[OK] 唯一键已迁移为 (symbol, market, venue)；当前唯一索引: {idx}'
    raise RuntimeError('watchlist 唯一键迁移后校验失败')


def migrate_watchlist_family_scoped_unique_key(engine: Engine) -> str:
    """自选表唯一键补 family_id：(symbol, market, venue) → (family_id, symbol, market, venue)（#1491 评审阻断项）。

    watchlist 继承 FamilyScopedMixin（含 family_id），写入查重也按家庭维度
    （watchlist_service.create_watchlist_item 的 filter_by(..., family_id=family_id)）。
    唯一键不含 family_id 时：家庭 B 关注家庭 A 已关注的同一标的，应用层查重判定「不存在」，
    INSERT 却撞 DB 唯一约束 → IntegrityError(500)。即一个家庭关注过的标的，其他家庭再也加不进来。

    与前一个迁移同法：SQLite 不支持改约束，走「建新表→拷贝→删旧→改名」标准重建流程；
    非 SQLite（Supabase Postgres）由 ORM 模型 / 迁移工具负责，直接跳过。
    兼容两种前序形态：(symbol, market, venue) 与更旧的 (symbol, venue)。
    """
    url = str(getattr(engine, 'url', '') or '')
    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎（如 Supabase Postgres），唯一键由 ORM 模型/迁移工具负责，无需重建'

    with engine.connect() as conn:
        ddl = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='watchlist'")).scalar()
        if ddl is None:
            return '[SKIP] watchlist 表不存在（空库，init_db 将按新约束建表）'
        if 'uk_watchlist_family_symbol_market_venue' in ddl:
            return '[SKIP] 家庭维度唯一键已存在，无需迁移'

        cols = [c['name'] for c in inspect(engine).get_columns('watchlist')]
        if 'family_id' not in cols:
            raise RuntimeError(f'watchlist 表无 family_id 列，结构异常，请人工确认：\n{ddl}')

        new_constraint = 'CONSTRAINT uk_watchlist_family_symbol_market_venue UNIQUE (family_id, symbol, market, venue)'
        new_ddl = ddl.replace(
            'CONSTRAINT uk_watchlist_symbol_market_venue UNIQUE (symbol, market, venue)',
            new_constraint,
        )
        if new_ddl == ddl:
            # 更早形态：(symbol, venue)（前一个迁移尚未跑）
            new_ddl = ddl.replace(
                'CONSTRAINT uk_watchlist_symbol_venue UNIQUE (symbol, venue)',
                new_constraint,
            )
        if new_ddl == ddl:
            # 无名约束兜底：UNIQUE (symbol, market, venue) / UNIQUE (symbol, venue)
            new_ddl = re.sub(
                r'UNIQUE\s*\(\s*symbol\s*,\s*m\w*\s*,\s*venue\s*\)',
                new_constraint,
                ddl,
                count=1,
            )
        if new_ddl == ddl:
            new_ddl = re.sub(
                r'UNIQUE\s*\(\s*symbol\s*,\s*venue\s*\)',
                new_constraint,
                ddl,
                count=1,
            )
        if new_ddl == ddl:
            raise RuntimeError(f'约束替换失败，watchlist 表结构：\n{ddl}')

        col_list = ', '.join(cols)

        new_ddl = new_ddl.replace('CREATE TABLE watchlist', 'CREATE TABLE watchlist_new', 1)
        conn.execute(text('PRAGMA foreign_keys=OFF'))
        conn.execute(text(new_ddl))
        conn.execute(text(f'INSERT INTO watchlist_new SELECT {col_list} FROM watchlist'))
        conn.execute(text('DROP TABLE watchlist'))
        conn.execute(text('ALTER TABLE watchlist_new RENAME TO watchlist'))
        conn.commit()

    with engine.connect() as conn:
        ddl2 = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='watchlist'")).scalar()
    if 'uk_watchlist_family_symbol_market_venue' in (ddl2 or ''):
        logger.info('[OK] watchlist 唯一键已迁移为 (family_id, symbol, market, venue)')
        return '[OK] 唯一键已迁移为 (family_id, symbol, market, venue)'
    raise RuntimeError('watchlist 家庭维度唯一键迁移后校验失败')


def migrate_watchlist_venue_not_null(engine: Engine) -> str:
    """自选表 venue 历史 NULL 回填空串（#1286 / #1362 评审 #6）。

    SQLite UNIQUE 中 NULL 互不相等：venue 为 NULL 会让 (symbol, market, venue)
    唯一键对这行静默失效（同码条目可重复插入）。模型已加 nullable=False + default=''，
    但存量库的历史 NULL 必须靠本迁移回填。

    只回填数据、不改表结构：SQLite 加 NOT NULL 需整表重建（风险高于收益），
    新写入由 ORM 的 default='' 保证非空，唯一键语义已能生效。

    回填 SQL 是标准 ``UPDATE``（两种引擎通用），故本迁移**全引擎执行**——
    生产 user 域是 Postgres，「非 SQLite 就跳过」会让存量 NULL 永远躺在库里
    （#2534；唯一键对这类行失效正是本迁移要修的问题）。
    """
    insp = inspect(engine)
    if 'watchlist' not in insp.get_table_names():
        return '[SKIP] watchlist 表不存在（空库，init_db 将按新模型建表）'
    if 'venue' not in [c['name'] for c in insp.get_columns('watchlist')]:
        return '[SKIP] watchlist 表无 venue 列，跳过'

    with engine.connect() as conn:
        res = conn.execute(text("UPDATE watchlist SET venue = '' WHERE venue IS NULL"))
        conn.commit()
        n = res.rowcount or 0
    if n:
        logger.info(f'[OK] watchlist venue NULL 回填空串 {n} 行（唯一键对存量数据恢复生效）')
        return f'[OK] venue NULL 回填空串 {n} 行'
    return '[SKIP] 无 venue 为 NULL 的历史数据'


def migrate_watchlist_name_snapshot(engine: Engine) -> str:
    """watchlist 补 name 名称快照列（#1508）。

    背景：自选展示名此前**不落库**，只在读取时由 ``resolve_display_name`` 跨
    funds / index_catalog / securities / convertible_bond_terms / advisor_portfolios /
    managers 六张**码空间重叠**的表按裸码反查（index_catalog 与 funds 同码重叠 258 条，
    000300 指数=沪深300 / funds=德邦德利货币A），任何一次「未命中就回退别表」的猜测
    都可能给出**错名**（#1497 / #1499 的根因）。本迁移补上快照列，让名称随产品一起落库。

    加入方式：走 ``_add_columns_if_missing``（PG 用 ``ADD COLUMN IF NOT EXISTS``，
    SQLite 裸 ALTER，幂等由「列已存在则跳过」保证）。**不再按引擎早退**——
    生产 user 域是 Postgres，而本仓没有任何工具会替它加列（#2534，
    #2469 / #2532 两次停摆的根因都是「非 SQLite 就跳过」）。

    历史行 ``name`` 为 NULL → 读取端自动落回反查链，行为与迁移前一致（不倒退）；
    随后的买入（``ensure_watchlist_for_positions``）会顺带回填（``positions.name``）。
    """
    if not _table_exists(engine, 'watchlist'):
        return '[SKIP] watchlist 表不存在（空库，init_db 将按新模型建表）'

    added = _add_columns_if_missing(engine, 'watchlist', [('name', 'VARCHAR(100)')])
    if added:
        logger.info(f'[OK] watchlist 增加列: {added}')
        return f'[OK] 增加列 {added}'
    return '[SKIP] watchlist.name 快照列已存在'


def migrate_advisor_portfolio_metrics(engine: Engine) -> str:
    """advisor_portfolios 补 投顾品类差异化指标列（#1392）：区间收益 / 回撤 / 超额。

    SQLite / libsql 支持对「可空列」直接 ALTER ADD COLUMN（无需整表重建）。
    幂等：列已存在则跳过。两种引擎都由本迁移负责（走 ``_add_columns_if_missing``，
    PG 用 ``ADD COLUMN IF NOT EXISTS``）——生产 user 域是 Postgres，本仓没有
    Alembic、``create_all()`` 也不给存量表加列（#2534）。
    """
    if not _table_exists(engine, 'advisor_portfolios'):
        return '[SKIP] advisor_portfolios 表不存在（空库，init_db 将按新模型建表）'

    cols = [
        ('return_1w', 'NUMERIC(7,2)'),
        ('return_1m', 'NUMERIC(7,2)'),
        ('return_1y', 'NUMERIC(7,2)'),
        ('return_ytd', 'NUMERIC(7,2)'),
        ('return_since_incep', 'NUMERIC(7,2)'),
        ('benchmark', 'VARCHAR(50)'),
        ('max_drawdown', 'NUMERIC(6,2)'),
        ('excess_return', 'NUMERIC(7,2)'),
    ]
    added = _add_columns_if_missing(engine, 'advisor_portfolios', cols)
    if added:
        logger.info(f'[OK] advisor_portfolios 增加列: {added}')
        return f'[OK] 增加列 {added}'
    return '[SKIP] advisor_portfolios 指标列已存在'


def migrate_advisor_portfolio_metadata(engine: Engine) -> str:
    """advisor_portfolios 补且慢组合策展元数据列（#1468）。

    含两类：
    - 策展分类：``allocation``（五笔钱）/ ``product_type``（产品类型）
    - GetStrategyDetails 抓取：``volatility`` / ``sharpe_ratio`` / ``strategy_summary`` /
      ``source_url`` / ``nav`` / ``nav_date`` / ``return_1d`` / ``return_1q`` / ``return_6m``

    与 :func:`migrate_advisor_portfolio_metrics` 同源同法：SQLite / libsql 支持对「可空列」
    直接 ALTER ADD COLUMN（无需整表重建）。幂等：列已存在则跳过。两种引擎都由本迁移负责
    （走 ``_add_columns_if_missing``，PG 用 ``ADD COLUMN IF NOT EXISTS``）——生产 user 域
    是 Postgres，本仓没有 Alembic、``create_all()`` 也不给存量表加列（#2534）。
    """
    if not _table_exists(engine, 'advisor_portfolios'):
        return '[SKIP] advisor_portfolios 表不存在（空库，init_db 将按新模型建表）'

    cols = [
        ('volatility', 'NUMERIC(6,2)'),
        ('sharpe_ratio', 'NUMERIC(6,3)'),
        ('allocation', 'VARCHAR(20)'),
        ('product_type', 'VARCHAR(20)'),
        ('strategy_summary', 'VARCHAR(300)'),
        ('source_url', 'VARCHAR(120)'),
        ('nav', 'NUMERIC(12,6)'),
        ('nav_date', 'DATE'),
        ('return_1d', 'NUMERIC(7,2)'),
        ('return_1q', 'NUMERIC(7,2)'),
        ('return_6m', 'NUMERIC(7,2)'),
    ]
    added = _add_columns_if_missing(engine, 'advisor_portfolios', cols)
    if added:
        logger.info(f'[OK] advisor_portfolios 增加列: {added}')
        return f'[OK] 增加列 {added}'
    return '[SKIP] advisor_portfolios 元数据列已存在'


def migrate_advisor_portfolio_provenance(engine: Engine) -> str:
    """advisor_portfolios 补「数据来历 + 平台特有字段」列（#1392 Ports & Adapters 收口）。

    - ``source``：本行概览/指标最近一次写入来源（``tiantian`` / ``qieman`` / ``seed``），
      与 ``advisor_holdings.source`` 同口径——「这行数据是谁写的」此前无处回答；
    - ``extra``：canonical 概览覆盖不到的**平台特有字段**（JSON 原样保留），
      新增平台不必为此加列，日后真要补列时可回填，无需重新抓取。

    与 :func:`migrate_advisor_portfolio_metrics` 同源同法：SQLite / libsql 支持对「可空列」
    直接 ALTER ADD COLUMN（无需整表重建）。幂等：列已存在则跳过。两种引擎都由本迁移负责
    （走 ``_add_columns_if_missing``，PG 用 ``ADD COLUMN IF NOT EXISTS``）——生产 user 域
    是 Postgres，本仓没有 Alembic、``create_all()`` 也不给存量表加列（#2534）。
    """
    if not _table_exists(engine, 'advisor_portfolios'):
        return '[SKIP] advisor_portfolios 表不存在（空库，init_db 将按新模型建表）'

    cols = [
        ('source', 'VARCHAR(20)'),
        ('extra', 'JSON'),
    ]
    added = _add_columns_if_missing(engine, 'advisor_portfolios', cols)
    if added:
        logger.info(f'[OK] advisor_portfolios 增加列: {added}')
        return f'[OK] 增加列 {added}'
    return '[SKIP] advisor_portfolios 来历列已存在'


def migrate_positions_symbol_norm(engine: Engine) -> str:
    """positions 补归一身份列 `symbol_norm` + 唯一索引（#1662 后续）。

    ## 为什么

    #1662 的根因是 `positions` 的唯一约束是**字面量** `UNIQUE(ledger_id, symbol)`：
    `SZ004369` / `sz004369` / ` SZ004369 ` / `SH.004369` 在 SQLite 里是四个不同字符串，
    却是同一只基金 ⇒ 同一账户下同一持仓长出多行。PR #1665 修的是**读写路径**
    （写入侧显式传 venue、读侧按候选集查重），**约束层没动** —— 只要有一条写入路径
    漏传 venue / 拼错形态，重复行依然能落库。本迁移把约束补上。

    身份键构造见 `core/symbol_utils.symbol_identity`（`EXCHANGE:SZ159915` / `OTC:004369`），
    与审计脚本 `scripts/audit_symbol_venue_conformance.py` 共用 `core.venues.venue_of_row`，
    口径不分叉。

    ## 为什么不重建表

    SQLite 加列可直接 `ALTER TABLE ADD COLUMN`（可空列或带常量默认值的 NOT NULL 列），
    加索引可直接 `CREATE UNIQUE INDEX` —— 都不需要「建新表→拷贝→删旧→改名」。
    `invest.db` 已 1.2 GB 且带未 checkpoint 的 WAL，整表重建风险远高于收益。
    旧的 `uq_positions_ledger_symbol` **保留**（它更严，与新约束不冲突）。

    ## 存量有重复行时会怎样

    **显式抛错并给出修复命令**，不静默跳过、也不自动合并（合并持仓涉及份额与均价口径，
    必须由 `scripts/audit_symbol_venue_conformance.py --apply --merge` 在备份后执行）。
    与本模块「失败显式抛错，避免带病启动」的约定一致。

    幂等：列已存在则跳过加列、无空值则跳过回填、索引已存在则跳过创建。
    非 SQLite 引擎（Supabase Postgres）由 ORM 模型 / 迁移工具负责，直接跳过。

    重复检测**排除 `ledger_id IS NULL` 的行**：SQLite 的唯一索引把 NULL 视为互不相等，
    这类行本就不参与约束（与旧的字面量约束同语义），`GROUP BY` 却会把它们归到一组 ——
    不排除就会误报、进而无谓地阻断启动。
    """
    url = str(getattr(engine, 'url', '') or '')
    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎，列与索引由 ORM 模型/迁移工具负责'

    if 'positions' not in inspect(engine).get_table_names():
        return '[SKIP] positions 表不存在（空库，init_db 将按新模型建表）'

    from app.core.symbol_utils import symbol_identity

    actions: list[str] = []
    with engine.connect() as conn:
        existing = {c['name'] for c in inspect(engine).get_columns('positions')}
        if 'symbol_norm' not in existing:
            # NOT NULL 必须带常量默认值，SQLite 才允许 ADD COLUMN；随后立即回填真实身份，
            # 空串只是过渡态（空串行会被下面的重复检测当成同一身份报出来，不会静默放过）。
            conn.execute(text("ALTER TABLE positions ADD COLUMN symbol_norm VARCHAR(64) NOT NULL DEFAULT ''"))
            actions.append('加列 symbol_norm')

        rows = conn.execute(text('SELECT id, symbol, type, symbol_norm FROM positions')).fetchall()
        pending = [(r[0], r[1], r[2]) for r in rows if not r[3]]
        for rid, sym, atype in pending:
            conn.execute(
                text('UPDATE positions SET symbol_norm = :n WHERE id = :i'),
                {'n': symbol_identity(sym, atype), 'i': rid},
            )
        if pending:
            actions.append(f'回填 {len(pending)} 行')

        dupes = conn.execute(
            text(
                'SELECT ledger_id, symbol_norm, COUNT(*) AS n, GROUP_CONCAT(symbol) AS syms '
                'FROM positions WHERE ledger_id IS NOT NULL '
                'GROUP BY ledger_id, symbol_norm HAVING n > 1'
            )
        ).fetchall()
        if dupes:
            detail = '\n'.join(
                f'  - ledger_id={d[0]} symbol_norm={d[1]!r} 共 {d[2]} 行（symbol: {d[3]}）' for d in dupes
            )
            raise RuntimeError(
                f'positions 存在 {len(dupes)} 组「同账户同归一身份」的重复行，唯一索引无法建立：\n{detail}\n'
                '修复路径（会先自动备份）：\n'
                '  python scripts/audit_symbol_venue_conformance.py --apply --merge\n'
                '合并口径：份额相加、成交均价按份额加权重算，跨账户同码**不合并**（那是正常业务）。'
            )

        conn.execute(
            text(
                'CREATE UNIQUE INDEX IF NOT EXISTS uq_positions_ledger_symbol_norm '
                'ON positions (ledger_id, symbol_norm)'
            )
        )
        conn.commit()

    idx = [i['name'] for i in inspect(engine).get_indexes('positions') if i.get('unique')]
    if 'uq_positions_ledger_symbol_norm' not in idx:
        raise RuntimeError(f'positions.symbol_norm 唯一索引创建后校验失败，当前唯一索引: {idx}')
    if actions:
        logger.info(f'[OK] positions.symbol_norm 迁移完成：{"、".join(actions)}')
        return f'[OK] {"、".join(actions)}；唯一索引: uq_positions_ledger_symbol_norm'
    return '[SKIP] positions.symbol_norm 列与唯一索引均已就绪'


def migrate_channel_link_indexes(engine: Engine) -> str:
    """channel_links 补 to_symbol 索引（#1491 评审）。

    `to_symbol` 是查询 / join 字段（跨渠道关联回填与「ETF→联接」查询都按它过滤），
    模型此前未声明索引 → 按目标代码查找会全表扫描。

    PG 与 SQLite 都支持 `CREATE INDEX IF NOT EXISTS`，**无需方言分支**；`create_all`
    只建新表、不给存量表加索引，故与 watchlist 约束同法由 init_db 启动期兜底——
    且对两种引擎都兜底（生产 user 域是 Postgres，#2534：本仓没有 Alembic，
    「非 SQLite 就跳过」等于生产永远没索引）。
    """
    if not _table_exists(engine, 'channel_links'):
        return '[SKIP] channel_links 表不存在（空库，init_db 将按新模型建表）'

    _ensure_index(
        engine,
        'ix_channel_links_to_symbol',
        'CREATE INDEX IF NOT EXISTS ix_channel_links_to_symbol ON channel_links (to_symbol)',
        table='channel_links',
    )
    logger.info('[OK] channel_links.to_symbol 索引已就绪')
    return '[OK] channel_links.to_symbol 索引已就绪'


#: 费率三表的唯一约束 DDL（2026-10-18）。与 ORM 模型 ``__table_args__`` 逐字一致——
#: 那边让新库由 create_all 建出，这里给存量库补建；两处必须同源，改一处就要改两处。
#: 三元组：(索引名, 表名, DDL)——表名单列一项，供 ``_ensure_index`` 反射校验用
#: （从 DDL 字符串里解析表名太脆，改一次 SQL 形态就断）。
_FEE_UNIQUE_INDEX_DDL_ALL = (
    (
        'uq_fee_ratios_scope',
        'fee_ratios',
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_fee_ratios_scope ON fee_ratios '
        '(fund_code, fee_type, COALESCE(purchase_rule_id, -1), COALESCE(redeem_rule_id, -1))',
    ),
    (
        'uq_redeem_rules_range',
        'redeem_rules',
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_redeem_rules_range ON redeem_rules '
        '(COALESCE(start_day, -1), COALESCE(end_day, -1))',
    ),
    (
        'uq_purchase_rules_quota',
        'purchase_rules',
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_rules_quota ON purchase_rules '
        '(COALESCE(start_quota, -1), COALESCE(end_quota, -1))',
    ),
)


def _fee_duplication_report(engine: Engine) -> list[str]:
    """统计三张费率表里「会被唯一索引拒掉」的重复组，返回人类可读的问题列表。"""
    checks = (
        (
            'fee_ratios',
            '同一 (fund_code, fee_type, purchase_rule_id, redeem_rule_id) 存在多行',
            'SELECT COUNT(*) FROM (SELECT 1 FROM fee_ratios '
            'GROUP BY fund_code, fee_type, COALESCE(purchase_rule_id, -1), COALESCE(redeem_rule_id, -1) '
            'HAVING COUNT(*) > 1)',
        ),
        (
            'redeem_rules',
            '同一 (start_day, end_day) 区间存在多行',
            'SELECT COUNT(*) FROM (SELECT 1 FROM redeem_rules '
            'GROUP BY COALESCE(start_day, -1), COALESCE(end_day, -1) HAVING COUNT(*) > 1)',
        ),
        (
            'purchase_rules',
            '同一 (start_quota, end_quota) 区间存在多行',
            'SELECT COUNT(*) FROM (SELECT 1 FROM purchase_rules '
            'GROUP BY COALESCE(start_quota, -1), COALESCE(end_quota, -1) HAVING COUNT(*) > 1)',
        ),
    )
    problems = []
    with engine.connect() as conn:
        for table, desc, sql in checks:
            groups = conn.execute(text(sql)).scalar() or 0
            if groups:
                problems.append(f'{table}: {groups} 组重复（{desc}）')
    return problems


def migrate_fee_unique_indexes(engine: Engine) -> str:
    """费率三表补唯一约束（2026-10-18）。

    ## 为什么补

    ``fee_ratios`` / ``redeem_rules`` / ``purchase_rules`` 此前**一个索引都没有**。
    2026-05-31 的一次整表复制在库里留下 12,732 组逐字相同的副本行（fee_ratios
    25,471 行；重复对的 rate/currency/created_at/updated_at 全同 ⇒ 复制而非重写），
    用户可见表现是「赎回费率分布每档显示两次」。

    应用层已收口为 upsert + 结构校验 + 清残档，但那些闸只在**已知写路径**上生效；
    唯一约束是最后一道、也是唯一会让错误**当场报错**而不是静默通过的一道。

    ## 为什么必须用表达式索引

    SQLite 里 NULL 不参与唯一性判断，而 ``fee_ratios`` 的 ``purchase_rule_id``
    （redeem 行恒为 NULL）与 ``redeem_rules`` / ``purchase_rules`` 最后一档的
    ``end_day`` / ``end_quota`` 都是 NULL——普通唯一索引对它们形同虚设。故一律
    ``COALESCE(列, -1)`` 之后再比。

    ## 存量库有重复行时

    **fail closed**：直接抛错并指明处置命令，而不是「跳过不建」。跳过等于把刚修好的
    问题原样放回去，且没人会知道——重复行正是这样静默存在了五个月。

    ## 但修复窗口必须能启动应用（实测踩到）

    「同区间两个费率」这类重复行，正确的修复方式是**用修好的解析重新同步**，
    而重新同步要跑 ``sync_metadata.py``——它启动时就调 ``init_db``，于是 fail closed
    会把**修复路径自己**堵死（2026-10-18 实测：CLI 直接 RuntimeError 退出，一只都没跑）。

    故提供显式开关 ``ALLOW_FEE_DUPLICATES=1``：只在该环境下放行（记ERROR 日志、
    不建索引、继续启动），供「清理 / 重同步」这个窗口使用。默认不放行。

    ``create_all`` 只建新表、不给存量表加索引，故与 watchlist 约束同法由 init_db 兜底——
    且对两种引擎都兜底：表达式唯一索引 + ``IF NOT EXISTS`` 在 PG 与 SQLite 上都成立，
    「非 SQLite 就跳过」会让生产（Supabase PG）的费率表永远没有唯一约束（#2534；
    本仓没有 Alembic）。校验一律走 ``inspect().get_indexes()`` 的索引名，
    **不再查 ``sqlite_master``**（那张表只有 SQLite 有）。
    """
    present = set(inspect(engine).get_table_names())
    missing = [t for t in ('fee_ratios', 'redeem_rules', 'purchase_rules') if t not in present]
    if missing:
        return f'[SKIP] 表不存在（空库，init_db 将按新模型建表）: {missing}'

    problems = _fee_duplication_report(engine)
    if problems:
        detail = '\n  - '.join(problems)
        remediation = (
            'python backend/scripts/cleanup_fee_ratio_dupes.py --db <库路径>'
            '（默认 dry-run；确认后加 --apply，会自动写回滚 SQL）'
        )
        if os.getenv('ALLOW_FEE_DUPLICATES') == '1':
            msg = (
                '[BLOCKED] 费率三表仍有重复行，未建唯一索引（ALLOW_FEE_DUPLICATES=1 显式放行，'
                f'仅供清理/重同步窗口使用）:\n  - {detail}\n处理完成后请去掉该环境变量重启，'
                f'索引会自动补建。处置：{remediation}'
            )
            logger.error(msg)
            return msg
        raise RuntimeError(f'费率三表存在重复行，唯一索引无法建立：\n  - {detail}\n请先清理存量：{remediation}')

    for name, table, sql in _FEE_UNIQUE_INDEX_DDL_ALL:
        _ensure_index(engine, name, sql, table=table)

    msg = '[OK] 费率三表唯一约束已就绪: ' + ' / '.join(name for name, _t, _s in _FEE_UNIQUE_INDEX_DDL_ALL)
    logger.info(msg)
    return msg


def migrate_positions_price_columns(engine: Engine) -> str:
    """positions 补「当日盈亏」的基准列（#2007）：`prev_close` + `price_date`。

    ## 为什么需要

    当日盈亏 = (current_price − prev_close) × quantity。此前 `positions` 只落了
    `current_price`，而且**没有表达「这个价是哪一天的」**的列（`position_price` job
    同价不写以保护 `updated_at`，故 `updated_at` 也当不了价格日期）。于是两件事都做不到：
    算不出当日盈亏（缺上一确认价）；即便硬算，也说不清差额对应哪一天——用户会拿它当
    「今天赚了多少」，那正是最需要准确的数。

    ## 加列方式

    SQLite / libsql 对**可空列**支持直接 `ALTER TABLE ADD COLUMN`（无需整表重建），
    故两列都声明为可空：历史行没有基准价，只能 NULL；NULL 在读取端降级为「—」，
    **不写 0**（0 会被读成「今天没涨没跌」，那是编造）。

    幂等：列已存在则跳过。两种引擎都由本迁移负责（走 ``_add_columns_if_missing``，
    PG 用 ``ADD COLUMN IF NOT EXISTS``）——生产 user 域是 Postgres，本仓没有
    Alembic、``create_all()`` 也不给存量表加列（#2534）。

    ⚠️ 本迁移**只加列、不回填**：`prev_close` 是「上一确认价」，只能在写入
    `current_price` 的**同一批**里取到（`sync/jobs/position_price_job`），事后凭历史数据
    补不出时点正确的值（补错了比空着更糟）。存量行会在下次调度自然补齐。
    """
    if not _table_exists(engine, 'positions'):
        return '[SKIP] positions 表不存在（空库，init_db 将按新模型建表）'

    cols = [('prev_close', 'INTEGER'), ('price_date', 'DATE')]
    added = _add_columns_if_missing(engine, 'positions', cols)
    if added:
        logger.info(f'[OK] positions 增加列: {added}')
        return f'[OK] 增加列 {added}'
    return '[SKIP] positions.prev_close / price_date 已存在'


# ── #2239 拆分用的手写 DDL ────────────────────────────────────────────────────
# 刻意**不** import ``app.domains.funds.models``：core 层不得依赖 domains 层
# （`tests/core/test_layer_direction.py` R1 守卫：core → 上层一律违规），而这里干的是
# **建表**——除了 DDL 本身没有别的东西可依赖。代价是结构可能随模型漂移，故迁移末尾
# **自校验**两件事：任期列是否真的删掉、唯一约束是否真的存在
# （`_validate_schema` 只查「模型有列而库没列」，查不出「库多列」与「少约束」）。
_FUND_MANAGERS_NEW_DDL = """
CREATE TABLE fund_managers_new (
    id INTEGER NOT NULL,
    fund_id INTEGER NOT NULL,
    mgr_id INTEGER NOT NULL,
    is_classic BOOLEAN,
    PRIMARY KEY (id),
    CONSTRAINT uq_fund_managers_fund_mgr UNIQUE (fund_id, mgr_id),
    FOREIGN KEY(fund_id) REFERENCES funds (id),
    FOREIGN KEY(mgr_id) REFERENCES managers (id)
)
"""
_MANAGER_TENURES_DDL = """
CREATE TABLE IF NOT EXISTS manager_tenures (
    id INTEGER NOT NULL,
    fund_id INTEGER NOT NULL,
    mgr_id INTEGER NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    current BOOLEAN DEFAULT 0,
    source VARCHAR(20),
    created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
    updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
    PRIMARY KEY (id),
    CONSTRAINT uq_manager_tenures_fund_mgr_start UNIQUE (fund_id, mgr_id, start_date),
    FOREIGN KEY(fund_id) REFERENCES funds (id),
    FOREIGN KEY(mgr_id) REFERENCES managers (id)
)
"""
_MANAGER_TENURES_INDEXES = (
    'CREATE INDEX IF NOT EXISTS ix_manager_tenures_mgr_id ON manager_tenures (mgr_id)',
    'CREATE INDEX IF NOT EXISTS ix_manager_tenures_fund_id ON manager_tenures (fund_id)',
)


def migrate_fund_managers_split_tenures(engine: Engine) -> str:
    """拆分 ``fund_managers``：关联（+唯一约束）归本表，任期归 ``manager_tenures``（#2239）。

    ## 为什么要整表重建

    SQLite 的 ``ALTER TABLE`` **只能加列/改名**，既不能加约束、也不能删列。而本次改造两件
    都要做：加 ``UNIQUE(fund_id, mgr_id)``、删 ``start_date`` / ``end_date``。故走标准流程
    **建新表 → 拷贝（顺带去重）→ 删旧 → 改名**（同 :func:`migrate_watchlist_unique_key`）。

    ## 步骤顺序是刻意的：**先搬任期，后重建**

    若先重建（DROP 掉 start_date / end_date）再搬任期，中途失败就**永久丢日期** —— 那两个
    字段是每次 F10 抓取（每只基金一次 HTTP）才有的，事后补不回来。反过来先搬任期：
    万一在重建处崩掉，重跑时任期源数据仍在旧表里，迁移整体可重入。

    ## 去重口径

    ``(fund_id, mgr_id)`` 取一行，**优先 ``is_classic=True``** —— 那是「代表作品」标记，
    丢掉它会让代表作挑选逻辑（``manager_holdings``）在迁移后变差。多出来的行直接丢弃
    （它们与保留行除了 id 之外没有任何差异，卡内实测：重复组内三列值完全一致）。

    ## 任期写入口径

    只有 ``start_date`` 非空的才写成任期（空起始日的行本来就无法定位一段任期，
    编一个日期比留空更糟）；``start_date > end_date`` 属脏行，跳过并计数。
    ``current`` 按 ``end_date IS NULL`` 落 —— **不是**无条件 True：无条件为真等于
    把所有历史段都标成「在任」，读侧按 ``current`` 筛选代表作时会跨轮次选错人。

    ## 幂等

    三种「已完成」形态都直接跳过：非 SQLite 引擎；``fund_managers`` 不存在（空库，
    ``create_all`` 会按新模型建）；已无任期列且 ``manager_tenures`` 已存在。
    任期写入用 ``INSERT OR IGNORE`` 依赖 ``uq_manager_tenures_fund_mgr_start``。
    """
    url = str(getattr(engine, 'url', '') or '')
    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎，结构由 ORM 模型/迁移工具负责'

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if 'fund_managers' not in tables:
        return '[SKIP] fund_managers 不存在（空库，init_db 将按新模型建表）'

    cols = {c['name'] for c in insp.get_columns('fund_managers')}
    tenure_cols = {'start_date', 'end_date'} & cols
    if not tenure_cols and 'manager_tenures' in tables:
        return '[SKIP] 已拆分完成（fund_managers 无任期列，manager_tenures 已存在）'

    # ── 1. 先把任期搬到新表（顺序理由见 docstring）────────────────────────────
    # 启动期 `create_all` 已按模型建好该表；这里再 `IF NOT EXISTS` 一遍，是为了让
    # **单独跑这个迁移**也成立（手工修库、或只调迁移的单测）。
    with engine.connect() as conn:
        conn.execute(text(_MANAGER_TENURES_DDL))
        for stmt in _MANAGER_TENURES_INDEXES:
            conn.execute(text(stmt))
        conn.commit()

    select_cols = ['id', 'fund_id', 'mgr_id', 'is_classic']
    select_cols += [c for c in ('start_date', 'end_date') if c in cols]
    with engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(text(f'SELECT {", ".join(select_cols)} FROM fund_managers')).mappings()]

    # 按 (fund_id, mgr_id) 去重，优先保留 is_classic=True 的那行
    best: dict = {}
    for r in rows:
        key = (r['fund_id'], r['mgr_id'])
        cur = best.get(key)
        if cur is None or (r.get('is_classic') and not cur.get('is_classic')):
            best[key] = r

    tenures, invalid = [], 0
    for r in best.values():
        start = r.get('start_date')
        end = r.get('end_date')
        if not start:
            continue
        if end and str(start) > str(end):
            # 起始晚于结束属脏行：宁可少一段任期，也不把倒挂的区间写进库
            invalid += 1
            continue
        tenures.append(
            {
                'fund_id': r['fund_id'],
                'mgr_id': r['mgr_id'],
                'start_date': str(start),
                'end_date': str(end) if end else None,
                'current': 1 if not end else 0,
                'source': 'legacy_split',
            }
        )

    with engine.connect() as conn:
        if tenures:
            conn.execute(
                text(
                    'INSERT OR IGNORE INTO manager_tenures '
                    '(fund_id, mgr_id, start_date, end_date, current, source) '
                    'VALUES (:fund_id, :mgr_id, :start_date, :end_date, :current, :source)'
                ),
                tenures,
            )
        conn.commit()

    # ── 2. 重建 fund_managers：只留关联列 + 唯一约束 ──────────────────────────
    # DDL 手写（理由见文件上方常量注释）；列清单必须与 models.FundManager 一致
    ddl = _FUND_MANAGERS_NEW_DDL
    new_rows = [
        {
            'id': r['id'],
            'fund_id': r['fund_id'],
            'mgr_id': r['mgr_id'],
            'is_classic': r.get('is_classic'),
        }
        for r in best.values()
    ]

    with engine.connect() as conn:
        conn.execute(text('PRAGMA foreign_keys=OFF'))
        conn.execute(text('DROP TABLE IF EXISTS fund_managers_new'))
        conn.execute(text(ddl))
        if new_rows:
            conn.execute(
                text(
                    'INSERT INTO fund_managers_new (id, fund_id, mgr_id, is_classic) '
                    'VALUES (:id, :fund_id, :mgr_id, :is_classic)'
                ),
                new_rows,
            )
        conn.execute(text('DROP TABLE fund_managers'))
        conn.execute(text('ALTER TABLE fund_managers_new RENAME TO fund_managers'))
        conn.execute(text('PRAGMA foreign_keys=ON'))
        conn.commit()

    # ── 3. 迁移后自校验：_validate_schema 只查缺列，查不出「多列 / 少约束」
    after_cols = {c['name'] for c in inspect(engine).get_columns('fund_managers')}
    leftover = {'start_date', 'end_date'} & after_cols
    if leftover:
        raise RuntimeError(f'fund_managers 重建后仍含任期列 {sorted(leftover)}，迁移失败')
    # 唯一约束按**列**判定而不是按名：SQLite 不曝露内联约束名（反射回来是 None）
    uniques = inspect(engine).get_unique_constraints('fund_managers')
    if not any(sorted(u.get('column_names') or []) == ['fund_id', 'mgr_id'] for u in uniques):
        raise RuntimeError(f'fund_managers 缺少 (fund_id, mgr_id) 唯一约束，迁移失败：{uniques}')

    merged = len(rows) - len(best)
    msg = (
        f'[OK] fund_managers 去重 {len(rows)} → {len(best)} 行（合并 {merged} 行）；'
        f'manager_tenures 迁入 {len(tenures)} 段任期' + (f'（跳过倒挂脏行 {invalid}）' if invalid else '')
    )
    logger.info(msg)
    return msg


# 写路径（#1661）已强制「显式非基金类型 → False」；存量若仍为 True 属历史污染，本迁移清零。
_NON_FUND_ASSET_TYPES: tuple[str, ...] = ('stock', 'etf', 'bond', 'reverse_repo', 'crypto', 'index')
# 只有这两类才可能真为货基（与 `core/venues._OTC_ASSET_TYPES` 同族）
_FUND_ASSET_TYPES: tuple[str, ...] = ('fund', 'money_fund')


def migrate_positions_money_fund_flag(engine: Engine) -> str:
    """#1661 存量回填：按「基金名录 + 品种」新口径重算 `positions.is_money_fund`。

    ## 为什么需要

    PR #1663 修的是**读写路径**：`_resolve_money_fund_flag` 不再丢 `asset_type`，代码段兜底
    也补上了交易所维度。但**已经落库的历史标记不会自己变**——本机实测 11 行真货基里
    仍有 8 行 `is_money_fund = 0`（#863 的回填脚本是手动脚本，从未挂进启动链路，修完
    判定口径后也没重跑）。标记错了就有两个方向的金融口径错误：

    - 真货基标 0 → 被排除出「现金等价物」聚合桶，饼图把货基算成「基金投资」；
    - 非货基标 1 → `sync/jobs/position_price_job.py` 见到标记即按**面值 1.0000** 回写
      `current_price`，持仓市值塌成「份额数」（P0 数据损坏）。

    ## 判定口径（与写路径同源，但**只信名录**）

    - 显式 `type = 'money_fund'` → True；显式非基金类型（`stock`/`etf`/`bond`/…）→ 清零；
    - `type = 'fund'` → 查 market 域 `funds` 名录的 `fund_types.name`：
      `货币型` → True，其它明确类型 → False；
    - 名录**没有**该代码 / 类型未知 / market 域不可达 → **保持原值不动**（见
      `fund_utils.resolve_money_fund_flags_strict` 返回 `None` 的语义）。

    最后这条是硬边界：迁移每次启动都跑，若把「名录不可达」当成「不是货基」，一次
    market 域抖动就会把全库货基标记清空。宁漏不误（#1661 取舍）。

    幂等：结论与库中值一致就不写。判定与回填都在 **Python 侧**做（读全行 →
    算 → 逐行参数化 UPDATE），SQL 只有标准 SELECT/UPDATE，两种引擎通用，故本迁移
    **全引擎执行**——生产 user 域是 Postgres，存量污染标记不会因为引擎不同而
    该留着（#2534）。
    """
    if 'positions' not in inspect(engine).get_table_names():
        return '[SKIP] positions 表不存在（空库，init_db 将按新模型建表）'
    if 'is_money_fund' not in {c['name'] for c in inspect(engine).get_columns('positions')}:
        return '[SKIP] positions 无 is_money_fund 列（空库，新录入由写路径直接落正确值）'

    with engine.connect() as conn:
        rows = conn.execute(
            text('SELECT id, symbol, type, is_money_fund FROM positions WHERE symbol IS NOT NULL')
        ).fetchall()
    if not rows:
        return '[SKIP] positions 无持仓行'

    updates: list[tuple[int, int]] = []
    # 一、显式非基金类型仍标 True → 清零（历史污染，方向 2）
    for rid, _sym, atype, flag in rows:
        if atype in _NON_FUND_ASSET_TYPES and flag:
            updates.append((rid, 0))

    # 二、基金类按名录重算（方向 1）
    fund_rows = [(rid, sym, atype, flag) for rid, sym, atype, flag in rows if atype in _FUND_ASSET_TYPES]
    recomputed = 0
    undecidable = 0
    if fund_rows:
        # 延迟导入：core 层不在导入期依赖 services，且避免与 domains 模型形成环
        from app.services.fund_utils import normalize_fund_code, resolve_money_fund_flags_strict

        flags = resolve_money_fund_flags_strict([sym for _rid, sym, _t, _f in fund_rows])
        for rid, sym, atype, flag in fund_rows:
            resolved: bool | None = True if atype == 'money_fund' else flags.get(normalize_fund_code(sym))
            if resolved is None:
                undecidable += 1
                continue
            if (1 if resolved else 0) != (1 if flag else 0):
                updates.append((rid, 1 if resolved else 0))
                recomputed += 1

    if not updates:
        return '[SKIP] positions.is_money_fund 已与新口径一致（无需回填）'

    with engine.connect() as conn:
        for rid, val in updates:
            conn.execute(text('UPDATE positions SET is_money_fund = :v WHERE id = :i'), {'v': val, 'i': rid})
        conn.commit()

    msg = f'回填 {recomputed} 行 + 清除非基金误标 {len(updates) - recomputed} 行'
    if undecidable:
        msg += f'；{undecidable} 行名录无记录/类型未知，保持原值'
    logger.info(f'[OK] positions.is_money_fund 存量重算：{msg}')
    return f'[OK] {msg}'


def migrate_fund_equity_position_period(engine: Engine) -> str:
    """funds 补 equity_position_period 列（#870）。

    `equity_position` 的口径由「前十大重仓之和」改为「行业配置合计」（详见 Fund 模型注释），
    需要一并记录该值对应的报告期：Q1 与 Q2 都是全量口径但数值会随季报变化，没有报告期
    就无法判断差异是「真的调仓」还是「口径/版本混淆」。

    存量行**故意留 NULL**——旧值来自已废弃口径，其报告期无从得知，不假装知道。

    SQLite / libsql 支持对可空列直接 ALTER ADD COLUMN（无需整表重建）；新表
    fund_holdings / fund_industry_allocs 由 create_all 建，无需迁移。两种引擎都
    由本迁移负责（走 ``_add_columns_if_missing``，PG 用 ``ADD COLUMN IF NOT
    EXISTS``）——生产 user 域是 Postgres，本仓没有 Alembic、``create_all()``
    也不给存量表加列（#2534）。
    """
    if not _table_exists(engine, 'funds'):
        return '[SKIP] funds 表不存在（空库，init_db 将按新模型建表）'

    added = _add_columns_if_missing(engine, 'funds', [('equity_position_period', 'VARCHAR(8)')])
    if not added:
        return '[SKIP] funds.equity_position_period 已存在'

    if 'equity_position_period' not in {c['name'] for c in inspect(engine).get_columns('funds')}:
        raise RuntimeError('funds.equity_position_period 增加后校验失败')
    logger.info('[OK] funds.equity_position_period 已就绪（#870 仓位口径版本留痕）')
    return '[OK] funds.equity_position_period 已就绪'


def migrate_fund_valuation_official_columns(engine: Engine) -> str:
    """fund_valuation_daily 补对照三列（#2142）：official_nav / deviation / deviation_pct。

    ## 为什么需要

    K 卡（#2141）落库的估值行只有预估侧字段；官方净值到位后 `fund_valuation_reconcile`
    job 要把 status 翻 confirmed 并记录「预估 vs 官方」偏差，供数据源质量观察——
    没有这三列，对照结果无处可写（status 单独翻 confirmed 会丢失对照依据）。

    ## 加列方式

    三列全为**可空**列：SQLite / libsql 对可空列支持直接 ALTER ADD COLUMN；
    历史行（对照发生前落库的预估行）留 NULL，读取端 NULL → None 降级，不写 0。
    幂等：列已存在则跳过。两种引擎都由本迁移负责（走 ``_add_columns_if_missing``，
    PG 用 ``ADD COLUMN IF NOT EXISTS``）——生产 user 域是 Postgres，本仓没有
    Alembic、``create_all()`` 也不给存量表加列（#2534）。

    ⚠️ 本迁移**只加列、不回填**：偏差是「当时预估 vs 当时官方」的时点对照，
    事后可以补算（reconcile job 会自然收敛历史 estimated 行），无需启动期回填。
    """
    if not _table_exists(engine, 'fund_valuation_daily'):
        return '[SKIP] fund_valuation_daily 表不存在（空库，init_db 将按新模型建表）'

    cols = [
        ('official_nav', 'NUMERIC(18, 6)'),
        ('deviation', 'NUMERIC(18, 6)'),
        ('deviation_pct', 'NUMERIC(10, 4)'),
    ]
    added = _add_columns_if_missing(engine, 'fund_valuation_daily', cols)
    if added:
        logger.info(f'[OK] fund_valuation_daily 增加对照列: {added}')
        return f'[OK] 增加列 {added}'
    return '[SKIP] fund_valuation_daily 对照三列已存在'


def migrate_fund_risk_metrics_period_returns(engine: Engine) -> str:
    """fund_risk_metrics 补区间收益三列（#2284）：ret_1m / ret_3m / ret_1y。

    ## 为什么需要

    同类风险榜要展示「近1月 / 近3月 / 近1年」三列区间收益（#2284）；既有快照表
    没有这三列，读路径无处可取。三列全为**可空**列：SQLite / libsql 对可空列
    支持直接 ALTER ADD，历史行留 NULL，由读取端降级为「—」。

    ## 只加列、不回填

    区间收益是「由净值序列可复现的派生值」，不是时点对照——但迁移阶段回填会
    在启动路径里做计算扫描（读全量净值），得不偿失。正确路径是
    ``fund_risk_metrics_job.CALIBER_VERSION`` bump（v1 → v2）后由 job 重算覆盖，
    启动期迁移只负责把列建好。幂等：列已存在则跳过。两种引擎都由本迁移负责
    （走 ``_add_columns_if_missing``，PG 用 ``ADD COLUMN IF NOT EXISTS``）——
    生产 user 域是 Postgres，本仓没有 Alembic、``create_all()`` 也不给存量表
    加列（#2534）。
    """
    if not _table_exists(engine, 'fund_risk_metrics'):
        return '[SKIP] fund_risk_metrics 表不存在（空库，init_db 将按新模型建表）'

    cols = [
        ('ret_1m', 'NUMERIC(10, 4)'),
        ('ret_3m', 'NUMERIC(10, 4)'),
        ('ret_1y', 'NUMERIC(10, 4)'),
    ]
    added = _add_columns_if_missing(engine, 'fund_risk_metrics', cols)
    if added:
        logger.info(f'[OK] fund_risk_metrics 增加区间收益列: {added}')
        return f'[OK] 增加列 {added}'
    return '[SKIP] fund_risk_metrics 区间收益三列已存在'


def migrate_positions_snapshot_anchor(engine: Engine) -> str:
    """positions 补「快照锚点」四列，并回填日期/来源（不猜份额）。

    ## 为什么需要

    `quantity` 过去同时是「快照绝对值」与「流水累加结果」：持仓快照导入用 SET 写，
    交易落库用 INCR 加，两条路径无时序约束。先导快照、后导历史流水的账户会被
    二次计入（实测 012708 精确 2 倍：11,083.22 → 22,166.44）。

    加入锚点后 `quantity` 降级为派生值：
        quantity = snapshot_quantity + Σ(confirm_date > snapshot_date 的流水净额)

    ## 回填策略：**只回填日期，不回填份额**

    `snapshot_quantity` 的历史真实值已经丢失（导入时直接写进 quantity，随后被流水
    加权）。同一个 `quantity = 22,166.44` 可能是两种截然相反的历史：

    - 先流水后快照（正确）：quantity 就是快照值；
    - 先快照后流水（错误）：quantity = 快照值 + 快照前流水。

    盲猜任一方向都会把另一半账户改错，故本迁移**只**做两件无歧义的事：
    1. 加列；
    2. 从 `position_import_meta.snapshot_date` 回填 `snapshot_date`（`anchor_kind`
       置 `external`），份额列保持 NULL。

    `snapshot_quantity IS NULL` 的持仓继续走「全量流水净额」旧口径，**不会因迁移
    改坏**。具体修复由 `app/tools/repair_snapshot_double_count.py` 扫描出报告，
    人工确认后才写入锚点。

    幂等：列已存在则跳过；回填只填 `snapshot_date IS NULL` 的行。
    两种引擎都由本迁移负责（加列走 ``_add_columns_if_missing``，回填是标准
    SQL）——生产 user 域是 Postgres，本仓没有 Alembic、``create_all()``
    也不给存量表加列（#2534）。
    """
    tables = set(inspect(engine).get_table_names())
    if 'positions' not in tables:
        return '[SKIP] positions 表不存在（空库，init_db 将按新模型建表）'

    cols = [
        ('snapshot_quantity', 'INTEGER'),
        ('snapshot_avg_price', 'INTEGER'),
        ('snapshot_date', 'DATE'),
        ('anchor_kind', 'VARCHAR(20)'),
    ]
    added = _add_columns_if_missing(engine, 'positions', cols)

    # 回填：日期 + 来源。份额不填（见 docstring）。
    backfilled = 0
    if 'position_import_meta' in tables:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE positions
                       SET snapshot_date = (
                               SELECT pim.snapshot_date FROM position_import_meta pim
                                WHERE pim.position_id = positions.id
                                  AND pim.snapshot_date IS NOT NULL
                                LIMIT 1
                           ),
                           anchor_kind = 'external'
                     WHERE snapshot_date IS NULL
                       AND EXISTS (
                               SELECT 1 FROM position_import_meta pim
                                WHERE pim.position_id = positions.id
                                  AND pim.snapshot_date IS NOT NULL
                           )
                    """
                )
            )
            backfilled = result.rowcount or 0
            conn.commit()

    if added or backfilled:
        logger.info(f'[OK] positions 锚点列: 新增={added}, 回填日期={backfilled}')
        return f'[OK] 新增列 {added}，回填 snapshot_date {backfilled} 行（份额列留空待人工确认）'
    return '[SKIP] positions 锚点四列已存在且无待回填行'


def migrate_positions_cleared_at(engine: Engine) -> str:
    """positions 补 `cleared_at` 一列（issue #2343 第二步）。

    ## 为什么需要

    清仓（整笔卖出）过去是 `db.delete(position)`，持仓行连同快照锚点四列一起消失。
    此后删除该笔卖出流水触发重建，只能退回「全量流水」口径，份额会被二次累加
    （与 2026-10-18 修复的快照锚点 bug 同源）。同时「历史曾持有」也彻底不可追溯。

    改为保留行后需要两件事实：
    - 当前是否已清仓 → `ownership_status='cleared'`（本轮第一步已落地枚举与过滤器）；
    - **何时**清仓 → 本列。它是「清仓后再买入」时新一轮周期的下界，也是
      持有天数 / 已实现盈亏能按周期切分的唯一依据。

    ## 回填策略：**不回填**

    历史清仓行的持仓记录已经被删掉了，没有任何可靠数据源能反推它们的清仓时间
    （`transactions` 里的卖出流水无 `position_id` 或指向已删行，且无法区分
    「整笔清仓」与「部分卖出」）。因此本迁移只加列，历史行保持 NULL。

    NULL 的语义是「无已知清仓时间」，等同于「从未清仓」，与现存数据完全一致。

    幂等：列已存在则跳过。两种引擎都由本迁移负责（走 ``_add_columns_if_missing``，
    PG 用 ``ADD COLUMN IF NOT EXISTS``）——生产 user 域是 Postgres，本仓没有
    Alembic、``create_all()`` 也不给存量表加列（#2534）。
    """
    if not _table_exists(engine, 'positions'):
        return '[SKIP] positions 表不存在（空库，init_db 将按新模型建表）'

    added = _add_columns_if_missing(engine, 'positions', [('cleared_at', 'DATETIME')])
    if added:
        logger.info('[OK] positions.cleared_at 已新增（历史清仓行无法反推，保持 NULL）')
        return '[OK] 新增列 cleared_at（不回填：历史清仓行已删除，无可靠数据源）'
    return '[SKIP] positions.cleared_at 已存在'


def migrate_account_name_snapshot(engine: Engine) -> str:
    """回填 `positions` / `transactions` 的 `account_name` 冗余快照空值。

    ## 为什么需要

    `account_name` 是 `ledgers.name` 的**冗余快照**（供明细展示与「按账户分组」使用，
    账户改名由 `ledger_write_service.sync_account_name_snapshots` 级联刷新）。它的唯一
    真相是 `ledger_id`，但历史上由各写入路径**分别传递**：基金转换「转入腿」只传了
    `ledger_id`、漏传 `account_name`，于是落成 NULL（2026-10-18 实测 position 618 /
    transaction 3001）。

    NULL 一旦成为「按账户分组」的字典键，`flask.jsonify(sort_keys=True)` 会在
    `str` 与 `None` 比较时抛 `TypeError`，整个持仓列表 500 —— 问题不在排序，
    在数据本身违反了「有账户就该有账户名」。

    代码侧已由 `Position` 的 `before_insert` / `before_update` 事件兜住**新写入**；
    本迁移收编**存量**行，否则「新数据按新规矩、老数据按老规矩」两套真相会长期并存
    （改口径时存量必须一起收编，见 AGENTS.md）。

    ## 口径

    只补 `ledger_id IS NOT NULL` 且 `account_name` 为 `NULL` / 空串的行；`ledger_id`
    为空（未归档持仓 / 导入影子行）的保持原样 —— 它们确实没有账户，显示层的
    「未指定账户」是对这类行的正确兜底。逐行 `UPDATE ... WHERE` 而非全表覆盖，
    幂等、可重复跑。

    回填 SQL 是标准相关子查询 UPDATE（两种引擎通用），故本迁移**全引擎执行**——
    生产 user 域是 Postgres，存量 NULL 不该因为引擎不同而继续违反「有账户就该有
    账户名」（#2534；那个 TypeError 500 在任何引擎上都会炸）。
    """
    tables = set(inspect(engine).get_table_names())
    missing = [t for t in ('positions', 'transactions', 'ledgers') if t not in tables]
    if missing:
        return f'[SKIP] 缺表 {missing}（空库，init_db 将按新模型建表）'

    actions: list[str] = []
    with engine.begin() as conn:
        for table in ('positions', 'transactions'):
            res = conn.execute(
                text(
                    f'UPDATE {table} '
                    f'SET account_name = (SELECT name FROM ledgers WHERE ledgers.id = {table}.ledger_id) '
                    f'WHERE ledger_id IS NOT NULL '
                    f"  AND (account_name IS NULL OR account_name = '') "
                    f'  AND EXISTS (SELECT 1 FROM ledgers '
                    f'              WHERE ledgers.id = {table}.ledger_id '
                    f"                AND ledgers.name IS NOT NULL AND ledgers.name != '')"
                )
            )
            if res.rowcount:
                actions.append(f'{table}: 回填 {res.rowcount} 行')
    if not actions:
        return '[OK] account_name 快照无空值'
    logger.info('[OK] account_name 冗余快照已回填: {}', '; '.join(actions))
    return '[OK] ' + '; '.join(actions)


def migrate_conversion_in_leg_snapshot(engine: Engine) -> str:
    """回填转换「转入腿」持仓的 `name` / `market` 快照空值与污染值（#2406）。

    ## 为什么需要

    手动基金转换的转入腿 `in_data` 只传了 `symbol`，漏传 `name` / `market`
    （`account_name` 已由 PR #2404 收口，同一份 dict 的同一缺陷族）。后果：

    - `name` 缺省时 `process_buy_or_deposit` 退回 `name=data.get('name') or symbol`
      → 持仓明细显示 6 位编码而非基金名；
    - `market` 落 NULL → 展示层 `position_presenter` 兜 `'UNKNOWN'`，
      `MARKET_LABELS` 查不到 → 前端「未知资产」。

    本地库实证 position 618（519771，转入腿所建）：`name=NULL`、
    `market='UNKNOWN'`——其中 'UNKNOWN' 还是 presenter 旧实现直接改 ORM 对象、
    被同 session 的 flush 落进库的污染值（#2406 已修读函数写库的病根）。

    代码侧已由 #2406 的调用点显式传值 + presenter 停变异收口**新写入**；本迁移收编
    **存量**行，否则「新数据按新规矩、老数据按老规矩」两套真相长期并存。

    ## 口径（宁漏不误，与 `resolve_fund_names` 的 None 语义对齐）

    - `name`：NULL / 空串、`symbol` 有值、`asset_type` 属基金类 → 按 market 域
      `funds` 名录回填；名录无记录 / market 域不可达 → **保持原值**，不编造；
    - `market`：NULL 或非契约值（实证污染值 'UNKNOWN'）→ 基金类行按场外惯例
      写 `'CN_A'`（`process_buy_or_deposit` 写入缺省与导入路径同值，全库 151/152
      行实证）；非基金类行不动（股票市场推断另有权威入口，不在此越权）；

    只补数据不动结构，逐行 `UPDATE ... WHERE`，幂等可重复跑。判定与回填都在
    **Python 侧**做（读全行 → 名录反查 → 逐行参数化 UPDATE），SQL 只有标准
    SELECT/UPDATE，两种引擎通用，故本迁移**全引擎执行**——生产 user 域是
    Postgres，存量空值/污染值不该因为引擎不同而留在库里（#2534）。
    """
    tables = set(inspect(engine).get_table_names())
    if 'positions' not in tables:
        return '[SKIP] positions 表不存在（空库，init_db 将按新模型建表）'
    cols = {c['name'] for c in inspect(engine).get_columns('positions')}
    missing = [c for c in ('name', 'market', 'symbol', 'type') if c not in cols]
    if missing:
        return f'[SKIP] positions 缺列 {missing}（空库，新录入由写路径直接落正确值）'

    # 契约市场集合（core/markets 的唯一真相；延迟导入避免 core 层环）
    from app.core.markets import CONTRACT_MARKETS

    contract_list = ', '.join(f"'{m}'" for m in CONTRACT_MARKETS)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                'SELECT id, symbol, type, name, market FROM positions '
                "WHERE symbol IS NOT NULL AND symbol != '' "
                "  AND type IN ('fund', 'money_fund') "
                "  AND ((name IS NULL OR name = '') "
                '       OR market IS NULL OR market NOT IN (' + contract_list + '))'
            )
        ).fetchall()
    if not rows:
        return '[OK] 转入腿快照无空值/污染值'

    # 延迟导入：core 层不在导入期依赖 services，且避免与 domains 模型形成环
    from app.services.fund_utils import normalize_fund_code, resolve_fund_names

    names = resolve_fund_names([r.symbol for r in rows])

    updates: list[tuple[int, str | None, str | None]] = []
    filled_name = undecidable = 0
    for rid, symbol, _atype, name, market in rows:
        new_name = name
        if not name:
            resolved = names.get(normalize_fund_code(symbol))
            if resolved:
                new_name = resolved
                filled_name += 1
            else:
                undecidable += 1  # 名录无记录/不可达：保持原值，不编造
        new_market = market if market in CONTRACT_MARKETS else 'CN_A'
        if new_name != name or new_market != market:
            updates.append((rid, new_name, new_market))

    if not updates:
        return '[OK] 转入腿快照无空值/污染值'

    with engine.begin() as conn:
        for rid, new_name, new_market in updates:
            conn.execute(
                text('UPDATE positions SET name = :n, market = :m WHERE id = :i'),
                {'n': new_name, 'm': new_market, 'i': rid},
            )
    msg = f'回填 {len(updates)} 行（name 补 {filled_name} 行'
    if undecidable:
        msg += f'，{undecidable} 行名录无记录/不可达保持原名'
    msg += '，market 收编为契约值）'
    logger.info('[OK] 转换转入腿快照存量收编：{}', msg)
    return '[OK] ' + msg


def migrate_asset_major_category_current_to_cash(engine: Engine) -> str:
    """assets.major_category 归一：历史错值 ``'current'`` → ``'cash'``（#2136）。

    ## 为什么

    #2136 裁决：账户现金的大类取值以权威词表 ``ASSET_CATEGORY_LABELS`` 为准，
    即 ``'cash'``。读侧三处此前按 ``'current'`` 过滤——那是个**词表外**的值，
    写入侧从来不会产出它，于是账户现金恒读成 0。读侧已改回 ``'cash'``，
    但**存量行**若历史上被写成 ``'current'``，改完读侧它们依然读不到
    （= 隐形行：钱在库里，页面上没有）。

    ## 做什么

    只把 ``major_category='current'`` 的行改成 ``'cash'``，不改表结构、
    不动其他取值。语义上这是**把错值改回词表里的那个值**，不涉及任何口径变更。

    ## 幂等与跳过

    - 幂等：重复执行影响 0 行；
    - 库表不存在 → 跳过；
    - 归一 SQL 是标准 ``UPDATE``（两种引擎通用），故**全引擎执行**——生产 user 域
      是 Postgres，词表外值 'current' 在任何引擎上都读不到（#2534）。
    """
    if 'assets' not in inspect(engine).get_table_names():
        return '[SKIP] assets 表不存在'

    with engine.begin() as conn:
        n = conn.execute(text("UPDATE assets SET major_category='cash' WHERE major_category='current'")).rowcount
    msg = f'major_category 归一 current→cash：{n} 行'
    logger.info('[OK] {}', msg)
    return '[OK] ' + msg


def migrate_fund_style_columns(engine: Engine) -> str:
    """funds 补 dominant_style / style_period 列（#2478 风格箱接入）。

    `fund_style_exposures`（long 明细表）由 create_all 建，无需迁移；本迁移只补
    `funds` 上的两个**派生标量**：当前主导风格 + 对应时点。派生口径与
    `equity_position` 同构——「明细是源、标量是派生，无源即不派生」，故存量行
    **故意留 NULL**（从未抓到风格箱的基金不冒充 '未知'）。

    两列均可空：SQLite / libsql 支持对可空列直接 ALTER ADD COLUMN；幂等：列已存在
    则跳过。两种引擎都由本迁移负责（走 ``_add_columns_if_missing``，PG 用
    ``ADD COLUMN IF NOT EXISTS``）——生产 user 域是 Postgres，本仓没有 Alembic、
    ``create_all()`` 也不给存量表加列（#2534）。
    """
    if not _table_exists(engine, 'funds'):
        return '[SKIP] funds 表不存在（空库，init_db 将按新模型建表）'

    cols = [
        ('dominant_style', 'VARCHAR(20)'),
        ('style_period', 'VARCHAR(10)'),
    ]
    added = _add_columns_if_missing(engine, 'funds', cols)
    if added:
        logger.info(f'[OK] funds 增加风格箱派生列: {added}（#2478）')
        return f'[OK] funds 增加风格箱派生列 {added}'
    return '[SKIP] funds 风格箱派生列已存在'


def migrate_convertible_bond_enhanced_columns(engine: Engine) -> str:
    """convertible_bond_terms 补条款增强两列（#1400 / #2575）。

    新增 ``stock_pb``（正股市净率）/ ``ytm``（到期税前收益，自算）。

    ## 为什么是「加列」而不是「建表」

    `convertible_bond_terms` 已有存量行（约 300+ 只转债），本迁移**只加可空列**：
    SQLite / libsql 支持对可空列直接 `ALTER TABLE ADD COLUMN`（无需整表重建），
    PG 用 `ADD COLUMN IF NOT EXISTS`。两种引擎都由本迁移负责（走
    ``_add_columns_if_missing``）——生产 user 域是 Postgres，本仓没有 Alembic、
    ``create_all()`` 也不给存量表加列（#2534）。

    ## 为什么不回填

    两列都是**当期快照值**（PB / YTM 随行情与条款变动），存量行没有「当时的值」
    可回填——回填等于用今天的数贴到历史行。故存量行保持 NULL，读侧降级为「—」，
    由下次 `convertible_bond` 调度自然补齐。

    幂等：列已存在则跳过，可重复跑。
    """
    if not _table_exists(engine, 'convertible_bond_terms'):
        return '[SKIP] convertible_bond_terms 表不存在（空库，init_db 将按新模型建表）'

    cols = [
        ('stock_pb', 'NUMERIC(10, 4)'),
        ('ytm', 'NUMERIC(12, 4)'),
    ]
    added = _add_columns_if_missing(engine, 'convertible_bond_terms', cols)
    if added:
        logger.info(f'[OK] convertible_bond_terms 增加条款增强列: {added}（#2575）')
        return f'[OK] 增加列 {added}'
    return '[SKIP] convertible_bond_terms 条款增强列已存在'


def migrate_fund_rating_columns(engine: Engine) -> str:
    """funds 补晨星星级评级当期值三列（#1440）：morningstar_rating / _delta / _asof。

    数据源为东财评级总汇页（fund.eastmoney.com/data/fundrating.html，akshare
    `fund_rating_all` 同源），采**晨星 3 年期**星级。口径已双重坐实：
    - 三家机构评级专页反证综合页字段顺序（招商 15576/15576、上海 382/382、
      济安 46/46，pos14=晨星）；
    - 晨星官方 MCP `getFundPerformance` 的 `starRatingDetails` 标注
      `ratingPeriod: 36`，三只探针（000001/110011/161725）与 pos14 逐只一致。

    存储为**当期值列**而非快照表（D1 拍板）：全仓无评级消费方即无历史需求，
    delta 的含义在写入期已定格；升级路径 = 换 job 的 `_save_data`，解析层复用。

    三列均可空：SQLite / libsql 支持对可空列直接 ALTER ADD COLUMN；幂等：列已存在
    则跳过。两种引擎都由本迁移负责（走 ``_add_columns_if_missing``，PG 用
    ``ADD COLUMN IF NOT EXISTS``）——生产 user 域是 Postgres，本仓没有 Alembic、
    ``create_all()`` 也不给存量表加列（#2534）。存量行留 NULL = 未采集，
    job 首次跑后按 fund_code 覆盖写（同 scale 先例）。
    """
    if not _table_exists(engine, 'funds'):
        return '[SKIP] funds 表不存在（空库，init_db 将按新模型建表）'

    cols = [
        ('morningstar_rating', 'SMALLINT'),
        ('morningstar_rating_delta', 'SMALLINT'),
        ('morningstar_rating_asof', 'DATE'),
    ]
    added = _add_columns_if_missing(engine, 'funds', cols)
    if added:
        logger.info(f'[OK] funds 增加晨星星级评级列: {added}（#1440）')
        return f'[OK] funds 增加晨星星级评级列 {added}'
    return '[SKIP] funds 晨星星级评级列已存在'


def migrate_transaction_fee_breakdown(engine: Engine) -> str:
    """transactions 补费用拆分四列（#2137）：佣金 / 印花税 / 过户费等税费 / 其他费用。

    ## 为什么需要

    交割单（同花顺导出）本就带四列费用明细，解析器此前只能合并成聚合 ``fee``
    落库——「这笔 15 元手续费里佣金/印花税/过户费各多少」无从回答。
    四列让费用结构可记、可查、可按类别汇总。

    ## 与聚合 fee 的关系（存量兼容策略）

    ``fee`` 仍是唯一权威总额（已实现盈亏结转、卖出回款净额等口径都不动）；
    四列全 NULL = 未拆分，是存量数据与未提供拆分的写入路径的默认态，
    读取端按 ``fee`` 展示，**行为与迁移前完全一致**（不造错数、不改写历史）。

    ## 加列方式（2026-10-23 修正：PG 也必须由本迁移负责）

    四列均为**可空**列，两种引擎都能直接 ``ALTER TABLE ADD COLUMN``：
    SQLite / libsql 无需整表重建，Postgres 用 ``IF NOT EXISTS`` 保证幂等
    （见 ``_add_column_sql``）；列已存在则跳过。

    ⚠️ **这里曾经对非 SQLite 引擎直接早退**（原文写「由 ORM 模型 / 迁移工具负责」），
    而那前提在本仓**不成立**：

    - 本仓没有 Alembic，迁移都是本文件里手写的函数；
    - ``create_all()`` **只建缺失的表，不会给已有表加列**；
    - 生产 user 域是 Supabase Postgres（手工建表，与模型不同步）。

    三者叠加 ⇒ 四列在生产**永远加不上**，而 ``init_db()`` 末尾的 ``_validate_schema``
    又会因「表 transactions 缺列」**拒绝启动** ⇒ 每日调度（#1490）死在 ``init_db()``，
    一个 job 都跑不到。实测：schedule 运行 39848022855（2026-10-22T20:20:42Z）。
    与 #2469（watchlist 三表补列）是同一类错——迁移写成 SQLite-only，本地全绿、生产必崩。

    收尾有**自校验**：加列后四列必须都在，缺了直接抛错。迁移失败必须显性，
    不能返回一个「看起来 OK」的字符串让调用方继续往下走。

    ⚠️ 本迁移**只加列、不回填**：历史行的拆分事实已随合并丢失，唯一的总额
    ``fee`` 无法反推四类各是多少——盲猜等于编数，宁空不猜。
    """
    if 'transactions' not in inspect(engine).get_table_names():
        return '[SKIP] transactions 表不存在（空库，init_db 将按新模型建表）'

    cols = [
        ('commission', 'INTEGER'),
        ('stamp_duty', 'INTEGER'),
        ('transfer_fee', 'INTEGER'),
        ('other_fee', 'INTEGER'),
    ]
    is_pg = _is_postgres(engine)
    added = []
    with engine.connect() as conn:
        existing = {c['name'] for c in inspect(engine).get_columns('transactions')}
        for name, typ in cols:
            if name not in existing:
                conn.execute(text(_add_column_sql('transactions', name, typ, is_pg)))
                added.append(name)
        conn.commit()

    # 收尾自校验：缺列即抛错（PG 上若 DDL 被静默忽略，这里必须让调用方看到）
    missing = [name for name, _ in cols if name not in {c['name'] for c in inspect(engine).get_columns('transactions')}]
    if missing:
        raise RuntimeError(
            f'transactions 补费用拆分列失败，仍缺列: {missing}（引擎 {"Postgres" if is_pg else "SQLite"}）'
        )

    if added:
        logger.info(f'[OK] transactions 增加费用拆分列: {added}（#2137，存量留 NULL=未拆分）')
        return f'[OK] transactions 增加费用拆分列 {added}'
    return '[SKIP] transactions 费用拆分四列已存在'


def migrate_transaction_plan_id(engine: Engine) -> str:
    """transactions 补 ``plan_id``（#2138）：把一笔买入归到产生它的定投计划。

    ## 为什么需要

    定投计划与流水的关联只能落在流水侧（计划可停用/删除，历史流水必须保留），
    否则「累计投入 / 已执行几期」只能靠日期区间猜——补录一笔同标的的手动买入
    就会被误算成计划执行。加一列显式引用，口径才有唯一答案。

    ## 方言（#2534 的纪律）

    走 ``_add_columns_if_missing`` 单一通道：SQLite / libsql 直接加列，
    Postgres 用 ``ADD COLUMN IF NOT EXISTS``，幂等且收尾自校验。
    **不写「非 SQLite 就跳过」**——生产 user 域就是 Postgres，
    跳过等于让 ``_validate_schema`` 在下次启动时拒绝启动（#2469 / #2532 同形态）。

    索引同步补（模型声明 ``index=True``）：``create_all`` 只建缺失的表，
    不给存量表建索引，故这里按名幂等补 ``ix_transactions_plan_id``。

    只加列不回填：历史流水是否由定投产生已不可考，NULL = 非定投（正确语义）。
    """
    if not _table_exists(engine, 'transactions'):
        return '[SKIP] transactions 表不存在（空库，init_db 将按新模型建表）'
    added = _add_columns_if_missing(engine, 'transactions', [('plan_id', 'INTEGER')])
    indexed = _ensure_index(
        engine,
        'ix_transactions_plan_id',
        'CREATE INDEX IF NOT EXISTS ix_transactions_plan_id ON transactions (plan_id)',
        table='transactions',
    )
    if added or indexed:
        logger.info(f'[OK] transactions 增加定投计划关联列/索引（#2138）：added={added} indexed={indexed}')
        return f'[OK] transactions 增加 plan_id={added} indexed={indexed}'
    return '[SKIP] transactions.plan_id 与索引已存在'


# ── #1173 家庭成员档案（family_members）+ 账户归属列 ──────────────────────────
# 刻意**不** import ``app.domains.families.models``：core 层不得依赖 domains 层
# （`tests/core/test_layer_direction.py` R1 守卫：core → 上层一律违规）。
# 代价是表结构可能随模型漂移，故迁移末尾**自校验**两件事：
# 表是否真的建出来、账户的归属列是否真的在（`_validate_schema` 只查
# 「模型有列而库没列」，查不出「库多列」与「少表」）。
#
# DDL 逐列对齐模型：``family_members`` 的列类型与
# ``app/domains/families/models.py`` 的 ``FamilyMember`` 一一对应。
_FAMILY_MEMBERS_DDL = """
CREATE TABLE IF NOT EXISTS family_members (
    id INTEGER NOT NULL,
    family_id INTEGER NOT NULL DEFAULT 1,
    name VARCHAR(50) NOT NULL,
    role VARCHAR(20) DEFAULT 'other',
    user_id INTEGER,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
    updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
    PRIMARY KEY (id)
)
"""
_FAMILY_MEMBERS_INDEXES = (
    'CREATE INDEX IF NOT EXISTS ix_family_members_family_id ON family_members (family_id)',
    'CREATE INDEX IF NOT EXISTS ix_ledgers_owner_member_id ON ledgers (owner_member_id)',
)


def migrate_family_members_ownership(engine: Engine) -> str:
    """建 ``family_members`` 表 + 给 ``ledgers`` 补 ``owner_member_id`` 列（#1173）。

    ## 为什么需要

    账户（``ledgers``）此前无法归属到具体家庭成员——多账户只能靠起名
    「老婆的招行」区分，系统层面无法按人切片 / 汇总 / 看走势。定位级缺口：
    产品主打家庭资产管理，而「谁的钱」这一维度缺失。

    ## 为什么成员档案独立成表（而不是复用 ``users``）

    - ``users`` 是**登录账号**：``supabase_id`` 唯一非空，成员很可能没有 App 账号，
      硬塞就得造一个假 supabase_id；
    - ``users.role``（admin/member/viewer）是**权限角色**，
      「谁能改账本」与「这笔钱是谁的」是两件事，复用会让「角色」一词两义。

    故成员档案另立 ``family_members``，``user_id`` 可空（纯档案成员无账号）、
    **不加外键**（SQLite 的 ``ALTER TABLE ADD COLUMN`` 不支持带约束的列定义，
    存量表加不上 FK；本文件亦无存量表加 FK 先例）。

    ## 加列而不回填

    ``owner_member_id`` 是**当期归属事实**：历史账户归属谁不可考（多数本就是
    家庭共有），回填等于编造归属。保持 NULL = 「未归属/家庭共有」，
    与 UI 上「不选成员即共有」一致。

    幂等：表/列已存在则跳过。两种引擎都由本迁移负责（PG 用
    ``ADD COLUMN IF NOT EXISTS``）——生产 user 域是 Postgres。
    """
    if not _table_exists(engine, 'ledgers'):
        return '[SKIP] ledgers 表不存在（空库，init_db 将按新模型建表）'

    is_pg = _is_postgres(engine)
    notes: List[str] = []

    # 1. 建 family_members 表（表不存在才建）
    if 'family_members' not in set(inspect(engine).get_table_names()):
        with engine.connect() as conn:
            conn.execute(text(_FAMILY_MEMBERS_DDL))
            conn.commit()
        notes.append('family_members 表已建')
    else:
        notes.append('family_members 表已存在')

    # 2. ledgers 补归属列（走唯一允许的加列通道）
    added = _add_columns_if_missing(engine, 'ledgers', [('owner_member_id', 'INTEGER')])
    if added:
        notes.append(f'ledgers 新增列 {added}（存量留 NULL=未归属/家庭共有）')
    else:
        notes.append('ledgers.owner_member_id 已存在')

    # 3. 索引（owner_member_id 是筛选热路径）
    for ddl in _FAMILY_MEMBERS_INDEXES:
        with engine.connect() as conn:
            conn.execute(text(ddl))
            conn.commit()

    # 收尾自校验：表与列都要真的在（PG 上 DDL 若被静默忽略，这里必须让调用方看到）
    names = set(inspect(engine).get_table_names())
    if 'family_members' not in names:
        raise RuntimeError(f'family_members 建表失败（引擎 {"Postgres" if is_pg else "SQLite"}），迁移失败')
    ledger_cols = {c['name'] for c in inspect(engine).get_columns('ledgers')}
    if 'owner_member_id' not in ledger_cols:
        raise RuntimeError(f'ledgers 补 owner_member_id 失败（引擎 {"Postgres" if is_pg else "SQLite"}），迁移失败')

    logger.info(f'[OK] #1173 家庭成员档案与账户归属：{"；".join(notes)}')
    return '[OK] ' + '；'.join(notes)
