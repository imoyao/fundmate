# -*- coding: utf-8 -*-
"""为既有 SQLite 数据库补销售机构「常用机构」策展列（#1081）。

背景：SalesInstitution 新增 `is_common` / `common_sort` 两列（常用分组置顶 + 组内排序），
而 SQLAlchemy 的 `create_all` 不会给已存在的表补列，直接启动会被
`_validate_schema` 的漂移检查拒绝（数据库结构与模型不一致）。

本脚本幂等执行：
1. 对 `sales_institutions` 缺失的列执行 `ALTER TABLE ... ADD COLUMN`；
2. 不做数据回填——策展值由 AMAC 同步 job 按代码常量 CURATED_INSTITUTIONS
   幂等覆写（代码即 source of truth），跑一次 `sync --job amac_institution` 即收敛。

用法（在 backend 目录）：
    pdm run python scripts/migrate_sales_institution_common.py
"""

import os
import sqlite3
import sys

from loguru import logger

# 列定义与模型保持一致（app/domains/positions/models.py SalesInstitution）
COLUMNS = {
    'is_common': 'INTEGER NOT NULL DEFAULT 0',
    'common_sort': 'INTEGER',
    'pinyin_short': 'VARCHAR(100)',
}


def main() -> None:
    db_url = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')
    if not db_url.startswith('sqlite'):
        logger.warning('仅支持 SQLite 数据库迁移，当前 DATABASE_URL={}，请手动处理。', db_url)
        sys.exit(1)

    # 提取文件路径：sqlite:///./invest.db 或 sqlite:////abs/path.db
    path = db_url.replace('sqlite:///', '', 1)
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    logger.info('目标数据库: {}', path)
    if not os.path.exists(path):
        logger.info('数据库文件不存在，无需迁移（首次启动将自动建表）。')
        sys.exit(0)

    conn = sqlite3.connect(path)
    try:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
        if 'sales_institutions' not in tables:
            logger.info('sales_institutions 表不存在，无需迁移（首次启动将自动建表）。')
            sys.exit(0)
        cols = {row[1] for row in conn.execute('PRAGMA table_info(sales_institutions)')}
        for col, ddl in COLUMNS.items():
            if col in cols:
                logger.info('  [SKIP] {} 已存在', col)
                continue
            conn.execute(f'ALTER TABLE sales_institutions ADD COLUMN {col} {ddl}')
            logger.success('  [OK] 已添加 {}', col)
        conn.commit()
    finally:
        conn.close()
    logger.info('[OK] 迁移完成。策展数据请运行: pdm run sync --job amac_institution')


if __name__ == '__main__':
    main()
