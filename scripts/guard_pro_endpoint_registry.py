#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守门：Pro 端点必须挂权益校验，权益位必须登记在 PRO_FEATURES（#2324 验收第 2 条）。

WHY（缺口是真实的，不是假想）
----------------------------
#2324 的验收清单里有一条写得很清楚：**新增 Pro 端点未登记权益位 → CI 报错**。
当时落地了两块地基：

- ``backend/app/core/entitlements.py:13`` 的 ``@require_pro_feature``；
- ``backend/app/services/entitlement_check.py:20`` 的 ``PRO_FEATURES`` 白名单。

三个 Pro 端点也确实都挂上了（``backend/app/domains/products/views.py:557 / 582 / 612``）。
但那两块地基都只在**被调用时**生效：装饰器对「未登记的 feature」抛 ``ValueError``，
管的是「写错名字」；而一个**根本没写装饰器**的新 Pro 端点不会触发任何检查——
它会安静地对未付费用户返回完整业务数据。

这正是「付费墙只在 UI 层」那个洞的复发形态（原卡证据：UI 直接调
``/api/products/pro-insight/`` 就能拿到数据）。本次补的不是权限逻辑，是**接线判据**：
漏挂装饰器，静态就能看见。

判据
----
1. ``PRO_FEATURES`` 必须可静态解析；解析不出来 ⇒ 退出码 **2**，
   **不得**退化成「没问题」（拿不到输入 ≠ 输入为空，同 CNB #171 那类假绿）。
2. 每个 ``@require_pro_feature(<常量>)`` 的 feature 必须在 ``PRO_FEATURES`` 中；
   参数不是字符串常量 ⇒ 报红（静态不可判定，fail-closed）。
3. 每个 Pro 形路由（路径第一段是 ``pro`` / ``pro-*`` / ``pro_*``）必须挂
   ``@require_pro_feature``。唯一例外是 ``PUBLIC_PRO_ROUTES`` 里**逐条登记并写明理由**
   的公开端点：当前只有 ``/pro/`` 状态位——未开通用户必须能读它，
   否则前端无从决定要不要渲染付费墙（见 ``product_pro_status.py`` 的口径）。
4. ``PUBLIC_PRO_ROUTES`` 的条目必须仍对应真实存在的 Pro 路由；路由改名 / 删除后
   条目失效 ⇒ 报红，避免白名单长成「永远豁免」的垃圾桶。

退出码
------
- 0：通过；
- 1：有违规；
- 2：输入不可信（文件缺失 / 语法错误 / ``PRO_FEATURES`` 解析不出）。

边界（有意不覆盖）
------------------
- **不判断响应里有没有 Pro 内容**：那是业务逻辑；本守卫只保证「接线在」。
- **不判断装饰器实现是否正确**：``backend/tests/domains/products/test_pro_entitlement_gate.py`` 管。
- **不扫前端**：权益态渲染由 ``frontend/src/views/product/components/proEntitlement.ts`` 决定。
- **只认 ``bp.get/post/put/delete/patch/route`` 的静态路由**；``add_url_rule`` 动态注册不在判据内
  （本仓当前没有这种写法；将来若出现，先扩判据再合并）。

用法
----
    python scripts/guard_pro_endpoint_registry.py            # 在仓库根执行（CI）
    python scripts/guard_pro_endpoint_registry.py --root .   # 显式指定根目录
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Iterable

#: 允许「不挂权益校验」的 Pro 形端点：``(仓库相对路径, 路由路径) -> 理由``。
#: **只登记必须对未开通用户可读的端点**，不是「暂时没空挂」的免责名单。
PUBLIC_PRO_ROUTES: dict[tuple[str, str], str] = {
    (
        'backend/app/domains/products/views.py',
        '/pro/',
    ): 'Pro 状态位：未开通用户也必须能读，前端据此渲染付费墙（#2324）',
}

APP_DIR = 'backend/app'
ENTITLEMENT_FILE = 'backend/app/services/entitlement_check.py'
ENTITLEMENT_NAME = 'PRO_FEATURES'

#: Flask/APIFlask 蓝图上的路由装饰器方法名。
ROUTE_DECORATORS = frozenset({'get', 'post', 'put', 'delete', 'patch', 'route'})


class InputError(Exception):
    """输入不可信：调用方必须以退出码 2 收场，而不是当成「没问题」。"""


def _parse(path: Path) -> ast.Module:
    try:
        source = path.read_text(encoding='utf-8')
    except OSError as exc:  # pragma: no cover - 仅在文件被删除时触发
        raise InputError(f'读不到 {path}: {exc}') from exc
    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise InputError(f'{path} 语法错误：{exc}') from exc


def _string_elements(node: ast.AST) -> list[str] | None:
    """从 set/list/tuple 字面量里取全部字符串元素；有非字符串元素即认为不可静态判定。"""
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        out: list[str] = []
        for element in node.elts:
            if not (isinstance(element, ast.Constant) and isinstance(element.value, str)):
                return None
            out.append(element.value)
        return out
    # PRO_FEATURES = frozenset({...}) / set([...]) 这类包装，只看第一个参数。
    if isinstance(node, ast.Call) and node.args:
        return _string_elements(node.args[0])
    return None


def extract_pro_features(tree: ast.Module) -> list[str] | None:
    """取 ``PRO_FEATURES`` 的字符串集合；取不到返回 None（调用方必须判输入不可信）。"""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == ENTITLEMENT_NAME:
                return _string_elements(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == ENTITLEMENT_NAME
        ):
            return _string_elements(node.value) if node.value is not None else None
    return None


def _route_paths(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """取函数上声明的静态路由路径（``@bp.get('/x/')`` / ``@bp.route('/x/')``）。"""
    paths: list[str] = []
    for decorator in func.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if not isinstance(decorator.func, ast.Attribute):
            continue
        if decorator.func.attr not in ROUTE_DECORATORS:
            continue
        if not decorator.args:
            continue
        first = decorator.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            paths.append(first.value)
    return paths


def _declared_features(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str | None]:
    """取 ``@require_pro_feature(...)`` 的实参；非字符串常量记成 None（不可静态判定）。"""
    features: list[str | None] = []
    for decorator in func.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if not (isinstance(decorator.func, ast.Name) and decorator.func.id == 'require_pro_feature'):
            continue
        if not decorator.args:
            features.append(None)
            continue
        first = decorator.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            features.append(first.value)
        else:
            features.append(None)
    return features


def is_pro_route(path: str) -> bool:
    """路由第一段是 ``pro`` / ``pro-*`` / ``pro_*`` 即视为 Pro 形端点。

    刻意不用「包含 pro」：``/fund-profile/`` 这类普通端点第一段是 ``fund-profile``，
    不在判据内；只有**第一段**以 ``pro`` 开头才算，避免误伤。
    """
    stripped = path.strip('/')
    if not stripped:
        return False
    first = stripped.split('/')[0]
    return first == 'pro' or first.startswith('pro-') or first.startswith('pro_')


def _iter_python_files(app_dir: Path) -> Iterable[Path]:
    return sorted(app_dir.rglob('*.py'))


def run(root: Path, public_routes: dict[tuple[str, str], str] | None = None) -> int:
    """扫一遍并打印结论。返回值即进程退出码。"""
    allowed = PUBLIC_PRO_ROUTES if public_routes is None else public_routes
    app_dir = root / APP_DIR
    entitlement_path = root / ENTITLEMENT_FILE

    if not app_dir.is_dir():
        raise InputError(f'找不到 {app_dir}（不在仓库根执行？）')
    if not entitlement_path.is_file():
        raise InputError(f'找不到 {entitlement_path}')

    features = extract_pro_features(_parse(entitlement_path))
    if features is None:
        raise InputError(
            f'{ENTITLEMENT_FILE} 里的 {ENTITLEMENT_NAME} 不是可静态解析的字符串集合'
            '（拒绝在「读不懂」时给出「通过」）'
        )
    known = set(features)

    findings: list[str] = []
    checked_endpoints = 0
    seen_public: set[tuple[str, str]] = set()

    for path in _iter_python_files(app_dir):
        relative = path.relative_to(root).as_posix()
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            declared = _declared_features(node)
            routes = _route_paths(node)
            if not declared and not routes:
                continue

            for feature in declared:
                if feature is None:
                    findings.append(
                        f'{relative}:{node.lineno} {node.name}：'
                        '@require_pro_feature 的实参不是字符串常量，静态无法判定（fail-closed）'
                    )
                elif feature not in known:
                    findings.append(
                        f'{relative}:{node.lineno} {node.name}：'
                        f"feature '{feature}' 未登记在 {ENTITLEMENT_NAME}——"
                        '先登记权益位，再挂装饰器'
                    )

            for route in routes:
                if not is_pro_route(route):
                    continue
                checked_endpoints += 1
                key = (relative, route)
                if declared:
                    continue
                if key in allowed:
                    seen_public.add(key)
                    continue
                findings.append(
                    f'{relative}:{node.lineno} {node.name}：'
                    f"Pro 端点 '{route}' 没有 @require_pro_feature——"
                    '未付费用户可直接取到数据；确属公开端点请登记 PUBLIC_PRO_ROUTES 并写明理由'
                )

    for key in sorted(set(allowed) - seen_public):
        findings.append(
            f'PUBLIC_PRO_ROUTES 条目已失效：{key[0]} {key[1]} 不再对应「未挂装饰器的 Pro 路由」'
            '——路由改名/删除后请删掉该条目，别让白名单变成永久豁免'
        )

    if findings:
        print(f'❌ Pro 端点权益接线不通过（{len(findings)} 处）：', file=sys.stderr)
        for item in findings:
            print(f'  - {item}', file=sys.stderr)
        return 1

    print(
        f'✅ Pro 端点权益接线通过：{checked_endpoints} 个 Pro 形端点、'
        f'{len(known)} 个已登记权益位、{len(seen_public)} 个公开端点白名单条目'
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK，直接 print 中文/符号会 UnicodeEncodeError 崩掉——
    # 守门在本地跑崩 = 守门失效。统一把输出流切到 UTF-8（同 guard_job_schedule_coverage.py）。
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is not None:
            try:
                reconfigure(encoding='utf-8')
            except (AttributeError, ValueError, OSError):
                pass

    parser = argparse.ArgumentParser(description='Pro 端点权益接线守门（#2324）')
    parser.add_argument(
        '--root',
        default=None,
        help='仓库根目录，默认为本脚本的上一级（scripts/ 的父目录）',
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    try:
        return run(root)
    except InputError as exc:
        print(f'❌ 输入不可信：{exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
