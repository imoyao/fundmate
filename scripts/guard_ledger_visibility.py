#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：账户可见性判定只经 ``visible_ledger_ids()`` / ``can_view()`` 单点出口（#3246 第三段）。

WHY
---
``ledgers.visibility`` + ``owner_user_id`` 落地后，最大的风险不是「没过滤」，而是
**过滤散落**：每个新端点都顺手写一句 ``if ledger.visibility == 'private' and ...``。
写对十处不难，难的是三年后第十一处——漏一句就是一个越权洞，而且它不会报错、
不会崩，只会让某个人的账户出现在别人屏幕上。

散文规范拦不住「顺手再判一次」（#1798 路由死链、#119 净资产现算同款教训），
故把判据钉进 CI：视图层不许直接读 ``visibility`` 列，也不许拿它跟取值字面量比较。
判定只有三个合法入口（都在 ``domains/ledgers``，且共用同一份规则）：

- ``visible_ledger_ids(db, family_id, user_id)``      → 集合，列表查询下推 ``IN``；
- ``visible_ledger_clause`` / ``restrict_visible``    → 明细表 query 收窄；
- ``can_view(...)`` / ``get_visible_ledger_or_404`` / ``assert_ledger_visible``
                                                      → 单行判定（含明细行的账户归属）。

判据（AST，纯标准库，扫 ``backend/app/domains/**/views.py``）
------------------------------------------------------------
- V1 ``X.visibility`` 属性访问 —— 视图拿到了列值，下一步必然是比较；
- V2 ``Compare`` 的一侧是名为 ``visibility`` 的标识符或 ``*.visibility``；
- V3 ``Compare`` 里出现 ``'private'`` / ``'shared'`` 字符串字面量（防绕：换个变量名也算）。

**注释与 docstring 不算**：AST 天然不含注释，docstring 是 ``Constant`` 不会被当比较——
所以 ``positions/views.py`` 里那句「判定收口在 visibility.restrict_visible」的说明文字
不会误报（散文守卫按行正则就会误伤，这正是这里用 AST 的原因）。

刻意不覆盖（宁可漏报也不误报）
------------------------------
- ``visibility, owner_user_id, err = resolve_ledger_scope(...)``（创建账户时解析 scope）
  —— 那是**写入**侧的合法用法，返回的是待落库的取值，不是判定；
- ``services/`` 与 ``core/`` 层（那里没有 ``Ledger`` 行对象，也拿不到请求身份）；
- 把取值先存进无关键字面量再比（``v = row.visibility`` 已被 V1 拦下）；
- 不判判定函数本身写得对不对（那是 ``tests/domains/test_ledger_visibility*.py`` 的事）。

用法
----
    python scripts/guard_ledger_visibility.py              # 扫 backend/app/domains 全量
    python scripts/guard_ledger_visibility.py a.py b.py    # 只扫指定文件

退出码：0 = 通过；1 = 命中散落判定；2 = 拿不到输入（结论不可信，不得当成通过）。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / 'backend' / 'app' / 'domains'
SCAN_NAME_SUFFIX = 'views.py'
VISIBILITY_VALUES = {'private', 'shared'}


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def iter_files(roots: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in roots:
        p = Path(raw)
        if p.is_file():
            out.append(p)
            continue
        for f in sorted(p.rglob(SCAN_NAME_SUFFIX)):
            if f.name.endswith(SCAN_NAME_SUFFIX):
                out.append(f)
    return out


def _is_visibility(node: ast.AST) -> bool:
    """``x.visibility`` 或裸 ``visibility``（后者仅用于比较位置，赋值合法）."""
    if isinstance(node, ast.Attribute):
        return node.attr == 'visibility'
    return isinstance(node, ast.Name) and node.id == 'visibility'


def _visibility_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value in VISIBILITY_VALUES


def scan_tree(tree: ast.AST) -> list[tuple[int, str]]:
    """返回 ``[(行号, 说明)]``。V1 与 V2/V3 分开报，便于定位是读列还是比取值."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == 'visibility':
            hits.append((node.lineno, 'V1 直接读取 `.visibility` 列'))
        elif isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            if any(_is_visibility(op) for op in operands):
                hits.append((node.lineno, 'V2 用 visibility 参与比较'))
            elif any(_visibility_literal(op) for op in operands):
                hits.append((node.lineno, "V3 比较里出现 'private'/'shared' 字面量"))
    return sorted(set(hits))


def main(argv: list[str]) -> int:
    roots = argv[1:] or [str(DEFAULT_ROOT)]
    files = iter_files(roots)
    if not files:
        print('❌ 拿不到输入：未扫描到任何 `*views.py` —— 本轮结论不可信，不得当成通过')
        return 2

    violations: list[tuple[str, int, str]] = []
    for f in files:
        try:
            source = f.read_text(encoding='utf-8')
            tree = ast.parse(source, filename=str(f))
        except (UnicodeDecodeError, OSError, SyntaxError) as exc:  # 解析不了就不能说「通过」
            print(f'❌ 无法解析 {_rel(f)}：{exc}', file=sys.stderr)
            return 2
        for lineno, why in scan_tree(tree):
            violations.append((_rel(f), lineno, why))

    if not violations:
        print(f'OK: 视图层未出现散落的可见性判定（扫描 {len(files)} 个 views.py，判定只经 domains/ledgers 单点出口）')
        return 0

    print(
        f'ERROR: 发现 {len(violations)} 处视图层散落判定，违反 #3246 第三段「可见性判定单点」：',
        file=sys.stderr,
    )
    for rel, lineno, why in violations:
        print(f'  {rel}:{lineno}  {why}', file=sys.stderr)
    print(
        '\n  正解：列表/明细查询用 `visible_ledger_id_set(db)` 或 `restrict_visible(query, Column, ids)`；\n'
        '        单行取数用 `get_visible_ledger_or_404(db, id)` / `assert_ledger_visible(db, ledger_id)`。\n'
        '        判定规则只有 `backend/app/domains/ledgers/visibility.py` 一份——散落的那份必然漂移。',
        file=sys.stderr,
    )
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
