# -*- coding: utf-8 -*-
"""为既有 SQLite 数据库的 fee_ratios 表补充币种列（currency）。

背景：issue #820 为 FeeRatio 增加币种字段并落库。SQLAlchemy 的 `create_all`
不会给已存在的表补列，直接启动会导致 `no such column: currency`。

本脚本幂等执行：
1. 检查 `fee_ratios` 表是否已有 `currency` 列；
2. 对缺失列执行 `ALTER TABLE fee_ratios ADD COLUMN currency VARCHAR(10) NOT NULL DEFAULT 'CNY'`；
3. 按基金份额名称特征回填币种（与 FundService.infer_fund_currency 同规则）：
   含"人民币"或全无外币字样 → CNY；含"美元/港币/港元/日元/欧元/英镑" → 对应 ISO 码；
4. 兼容既有 `invest.db`（无需重建数据库文件）。

用法（在 backend 目录）：
    pdm run python scripts/migrate_fee_ratio_currency.py
"""

import os
import sqlite3
import sys

# 与 app/services/fund_service.py 的 _CURRENCY_MARKERS 保持同序同义：
# "人民币"优先匹配（QDII 名称可能同时含"美元"与"人民币"，如"中银美元债债券(QDII)人民币A"）
CURRENCY_MARKERS = (
    ('人民币', 'CNY'),
    ('美元', 'USD'),
    ('港币', 'HKD'),
    ('港元', 'HKD'),
    ('日元', 'JPY'),
    ('欧元', 'EUR'),
    ('英镑', 'GBP'),
)


def _infer_currency(full_name: str, name: str) -> str:
    text = ' '.join([full_name or '', name or ''])
    for marker, currency in CURRENCY_MARKERS:
        if marker in text:
            return currency
    return 'CNY'


def main() -> None:
    db_url = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')
    if not db_url.startswith('sqlite'):
        print('仅支持 SQLite 数据库迁移，当前 DATABASE_URL=%s，请手动处理。' % db_url)
        sys.exit(1)

    path = db_url.replace('sqlite:///', '', 1)
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    print(f'目标数据库: {path}')
    if not os.path.exists(path):
        print('数据库文件不存在，无需迁移（首次启动将自动建表）。')
        sys.exit(0)

    conn = sqlite3.connect(path)
    try:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
        if 'fee_ratios' not in tables:
            print('fee_ratios 表不存在，无需迁移。')
            sys.exit(0)
        cols = {row[1] for row in conn.execute('PRAGMA table_info(fee_ratios)')}
        if 'currency' not in cols:
            conn.execute("ALTER TABLE fee_ratios ADD COLUMN currency VARCHAR(10) NOT NULL DEFAULT 'CNY'")
            print('  [OK] fee_ratios: 已添加 currency')

        # 按基金份额名称特征回填币种（同 FundService.infer_fund_currency 规则）
        rows = conn.execute(
            """
            SELECT fr.rowid, f.name, f.full_name
            FROM fee_ratios fr
            LEFT JOIN funds f ON fr.fund_code = f.fund_code
            """
        ).fetchall()
        updated = 0
        for rowid, name, full_name in rows:
            currency = _infer_currency(full_name, name)
            conn.execute('UPDATE fee_ratios SET currency = ? WHERE rowid = ?', (currency, rowid))
            updated += 1
        conn.commit()
        print(f'  [OK] fee_ratios: 已回填币种 {updated} 行')
    finally:
        conn.close()
    print('[OK] 费率币种迁移完成')


if __name__ == '__main__':
    main()
