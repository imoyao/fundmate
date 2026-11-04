#!/usr/bin/env python3
"""守卫：watchlist 模块的「当前持仓」查询必须统一走 ``active_holdings()``。

WHY（缺口是真实发生过的，不是假想）
------------------------------------
``positions.ownership_status`` 有三态：``active`` / ``shadow``（E账户对账镜像）/
``cleared``（已清仓保留行）。「当前持仓」口径由 ``services/position_scope.py`` 的
``active_holdings(query)`` 统一定义，但 ``watchlist_service.py`` / ``watchlist_display.py``
历史上散落着 17 处 ``Position.ownership_status == 'active'`` 字面量比较：

- 2026-11-04 用户报 023887 自选页显示 **84,282.0222 份 / ¥59,720.99**，
  产品详情页只有 **42,850.4322 份 / ¥28,949.76**。真因是 ``BatchContext._prefetch_all()``
  里第 1/2 段聚合没过滤状态，而**同一个函数内**第 3 段「代表持仓行 meta」早就过滤了 ——
  即「行集合是对的、行里的数值是错的」，典型的**改了一半**；
- 修的时候给漏掉的两段补字面量，看起来是收口了，但下一个新加的 ``query(Position...)``
  依然没有任何东西拦得住它再漏一次。

所以判据不能只查「有没有过滤」，得查「过滤是不是从同一个入口来的」，以及
「**每一个** ``query/select(Position...)`` 是不是都在口径内」。

判据（全部静态可判，纯标准库 AST）
----------------------------------
R1 **禁止裸状态字面量**：``Position.ownership_status`` 与字符串常量直接比较即红。
   必须走 ``active_holdings()``，或用 ``OwnershipStatus.ACTIVE.value`` 枚举。
R2 **查询全覆盖**：两个 watchlist 模块里每个 ``query(Position...)`` / ``select(Position...)``
   都必须被 ``active_holdings(...)`` 直接包装，否则须命中 ``ALLOWLIST`` 精确白名单。
R3 **白名单不许陈旧**：``ALLOWLIST`` 里每一条都必须恰好命中一次；代码收敛了却留着
   白名单同样红（与迁移守卫「收敛一个删一个」同规）。
R4 **统一入口不许被掏空**：``position_scope.active_holdings`` 必须存在，且函数体内
   仍引用 ``OwnershipStatus.ACTIVE.value``。否则守卫全绿而语义已变，属假绿。
R5 **导入接线**：两个目标模块必须从 ``app.services.position_scope`` 导入 ``active_holdings``。
R6 **目标清单不许漏**：``backend/app/services/watchlist*.py`` 若出现未列入 ``TARGETS``
   的模块即红（新增模块必须显式接进本守卫）。

刻意不覆盖
----------
- **不判运行时行为**：``shadow`` / ``cleared`` 真的不进统计由
  ``backend/tests/domains/test_watchlist_holding_scope.py`` 钉住；本守卫只保证接线在。
- **不扫别的模块**：``position_display.py`` / ``ledger_service.py`` 等已各自走统一入口，
  各自有测试；本守卫的边界就是 watchlist 两个模块（新增模块走 R6 显式登记）。
- **不判 SQL 语义**：``active_holdings(select(...))`` 在 SQLAlchemy 里未必合法，
  本守卫只认 AST 包装形态；2.x ``select()`` 的刻意全量例外已列进白名单。

退出码
------
- 0：通过；
- 1：有违规；
- 2：输入不可信（文件缺失 / 语法错误 / 统一入口被删）——**不得**退化成「通过」。

用法
----
    python scripts/guard_watchlist_active_scope.py             # CI（仓库根）
    python scripts/guard_watchlist_active_scope.py --root .    # 显式指定根目录
回归网：scripts/tests/test_guard_watchlist_active_scope.py
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

SERVICES_DIR = 'backend/app/services'

#: 本守卫覆盖的 watchlist 模块（新增模块须同步登记，R6 会兜底）。
TARGETS = (
    'backend/app/services/watchlist_service.py',
    'backend/app/services/watchlist_display.py',
)

SCOPE_REL = 'backend/app/services/position_scope.py'
SCOPE_FUNC = 'active_holdings'
SCOPE_MODULE = 'app.services.position_scope'

#: 刻意「全量」的查询白名单：``(文件名, 函数名, 赋值目标, 调用形态) -> 理由``。
#: 这些查询**不能**挂 active_holdings()，挂了反而错；新增条目必须写清理由。
ALLOWLIST: dict[tuple[str, str, str, str], str] = {
    ('watchlist_service.py', 'build_groups_data', 'position_sum', 'query'): (
        '「已清仓」系统分组按 sum(quantity)==0 判定，必须看到全量 positions 行；'
        '过滤 active 后清仓行消失，分组恒为 0。'
    ),
    ('watchlist_service.py', 'create_watchlist_item', 'has_position', 'query'): (
        '新建自选项时判断「该 symbol 有没有 positions 行」以决定初始 HOLDING/WATCHING，'
        '是历史语义的存在性判定，不是当前持仓统计；本 PR 刻意不改。'
    ),
    ('watchlist_service.py', 'get_filtered_items_query', 'position_sum', 'select'): (
        '筛选查询的「已清仓」判定，与 build_groups_data 同理必须全量（2.x select 形态）。'
    ),
    ('watchlist_service.py', 'get_filtered_items_query', 'name_symbols', 'query'): (
        '按 positions.name 反查 symbol 的名称搜索，属身份反查不是持仓统计；'
        '多算无害，漏算会让搜索结果缺失。'
    ),
    ('watchlist_display.py', '_prefetch_display_fields', 'pos_types', 'query'): (
        '基金回撤的 asset_type 并集反查，源码注释已写明「多算无害，少算会让基金行误报 '
        'insufficient」；刻意全量。'
    ),
}


class InputError(Exception):
    """输入不可信：文件缺失 / 语法错误 / 统一入口失踪。退出码 2，不得读成「通过」。"""


def _parse(source: str, rel: str) -> ast.Module:
    try:
        return ast.parse(source)
    except SyntaxError as exc:
        raise InputError(f'{rel}: 语法错误，守卫无法判定（{exc}）') from exc


def _mentions_position(node: ast.AST) -> bool:
    return any(isinstance(child, ast.Name) and child.id == 'Position' for child in ast.walk(node))


def _is_ownership_attr(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == 'ownership_status'


def check_ownership_literal(source: str, rel: str | Path) -> list[str]:
    """R1：``Position.ownership_status`` 不许与字符串字面量直接比较。"""
    tree = _parse(source, str(rel))
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        if not any(_is_ownership_attr(op) for op in operands):
            continue
        if any(isinstance(op, ast.Constant) and isinstance(op.value, str) for op in operands):
            findings.append(
                f'{rel}:{node.lineno}: ownership_status 与字符串字面量直接比较；'
                f'改走 {SCOPE_FUNC}() 或 OwnershipStatus 枚举'
            )
    return findings


def _target_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, (ast.Tuple, ast.List)) and node.elts:
        return _target_name(node.elts[0])
    return '<expr>'


def _expr_var_name(call: ast.Call) -> str:
    """``name_symbols.update(...)`` → ``name_symbols``；其余退回 ``<expr>``。"""
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id
    if isinstance(func, ast.Name):
        return func.id
    return '<expr>'


def _context_of(tree: ast.Module) -> tuple[dict[int, ast.AST], dict[int, str], dict[int, ast.stmt], dict[int, str]]:
    """为每个 Call 节点建立 (父节点, 所在函数名, 所在语句, 赋值目标名) 索引。

    必须传入**与调用方同一棵 AST**：索引以 ``id(node)`` 为键，另 parse 一次会全部对不上
    （表现为「明明包了 active_holdings 却报未包装」，守卫自身假红）。
    """
    parents: dict[int, ast.AST] = {}
    funcs: dict[int, str] = {}
    stmts: dict[int, ast.stmt] = {}
    vars_: dict[int, str] = {}

    def walk(node: ast.AST, func: str, stmt: ast.stmt | None, var: str) -> None:
        new_func = node.name if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else func
        new_stmt = node if isinstance(node, ast.stmt) else stmt
        new_var = var
        if isinstance(node, ast.Assign):
            new_var = _target_name(node.targets[0])
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            new_var = _target_name(node.target)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            new_var = _expr_var_name(node.value)
        key = id(node)
        funcs[key], stmts[key], vars_[key] = new_func, new_stmt, new_var
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
            walk(child, new_func, new_stmt, new_var)

    walk(tree, '<module>', None, '<expr>')
    return parents, funcs, stmts, vars_


def _call_kind(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == 'query':
        return 'query'
    if isinstance(func, ast.Name) and func.id == 'select':
        return 'select'
    return None


def check_query_scope(source: str, rel: str | Path) -> tuple[list[str], set[tuple[str, str, str, str]]]:
    """R2：每个 query/select(Position...) 都要被 active_holdings() 包装或命中白名单。

    返回 ``(违规列表, 命中的白名单 key 集合)``；R3 的「白名单陈旧」由 ``run()`` 汇总判定。
    """
    tree = _parse(source, str(rel))
    parents, funcs, _stmts, vars_ = _context_of(tree)
    findings: list[str] = []
    used: set[tuple[str, str, str, str]] = set()
    filename = Path(rel).name

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kind = _call_kind(node)
        if kind is None or not any(_mentions_position(arg) for arg in node.args):
            continue

        parent = parents.get(id(node))
        wrapped = (
            isinstance(parent, ast.Call)
            and isinstance(parent.func, ast.Name)
            and parent.func.id == SCOPE_FUNC
            and any(arg is node for arg in parent.args)
        )
        if wrapped:
            continue

        key = (filename, funcs.get(id(node), '<module>'), vars_.get(id(node), '<expr>'), kind)
        if key in ALLOWLIST:
            used.add(key)
            continue
        findings.append(
            f'{rel}:{node.lineno}: 未经 {SCOPE_FUNC}() 包装的 {kind}(Position...) '
            f'（函数={key[1]}, 赋值={key[2]}）；「当前持仓」查询须走统一入口，'
            f'确属全量语义请在 ALLOWLIST 登记理由'
        )
    return findings, used


def check_imports(source: str, rel: str | Path) -> list[str]:
    """R5：目标模块必须从统一入口导入 active_holdings。"""
    tree = _parse(source, str(rel))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == SCOPE_MODULE
            and any(alias.name == SCOPE_FUNC for alias in node.names)
        ):
            return []
    return [f'{rel}: 缺少 `from {SCOPE_MODULE} import {SCOPE_FUNC}`']


def check_scope_source(source: str, rel: str | Path) -> list[str]:
    """R4：统一入口不许被掏空（守卫绿而语义已变 = 假绿）。"""
    tree = _parse(source, str(rel))
    fn = next(
        (node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == SCOPE_FUNC),
        None,
    )
    if fn is None:
        raise InputError(f'{rel}: 找不到 {SCOPE_FUNC}() 定义，统一入口失踪')
    body = ast.unparse(fn)
    if 'OwnershipStatus.ACTIVE.value' not in body:
        msg = (
            f'{rel}: {SCOPE_FUNC}() 函数体内不再引用 OwnershipStatus.ACTIVE.value；'
            '入口仍在但口径可能已被改掉，守卫会假绿'
        )
        return [msg]
    return []


def run(root: Path) -> int:
    """扫真实仓库，返回 0（通过）/ 1（违规）。输入不可信抛 :class:`InputError`。"""
    findings: list[str] = []
    used: set[tuple[str, str, str, str]] = set()

    for rel in TARGETS:
        path = root / rel
        if not path.is_file():
            raise InputError(f'缺少目标文件：{rel}')
        source = path.read_text(encoding='utf-8')
        findings += check_ownership_literal(source, rel)
        file_findings, file_used = check_query_scope(source, rel)
        findings += file_findings
        used |= file_used
        findings += check_imports(source, rel)

    # R3：白名单必须条条命中，否则说明代码已收敛而白名单没跟着删。
    for key, reason in ALLOWLIST.items():
        if key not in used:
            findings.append(f'ALLOWLIST 陈旧：{key} 在真实代码里已无对应查询（理由：{reason}）；请删除该条目')

    scope_path = root / SCOPE_REL
    if not scope_path.is_file():
        raise InputError(f'缺少统一入口文件：{SCOPE_REL}')
    findings += check_scope_source(scope_path.read_text(encoding='utf-8'), SCOPE_REL)

    # R6：新增 watchlist 服务模块必须显式登记。
    services = root / SERVICES_DIR
    if services.is_dir():
        for path in sorted(services.glob('watchlist*.py')):
            rel = f'{SERVICES_DIR}/{path.name}'
            if rel not in TARGETS:
                findings.append(f'{rel}: 新的 watchlist 模块未登记进守卫 TARGETS')

    for item in findings:
        print(f'[违规] {item}', file=sys.stderr)
    if not findings:
        print(f'[OK] watchlist 当前持仓口径：{len(TARGETS)} 个模块全部走 {SCOPE_FUNC}()')
    return 1 if findings else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='watchlist 当前持仓口径守卫')
    parser.add_argument('--root', default='.', help='仓库根目录（默认当前目录）')
    args = parser.parse_args(argv)
    try:
        return run(Path(args.root))
    except InputError as exc:
        print(f'[输入不可信] {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
