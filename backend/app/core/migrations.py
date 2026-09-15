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
"""

import re

from loguru import logger
from sqlalchemy import Engine, inspect, text


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
    """
    url = str(getattr(engine, 'url', '') or '')
    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎（如 Supabase Postgres），由 ORM/迁移工具负责'

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

    加入方式：SQLite / libsql 支持对「可空列」直接 ``ALTER TABLE ADD COLUMN``（无需整表重建）。
    幂等：列已存在则跳过。非 SQLite 引擎（Supabase Postgres）由 ORM 模型 / 迁移工具负责，
    直接跳过，避免 init_db 在 Supabase 路径上误跑 SQLite 专属 SQL。

    历史行 ``name`` 为 NULL → 读取端自动落回反查链，行为与迁移前一致（不倒退）；
    随后的买入（``ensure_watchlist_for_positions``）会顺带回填（``positions.name``）。
    """
    url = str(getattr(engine, 'url', '') or '')
    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎，列由 ORM 模型/迁移工具负责'

    if 'watchlist' not in inspect(engine).get_table_names():
        return '[SKIP] watchlist 表不存在（空库，init_db 将按新模型建表）'

    cols = [('name', 'VARCHAR(100)')]
    with engine.connect() as conn:
        existing = {c['name'] for c in inspect(engine).get_columns('watchlist')}
        added = []
        for name, typ in cols:
            if name not in existing:
                conn.execute(text(f'ALTER TABLE watchlist ADD COLUMN {name} {typ}'))
                added.append(name)
        conn.commit()
    if added:
        logger.info(f'[OK] watchlist 增加列: {added}')
        return f'[OK] 增加列 {added}'
    return '[SKIP] watchlist.name 快照列已存在'


def migrate_advisor_portfolio_metrics(engine: Engine) -> str:
    """advisor_portfolios 补 投顾品类差异化指标列（#1392）：区间收益 / 回撤 / 超额。

    SQLite / libsql 支持对「可空列」直接 ALTER ADD COLUMN（无需整表重建）。
    幂等：列已存在则跳过。非 SQLite 引擎（Supabase Postgres）由 ORM 模型 / 迁移工具负责，
    直接跳过，避免 init_db 在 Supabase 路径上误跑 SQLite 专属 SQL。
    """
    url = str(getattr(engine, 'url', '') or '')
    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎，列由 ORM 模型/迁移工具负责'

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
    with engine.connect() as conn:
        existing = {c['name'] for c in inspect(engine).get_columns('advisor_portfolios')}
        added = []
        for name, typ in cols:
            if name not in existing:
                conn.execute(text(f'ALTER TABLE advisor_portfolios ADD COLUMN {name} {typ}'))
                added.append(name)
        conn.commit()
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
    直接 ALTER ADD COLUMN（无需整表重建）。幂等：列已存在则跳过。非 SQLite 引擎
    （Supabase Postgres）由 ORM 模型 / 迁移工具负责，直接跳过，避免 init_db 误跑 SQLite 专属 SQL。
    """
    url = str(getattr(engine, 'url', '') or '')
    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎，列由 ORM 模型/迁移工具负责'

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
    with engine.connect() as conn:
        existing = {c['name'] for c in inspect(engine).get_columns('advisor_portfolios')}
        added = []
        for name, typ in cols:
            if name not in existing:
                conn.execute(text(f'ALTER TABLE advisor_portfolios ADD COLUMN {name} {typ}'))
                added.append(name)
        conn.commit()
    if added:
        logger.info(f'[OK] advisor_portfolios 增加列: {added}')
        return f'[OK] 增加列 {added}'
    return '[SKIP] advisor_portfolios 元数据列已存在'


def migrate_channel_link_indexes(engine: Engine) -> str:
    """channel_links 补 to_symbol 索引（#1491 评审）。

    `to_symbol` 是查询 / join 字段（跨渠道关联回填与「ETF→联接」查询都按它过滤），
    模型此前未声明索引 → 按目标代码查找会全表扫描。

    SQLite 支持 `CREATE INDEX IF NOT EXISTS`，无需重建表；非 SQLite 引擎
    （Supabase Postgres）由 ORM 模型 / 迁移工具负责，直接跳过。
    `create_all` 只建新表、不给存量表加索引，故与 watchlist 约束同法由 init_db 启动期兜底。
    """
    url = str(getattr(engine, 'url', '') or '')
    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎，索引由 ORM 模型/迁移工具负责'

    if 'channel_links' not in inspect(engine).get_table_names():
        return '[SKIP] channel_links 表不存在（空库，init_db 将按新模型建表）'

    with engine.connect() as conn:
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_channel_links_to_symbol ON channel_links (to_symbol)'))
        conn.commit()

    names = [i['name'] for i in inspect(engine).get_indexes('channel_links')]
    if 'ix_channel_links_to_symbol' in names:
        logger.info('[OK] channel_links.to_symbol 索引已就绪')
        return '[OK] channel_links.to_symbol 索引已就绪'
    raise RuntimeError('channel_links.to_symbol 索引创建后校验失败')
