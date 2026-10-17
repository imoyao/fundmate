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


def migrate_advisor_portfolio_provenance(engine: Engine) -> str:
    """advisor_portfolios 补「数据来历 + 平台特有字段」列（#1392 Ports & Adapters 收口）。

    - ``source``：本行概览/指标最近一次写入来源（``tiantian`` / ``qieman`` / ``seed``），
      与 ``advisor_holdings.source`` 同口径——「这行数据是谁写的」此前无处回答；
    - ``extra``：canonical 概览覆盖不到的**平台特有字段**（JSON 原样保留），
      新增平台不必为此加列，日后真要补列时可回填，无需重新抓取。

    与 :func:`migrate_advisor_portfolio_metrics` 同源同法：SQLite / libsql 支持对「可空列」
    直接 ALTER ADD COLUMN（无需整表重建）。幂等：列已存在则跳过。非 SQLite 引擎
    （Supabase Postgres）由 ORM 模型 / 迁移工具负责，直接跳过，避免 init_db 误跑 SQLite 专属 SQL。
    """
    url = str(getattr(engine, 'url', '') or '')
    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎，列由 ORM 模型/迁移工具负责'

    # 空库（表还没建）直接 skip：create_all 会按新模型建表，此处不该替它兜底
    if 'advisor_portfolios' not in inspect(engine).get_table_names():
        return '[SKIP] advisor_portfolios 表不存在（空库，init_db 将按新模型建表）'

    cols = [
        ('source', 'VARCHAR(20)'),
        ('extra', 'JSON'),
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

    幂等：列已存在则跳过。非 SQLite 引擎（Supabase Postgres）由 ORM 模型 / 迁移工具负责，
    直接跳过，避免 init_db 在 Supabase 路径上误跑 SQLite 专属 SQL。

    ⚠️ 本迁移**只加列、不回填**：`prev_close` 是「上一确认价」，只能在写入
    `current_price` 的**同一批**里取到（`sync/jobs/position_price_job`），事后凭历史数据
    补不出时点正确的值（补错了比空着更糟）。存量行会在下次调度自然补齐。
    """
    url = str(getattr(engine, 'url', '') or '')
    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎，列由 ORM 模型/迁移工具负责'

    if 'positions' not in inspect(engine).get_table_names():
        return '[SKIP] positions 表不存在（空库，init_db 将按新模型建表）'

    cols = [('prev_close', 'INTEGER'), ('price_date', 'DATE')]
    with engine.connect() as conn:
        existing = {c['name'] for c in inspect(engine).get_columns('positions')}
        added = []
        for name, typ in cols:
            if name not in existing:
                conn.execute(text(f'ALTER TABLE positions ADD COLUMN {name} {typ}'))
                added.append(name)
        conn.commit()
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

    幂等：结论与库中值一致就不写；非 SQLite 引擎（Supabase Postgres）跳过，由 ORM /
    迁移工具负责。
    """
    url = str(getattr(engine, 'url', '') or '')
    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎，货基标记由 ORM 模型/迁移工具负责'

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

    SQLite / libsql 支持对可空列直接 ALTER ADD COLUMN（无需整表重建）；非 SQLite 引擎
    由 ORM 模型 / 迁移工具负责，直接跳过。新表 fund_holdings / fund_industry_allocs
    由 create_all 建，无需迁移。
    """
    url = str(getattr(engine, 'url', '') or '')
    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎，列由 ORM 模型/迁移工具负责'

    if 'funds' not in inspect(engine).get_table_names():
        return '[SKIP] funds 表不存在（空库，init_db 将按新模型建表）'

    existing = {c['name'] for c in inspect(engine).get_columns('funds')}
    if 'equity_position_period' in existing:
        return '[SKIP] funds.equity_position_period 已存在'

    with engine.connect() as conn:
        conn.execute(text('ALTER TABLE funds ADD COLUMN equity_position_period VARCHAR(8)'))
        conn.commit()

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
    幂等：列已存在则跳过。非 SQLite 引擎（Supabase Postgres）由 ORM 模型 / 迁移工具
    负责，直接跳过。

    ⚠️ 本迁移**只加列、不回填**：偏差是「当时预估 vs 当时官方」的时点对照，
    事后可以补算（reconcile job 会自然收敛历史 estimated 行），无需启动期回填。
    """
    url = str(getattr(engine, 'url', '') or '')
    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎，列由 ORM 模型/迁移工具负责'

    if 'fund_valuation_daily' not in inspect(engine).get_table_names():
        return '[SKIP] fund_valuation_daily 表不存在（空库，init_db 将按新模型建表）'

    cols = [
        ('official_nav', 'NUMERIC(18, 6)'),
        ('deviation', 'NUMERIC(18, 6)'),
        ('deviation_pct', 'NUMERIC(10, 4)'),
    ]
    with engine.connect() as conn:
        existing = {c['name'] for c in inspect(engine).get_columns('fund_valuation_daily')}
        added = []
        for name, typ in cols:
            if name not in existing:
                conn.execute(text(f'ALTER TABLE fund_valuation_daily ADD COLUMN {name} {typ}'))
                added.append(name)
        conn.commit()
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
    启动期迁移只负责把列建好。幂等：列已存在则跳过；非 SQLite 引擎
    （Supabase Postgres）由 ORM 模型 / 迁移工具负责，直接跳过。
    """
    url = str(getattr(engine, 'url', '') or '')
    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎，列由 ORM 模型/迁移工具负责'

    if 'fund_risk_metrics' not in inspect(engine).get_table_names():
        return '[SKIP] fund_risk_metrics 表不存在（空库，init_db 将按新模型建表）'

    cols = [
        ('ret_1m', 'NUMERIC(10, 4)'),
        ('ret_3m', 'NUMERIC(10, 4)'),
        ('ret_1y', 'NUMERIC(10, 4)'),
    ]
    with engine.connect() as conn:
        existing = {c['name'] for c in inspect(engine).get_columns('fund_risk_metrics')}
        added = []
        for name, typ in cols:
            if name not in existing:
                conn.execute(text(f'ALTER TABLE fund_risk_metrics ADD COLUMN {name} {typ}'))
                added.append(name)
        conn.commit()
    if added:
        logger.info(f'[OK] fund_risk_metrics 增加区间收益列: {added}')
        return f'[OK] 增加列 {added}'
    return '[SKIP] fund_risk_metrics 区间收益三列已存在'
