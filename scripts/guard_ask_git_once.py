#!/usr/bin/env python3
"""守门：`git` 的**同一次询问**不许问两遍再取第二遍的输出。

WHY（源 CNB #573，2026-10-18 构建 `cnb-um5-1k57nplko`）
-------------------------------------------------------
`machine_branch.py` 的演练路径原先是这么写的：

    code, _, _ = _git(['merge-tree', '--write-tree', base, merge])   # ① 取退出码
    if code == 1:
        _, out, _ = _git(['merge-tree', '--write-tree', base, merge])  # ② 再跑一遍取输出

两次**独立进程**，却当成「同一个答案的两半」。只要 ② 的输出（或它对返回值的解包）
与 ① 对不上——比如 `_git()` 的返回约定从两值改成三值而某个调用点没跟着改——
冲突清单就**恒为空**，于是「有冲突」与「无冲突」在报告里长得一模一样：

    ⚠️ 有 N 个文件冲突 —— 什么都没推        ← 实际从没打印出来过
    ✅ 无冲突，两侧内容可合。                ← 这才是每次都在打的那一句

**它的失败形态是静默的**：报告更响亮地给出错误结论，构建照样红在别处，
没人会去怀疑「冲突清单为什么总是空的」。

判据
----
对 `scripts/**/*.py`：**同一个 `_git([...])` 参数元组**在同一个函数里出现两次以上，
且第二次的姿态是「丢掉退出码」（`_, out, _ =`）⇒ 报红。
「问两遍」本身不违法（探针、重试都合法）；违法的是**拿两次结果拼一个结论**。

边界（有意为之）
----------------
- 参数按**结构形状**比对（`_shape()`：常量保内容、变量保名字、其它保骨架），
  故 `p['base_ref']` 与 `cwd` 这类参数能认出来。真正的「算出来的参数」（比如
  `_git(build_args())`）只有在形状也一致时才会命中 —— 那种情况本来就该报红；
- 只管同一个函数内：跨函数复用同一个查询是有意的缓存语义，不在判据内；
- 不判「两次结果是否真的不一致」——那要跑起来才知道；**判据要的是「不许有这种形状」**，
  因为这种形状的正确性依赖「两次之间没有东西变化」，而那是无法静态保证的。
- 读不到输入（文件不存在 / 语法错）⇒ 退 2 并声明结论不可信，不得退化成「没问题」。

用法
----
    python scripts/guard_ask_git_once.py          # 扫全仓 scripts/**/*.py
    python scripts/guard_ask_git_once.py --file x # 只查一个文件
退出码 0 = 通过，1 = 发现问题，2 = 输入不可用。
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / 'scripts'

# `_git` 家族：本仓所有 git 调用的入口（见各 bridge 脚本的 `_git()`）
GIT_FN = '_git'


def _shape(node: ast.AST) -> str:
    """把表达式压成**结构形状**（丢掉常量内容与变量名，只留骨架）。

    这一步是判据的核心：真实代码里两次调用写作
    `_git(['merge-tree', '--write-tree', p['base_ref'], p['merge_ref']], cwd)` ——
    参数**逐字相同**，但 `p['base_ref']` 是 Subscript、`cwd` 是 Name。
    只认「纯字面量」的判据会在真实代码上**恒绿**（第一版就是这么写的，实测自咬）。
    """
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Name):
        return f'Name({node.id})'
    return f'{type(node).__name__}({",".join(_shape(c) for c in ast.iter_child_nodes(node))})'


def _call_key(node: ast.Call) -> str | None:
    """把 `_git([...])` 的参数元组压成形状键（位置参数逐个取 `_shape`）。"""
    if not node.args:
        return None
    return '\x00'.join(_shape(a) for a in node.args)


def _is_git_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == GIT_FN


def _discards_status(node: ast.Assign | ast.AnnAssign) -> bool:
    """判「这一行的赋值把退出码丢掉了」：`_, out, _ = …` / `_, out = …`。"""
    value = node.value
    if not (_is_git_call(value)):
        return False
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    if len(targets) != 1 or not isinstance(targets[0], ast.Tuple):
        return False
    first = targets[0].elts[0] if targets[0].elts else None
    return isinstance(first, ast.Name) and first.id == '_'


def scan_source(src: str, filename: str = '<src>') -> list[str]:
    """返回问题清单（空 = 通过）。抽成纯函数，便于回归网用可控输入钉住。"""
    try:
        tree = ast.parse(src, filename=filename)
    except SyntaxError as exc:  # 读不懂就不猜
        return [f'{filename}: 语法解析失败（{exc.msg}）—— 本轮结论不可信']

    problems: list[str] = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        asked: dict[str, tuple[int, bool]] = {}
        for node in ast.walk(fn):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            if not _is_git_call(node.value):
                continue
            key = _call_key(node.value)
            if key is None:
                continue
            first_line, _ = asked.get(key, (node.lineno, False))
            if key in asked and _discards_status(node):
                problems.append(
                    f'{filename}:{node.lineno}: 函数 `{fn.name}` 里同一个 git 询问出现了两次，'
                    f'且第二遍丢掉了退出码（第一遍在 {first_line} 行）——'
                    '两次独立进程的结果被当成同一个答案，其中一遍读空就会静默翻转结论'
                )
            asked.setdefault(key, (node.lineno, False))
    return problems


def scan_paths(paths: list[Path]) -> tuple[list[str], list[str]]:
    """返回 (问题, 读不到的文件)。后者用于「输入不可信」的显式失败态。"""
    problems: list[str] = []
    unreadable: list[str] = []
    for p in paths:
        try:
            src = p.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as exc:
            unreadable.append(f'{p}: {exc}')
            continue
        problems.extend(scan_source(src, str(p.relative_to(REPO_ROOT)) if p.is_relative_to(REPO_ROOT) else str(p)))
    return problems, unreadable


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='守门：git 的同一次询问不许问两遍再取第二遍输出')
    ap.add_argument('--file', action='append', default=None, help='只检查指定文件（可重复）')
    args = ap.parse_args(argv)

    if args.file:
        paths = [Path(f) for f in args.file]
    else:
        if not SCRIPTS_DIR.is_dir():
            print('❌ 读不到 scripts/ 目录 —— 本轮结论不可信', file=sys.stderr)
            return 2
        paths = sorted(SCRIPTS_DIR.rglob('*.py'))

    problems, unreadable = scan_paths(paths)
    if unreadable:
        for u in unreadable:
            print(f'⚠️ 读不到：{u}', file=sys.stderr)
        print('❌ 有文件读不到 —— 本轮结论不可信，不得读成「没问题」', file=sys.stderr)
        return 2
    if problems:
        for p in problems:
            print(f'❌ {p}', file=sys.stderr)
        print('\n改法：一次调用同时拿「退出码」和「输出」，别把同一个 git 询问问两遍。', file=sys.stderr)
        return 1
    print(f'✅ {len(paths)} 个脚本无「同一 git 询问问两遍」的形态')
    return 0


if __name__ == '__main__':
    sys.exit(main())
