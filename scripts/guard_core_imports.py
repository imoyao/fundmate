#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：`backend/app/core/**` 不得反向依赖领域层（#1607）。

依赖方向（`docs/spec/decisions.md` 2026-09-19 决策行）
----------------------------------------------------
    core ← domains.models ← services ← domains.<域>.views

core 是业务无关的基础设施层（DB / money / auth / 异常 / 补丁 / 缓存），**不得** import
`app.domains.*` 或 `app.models.*`。历史问题是：`core/auth.py` 直接持有 `User`、
`core/database.py` 的 `_seed_default_identity` 把默认家庭/用户种子写在 core，靠函数内
延迟 import 掩盖——属「用延迟 import 掩盖的架构问题」（审查报告 §4.2）。修复方式是把
领域读写下沉到 domains 侧、由组合根（`app/main.py`）注入 / 调用，本守卫固定该边界。

检测策略（AST，纯标准库）
-------------------------
扫描 `backend/app/core/**/*.py`：

1. **import 语句**：`import app.domains.x` / `from app.domains.x import y` /
   `import app.models.x` / `from app.models import y`；
2. **动态 import 字面量**：`importlib.import_module('app.domains...')` / `__import__('app.models...')`。

注释与 docstring 里的提及**不算违规**（决策原文即「除注释外零引用」；本守卫自身、
`docs/spec/decisions.md` 都需要在文字里引用这些路径）。

用法
----
    python scripts/guard_core_imports.py [--core-dir backend/app/core]
退出码：0 = 干净；1 = 发现违规（并打印修复方向）；2 = 参数错误。
"""

import argparse
import ast
import sys
from pathlib import Path

# 禁止 core 引用的包前缀（命中其一即违规）
FORBIDDEN_PREFIXES = ('app.domains', 'app.models')
# 动态 import 的入口函数名（其首个字符串字面量实参按包路径审查）
DYNAMIC_IMPORT_FUNCS = {'import_module', '__import__'}


def _is_forbidden(module: str | None) -> bool:
    """模块路径是否落在禁止前缀内（按包边界匹配，避免 `app.domains_x` 误判）。"""
    if not module:
        return False
    return any(module == prefix or module.startswith(prefix + '.') for prefix in FORBIDDEN_PREFIXES)


def _call_name(node: ast.AST) -> str | None:
    """从 Call 节点取出被调用者的名字（`importlib.import_module` → 'import_module'）。"""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _dynamic_import_target(node: ast.AST) -> str | None:
    """若 node 是 `import_module('app.domains...')` 形态，返回其字面量模块名。"""
    if _call_name(node) not in DYNAMIC_IMPORT_FUNCS:
        return None
    if not isinstance(node, ast.Call) or not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def scan_file(path: Path, violations: list[str]) -> None:
    """扫描单个 core 文件，命中即追加违规描述（含行号与源码原文）。"""
    try:
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - 语法错误由 ruff/CI 先行拦截
        violations.append(f'{path}: 语法错误（{exc}）—— 请先过 ruff')
        return
    except Exception as exc:  # pragma: no cover
        violations.append(f'{path}: 无法读取（{exc}）')
        return

    lines = source.splitlines()

    def _report(lineno: int, module: str, stmt: str) -> None:
        snippet = lines[lineno - 1].strip() if 0 < lineno <= len(lines) else stmt
        violations.append(
            f'{path}:{lineno}  core 不得 import 领域层：{module}\n'
            f'         源码：{snippet}\n'
            f'         → 领域读写下沉到 app/domains/ 侧，由组合根（app/main.py）注入或调用'
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden(alias.name):
                    _report(node.lineno, alias.name, f'import {alias.name}')
        elif isinstance(node, ast.ImportFrom):
            if _is_forbidden(node.module):
                _report(node.lineno, node.module or '', f'from {node.module} import ...')
        else:
            target = _dynamic_import_target(node)
            if target is not None and _is_forbidden(target):
                _report(node.lineno, target, f"import_module({target!r})")


def scan_core(core_dir: Path) -> list[str]:
    """扫描整个 core 目录，返回违规清单（空列表 = 干净）。"""
    violations: list[str] = []
    for py_file in sorted(core_dir.rglob('*.py')):
        scan_file(py_file, violations)
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description='core 层零领域依赖守卫（#1607）')
    parser.add_argument(
        '--core-dir',
        default=str(Path(__file__).resolve().parent.parent / 'backend' / 'app' / 'core'),
        help='要扫描的 core 目录（默认仓库 backend/app/core）',
    )
    args = parser.parse_args()

    core_dir = Path(args.core_dir)
    if not core_dir.is_dir():
        print(f'ERROR: core 目录不存在：{core_dir}', file=sys.stderr)
        return 2

    violations = scan_core(core_dir)
    if violations:
        print('ERROR: app/core 反向依赖领域层（依赖方向应为 core ← domains ← services）：', file=sys.stderr)
        for violation in violations:
            print(f'  - {violation}', file=sys.stderr)
        print(
            '\n修复方向见 docs/spec/decisions.md「依赖方向」决策行；'
            'core 需要的领域能力一律经注入 / 组合根调用获得。',
            file=sys.stderr,
        )
        return 1

    print(f'OK: app/core 零领域依赖（扫描 {len(list(core_dir.rglob("*.py")))} 个文件）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
