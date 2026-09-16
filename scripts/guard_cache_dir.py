#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：禁止在 backend/app 里新增「未经文件缓存单一真相源路由的硬编码缓存目录」。

根因（#1531 → #1537 → #1539 → #1540 连犯四次）
------------------------------------------------
缓存 / 持久化目录被写成**模块级常量**，或在 import 期就拼好的字面量，导致 env
`CACHE_FILE_DIR` 只对部分实现生效（「部分生效」比「全不生效」更难排查）。这个坑在
#1531（`_FILE_DIR`）→ #1537（`_CACHE_DIR`）→ #1539（温度计三处）→ #1540（bias 价格缓存）
连犯四次，每次都是「换了个文件名又写一遍」。本守卫从**机器可拦**的角度把第五处堵死。

全仓「文件缓存落哪儿」的**唯一真相源**是 ``app/core/cache.py`` 的：
    - ``resolve_cache_file_dir()``   —— pickle 值对象的文件层目录
    - ``resolve_cache_subdir(name)`` —— parquet/CSV/JSON 大对象的命名子目录
任何新增的缓存目录字面量都必须经它们路由（或显式白名单，见 ``ALLOWLIST``）。

检测策略（AST，纯标准库）
-------------------------
扫描 ``backend/app/**/*.py``，对两类信号报错（命中即退出 1）：

1. **路径构造字面量含 ``cache``**（不区分大小写）：出现在 ``Path(...)`` /
   ``PurePath(...)`` / ``os.path.join(...)`` 的字符串参数，或 ``x / '字面量'`` 形式的
   ``BinOp`` 右操作数。**排除**出现在 ``resolve_cache_file_dir()`` /
   ``resolve_cache_subdir()`` 调用内部的字面量（解析器自身）。

2. **模块级 CACHE 命名常量**：模块顶层 ``NAME`` 含 ``CACHE`` 且其值为「路径构造出自字面量」
   或「读取 env（``os.environ.get`` / ``os.getenv``）」——对应 #1537 的 import 期读 env 反模式
   与 #1539 的模块级常量反模式。

白名单（``ALLOWLIST``）：当前唯一一条是 ``xalpha_adapter.py`` 的 ``data/xalpha_cache``，
它是**故意相对 CWD** 的基金净值历史缓存（搬家 = 全量重抓，耗时且没必要），属项目既有
``data/`` 约定，不是本坑。

注意：本守卫只扫 ``backend/app/``（生产代码），**不扫** ``tests/``——测试用 ``tmp_path``
硬编码临时路径是合法且必需的。

用法
----
    python scripts/guard_cache_dir.py [--app-dir backend/app]
退出码：0 = 干净；1 = 发现违规（并打印修复建议）；2 = 参数错误。
"""

import argparse
import ast
import sys
from pathlib import Path

# 路径构造入口（函数名）
PATH_FUNCS = {'join', 'Path', 'PurePath', 'PurePosixPath', 'PureWindowsPath'}
# 单一真相源解析器（其内部字面量不计入违规）
APPROVED_RESOLVERS = {'resolve_cache_file_dir', 'resolve_cache_subdir'}
# 模块级常量名若含这些片段，则进入「是否硬编码目录」的审查
CACHE_NAME_FRAGMENTS = ('CACHE', '_CACHE')
# 触发「读取 env」反模式的调用名
ENV_READ_FUNCS = {'getenv', 'environ'}

# 显式白名单：字面量子串 -> 允许理由（命中即放行，不计入违规）。
# 仅收录「刻意不路由真相源」的既有约定，新增白名单须在此留理由。
ALLOWLIST = {
    'xalpha_cache': (
        "xalpha_adapter 的 data/xalpha_cache：故意相对 CWD 的基金净值历史缓存，"
        "搬家会触发全量重抓，属项目既有 data/ 约定，非本坑（#1540 已评估）。"
    ),
}


def _call_name(node: ast.AST) -> str | None:
    """从 Call 节点取出被调用者的名字（``os.path.join`` → 'join'，``Path`` → 'Path'）。"""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _looks_like_cache_literal(value: str) -> bool:
    return 'cache' in value.lower()


def _is_allowlisted(value: str) -> bool:
    low = value.lower()
    for key, _reason in ALLOWLIST.items():
        if key.lower() in low:
            return True
    return False


def _collect_approved_nodes(tree: ast.AST) -> set[int]:
    """收集出现在「已批准解析器」调用内部的全部子节点 id，便于排除解析器自身字面量。"""
    approved: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node) in APPROVED_RESOLVERS:
            for sub in ast.walk(node):
                approved.add(id(sub))
    return approved


def _is_path_construction(node: ast.AST) -> bool:
    """node 是否出现在路径构造上下文：Path(...)/PurePath(...)/os.path.join(...) 的实参，
    或 `base / literal` 的 BinOp 右操作数。"""
    parent = getattr(node, '_parent', None)
    # 实参形式
    if isinstance(parent, ast.Call) and _call_name(parent) in PATH_FUNCS:
        return True
    # BinOp 右操作数（base / 'literal'）
    if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div) and parent.right is node:
        return True
    return False


def _value_is_env_read(node: ast.AST) -> bool:
    """node 是否为 `os.environ.get(...)` / `os.getenv(...)` 形式（import 期读 env 反模式）。"""
    if isinstance(node, ast.Call):
        return _call_name(node) in ENV_READ_FUNCS
    if isinstance(node, ast.Subscript):
        # os.environ['X']
        base = node.value
        if isinstance(base, ast.Attribute) and base.attr == 'environ':
            return True
        if isinstance(base, ast.Name) and base.id == 'environ':
            return True
    return False


def scan_file(path: Path, violations: list[str]) -> None:
    try:
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - 源码语法错误由 ruff/CI 先行拦截
        violations.append(f'{path}: 语法错误（{exc}）—— 请先过 ruff')
        return
    except Exception as exc:  # pragma: no cover
        violations.append(f'{path}: 无法读取（{exc}）')
        return

    # 给每个节点挂 _parent，便于判断字面量上下文
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            setattr(child, '_parent', parent)

    approved = _collect_approved_nodes(tree)

    # ── 信号 1：路径构造字面量含 cache ──
    for node in ast.walk(tree):
        lit = None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            lit = node.value
        if lit is None:
            continue
        if not _looks_like_cache_literal(lit):
            continue
        if id(node) in approved:
            continue
        if _is_allowlisted(lit):
            continue
        if _is_path_construction(node):
            lineno = getattr(node, 'lineno', '?')
            violations.append(
                f'{path}:{lineno}  路径构造字面量含 cache 但未路由真相源：{lit!r}\n'
                f'         → 改为 resolve_cache_subdir({lit!r}) 或经 resolve_cache_file_dir() 取目录'
            )

    # ── 信号 2：模块级 CACHE 命名常量 = 硬编码目录 / import 期读 env ──
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if not any(frag in target.id.upper() for frag in CACHE_NAME_FRAGMENTS):
                continue
            value = node.value
            # 解析器内部的 _FILE_DIR_NAME='fundmate_cache' 等纯字符串命名不算违规
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                # 纯字符串命名（无路径构造语义）放行：它是「名字」不是「目录路径」
                continue
            hard_path = (
                isinstance(value, ast.Call)
                and _call_name(value) in PATH_FUNCS
                and any(
                    isinstance(a, ast.Constant)
                    and isinstance(a.value, str)
                    and _looks_like_cache_literal(a.value)
                    for a in value.args
                )
            )
            env_read = _value_is_env_read(value)
            if hard_path or env_read:
                kind = 'import 期读 env' if env_read else '硬编码目录'
                violations.append(
                    f'{path}:{node.lineno}  模块级 CACHE 常量疑似{kind}：{target.id}\n'
                    f'         → 改为调用期经 resolve_cache_file_dir() / resolve_cache_subdir() 解析'
                )


def main() -> int:
    parser = argparse.ArgumentParser(description='缓存目录硬编码守卫')
    parser.add_argument(
        '--app-dir',
        default=str(Path(__file__).resolve().parent.parent / 'backend' / 'app'),
        help='要扫描的 app 目录（默认仓库 backend/app）',
    )
    args = parser.parse_args()

    app_dir = Path(args.app_dir)
    if not app_dir.is_dir():
        print(f'ERROR: app 目录不存在：{app_dir}', file=sys.stderr)
        return 2

    violations: list[str] = []
    py_files = sorted(app_dir.rglob('*.py'))
    for fp in py_files:
        scan_file(fp, violations)

    if violations:
        print('ERROR: 发现未经文件缓存单一真相源路由的硬编码缓存目录：', file=sys.stderr)
        for v in violations:
            print(f'  - {v}', file=sys.stderr)
        print(
            '\n请改用 app/core/cache.py 的 resolve_cache_file_dir() / resolve_cache_subdir()，'
            '或先在 scripts/guard_cache_dir.py 的 ALLOWLIST 中登记并说明理由。',
            file=sys.stderr,
        )
        return 1

    print(f'OK: 未发现硬编码缓存目录（扫描 {len(py_files)} 个文件，单一真相源有效）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
