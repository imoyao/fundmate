# -*- coding: utf-8 -*-
"""基金公司主数据合并：`fund_management_companies`（user 域死表）→ `fund_companies`。

背景（2026-09-10 审计）
--------------------
库里有两张表达「基金公司」的表，长期双写、零关联：

| 表 | 域 | 行数 | 写者 | 读者 |
|---|---|---|---|---|
| `fund_companies` | market | 176 | 东财链路（fund_list/fund_detail/manager 三个 job）+ 无 | funds/managers 外键 |
| `fund_management_companies` | user | 165 | 仅 `amac_institution_job` | **零**（无外键/无接口/无代码引用） |

死表本身不产生脏数据，但它承载的 AMAC 权威信息（全称/地址/官网/客服电话）无处可用，
且「公司数据到底在哪张表」是持续误导（`db_factory.py` 旧注释甚至写「被 positions 引用」，
实测为假）。本脚本把信息合并进唯一主数据表后删除死表。

顺带发现并一并处理的缺陷
------------------------
1. **`fund_companies` 内部有重复实体**（实测 8 组）：同一家公司因「东财给简称 / akshare
   给全称」被两个 job 各建一行，经理归属被分裂（招商基金 103 + 9 行）。根因已在
   代码侧收口（`company_resolver.get_or_create_fund_company` 成为唯一写入口），
   历史脏数据由本脚本合并——**规范行取简称行**（实测其同时持有东财权威 code 与绝大多数
   经理引用，见 `company_resolver.canonical_company_order`）。
2. **`full_name` 全表为空**（176 行）：合并后由 AMAC 全称填充。

本脚本做什么
------------
阶段 1（补列）：`fund_companies` 补 5 列——`register_addr` / `office_addr` /
    `website` / `phone` / `is_active`（原死表字段）。模型加了列而库没跟上会被
    `core/database._validate_schema` 拒绝启动，故必须先跑。
阶段 2（回填）：把 AMAC 全称写进 `full_name`，地址/官网/电话写进对应列。
    匹配用 `company_resolver`（归一化名 + 业务族），实测 165 条命中 161 条；
    **未命中不新建行**（AMAC 不提供东财 8 位编码，硬造编码等于给公司主数据开第二个写者）。
阶段 3（去重）：同键（归一化名 + 业务族）多行的，按 `pick_canonical_company` 选规范行，
    把 `managers.company_id` / `funds.company_id` 重映射过去，删除冗余行。
阶段 4（简称化）：`name` 列语义是简称，但存量里 **119/176 行的 `name` 是法人全称**
    （历史各来源写名形态不一）。用东财公司列表 `jjjz_gs.js` 的 `code → 简称` 映射
    （该表的 code 就是本表主键级标识，实测 113/119 可解析）把简称写回 `name`、
    全称移入 `full_name`。**只做 code 映射，不做名称模糊匹配**——模糊匹配有把
    A 公司简称写到 B 公司上的风险。剩余 6 行 `code=name` 占位无法映射，留报告待
    `company_resolver.backfill_fund_company_codes` 先补真值 code。
阶段 5（删除）：`DROP TABLE fund_management_companies`。

安全性
------
- **默认干跑**：不带 `--apply` 只打印将发生什么，不写任何库。
- 幂等：重复执行结果一致（列已存在就跳过、死表已删就跳过、无重复行就不动）。
- 只处理 SQLite 候选库文件；**生产（Supabase/Turso）不在覆盖范围**，需手工执行——
  见文件末尾 PRINT 的等价 SQL。

用法（在 backend 目录）
    pdm run python scripts/migrate_fund_company_merge.py            # 干跑，看报告
    pdm run python scripts/migrate_fund_company_merge.py --apply    # 落库
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.sync.company_resolver import (  # noqa: E402
    company_index_key,
    fetch_fund_company_list,
    looks_like_full_name,
    pick_canonical_company,
)

# 候选库文件（相对 backend 目录）：覆盖单库模式、dev 双库模拟模式与 env 覆写。
# `fund_companies`（market 域）与死表（user 域）在单库模式下同文件、拆库时分处两个文件，
# 故这里统一扫全部候选文件，各阶段按「表是否存在」自行跳过。
CANDIDATE_URLS = tuple(
    dict.fromkeys(
        (
            os.getenv('DATABASE_URL', 'sqlite:///./invest.db'),
            os.getenv('DEV_DATABASE_URL', 'sqlite:///./invest.db'),
            os.getenv('DEV_USER_DATABASE_URL', 'sqlite:///./invest.db'),
            os.getenv('USER_DATABASE_URL', 'sqlite:///./invest.db'),
            'sqlite:///./invest.db',
            'sqlite:///./invest.dev.db',  # 历史缺省文件名，存量机器可能还有
            'sqlite:///./invest.user.dev.db',  # 历史双库模拟的 user 库
        )
    )
)

# 阶段 1 要补的列（SQLite 的 ADD COLUMN 不支持 IF NOT EXISTS，故先查 PRAGMA）
NEW_COLUMNS = (
    ('register_addr', 'VARCHAR(200)'),
    ('office_addr', 'VARCHAR(200)'),
    ('website', 'VARCHAR(200)'),
    ('phone', 'VARCHAR(100)'),
    ('is_active', 'BOOLEAN DEFAULT 1'),
)

DEAD_TABLE = 'fund_management_companies'
MAIN_TABLE = 'fund_companies'


def _to_path(url: str) -> str:
    path = url.split('sqlite:///', 1)[-1]
    return path if os.path.isabs(path) else os.path.abspath(path)


def _tables(conn: sqlite3.Connection) -> set:
    return {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}


def _columns(conn: sqlite3.Connection, table: str) -> set:
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}


def collect_house_pool(paths) -> dict:
    """从所有候选库里收集 AMAC 基金管理人数据（死表尚未删除时才有内容）。"""
    pool = {}
    for path in paths:
        if not os.path.exists(path):
            continue
        conn = sqlite3.connect(path)
        try:
            if DEAD_TABLE not in _tables(conn):
                continue
            cur = conn.execute(f'select * from {DEAD_TABLE}')
            cols = [d[0] for d in cur.description]
            for row in cur:
                rec = dict(zip(cols, row))
                name = (rec.get('house_name') or '').strip()
                if name:
                    pool[name] = rec
            print(f'  [池] {path}: 读到 {len(pool)} 条基金管理人')
        finally:
            conn.close()
    return pool


def _build_index(conn: sqlite3.Connection) -> dict:
    """(归一化名, 业务族) → 规范行 id（与同步任务共用同一择一规则）。"""
    ref_counts = dict(
        conn.execute('select company_id, count(*) from managers where company_id is not null group by company_id')
    )
    for cid, cnt in conn.execute(
        'select company_id, count(*) from funds where company_id is not null group by company_id'
    ):
        ref_counts[cid] = ref_counts.get(cid, 0) + cnt

    grouped = {}
    for row_id, name in conn.execute(f'select id, name from {MAIN_TABLE}'):
        if name:
            grouped.setdefault(company_index_key(name), []).append((row_id, name, ref_counts.get(row_id, 0)))

    # full_name 现状（用于判断合并时是否还需把冗余行的全称提升上来）
    full_names = dict(conn.execute(f'select id, full_name from {MAIN_TABLE}'))
    index, canonical_rows = {}, {}
    for key, rows in grouped.items():
        canonical_id = pick_canonical_company(rows)[0]
        index[key] = canonical_id
        canonical_rows[canonical_id] = {
            'name': next(n for i, n, _ in rows if i == canonical_id),
            'full_name': full_names.get(canonical_id),
        }
    return index, canonical_rows, grouped


def migrate_file(path: str, house_pool: dict, short_name_map: dict, apply: bool) -> dict:
    report = {
        'added_columns': [],
        'enriched': 0,
        'unmatched': [],
        'renamed': [],
        'rename_unresolved': [],
        'merged': [],
        'repointed': 0,
        'dropped': False,
    }
    enriched_ids: set = set()
    if not os.path.exists(path):
        return report

    conn = sqlite3.connect(path)
    try:
        tables = _tables(conn)
        if MAIN_TABLE in tables:
            # ── 阶段 1：补列 ──
            existing = _columns(conn, MAIN_TABLE)
            for col, ddl in NEW_COLUMNS:
                if col in existing:
                    continue
                report['added_columns'].append(col)
                if apply:
                    conn.execute(f'ALTER TABLE {MAIN_TABLE} ADD COLUMN {col} {ddl}')

            if apply:
                conn.commit()

            index, canonical_rows, grouped = _build_index(conn)

            # ── 阶段 2：AMAC 回填 ──
            if house_pool:
                updates, unmatched = [], []
                for house_name, rec in house_pool.items():
                    target = index.get(company_index_key(house_name))
                    if target is None:
                        unmatched.append(house_name)
                        continue
                    updates.append(
                        (
                            house_name,
                            rec.get('register_addr'),
                            rec.get('office_addr'),
                            rec.get('website'),
                            rec.get('phone'),
                            target,
                        )
                    )
                report['enriched'] = len(updates)
                enriched_ids = {u[-1] for u in updates}
                report['unmatched'] = sorted(unmatched)
                if apply and updates:
                    conn.executemany(
                        f'UPDATE {MAIN_TABLE} SET full_name=?, register_addr=?, office_addr=?, '
                        f'website=?, phone=?, is_active=1 WHERE id=?',
                        updates,
                    )
                    conn.commit()

            # ── 阶段 3：合并重复实体 ──
            for key, rows in grouped.items():
                if len(rows) < 2:
                    continue
                canonical_id = pick_canonical_company(rows)[0]
                canonical_name = canonical_rows[canonical_id]['name']
                for row_id, name, _ in rows:
                    if row_id == canonical_id:
                        continue
                    # 简称行的 full_name 尚未填时，用冗余行的全称补上（名称含「公司」视为全称）
                    # 仅当规范行尚无 full_name（AMAC 未覆盖该组）才需要提升冗余行的全称
                    has_full_name = bool(canonical_rows[canonical_id]['full_name']) or canonical_id in enriched_ids
                    promote = '公司' in name and not has_full_name
                    report['merged'].append(
                        {
                            'keep': canonical_id,
                            'keep_name': canonical_name,
                            'drop': row_id,
                            'drop_name': name,
                            'promote_full_name': promote,
                        }
                    )
                    if not apply:
                        continue
                    if promote:
                        conn.execute(
                            f'UPDATE {MAIN_TABLE} SET full_name=? WHERE id=? AND (full_name IS NULL OR full_name=?)',
                            (name, canonical_id, ''),
                        )
                    report['repointed'] += conn.execute(
                        'UPDATE managers SET company_id=? WHERE company_id=?', (canonical_id, row_id)
                    ).rowcount
                    report['repointed'] += conn.execute(
                        'UPDATE funds SET company_id=? WHERE company_id=?', (canonical_id, row_id)
                    ).rowcount
                    conn.execute(f'DELETE FROM {MAIN_TABLE} WHERE id=?', (row_id,))
            if apply:
                conn.commit()

        # ── 阶段 4：name 收敛为简称（全称移入 full_name）──
        if MAIN_TABLE in tables and short_name_map:
            renames, unresolved = [], []
            for row_id, code, name, full_name in conn.execute(f'select id, code, name, full_name from {MAIN_TABLE}'):
                if not looks_like_full_name(name):
                    continue
                short = short_name_map.get(code)
                if not short or short == name:
                    unresolved.append((code, name))
                    continue
                renames.append((short, full_name or name, row_id))
            report['renamed'] = renames
            report['rename_unresolved'] = unresolved
            if apply and renames:
                conn.executemany(f'UPDATE {MAIN_TABLE} SET name=?, full_name=? WHERE id=?', renames)
                conn.commit()

        # ── 阶段 5：删除死表 ──
        if DEAD_TABLE in tables:
            report['dropped'] = True
            if apply:
                conn.execute(f'DROP TABLE {DEAD_TABLE}')
                conn.commit()
    finally:
        conn.close()
    return report


def fetch_short_name_map() -> dict:
    """东财基金公司列表的 `code → 简称` 映射（阶段 4 用）。

    该接口同时是本表 `code` 的权威来源，故 code→简称 是**可靠映射**（不是名称模糊匹配）。
    网络不可用时返回空 dict，阶段 4 自动跳过并在报告里说明——本脚本其余阶段离线可用。
    """
    try:
        companies = fetch_fund_company_list()
    except Exception as e:  # 网络/解析失败不应阻断迁移
        print(f'  [简称] 东财公司列表获取失败，阶段 4 跳过: {e}')
        return {}
    mapping = {c['code']: c['name'] for c in companies if c.get('code') and c.get('name')}
    print(f'  [简称] 东财公司列表 code→简称 {len(mapping)} 条')
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(description='合并 fund_management_companies 到 fund_companies')
    parser.add_argument('--apply', action='store_true', help='真正落库（默认只干跑报告）')
    args = parser.parse_args()

    paths = [_to_path(u) for u in CANDIDATE_URLS]
    mode = '【落库】' if args.apply else '【干跑】'
    print(f'{mode} 基金公司主数据合并\n')

    house_pool = collect_house_pool(paths)
    short_name_map = fetch_short_name_map()
    if not house_pool:
        print('  [池] 未找到 fund_management_companies（可能已迁移过），仍会补列/去重\n')

    for path in paths:
        if not os.path.exists(path):
            continue
        print(f'--- {path} ---')
        rep = migrate_file(path, house_pool, short_name_map, args.apply)
        if not any((rep['added_columns'], rep['enriched'], rep['renamed'], rep['merged'], rep['dropped'])):
            print('  [跳过] 无事可做（已迁移）')
            continue
        if rep['added_columns']:
            print(f'  补列 {len(rep["added_columns"])} 个: {", ".join(rep["added_columns"])}')
        if rep['enriched']:
            print(f'  AMAC 回填 {rep["enriched"]} 家公司（full_name/地址/官网/电话）')
        if rep['unmatched']:
            print(f'  未匹配 {len(rep["unmatched"])} 条（不新建行，需人工确认）:')
            for name in rep['unmatched']:
                print(f'      {name}')
        if rep['renamed']:
            print(f'  name 收敛为简称 {len(rep["renamed"])} 行（全称移入 full_name），示例：')
            for short, full, row_id in rep['renamed'][:5]:
                print(f'      id={row_id} {full}  →  {short}')
        if rep['rename_unresolved']:
            print(f'  简称无法解析 {len(rep["rename_unresolved"])} 行（code=name 占位，待 backfill 补真值 code）:')
            for code, name in rep['rename_unresolved'][:10]:
                print(f'      {name}')
        if rep['merged']:
            print(f'  合并重复实体 {len(rep["merged"])} 组：')
            for m in rep['merged']:
                extra = '（全称补入 full_name）' if m['promote_full_name'] else ''
                print(f'      keep id={m["keep"]} {m["keep_name"]}  ←  drop id={m["drop"]} {m["drop_name"]}{extra}')
            if args.apply:
                print(f'  重映射 managers/funds.company_id 共 {rep["repointed"]} 行')
        if rep['dropped']:
            print(f'  DROP TABLE {DEAD_TABLE}')

    if not args.apply:
        print('\n干跑结束，未写任何库。确认无误后加 --apply 执行。')
    else:
        print('\n完成。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
