# -*- coding: utf-8 -*-
"""清理「演示基金」伪数据及其穿透污染（#1982）。

背景（含 **2026-10-10 复核更正**）
-----------------------------
库里混入 3 只命名带「示例」的基金（`012345` / `023456` / `034567`）、共 6 行持仓，
全部 `source=e_account_holding`、`created_at` 落在同一秒（批量导入），分布在
「同花顺——银河」(shadow) 与三个「示例*」账户 (active) 上。

⚠️ **#1982 卡里写的「funds 表无记录」已不再成立**（那是 2026-10-08 的观测）。复核发现：

| 码 | 名录里的真实身份 | 名下有披露数据吗 |
|---|---|---|
| `012345` | **嘉实领先优势混合C** | 有：28 行持仓明细 + 10 行行业配置 |
| `023456` | **汇添富增强回报债券C** | 有：44 行持仓明细 + 11 行行业配置 |
| `034567` | 名录无此码 | 无 |

也就是说：**演示数据复用了真实基金的代码、配了假名字**。这直接否决了卡里方案 (a) 的
「删除 6 行持仓 **+ 相关 fund_industry_allocs / fund_holdings**」—— 那两个码名下的披露数据
属于**真实基金**，照删就是把真数据当垃圾清掉。故本脚本按**两级**处理（见下）。

**为什么迁移修不了它们**：`migrations.migrate_positions_money_fund_flag` 用
`resolve_money_fund_flags_strict`，该函数对「名录无该代码」一律返回 `None` 并**保持原值**
（#1661 取舍：宁漏不误，避免 market 域抖动把全库货基标记清空）。`034567` 落在这一类；
而 `012345` / `023456` 名录有记录但类型未知（`fund_type_id` 为空）→ 同样返回 `None`
→ `is_money_fund` 修不正。两条路径都只能靠清数据。

清理范围（**两级**，防误删）
--------------------------
判据起点统一是「名称含『示例』或『演示』」，随后按**代码是否在名录里**分流：

- **一级（安全，默认执行）**：代码在名录里**查无记录** → 删持仓 **且**删该码的
  `fund_industry_allocs` / `fund_holdings`（名录都没有的码不可能是真实在售品种）。
- **二级（需显式开启）**：代码**在名录里**（真实基金）→ **只删持仓行，绝不动子表**。
  默认**不执行**，须加 `--include-catalog-known` 明确纳入，因为这一步赌的是
  「用户没在真实账户里持有这只基金」，只有人才能拍板。

无论哪级，子表清理都额外限定「该代码的全部持仓行都在清理范围内」。

回滚手段
--------
输出**可完整还原的 INSERT 回滚语句**（stdout，可 `--rollback-out` 落文件）：列名由
`PRAGMA table_info` 动态取，因此新增列不会让回滚语句失效。删除在单个事务内完成，
`DELETE` 影响行数与表行数变化必须同时等于预期，否则整体回滚、非零退出。

不做的事
--------
**不动 `ledgers`（演示账户）**：库里那三个「示例*」账户是同源演示数据，可能是有意保留的
沙箱产物，删账户属用户决策，本脚本只在报告里列出它们与其余持仓数。

用法
----
  pdm run python scripts/clean_demo_fund_data.py                        # dry-run，仅列出
  pdm run python scripts/clean_demo_fund_data.py --apply                 # 执行一级清理
  pdm run python scripts/clean_demo_fund_data.py --apply --include-catalog-known
                                                                        # 连二级一起（只删持仓）
  pdm run python scripts/clean_demo_fund_data.py --db backend/invest.db
  pdm run python scripts/clean_demo_fund_data.py --rollback-out rollback_1982.sql
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DEFAULT_DB = 'invest.db'

# 名称命中词（演示 / 示例数据都见得到）
NAME_MARKERS = ('示例', '演示')

# 被清理持仓的附属表：这些表按 fund_code 关联，伪数据的行必须一起走，
# 否则穿透仍会拿它们的行业/持仓去摊（#1982 的污染正是从这里来的）
CHILD_TABLES = ('fund_industry_allocs', 'fund_holdings')


def _normalize_code(symbol: str) -> str:
    """剥离交易所前缀，取 6 位代码（与 `services.fund_utils.normalize_fund_code` 同形）。"""
    s = (symbol or '').strip().upper().replace('.', '')
    if len(s) > 6 and s[:2] in ('SH', 'SZ', 'BJ'):
        s = s[2:]
    if len(s) > 6 and s[-2:] in ('SH', 'SZ', 'BJ'):
        s = s[:-2]
    return s[-6:] if len(s) >= 6 and s[-6:].isdigit() else ''


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()]


def _name_predicate(alias: str) -> str:
    return ' OR '.join(f"{alias}.name LIKE '%{m}%'" for m in NAME_MARKERS)


def collect_candidates(conn: sqlite3.Connection) -> tuple[list[dict], list[dict]]:
    """收集候选，按「代码是否在名录里」分成两级。

    返回 `(targets, known)`：

    - `targets`（**一级**）：名称命中 **且** 代码在 `funds` 名录里查无记录
      → 可安全删持仓 + 子表（名录都没有的码不可能是真实在售品种）；
    - `known`（**二级**）：名称命中但名录**有**该码 —— 说明是**真实基金被配了假名字**
      （本机实测：`012345` = 嘉实领先优势混合C、`023456` = 汇添富增强回报债券C，
      两个码名下各有几十行真实披露数据）。这类只能删「假仓位」、**绝不动子表**，
      且必须由调用方显式开启。
    """
    sql = (
        'SELECT p.id, p.symbol, p.name, p.type, p.quantity, p.current_price, p.source, '
        'p.account_name, p.created_at, p.ledger_id, p.ownership_status, '
        '(SELECT COUNT(*) FROM funds f WHERE f.fund_code = p.symbol) AS in_catalog '
        'FROM positions p '
        f'WHERE {_name_predicate("p")} '
        'ORDER BY p.id'
    )
    targets: list[dict] = []
    exempt: list[dict] = []
    for row in conn.execute(sql).fetchall():
        item = {
            'id': row[0],
            'symbol': row[1],
            'code': _normalize_code(row[1]),
            'name': row[2],
            'type': row[3],
            'quantity': row[4],
            'current_price': row[5],
            'source': row[6],
            'account_name': row[7],
            'created_at': row[8],
            'ledger_id': row[9],
            'ownership_status': row[10],
            'in_catalog': row[11],
        }
        (exempt if item['in_catalog'] > 0 else targets).append(item)
    return targets, exempt


def target_codes(conn: sqlite3.Connection, targets: list[dict]) -> list[str]:
    """真正要清子表的代码：该代码的**全部**持仓行都命中（第三条限定）。"""
    codes: list[str] = []
    for code in sorted({t['symbol'] for t in targets if t['symbol']}):
        total = conn.execute('SELECT COUNT(*) FROM positions WHERE symbol = ?', (code,)).fetchone()[0]
        hit = sum(1 for t in targets if t['symbol'] == code)
        if total == hit:
            codes.append(code)
    return codes


def _lit(value) -> str:
    """Python 值 → SQL 字面量（仅用于生成回滚语句）。"""
    if value is None:
        return 'NULL'
    if isinstance(value, str):
        return "'%s'" % value.replace("'", "''")
    if isinstance(value, bytes):
        return "X'%s'" % value.hex()
    return repr(value)


def rollback_sql(conn: sqlite3.Connection, tables_rows: dict[str, list[tuple]]) -> str:
    """为每张被删的表生成 `INSERT ... VALUES ...` 回滚语句。

    列名由 `PRAGMA table_info` 动态取 —— 硬编码列名会让回滚语句在下次加列后失效。
    """
    lines = [
        '-- #1982 回滚脚本：还原被清理的「演示基金」伪数据',
        '-- 用法：sqlite3 <db> < 本文件',
    ]
    for table, rows in tables_rows.items():
        if not rows:
            continue
        cols = _columns(conn, table)
        col_list = ', '.join(cols)
        for row in rows:
            values = ', '.join(_lit(v) for v in row)
            label = row[cols.index('name')] if 'name' in cols else ''
            lines.append(f'INSERT INTO {table} ({col_list}) VALUES ({values});  -- {label}')
    return '\n'.join(lines) + '\n'


def _purge_table(conn: sqlite3.Connection, table: str, ids: list) -> int:
    """单事务按主键删除；条数与表行数变化必须同时等于预期，否则回滚并抛错。"""
    if not ids:
        return 0
    pk = _columns(conn, table)[0]  # 约定 id 为首列（PRAGMA 顺序即建表顺序）
    conn.execute('BEGIN IMMEDIATE')
    try:
        before = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        changed0 = conn.total_changes
        conn.executemany(f'DELETE FROM {table} WHERE {pk} = ?', [(i,) for i in ids])
        deleted = conn.total_changes - changed0
        after = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        if deleted != len(ids) or before - after != len(ids):
            raise RuntimeError(
                f'{table} 删除条数校验失败：预期 {len(ids)}，DELETE 实际影响 {deleted}，表行数 {before} → {after}'
            )
        conn.execute('COMMIT')
        return deleted
    except Exception:
        try:
            conn.execute('ROLLBACK')
        except sqlite3.Error:
            pass
        raise


def _industry_anomalies(conn: sqlite3.Connection) -> list[dict]:
    """行业名格式异常：`industry_name` 以 `industry_code` 打头（如 `45信息技术`）。

    全库正常形态是 `('45','信息技术')`；带前缀说明是手工构造插入、没走标准采集链路
    （#1982 第 3 条现象）。这里只**报告**，不在清理范围里顺手动它。
    """
    if 'fund_industry_allocs' not in {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }:
        return []
    rows = conn.execute(
        'SELECT id, fund_code, industry_code, industry_name FROM fund_industry_allocs '
        'WHERE industry_name IS NOT NULL AND industry_code IS NOT NULL '
        "AND industry_name LIKE industry_code || '%' AND industry_name <> industry_code"
    ).fetchall()
    return [{'id': r[0], 'fund_code': r[1], 'industry_code': r[2], 'industry_name': r[3]} for r in rows]


def run(
    conn: sqlite3.Connection,
    apply: bool,
    rollback_out: str | None,
    include_catalog_known: bool = False,
) -> int:
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    missing = {'positions', 'funds'} - tables
    if missing:
        print('[错误] 目标库缺少表: %s' % ', '.join(sorted(missing)))
        return 1

    targets, known = collect_candidates(conn)
    codes = target_codes(conn, targets)

    print(
        'positions 总行数 %d；命中「名称含示例/演示」%d 行'
        % (
            conn.execute('SELECT COUNT(*) FROM positions').fetchone()[0],
            len(targets) + len(known),
        )
    )

    if not targets and not known:
        print('未发现疑似演示数据，无需清理。')
        return 0

    print('\n【一级 · 安全】%d 行：名称命中 **且** funds 名录查无该码（删持仓 + 删其子表）' % len(targets))
    for t in targets:
        print(
            '  id=%-5s %-8s %-28s ledger=%-4s %s  %s'
            % (t['id'], t['symbol'], t['name'], t['ledger_id'], t['source'], t['created_at'])
        )

    if known:
        print('\n【二级 · 需确认】%d 行：名称命中，但该码在名录里是**真实基金**（只删持仓、绝不动子表）：' % len(known))
        for t in known:
            print('  id=%-5s %-8s %s  ledger=%s' % (t['id'], t['symbol'], t['name'], t['ledger_id']))
        print(
            '  ⚠️ 这些码名下的持仓明细/行业配置属于**真实基金**（卡里方案 (a) 会误删它们），\n'
            '     故本脚本对它们**不碰子表**；是否删掉这些「仓位」需你拍板：\n'
            '     加 --include-catalog-known 才会删除它们的持仓行。'
        )

    # 子表只按一级代码清（名录都没有的码，不可能是真实在售品种）
    child_plan: dict[str, list[tuple]] = {}
    for table in CHILD_TABLES:
        if table not in tables:
            continue
        rows: list[tuple] = []
        for code in codes:
            rows.extend(conn.execute(f'SELECT * FROM {table} WHERE fund_code = ?', (code,)).fetchall())
        child_plan[table] = rows
    print('\n附属表待清理（fund_code ∈ %s）：' % (codes or '空'))
    for table, rows in child_plan.items():
        print('  %-24s %d 行' % (table, len(rows)))

    anomalies = _industry_anomalies(conn)
    if anomalies:
        print('\n另有 %d 行行业名格式异常（名称带 code 前缀，仅报告、不删）：' % len(anomalies))
        for a in anomalies[:10]:
            print('  id=%-5s %s  %s / %s' % (a['id'], a['fund_code'], a['industry_code'], a['industry_name']))
        if len(anomalies) > 10:
            print('  …共 %d 行' % len(anomalies))
        print('  （归属真实基金码，故只报告；异常命名见 #1982 第 3 条现象）')

    # 待删持仓：一级总是删；二级需显式开启
    purge_ids = [t['id'] for t in targets]
    if include_catalog_known:
        purge_ids += [t['id'] for t in known]

    # 回滚 SQL（删除前留存）
    tables_rows: dict[str, list[tuple]] = {
        'positions': conn.execute(
            'SELECT * FROM positions WHERE id IN (%s)' % ','.join(str(i) for i in purge_ids)
        ).fetchall()
        if purge_ids
        else []
    }
    tables_rows.update(child_plan)
    sql = rollback_sql(conn, tables_rows)
    print('\n--- 回滚 SQL（删除前请留存）---')
    print(sql, end='')
    if rollback_out:
        Path(rollback_out).write_text(sql, encoding='utf-8')
        print('[回滚 SQL 已写入] %s' % rollback_out)

    if not apply:
        print('\n[dry-run] 未做任何修改；加 --apply 真正执行（二级另需 --include-catalog-known）。')
        return 0

    deleted_positions = _purge_table(conn, 'positions', purge_ids)
    deleted_children = 0
    for table, rows in child_plan.items():
        if not rows:
            continue
        deleted_children += _purge_table(conn, table, [r[0] for r in rows])
    print('\n[完成] 已删除 positions %d 行、附属表 %d 行。' % (deleted_positions, deleted_children))

    left, left_known = collect_candidates(conn)
    if left:
        print('[错误] 清理后一级仍命中 %d 行，请检查。' % len(left))
        return 1
    if include_catalog_known and left_known:
        print('[错误] 清理后二级仍命中 %d 行，请检查。' % len(left_known))
        return 1
    if left_known:
        print('[校验] 一级 = 0；二级 %d 行仍在（未加 --include-catalog-known，属预期）' % len(left_known))
    else:
        print('[校验] 疑似演示持仓 = 0')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='清理「演示基金」伪数据及其穿透污染（#1982）')
    parser.add_argument('--db', default=DEFAULT_DB, help='SQLite 数据库路径（默认 invest.db）')
    parser.add_argument('--apply', action='store_true', help='真正执行；缺省为 dry-run')
    parser.add_argument('--rollback-out', default=None, help='把回滚 SQL 写入指定文件（缺省仅打印）')
    parser.add_argument(
        '--include-catalog-known',
        action='store_true',
        help='连二级一起删（名录已知的真实基金码上的「假仓位」；只删持仓、绝不动子表）',
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print('[错误] 数据库不存在: %s' % db_path)
        return 1

    conn = sqlite3.connect(db_path, timeout=30)
    conn.isolation_level = None  # 事务完全显式控制（_purge_table 内 BEGIN IMMEDIATE / COMMIT / ROLLBACK）
    try:
        return run(conn, args.apply, args.rollback_out, args.include_catalog_known)
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
