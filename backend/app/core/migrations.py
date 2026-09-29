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
