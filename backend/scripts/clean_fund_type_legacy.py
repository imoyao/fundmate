# -*- coding: utf-8 -*-
"""清理历史脏分类「基金型」（#1224 反馈）。

背景：基金资料同步（akshare 原始类型文本）曾把一批 QDII/FOF 基金的类型文本
解析成「基金型」，在 fund_types / fund_varieties 各生成一条「基金型」记录。
标准基金分类（股票型/混合型/债券型/指数型/货币型）中没有此类型。

本脚本：
1. 把 fund_type_id / fund_variety_id 指向「基金型」的基金重置为未分类（NULL）；
2. 删除 fund_types 与 fund_varieties 中的「基金型」记录。

防再产生：FundTypeResolver 已加黑名单（fund_type_resolution.py），
后续同步不会再创建「基金型」；被重置的基金可在下次同步时按真实类型文本重新回填。

用法：
  pdm run python scripts/clean_fund_type_legacy.py                 # dry-run，仅列出
  pdm run python scripts/clean_fund_type_legacy.py --apply          # 真正执行（执行前自动备份 db）
  pdm run python scripts/clean_fund_type_legacy.py --db <path>     # 指定库
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

_LEGACY_TYPE = '基金型'


def main() -> int:
    parser = argparse.ArgumentParser(description='清理历史脏分类「基金型」')
    parser.add_argument('--db', default='invest.db', help='SQLite 数据库路径（默认 invest.db）')
    parser.add_argument('--apply', action='store_true', help='真正执行；缺省为 dry-run')
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f'[错误] 数据库不存在: {db_path}')
        return 1

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1) 找出「基金型」的 type / variety 记录
    type_ids = [r[0] for r in cur.execute('SELECT id FROM fund_types WHERE name = ?', (_LEGACY_TYPE,)).fetchall()]
    variety_ids = [
        r[0] for r in cur.execute('SELECT id FROM fund_varieties WHERE name = ?', (_LEGACY_TYPE,)).fetchall()
    ]

    if not type_ids and not variety_ids:
        print(f'未发现「{_LEGACY_TYPE}」记录，无需清理。')
        return 0

    # 2) 列出关联基金（去重）
    affected: list[tuple] = []
    seen: set[str] = set()
    for tid in type_ids:
        for code, name in cur.execute('SELECT fund_code, name FROM funds WHERE fund_type_id = ?', (tid,)).fetchall():
            if code not in seen:
                seen.add(code)
                affected.append((code, name))
    for vid in variety_ids:
        for code, name in cur.execute('SELECT fund_code, name FROM funds WHERE fund_variety_id = ?', (vid,)).fetchall():
            if code not in seen:
                seen.add(code)
                affected.append((code, name))

    print(f'待清理基金 {len(affected)} 只（重置为未分类）：')
    for code, name in affected:
        print(f'  {code}  {name}')

    if not args.apply:
        print('\n[dry-run] 未做任何修改；加 --apply 真正执行（执行前自动备份 db）。')
        return 0

    # 3) 备份
    backup = db_path.with_name(f'{db_path.name}.bak.{datetime.now().strftime("%Y%m%d%H%M%S")}')
    shutil.copy2(db_path, backup)
    print(f'[备份] {backup}')

    # 4) 重置基金分类为未分类
    for tid in type_ids:
        cur.execute('UPDATE funds SET fund_type_id = NULL WHERE fund_type_id = ?', (tid,))
    for vid in variety_ids:
        cur.execute('UPDATE funds SET fund_variety_id = NULL WHERE fund_variety_id = ?', (vid,))

    # 5) 删除「基金型」记录（先 type 后 variety）
    for tid in type_ids:
        cur.execute('DELETE FROM fund_types WHERE id = ?', (tid,))
    for vid in variety_ids:
        cur.execute('DELETE FROM fund_varieties WHERE id = ?', (vid,))

    conn.commit()
    conn.close()
    print(f'[完成] 已重置 {len(affected)} 只基金为未分类，并删除「{_LEGACY_TYPE}」记录。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
