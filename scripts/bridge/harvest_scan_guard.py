#!/usr/bin/env python3
"""静态守卫：`harvest_existing()` 不得再用状态文件当前置短路（源 CNB #450）。

## 为什么需要一条「读代码」的守卫

#450 的故障形态很特别：**代码看起来是对的**。「状态文件里有映射的直接信它」读起来
像是合理的缓存优化，review 时很难觉得它错；但它是「幂等建卡」这件事的**信任边界**——
一旦缓存不全，幂等当场失效，而且失效得**很安静**（每轮都建卡成功、日志全绿）。

这类「缓存被当成全集」的错误，靠人 review 是拦不住的（它就是靠人 review 漏过去的）。
能拦住的只有一条：**「扫描 CNB 侧」这件事必须在函数体里真的发生**，
不能被任何 `if <cache> : return` 提前返回。

## 判据

`harvest_existing` 函数体内：

1. 必须出现对 `list_cnb_issues(` 的调用（真的去列 CNB 卡）；
2. **不得**在 `list_cnb_issues(` 之前出现 `return`（提前返回 = 短路）。

第 2 条是关键：它不管短路条件写成什么形状（`if known:` / `if len(known) > 10:` /
`if cached and not force:`），只要「在扫描之前就返回」就报红 —— 不去拟合具体写法。

## 已知假阴性

- 把扫描挪进别的函数、`harvest_existing` 只调用它：第 1 条会红（误报），
  但那种重构本文档不鼓励（本函数就是「收集已存在」这件事本身）；
- 用 `sys.exit` / `raise` 代替 `return` 短路：拦不住。属于刻意绕过，不在判据范围内。

## 用法

    python scripts/bridge/harvest_scan_guard.py      # 退出码 0 = 通过，1 = 违规
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

TARGET_FILE = Path(__file__).resolve().parent / 'github_cnb_issues.py'
TARGET_FUNC = 'harvest_existing'
SCAN_CALL = 'list_cnb_issues'


def _function_node(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def check(source: str) -> list[str]:
    """返回违规清单（空 = 通过）。纯函数，供单测直接调用。"""
    problems: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f'{TARGET_FILE.name} 解析失败：{exc}']

    func = _function_node(tree, TARGET_FUNC)
    if func is None:
        return [f'找不到函数 {TARGET_FUNC}()（改名了？守卫需同步，不要静默放过）']

    scan_lines = [
        node.lineno
        for node in ast.walk(func)
        if isinstance(node, ast.Call) and _call_name(node) == SCAN_CALL
    ]
    if not scan_lines:
        problems.append(
            f'{TARGET_FUNC}() 里没有调用 {SCAN_CALL}() —— 必须真扫 CNB 侧，'
            f'不得只信状态文件缓存（#450：缓存是不全的，把它当全集就会重复建卡）'
        )
        return problems

    first_scan = min(scan_lines)
    early_returns = [
        node.lineno for node in ast.walk(func) if isinstance(node, ast.Return) and node.lineno < first_scan
    ]
    for lineno in sorted(early_returns):
        problems.append(
            f'{TARGET_FUNC}() 第 {lineno} 行的 return 出现在第 {first_scan} 行 '
            f'{SCAN_CALL}() 之前 —— 这是「拿缓存当前置短路」，即 #450 的根因；'
            f'扫描 CNB 侧必须是函数体的必经之路'
        )
    return problems


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def main() -> int:
    source = TARGET_FILE.read_text(encoding='utf-8')
    problems = check(source)
    if problems:
        print(f'❌ {TARGET_FILE.name} 违反「扫描不可短路」判据：')
        for p in problems:
            print(f'   - {p}')
        print()
        print('  依据：AGENTS.md「双端协作」+ docs/dev/github-cnb-mirror.md（源 CNB #450）')  # cross-repo-ref-allow
        return 1
    print(f'✅ {TARGET_FILE.name} 的 {TARGET_FUNC}() 真扫 CNB 侧且未被短路')
    return 0


if __name__ == '__main__':
    sys.exit(main())
