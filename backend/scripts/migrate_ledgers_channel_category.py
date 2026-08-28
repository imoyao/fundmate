# -*- coding: utf-8 -*-
"""为既有 SQLite 数据库的 ledgers 表补 channel_category 列并回填（#1101 渠道分类重设计）。

背景：账户新增 channel_category（用户可见的渠道分组/类型标签），与 ledger_type 正交。
SQLAlchemy create_all 不会给已存在表补列，需本脚本幂等迁移 + 回填存量数据。

回填规则（权威见 docs/working-notes/ledger-channel-category-redesign-2026-08-28.md §6）：
  - 有 sales_institution_id：JOIN sales_institutions.org_type → map_org_type_to_channel_category
    （org_type 权威，即使与 ledger_type 冲突也以 org_type 为准，如 fund 账本指向商业银行→bank）；
  - 无销售机构：按 ledger_type 回退 bank→bank, stock→securities, fund→fund_platform,
    property→other, e_account→other, family→other。

用法（在 backend 目录）：
    pdm run python scripts/migrate_ledgers_channel_category.py
"""

import os
import sqlite3
import sys

# 优先复用 app 内权威映射；导入失败则内联（必须与 app/domains/ledgers/constants.py 保持一致）。
try:
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    # 让 backend 目录进入 sys.path 以便 import app
    _backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if _backend_root not in sys.path:
        sys.path.insert(0, _backend_root)
    from app.domains.ledgers.constants import map_org_type_to_channel_category  # noqa: E402

    _USING_APP_MAPPING = True
except Exception:  # pragma: no cover - 兜底内联
    _USING_APP_MAPPING = False

    def map_org_type_to_channel_category(org_type):
        # 必须与 app/domains/ledgers/constants.py 保持一致
        mapping = {
            '商业银行': 'bank',
            '全国性商业银行': 'bank',
            '农村商业银行': 'bank',
            '外资银行': 'bank',
            '证券公司': 'securities',
            '证券投资咨询机构': 'securities',
            '独立基金销售机构': 'fund_platform',
            '基金销售支付结算机构': 'fund_platform',
            '保险公司': 'insurance',
            '期货公司': 'futures',
            '基金公司': 'other',
            '基金管理公司子公司': 'other',
        }
        if not org_type:
            return 'other'
        return mapping.get(org_type, 'other')


LEDGER_TYPE_FALLBACK = {
    'bank': 'bank',
    'stock': 'securities',
    'fund': 'fund_platform',
    'property': 'other',
    'e_account': 'other',
    'family': 'other',
}


def _backfill_channel_category(conn):
    """逐条回填 channel_category，返回各分类命中计数。"""
    rows = conn.execute('SELECT id, ledger_type, sales_institution_id FROM ledgers').fetchall()
    counts = {}
    for ledger_id, ledger_type, sales_institution_id in rows:
        channel_category = None
        if sales_institution_id:
            org_type = conn.execute(
                'SELECT org_type FROM sales_institutions WHERE id = ?',
                (sales_institution_id,),
            ).fetchone()
            if org_type and org_type[0]:
                channel_category = map_org_type_to_channel_category(org_type[0])
        if not channel_category:
            channel_category = LEDGER_TYPE_FALLBACK.get(ledger_type, 'other')
        conn.execute(
            'UPDATE ledgers SET channel_category = ? WHERE id = ?',
            (channel_category, ledger_id),
        )
        counts[channel_category] = counts.get(channel_category, 0) + 1
    return counts


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
        if 'ledgers' not in tables:
            print('ledgers 表不存在，无需迁移。')
            sys.exit(0)

        cols = {row[1] for row in conn.execute('PRAGMA table_info(ledgers)')}
        if 'channel_category' in cols:
            print('ledgers 表已含 channel_category 列，跳过加列。')
        else:
            conn.execute('ALTER TABLE ledgers ADD COLUMN channel_category VARCHAR(20)')
            print('  [OK] ledgers: 已添加 channel_category 列')

        # 回填（无论是否刚加列都执行，保证幂等）
        counts = _backfill_channel_category(conn)
        conn.commit()
        print('  [OK] channel_category 回填完成，各分类计数:')
        for cat in sorted(counts):
            print(f'        {cat}: {counts[cat]}')
    finally:
        conn.close()
    print(
        '[OK] ledgers channel_category 迁移完成' + ('（使用 app 内映射）' if _USING_APP_MAPPING else '（使用内联映射）')
    )


if __name__ == '__main__':
    main()
