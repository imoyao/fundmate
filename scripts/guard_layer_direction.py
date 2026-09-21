#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：后端分层依赖方向（#1607，批次 1 引入 core 专用版、批次 2 泛化为全层）。

依赖方向（`docs/spec/decisions.md` 2026-09-19 决策行 D24 + `architecture.md` §6）
--------------------------------------------------------------------------------
    core  ←  domains.<域>.models / schemas  ←  services  ←  domains.<域>.views

本守卫把下面四条**非法边**变成红灯（AST 静态可判、零误报面）：

| 规则 | 非法边 | 为什么 |
|---|---|---|
| R1 | `app.core.*` → `app.domains.*` / `app.models.*` | 基础设施层反向依赖领域层（批次 1 已归零） |
| R2 | `app.services.*` → `app.domains.<域>.views` | 服务层碰 HTTP 编排层 |
| R3 | `app.domains.<域>.{models,schemas}` → `app.services.*` | 叶子层反向依赖服务层 |
| R4 | `app.domains.A.views` → `app.domains.B.views`（A≠B） | 跨域引用对方视图（HTTP 细节外溢到另一域） |
| R5 | `app.services.adapters.*` / `job_base` / `import_records` → `app.services.{sync,importer,thermometer,bias,ai_recognizer}.*` | services 顶层**共享件**反向依赖家族包（共享件必须是叶子，否则又长回「寄生」） |

**不判的（刻意）**：`views → services`、`services → domains.models/schemas`、
`domains.A.models ↔ domains.B.models`、`家族包 → 共享件` 等**合法边**；
以及「包级双向依赖对」——它多数由 `views→services` 与 `services→models` 两条合法边叠加而成
（如 `domains.positions` ↔ `services.position_service`），不构成违规。
`services` 内部方向（编排层 vs 领域服务）见 `docs/spec/tech-debt.md` #1607 条目。

检测策略（AST，纯标准库）：import 语句 + 动态 import 字面量
（`importlib.import_module('app.domains...')` / `__import__('app.models...')`）。
注释与 docstring 里的提及**不算违规**（决策原文即「除注释外零引用」；
`decisions.md`、本守卫、迁移说明都需要在文字里引用这些路径）。

"views 层"的识别用**命名约定**：域包下第一段以 `views` 结尾者（`views` / `e_account_views`
等）；`models` / `schemas` 取同位置的精确名。域包下的其它模块（如 `constants`、`advisor_catalog`）
不受 R3/R4 约束。

用法
----
    python scripts/guard_layer_direction.py [--app-dir backend/app]
退出码：0 = 干净；1 = 发现违规（并打印修复方向）；2 = 参数错误。
"""

import argparse
import ast
import sys
from pathlib import Path

# 动态 import 的入口函数名（其首个字符串字面量实参按模块路径审查）
DYNAMIC_IMPORT_FUNCS = {'import_module', '__import__'}
# R3 约束的叶子层目录名
LEAF_LAYER_NAMES = ('models', 'schemas')
# R5：services 顶层共享件（跨家族共用，必须是叶子）
SHARED_SERVICE_MODULES = ('app.services.job_base', 'app.services.import_records')
SHARED_SERVICE_PACKAGES = ('app.services.adapters',)
# R5：services 下的家族包（各自拥有实现，可依赖共享件，但共享件不得反过来依赖它们）
SERVICE_FAMILY_PACKAGES = (
    'app.services.sync',
    'app.services.importer',
    'app.services.thermometer',
    'app.services.bias',
    'app.services.ai_recognizer',
)


def _matches(module: str, packages: tuple[str, ...]) -> bool:
    """模块是否等于某包或位于其下（按包边界匹配，避免 `app.services.sync_x` 误判）。"""
    return any(module == pkg or module.startswith(pkg + '.') for pkg in packages)


# R5 冻结基线（只拦新增，与 `check_css_vars.mjs` / `guard_breakpoints.py` 同款手法）：
# 既有且**已登记**的反向边，逐条说明理由与去向；新增任何其它反向边一律红灯。
# 当前为空——批次 4 已消除唯一一条（`adapters → thermometer`）。
R5_ALLOWLIST: dict = {}
# 空：#1607 批次 4 已把且慢取数（QiemanFetcher + 归一化助手 + 基类 + QIEMAN_* 常量）
# 上提到 adapters（`adapters/qieman_fetcher.py` / `adapters/fetcher_base.py`），
# `adapters → thermometer` 这条既有反向边已**消除**，冻结基线随之清空。


def _is_core_module(module: str) -> bool:
    return module == 'app.core' or module.startswith('app.core.')


def _is_services_module(module: str) -> bool:
    return module == 'app.services' or module.startswith('app.services.')


def _is_top_level_models(module: str) -> bool:
    """`app.models` / `app.models.sync_log`：顶层模型包（历史双轨，见 decisions.md 模型位置条款）。"""
    return module == 'app.models' or module.startswith('app.models.')


def _split_domain(module: str) -> tuple[str | None, str]:
    """`app.domains.<域>.<其余...>` → (域, 其余首段)；非 domains 模块返回 (None, '')。"""
    parts = module.split('.')
    if parts[:2] != ['app', 'domains'] or len(parts) < 3:
        return None, ''
    return parts[2], parts[3] if len(parts) > 3 else ''


def _is_views_module(module: str) -> bool:
    """目标是否是某域的视图层（按命名约定：域包下首段以 views 结尾）。"""
    _, tail = _split_domain(module)
    return tail.endswith('views')


def _violation(module_name: str, target_module: str) -> str | None:
    """按四条规则判定一条 import 边；命中返回规则号 + 说明，否则 None。"""
    if not module_name.startswith('app.'):
        return None

    if _is_core_module(module_name):
        if _split_domain(target_module)[0] or _is_top_level_models(target_module):
            return 'R1 core 不得依赖领域层（app.domains.* / app.models.*），需要的领域能力应由组合根注入'
        return None

    if _is_services_module(module_name):
        if _is_views_module(target_module):
            return 'R2 services 不得依赖 domains.*.views（视图是 HTTP 编排层，应在 domains 侧调用服务）'
        if _matches(module_name, SHARED_SERVICE_MODULES + SHARED_SERVICE_PACKAGES) and _matches(
            target_module, SERVICE_FAMILY_PACKAGES
        ):
            if (module_name, target_module) in R5_ALLOWLIST:
                return None
            return (
                'R5 services 顶层共享件不得反向依赖家族包（共享件必须是叶子：家族实现依赖共享件，'
                '不能反过来；否则又长成「寄生」）'
            )
        return None

    source_domain, source_tail = _split_domain(module_name)
    if source_domain and source_tail in LEAF_LAYER_NAMES and _is_services_module(target_module):
        return f'R3 domains.{source_domain}.{source_tail} 不得依赖 services（叶子层只依赖 core）'

    if source_domain and source_tail.endswith('views'):
        target_domain, _ = _split_domain(target_module)
        if target_domain and target_domain != source_domain and _is_views_module(target_module):
            return (
                f'R4 跨域不得引用对方 views（{source_domain} → {target_domain}）：'
                '共用逻辑下沉 services，或改引用对方的 models/schemas'
            )
    return None


def scan_file(path: Path, app_dir: Path, violations: list[str]) -> None:
    """扫描单个文件，命中即追加违规描述（含规则号、行号与源码原文）。"""
    try:
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - 语法错误由 ruff/CI 先行拦截
        violations.append(f'{path}: 语法错误（{exc}）—— 请先过 ruff')
        return
    except Exception as exc:  # pragma: no cover
        violations.append(f'{path}: 无法读取（{exc}）')
        return

    module_name = _module_name_of(path, app_dir)
    lines = source.splitlines()

    def _report(lineno: int, target: str) -> None:
        why = _violation(module_name, target)
        if why is None:
            return
        snippet = lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ''
        violations.append(f'{path}:{lineno}  {why}\n         源码：{snippet}')

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # `import app.domains.x` 与 `import app.domains.x as y` 都算这条边
                _report(node.lineno, alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                _report(node.lineno, node.module)
                # `from app.domains import users` 形态：把子名也当成一条边
                for alias in node.names:
                    if node.module.count('.') <= 1:
                        _report(node.lineno, f'{node.module}.{alias.name}')
        else:
            target = _dynamic_import_target(node)
            if target is not None:
                _report(node.lineno, target)


def _dynamic_import_target(node: ast.AST) -> str | None:
    """若 node 是 `import_module('app.domains...')` 形态，返回其字面量模块名。"""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else None)
    if name not in DYNAMIC_IMPORT_FUNCS or not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _module_name_of(path: Path, app_dir: Path) -> str:
    """文件路径 → 模块名（`app/domains/x/views.py` → `app.domains.x.views`）。"""
    rel = path.relative_to(app_dir.parent).with_suffix('')
    parts = list(rel.parts)
    if parts and parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def scan_app(app_dir: Path) -> list[str]:
    """扫描整个 app 目录，返回违规清单（空列表 = 干净）。"""
    violations: list[str] = []
    for py_file in sorted(app_dir.rglob('*.py')):
        scan_file(py_file, app_dir, violations)
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description='后端分层依赖方向守卫（#1607）')
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

    violations = scan_app(app_dir)
    if violations:
        print('ERROR: 发现违反分层依赖方向的 import（core ← domains ← services ← domains.views）：', file=sys.stderr)
        for violation in violations:
            print(f'  - {violation}', file=sys.stderr)
        print('\n规则与修复方向见 docs/spec/decisions.md 2026-09-19 行 / docs/spec/architecture.md §6。', file=sys.stderr)
        return 1

    print(f'OK: 分层依赖方向无违规（扫描 {len(list(app_dir.rglob("*.py")))} 个文件，R1~R5 全绿）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
