# -*- coding: utf-8 -*-
"""回填 ``sales_institutions`` 的 ``pinyin_short`` / ``pinyin_full``（#2980）。

## 为什么要它

``pinyin_full``（全拼）是本轮新增列：机构全名「蚂蚁（杭州）基金销售有限公司」只有
简拼 ``MYHZJJXSYXGS`` 时，用户输入 ``zhifubao`` 搜不到自己天天用的「支付宝」。
新列由迁移加出，但**存量 394 行留空**——空列等于没加，检索仍然搜不到。

AMAC 同步 job 每次跑都会覆写这两列，但「下次调度」可能是几天后；本地开发库、
刚迁移完的环境都需要立刻可用，故提供一次性回填。

## 判据

- 派生唯一来源 ``app.services.sync.institution_pinyin.derive_pinyin``——本脚本
  **不重复实现**拼音规则（两份实现必然漂移，见 #2958 教训）。
- ``pinyin_full`` = 全名全拼 + 空格 + 别名全拼；别名缺失时只留全名。
- 默认 dry-run，只打印计划；``--apply`` 才写库。
- 幂等：重复执行结果一致（每次都按当前 org_name/display_name 重算）。

用法（在 backend/ 目录下）::

    pdm run python scripts/backfill_institution_pinyin.py --db invest.db
    pdm run python scripts/backfill_institution_pinyin.py --db invest.db --apply
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.sync.institution_pinyin import derive_pinyin  # noqa: E402


def ensure_column(conn: sqlite3.Connection) -> bool:
    """列缺失时补上（与 ``migrate_sales_institution_pinyin_full`` 的 DDL 一致）。"""
    cols = {row[1] for row in conn.execute('PRAGMA table_info(sales_institutions)')}
    if 'pinyin_full' in cols:
        return False
    conn.execute('ALTER TABLE sales_institutions ADD COLUMN pinyin_full VARCHAR(400)')
    conn.commit()
    return True


def plan(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        'SELECT id, org_name, display_name, pinyin_short, pinyin_full FROM sales_institutions ORDER BY id'
    ).fetchall()
    changes = []
    for rid, org_name, display_name, short, full in rows:
        new_short, new_full = derive_pinyin(org_name, display_name)
        if new_short == short and new_full == full:
            continue
        changes.append(
            {
                'id': rid,
                'org_name': org_name,
                'short_old': short,
                'short_new': new_short,
                'full_old': full,
                'full_new': new_full,
            }
        )
    return changes


def apply_plan(conn: sqlite3.Connection, changes: list[dict]) -> None:
    conn.executemany(
        'UPDATE sales_institutions SET pinyin_short = ?, pinyin_full = ? WHERE id = ?',
        [(c['short_new'], c['full_new'], c['id']) for c in changes],
    )
    conn.commit()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='回填销售机构拼音简拼/全拼（#2980）')
    parser.add_argument('--db', required=True, help='invest.db 路径（必填，避免误连生产库）')
    parser.add_argument('--apply', action='store_true', help='真正写库（默认仅打印计划）')
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f'致命：找不到数据库 {db_path}')
        return 2

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        if ensure_column(conn):
            print('[OK] 已补 pinyin_full 列（等价于启动期迁移）')
        changes = plan(conn)
        print(f'需回填：{len(changes)} 行')
        for c in changes[:20]:
            print(f'  #{c["id"]:<4} {c["org_name"][:28]:<30} 全拼 ← {c["full_new"][:46]}')
        if len(changes) > 20:
            print(f'  ……另有 {len(changes) - 20} 行')
        if not args.apply:
            print('\n（dry-run，未写库；确认无误后加 --apply）')
            return 0
        apply_plan(conn, changes)
        print(f'\n[OK] 已写回 {len(changes)} 行')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
