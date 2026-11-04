#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上游列名契约守卫（#2543）：契约漂移必须显性失败，且不得被 except 吞回空列表。

WHY
===
2026-10-23 ``fund_scale`` job 报红，日志里躺着 akshare 抛的 ``"[...] not in index"``
——上游改列名了。适配层当时的写法是 ``row.get('基金代码')`` + ``except: return []``，
于是「列名漂移」与「上游今天没数据」**都表现为空列表**：job 层虽然判红了，报出来
的原因却是「返回空数据」，真正的原因只留在源日志里。

``backend/app/services/adapters/contract.py`` 提供了修法（钉契约 + ``assert_columns``
+ ``UpstreamContractError``）。本守卫负责让**这个修法不会退化回去**——
写进 AGENTS.md 的软约束管不住下一次「顺手改回 return []」。

判据（每个契约条目四条，任一不满足即红）
====================================
- **R1 契约常量存在**：模块级必须定义 ``<REQUIRED>`` 与 ``<KNOWN>`` 两个常量；
- **R2 调用了 assert_columns**：函数体内必须出现 ``assert_columns(...)``；
- **R3 引用契约常量**：``assert_columns`` 的关键字参数必须指向契约常量，
  不接受就地硬编码另一份列名（硬编码会让「契约」重新散落回函数里）；
- **R4 except 分支不得 return []**：吞掉失败态就是本次事故的同型复现。

退出码
======
    0 = 全部通过
    1 = 有条目违反判据
    2 = **拿不到输入**（文件缺失 / 语法解析失败）⇒ 结论不可信，不得读成通过

用法
====
    python scripts/guard_upstream_column_contract.py
    python scripts/guard_upstream_column_contract.py --root <临时目录>   # 回归网用
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Any, Dict, List

# 契约登记表：新接入一个上游契约 = 加一行（守卫生效，无需改判据代码）。
CONTRACTS: List[Dict[str, str]] = [
    {
        'name': 'fund_scale',
        'file': 'backend/app/services/adapters/akshare_adapter.py',
        'func': 'fetch_fund_scale',
        'required_const': 'FUND_SCALE_REQUIRED_COLUMNS',
        'known_const': 'FUND_SCALE_KNOWN_COLUMNS',
    },
]

ROOT = Path(__file__).resolve().parents[1]


# ── 取函数源码 ──


def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef:
    """按名字取模块的顶层类/函数的成员函数。

    只找类体里的成员函数（契约都挂在适配器类上），模块级函数也一并兼容。
    找不到抛 LookupError。
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise LookupError(f'未找到函数 {name}')


def _module_consts(tree: ast.AST) -> Dict[str, Any]:
    """模块级常量名 → 节点（只取简单赋值：Name / Tuple / Str）。"""
    out: Dict[str, Any] = {}
    for node in getattr(tree, 'body', []):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out[node.target.id] = node.value
    return out


# ── 判据 ──


def _calls_assert_columns(fn: ast.FunctionDef) -> List[ast.Call]:
    return [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'assert_columns'
    ]


def _kwargs_names(call: ast.Call) -> Dict[str, str]:
    """关键字参数 → 其源码表达式（只关心 Name 常量引用）。"""
    out: Dict[str, str] = {}
    for kw in call.keywords:
        if kw.arg is None:
            continue
        if isinstance(kw.value, ast.Name):
            out[kw.arg] = kw.value.id
        else:
            out[kw.arg] = ast.unparse(kw.value)
    return out


def _except_returns_empty(fn: ast.FunctionDef) -> bool:
    """except 处理器里是否存在 `return []`（吞掉失败态）。"""
    for node in ast.walk(fn):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            for sub in ast.walk(handler):
                if isinstance(sub, ast.Return) and isinstance(sub.value, ast.List):
                    if not sub.value.elts:
                        return True
    return False


def check_contract(root: Path, c: Dict[str, str]) -> List[str]:
    """返回违反的判据编号列表；空列表 = 通过。"""
    path = root / c['file']
    if not path.is_file():
        raise FileNotFoundError(f'{c["file"]} 不存在')

    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    fn = _find_function(tree, c['func'])
    consts = _module_consts(tree)

    bad: List[str] = []

    # R1 契约常量存在
    for key in ('required_const', 'known_const'):
        if c[key] not in consts:
            bad.append(f'R1(缺模块级常量 {c[key]})')

    calls = _calls_assert_columns(fn)
    if not calls:
        bad.append('R2(未调用 assert_columns)')
    else:
        # R3 必须引用契约常量，不接受就地硬编码
        ok = False
        for call in calls:
            kw = _kwargs_names(call)
            if kw.get('required') == c['required_const'] and kw.get('known') == c['known_const']:
                ok = True
                break
        if not ok:
            bad.append(f'R3(assert_columns 未引用 {c["required_const"]} / {c["known_const"]}，疑似就地硬编码列名)')

    # R4 except 分支不得 return []
    if _except_returns_empty(fn):
        bad.append('R4(except 分支 return [] —— 失败态被吞成本次事故同型的空列表)')

    return bad


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='上游列名契约守卫（#2543）')
    ap.add_argument('--root', default=str(ROOT), help='仓库根（回归网指向临时目录用）')
    ap.add_argument('--report', action='store_true', help='只报告，始终退出 0')
    args = ap.parse_args(argv)
    root = Path(args.root)

    violations: List[str] = []
    for c in CONTRACTS:
        try:
            bad = check_contract(root, c)
        except FileNotFoundError as e:
            print(f'[FATAL] 拿不到输入: {e}', file=sys.stderr)
            return 2
        except SyntaxError as e:
            print(f'[FATAL] 解析失败: {e}', file=sys.stderr)
            return 2
        except LookupError as e:
            print(f'[FATAL] 拿不到输入: {e}', file=sys.stderr)
            return 2

        if bad:
            violations.append(f'{c["name"]}: ' + '; '.join(bad))
            print(f'[FAIL] {c["name"]} ({c["file"]}::{c["func"]})')
            for b in bad:
                print(f'       ↳ {b}')
        else:
            print(f'[OK]   {c["name"]} ({c["file"]}::{c["func"]})')

    if violations:
        print(f'\n上游列名契约守卫：{len(violations)}/{len(CONTRACTS)} 个契约未达标', file=sys.stderr)
        return 0 if args.report else 1
    print(f'\n上游列名契约守卫：{len(CONTRACTS)}/{len(CONTRACTS)} 个契约达标')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
