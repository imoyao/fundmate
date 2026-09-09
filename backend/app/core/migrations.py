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
