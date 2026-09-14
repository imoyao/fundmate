# -*- coding: utf-8 -*-
"""为既有 SQLite 数据库的 watchlist 表补「下次复盘提醒日期」列（next_review_date）。

背景：未竟之蹊（/the-road-not-taken）卡片的复盘提醒需要持久化「下次复盘日期」，
而 SQLAlchemy 的 `create_all` 不会给已存在的表补列；且 `core/database._validate_schema`
在模型与库结构不一致时会拒绝启动，故模型加列必须配套迁移脚本。

watchlist 属 user 域（本地回退为 invest.user.dev.db），但历史库也有把全部表建在
invest.db / invest.dev.db 的情况，因此本脚本对全部候选库文件逐一幂等补齐。

本脚本幂等执行：
1. 逐个候选库文件检查 `watchlist` 表是否已有 `next_review_date` 列；
2. 缺失则执行 `ALTER TABLE watchlist ADD COLUMN next_review_date DATE`；
3. 文件不存在 / 表不存在 / 列已存在均跳过，不做任何破坏性操作。

用法（在 backend 目录）：
    pdm run python scripts/migrate_watchlist_review_date.py

生产（Supabase Postgres）不在本脚本覆盖范围，需手工执行：
    ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS next_review_date DATE;
"""

import os
import sqlite3

COLUMN_SQL = 'ALTER TABLE watchlist ADD COLUMN next_review_date DATE'

# 候选库文件（相对 backend 目录）：覆盖单库模式、dev 双库模拟模式与 env 覆写。
# 末尾两条是历史缺省文件名（invest.dev.db），已不再是代码缺省，但存量机器可能有，保留扫描。
CANDIDATE_URLS = (
    os.getenv('DATABASE_URL', 'sqlite:///./invest.db'),
    os.getenv('DEV_DATABASE_URL', 'sqlite:///./invest.db'),
    os.getenv('DEV_USER_DATABASE_URL', 'sqlite:///./invest.user.dev.db'),
    os.getenv('USER_DATABASE_URL', 'sqlite:///./invest.db'),
    'sqlite:///./invest.dev.db',
)


def _to_path(url: str) -> str:
    path = url.split('sqlite:///', 1)[-1]
    return path if os.path.isabs(path) else os.path.abspath(path)


def migrate_file(path: str) -> None:
    if not os.path.exists(path):
        print(f'  [跳过] 文件不存在: {path}')
        return

    conn = sqlite3.connect(path)
    try:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
        if 'watchlist' not in tables:
            print(f'  [跳过] 无 watchlist 表: {path}')
            return
        cols = {row[1] for row in conn.execute('PRAGMA table_info(watchlist)')}
        if 'next_review_date' in cols:
            print(f'  [跳过] 列已存在: {path}')
            return
        conn.execute(COLUMN_SQL)
        conn.commit()
        print(f'  [OK] 已补列 next_review_date: {path}')
    finally:
        conn.close()


def main() -> None:
    seen: set[str] = set()
    print('目标库文件：')
    for url in CANDIDATE_URLS:
        if not url.startswith('sqlite'):
            print(f'  [跳过] 非 SQLite 连接串: {url}')
            continue
        path = _to_path(url)
        if path in seen:
            continue
        seen.add(path)
        migrate_file(path)
    print('[OK] watchlist 复盘日期列迁移完成')


if __name__ == '__main__':
    main()
