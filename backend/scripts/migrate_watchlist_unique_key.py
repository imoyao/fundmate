# -*- coding: utf-8 -*-
"""自选表唯一键回归设计基线：(symbol, venue) → (symbol, market, venue)（#1286）。

背景：docs/features/watchlist.md §1.3.1 设计基线的唯一键本就是三列组合
（防 000001 上证指数 vs 平安银行跨市场同码冲突），早期实现缩水为两列。
本次回归基线，为指数/基金经理/投顾组合进入自选扫清唯一性障碍。

SQLite 不支持直接改表约束，走「建新表→拷贝→删旧→改名」标准重建流程。
幂等：已含新约束（建表 SQL 中出现 uk_watchlist_symbol_market_venue）时跳过。

用法（在 backend 目录）：
    pdm run python scripts/migrate_watchlist_unique_key.py
"""

import re
import sys

from sqlalchemy import inspect, text

from app.core.db_factory import DOMAIN_USER, DatabaseFactory


def main() -> None:
    # watchlist 属 user 域（默认单库时与 market 同引擎）
    engine = DatabaseFactory.create(DOMAIN_USER)

    with engine.connect() as conn:
        ddl = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='watchlist'")).scalar()
        if ddl is None:
            print('[SKIP] watchlist 表不存在（空库，init_db 将按新约束建表）')
            return
        if 'uk_watchlist_symbol_market_venue' in ddl:
            print('[SKIP] 新唯一键已存在，无需迁移')
            return
        if 'uk_watchlist_symbol_venue' not in ddl:
            print(f'[WARN] 未找到旧约束 uk_watchlist_symbol_venue，表结构如下，请人工确认：\n{ddl}')
            sys.exit(1)

        # 旧建表 SQL 中把两列约束替换为三列约束，其余保持原样
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
            print(f'[ERROR] 约束替换失败，表结构：\n{ddl}')
            sys.exit(1)

        new_ddl = new_ddl.replace('CREATE TABLE watchlist', 'CREATE TABLE watchlist_new', 1)
        conn.execute(text('PRAGMA foreign_keys=OFF'))
        conn.execute(text(new_ddl))
        conn.execute(
            text("""
                INSERT INTO watchlist_new
                SELECT id, symbol, market, asset_type, venue, status, favorite, favorite_at,
                       next_review_date, source_cycle_id, is_pinned, pinned_at, add_reason,
                       notes, cost_price, quantity, created_at, updated_at, family_id
                FROM watchlist
            """)
        )
        conn.execute(text('DROP TABLE watchlist'))
        conn.execute(text('ALTER TABLE watchlist_new RENAME TO watchlist'))
        conn.commit()

    insp = inspect(engine)
    idx = [i['name'] for i in insp.get_indexes('watchlist') if i.get('unique')]
    ddl2 = None
    with engine.connect() as conn:
        ddl2 = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='watchlist'")).scalar()
    if 'uk_watchlist_symbol_market_venue' in (ddl2 or ''):
        print(f'[OK] 唯一键已迁移为 (symbol, market, venue)；当前唯一索引: {idx}')
    else:
        print('[ERROR] 迁移后校验失败')
        sys.exit(1)


if __name__ == '__main__':
    main()
