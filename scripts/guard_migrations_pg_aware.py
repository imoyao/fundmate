#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：启动期迁移不许再写成「非 SQLite 就跳过」（#2534）。

## WHY（两次生产停摆逼出来的）

`backend/app/core/migrations.py` 里的迁移函数曾普遍这样开头：

    if not url.startswith(('sqlite://', 'sqlite+')):
        return '[SKIP] 非 SQLite 引擎，列由 ORM 模型/迁移工具负责'

而那句「由 ORM 模型 / 迁移工具负责」在本仓是**假前提**：本仓没有 Alembic，
`create_all()` 只建缺失的表、不给存量表加列/加索引，生产 user 域是 Supabase
Postgres（手工建表）。三者叠加 ⇒ 迁移覆盖的列在生产**永远加不上**，而
`init_db()` 末尾的 `_validate_schema` 判「库结构与模型不一致」**拒绝启动**：

| 次 | 卡 | 缺的列 | 后果 |
|---|---|---|---|
| 1 | #2469 | watchlist 三表四列 | 生产 init_db 拒绝启动（PR #2501 修） |
| 2 | #2532 | transactions 费用拆分四列 | 每日调度全线停摆（PR #2533 修） |

review 拦不住：两次都是在 review 里过的——「跳过非 SQLite」看起来是合理的兼容
处理，而不是缺陷。故把这条变成**机器判据**。

## 判据

`migrations.py` 的每个 `migrate_*` 函数内，`return` 一个含「非 SQLite」的
字符串常量 = 早退。规则（口径同 `check_view_thickness.py` 的基线纪律）：

1. **新早退即红**：函数不在 `BASELINE_SKIP_FUNCTIONS` 里却有早退 ⇒ 违规；
2. **收敛即收紧**：基线内函数已无早退 ⇒ 违规（改到一个函数就顺手把基线条目
   收掉，不允许「改了代码留着基线」——那会让基线慢慢失真）；
3. **陈旧条目即红**：基线里的函数名在文件中不存在 ⇒ 违规。

## 豁免 / 边界

- 基线内四个函数的 SQLite 路径是整表重建 / SQLite 专属 SQL（`sqlite_master`
  DDL 改写、`GROUP_CONCAT`、`INSERT OR IGNORE`），PG 分支要另写（唯一索引 /
  `string_agg` / `ON CONFLICT`），不能机械转换——它们留在基线里并**标注原因**，
  收敛一个删一个；
- 只判「早退」这一种形态。迁移里裸写 `ALTER TABLE` / `CREATE INDEX` 不在此判
  （由 module docstring 的单一通道约定 + review 管）；数据回填用标准 SQL 即可，
  两种引擎通用；
- docstring / 注释里提到「非 SQLite」不算早退（只认 `return` 语句的常量）。

## 用法

    python scripts/guard_migrations_pg_aware.py               # 校验（CI，阻断）
    python scripts/guard_migrations_pg_aware.py --report      # 早退清单与基线差集
    python scripts/guard_migrations_pg_aware.py --self-test   # 变异探针自检

退出码：0 = 通过；1 = 违规；2 = 拿不到输入（结论不可信，不得当成通过）。
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_REL = 'backend/app/core/migrations.py'

#: 仍允许「非 SQLite 就跳过」的函数（2026-10-23，#2534 首批收敛 18 个后冻结）。
#: 这三个的 SQLite 路径是**整表重建 / SQLite 专属 SQL**，PG 分支需另写，不能
#: 机械转换；收敛一个就从这里删一个（守卫第 2 条会拦「已无早退但条目还在」）。
#: 删条目必须与「删早退」同一个 PR——分开就会有一段「代码已修、基线还挂着」的
#: 窗口，那时任何新早退都能拿旧条目当掩护。
#:
#: `migrate_positions_symbol_norm` 已收敛（#2689）：PG 侧只差三处方言——加列走
#: `_add_column_sql`、聚合 `STRING_AGG`、`HAVING` 只写聚合表达式——两侧都有测试
#: （SQLite 真库 / `migrations_pg_fake.PgFake`），故条目已删。
BASELINE_SKIP_FUNCTIONS = frozenset(
    {
        'migrate_watchlist_unique_key',
        'migrate_watchlist_family_scoped_unique_key',
        'migrate_fund_managers_split_tenures',
    }
)

_SKIP_MARKER = '非 SQLite'


def _parse_migrations(source: str):
    """返回 (迁移函数名集合, {函数名: [早退行号]})。"""
    tree = ast.parse(source)
    names: set[str] = set()
    skips: dict[str, list[int]] = {}
    for node in tree.body:
        if not (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('migrate_')):
            continue
        names.add(node.name)
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Return):
                continue
            value = sub.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str) and _SKIP_MARKER in value.value:
                skips.setdefault(node.name, []).append(sub.lineno)
    return names, skips


def check_source(source: str) -> list[str]:
    """纯判据：源码文本 → 违规列表（空 = 通过）。"""
    names, skips = _parse_migrations(source)
    problems: list[str] = []

    for name in sorted(skips):
        if name not in BASELINE_SKIP_FUNCTIONS:
            problems.append(
                f'{name} 第 {skips[name]} 行仍是「非 SQLite 就跳过」早退，且不在 '
                f'BASELINE_SKIP_FUNCTIONS 基线内——生产 user 域是 Postgres，'
                f'该迁移覆盖的列/索引在 PG 上永远加不上（#2469 / #2532 的根因）。'
                f'请改走 _add_columns_if_missing / _ensure_index，或确有 SQLite 专属'
                f'逻辑时把函数加进基线（附理由，收敛一个删一个）。'
            )

    for name in sorted(BASELINE_SKIP_FUNCTIONS):
        if name not in names:
            problems.append(f'基线条目 {name} 在 {MIGRATIONS_REL} 中不存在（陈旧条目，请删除）')
        elif name not in skips:
            problems.append(
                f'{name} 已无「非 SQLite 就跳过」早退（已收敛），请同步从 '
                f'BASELINE_SKIP_FUNCTIONS 删除该条目——代码与基线必须同一个 PR 内贴合。'
            )

    return problems


def check(repo_root: Path = REPO_ROOT) -> list[str]:
    path = repo_root / MIGRATIONS_REL
    if not path.is_file():
        return [f'拿不到输入：{path} 不存在——本轮结论不可信，不得当成通过']
    try:
        source = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        return [f'读不到 {path}（{exc}）——本轮结论不可信，不得当成通过']
    return check_source(source)


def _report(repo_root: Path = REPO_ROOT) -> int:
    path = repo_root / MIGRATIONS_REL
    if not path.is_file():
        print(f'❌ 拿不到输入：{path}')
        return 2
    names, skips = _parse_migrations(path.read_text(encoding='utf-8'))
    print(f'迁移函数共 {len(names)} 个；仍带「非 SQLite 就跳过」早退的 {len(skips)} 个：')
    for name in sorted(skips):
        mark = '基线内' if name in BASELINE_SKIP_FUNCTIONS else '⚠️ 基线外（违规）'
        print(f'  {name:55s} 行 {skips[name]}  {mark}')
    stale = sorted(n for n in BASELINE_SKIP_FUNCTIONS if n not in skips)
    if stale:
        print(f'基线中已收敛（待删条目）：{stale}')
    print(f'基线条目数：{len(BASELINE_SKIP_FUNCTIONS)}')
    return 0


def _inject_new_skip(source: str) -> str:
    """变异探针：往一个**基线外**函数体内注入新的「非 SQLite」早退。"""
    lines = source.splitlines()
    target = 'def migrate_transaction_fee_breakdown('
    for idx, line in enumerate(lines):
        if line.startswith(target):
            lines.insert(idx + 1, "    if not str(getattr(engine, 'url', '')).startswith('sqlite'):")
            lines.insert(idx + 2, "        return '[SKIP] 非 SQLite 引擎，列由 ORM 模型/迁移工具负责'")
            return '\n'.join(lines) + '\n'
    raise AssertionError('探针未命中：migrate_transaction_fee_breakdown 不在文件中')


def _drop_baseline_skip(source: str) -> str:
    """变异探针：把基线内函数的早退 return 改成普通内容（模拟「收敛了但没收紧基线」）。

    刻意不删行：删掉 return 会留下空 if 体，ast.parse 直接语法错，测到的就不是
    「基线漂移」而是「语法坏」——探针必须只动一个变量。
    """
    lines = source.splitlines()
    target = 'def migrate_watchlist_unique_key('
    for idx, line in enumerate(lines):
        if line.startswith(target):
            for j in range(idx + 1, len(lines)):
                if _SKIP_MARKER in lines[j] and lines[j].lstrip().startswith('return'):
                    lines[j] = lines[j].replace(_SKIP_MARKER, '该引擎无需重建')
                    return '\n'.join(lines) + '\n'
            raise AssertionError('探针未命中：基线函数内找不到早退 return')
    raise AssertionError('探针未命中：migrate_watchlist_unique_key 不在文件中')


def _self_test() -> int:
    """变异探针：每条都确认「改坏会红、还原即绿」，跑一次绿不算数。"""
    path = REPO_ROOT / MIGRATIONS_REL
    if not path.is_file():
        print(f'❌ 自检拿不到输入：{path}')
        return 2
    real = path.read_text(encoding='utf-8')
    probes = []

    base = check_source(real)
    probes.append(('真实文件 + 当前基线通过', base == [], f'不应有违规：{base}'))

    injected = check_source(_inject_new_skip(real))
    probes.append(
        ('注入新早退（基线外函数）必须报红', any('不在' in p and '基线' in p for p in injected), f'未报红：{injected}')
    )

    dropped = check_source(_drop_baseline_skip(real))
    probes.append(('基线内函数删掉早退必须提示收紧基线', any('已无' in p for p in dropped), f'未报红：{dropped}'))

    phantom = sorted(BASELINE_SKIP_FUNCTIONS - set(_parse_migrations(real)[0]))
    probes.append(('当前无陈旧基线条目', phantom == [], f'陈旧条目：{phantom}'))

    ok = all(passed for _name, passed, _detail in probes)
    for name, passed, detail in probes:
        # 刻意不用 ✅/❌：Windows GBK 控制台印不出 emoji，本地跑自检会崩在打印上
        # （CI 是 UTF-8 不会，但「本地一跑就炸」会让没人愿意跑自检）。
        print(f'[{"PASS" if passed else "FAIL"}] {name}' + ('' if passed else f' —— {detail}'))
    print('OK: 自检通过（注入即红、还原即绿）。' if ok else 'FAIL: 自检失败：守卫对变异不敏感。')
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='迁移 PG-aware 守卫（禁「非 SQLite 就跳过」早退）')
    parser.add_argument('--report', action='store_true', help='打印早退清单与基线差集')
    parser.add_argument('--self-test', action='store_true', help='变异探针自检')
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if args.report:
        return _report()

    problems = check()
    if problems:
        print('❌ 迁移 PG-aware 守卫未通过：')
        for p in problems:
            print(f'  - {p}')
        return 1
    print(f'OK: 迁移无「非 SQLite 就跳过」早退（基线 {len(BASELINE_SKIP_FUNCTIONS)} 个函数，收敛一个删一个）。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
