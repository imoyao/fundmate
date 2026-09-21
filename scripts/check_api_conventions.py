#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：API 约定一致性 —— 端点尾斜杠 + api.md 覆盖率（#1611）。

背景（issue #1611）
-------------------
`conventions.md` §2.6（冻结区）规定「所有 API 端点强制尾部斜杠，杜绝 308 重定向导致的前端异常」，
但实测 131 个路由中 **18 个无尾斜杠**；`docs/spec/api.md` 自称「随代码演进的事实标准」却只列
30/131 个端点。规范无守卫必然漂移，故本脚本一次盯两件事：

1. **尾斜杠**：路由定义必须以 `/` 结尾；**豁免清单**见 `NO_TRAILING_SLASH_ALLOWLIST`
   （`/api/health` 运维探活 + `/api/temperature/{overview,history,multi,crowding-history}` 探市接口，
   前端按无斜杠调用且 `AGENTS.md` 已声明）；
2. **api.md 覆盖率**：`docs/spec/api.md` 的自动段（`<!-- AUTO-ENDPOINTS:START -->` …
   `<!-- AUTO-ENDPOINTS:END -->`）必须与真实路由**逐条一致**，漂移即红灯。

为什么用 AST 而不是 `app.url_map`（权威口径为何反而不用）
--------------------------------------------------------
`url_map` 需要 import 整个 app（DB / akshare 等依赖齐备 + `create_app()` 的 `init_db()` 副作用），
而本脚本要同时跑在 **pre-commit（隔离环境，无项目依赖）** 与 **CI 的 backend job（裸 `python`）**——
首版用 `app.url_map` 时在这两处都直接 `ModuleNotFoundError: loguru`。改为 AST 静态解析后零依赖、秒级。
**代价与补偿**：AST 只认「模块级 `APIBlueprint(...)` 赋值 + `@<bp>.<method>('<rule>')` 装饰器」这一
既定范式（全仓 24 个蓝图、131 条路由当前**全部**符合）；一旦有人用 `add_url_rule()` 等非范式注册，
AST 会漏——故 `backend/tests/test_api_conventions.py` 用**运行时 `url_map`** 做交叉校验
（pytest 环境依赖齐备），两侧必须逐条相等。规范没变、口径没变，只是把「静态可跑」与「运行时权威」
分开到两个入口。

用法
----
    python scripts/check_api_conventions.py            # 只读校验（CI / pre-commit），退出码 0/1
    python scripts/check_api_conventions.py --write    # 重新生成 api.md 自动段（幂等）
退出码：0 = 干净；1 = 违规；2 = 参数错误。
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOMAINS_DIR = REPO_ROOT / 'backend' / 'app' / 'domains'
API_MD = REPO_ROOT / 'docs' / 'spec' / 'api.md'
MARKER_START = '<!-- AUTO-ENDPOINTS:START（由 scripts/check_api_conventions.py --write 生成，勿手改） -->'
MARKER_END = '<!-- AUTO-ENDPOINTS:END -->'

#: 允许无尾斜杠的端点（规范明文例外；新增必须先在 conventions.md §2.6 登记）
NO_TRAILING_SLASH_ALLOWLIST = {
    '/api/health': '运维探活端点（探活工具普遍按 /health 调用，不纳入尾斜杠规范）',
    '/api/temperature/overview': '探市免登录接口，前端按无斜杠调用（AGENTS.md 已声明例外）',
    '/api/temperature/history': '同上',
    '/api/temperature/multi': '同上',
    '/api/temperature/crowding-history': '同上（与上述三个探市接口同族）',
}

HTTP_METHODS = ('get', 'post', 'put', 'patch', 'delete')


def _blueprint_prefixes(tree: ast.Module) -> dict[str, str]:
    """收集模块级 `xx_bp = APIBlueprint('name', __name__, url_prefix='/api/xx')` 的 var → 前缀。"""
    prefixes: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        func = value.func
        if not (isinstance(func, ast.Name) and func.id == 'APIBlueprint'):
            continue
        prefix = None
        for kw in value.keywords:
            if kw.arg == 'url_prefix' and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                prefix = kw.value.value
        if prefix is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = prefix
    return prefixes


def _routes_in_file(path: Path) -> list[tuple[str, str, str]]:
    """解析单个 views 文件，返回 (path, METHOD, 函数名) 列表。"""
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    prefixes = _blueprint_prefixes(tree)
    routes: list[tuple[str, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
                continue
            bp_var, method = func.value.id, func.attr
            if bp_var not in prefixes:
                continue
            if not dec.args or not isinstance(dec.args[0], ast.Constant) or not isinstance(dec.args[0].value, str):
                continue
            rule = dec.args[0].value
            prefix = prefixes[bp_var].rstrip('/')
            full_path = (prefix + rule) if rule.startswith('/') else (prefix + '/' + rule)
            if method in HTTP_METHODS:
                routes.append((full_path, method.upper(), node.name))
            elif method == 'route':
                for kw in dec.keywords:
                    if kw.arg != 'methods' or not isinstance(kw.value, (ast.List, ast.Tuple)):
                        continue
                    for elt in kw.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            if elt.value.upper() not in ('HEAD', 'OPTIONS'):
                                routes.append((full_path, elt.value.upper(), node.name))
    return routes


def collect_routes() -> list[tuple[str, str, str]]:
    """AST 静态收集全部路由（按 path, methods, 函数名 排序，保证生成内容稳定）。"""
    routes: list[tuple[str, str, str]] = []
    for path in sorted(DOMAINS_DIR.rglob('*.py')):
        routes.extend(_routes_in_file(path))
    routes.sort(key=lambda r: (r[0], r[1], r[2]))
    return routes


def render_auto_section(routes: list[tuple[str, str, str]]) -> str:
    """渲染 api.md 的自动端点清单段（守卫与 --write 共用，保证两侧逐字一致）。"""
    lines = [
        MARKER_START,
        '',
        f'全量端点清单（共 **{len(routes)}** 条）：由 `scripts/check_api_conventions.py --write` 从',
        '`backend/app/domains/**/views.py` 的 `@<bp>.<method>(...)` 装饰器静态生成，**禁止手改**——',
        '改路由后重跑该命令即可；CI 守卫会校验本段与实现逐条一致（不一致即红灯）。',
        '',
        '| 方法 | 路径 | 处理函数 |',
        '|---|---|---|',
    ]
    for route_path, method, func_name in routes:
        lines.append(f'| {method} | `{route_path}` | `{func_name}` |')
    lines += ['', MARKER_END]
    return '\n'.join(lines)


def check_trailing_slash(routes: list[tuple[str, str, str]]) -> list[str]:
    """返回无尾斜杠且不在豁免清单内的端点（违规）。"""
    bad = []
    for route_path, method, func_name in routes:
        if route_path.endswith('/') or route_path in NO_TRAILING_SLASH_ALLOWLIST:
            continue
        bad.append(f'  {method:<7} {route_path:<44} {func_name}')
    return bad


def check_api_md(routes: list[tuple[str, str, str]], *, write: bool) -> list[str]:
    """校验/重建 api.md 的自动段；返回违规描述（write 模式下为空）。"""
    expected = render_auto_section(routes)
    text = API_MD.read_text(encoding='utf-8')

    if write:
        if MARKER_START in text and MARKER_END in text:
            head, rest = text.split(MARKER_START, 1)
            _, tail = rest.split(MARKER_END, 1)
            API_MD.write_text(head + expected + tail, encoding='utf-8')
        else:
            suffix = '' if text.endswith('\n') else '\n'
            API_MD.write_text(text + suffix + '\n' + expected + '\n', encoding='utf-8')
        print(f'OK: 已重建 api.md 自动段（{len(routes)} 条端点）')
        return []

    if MARKER_START not in text or MARKER_END not in text:
        return ['  docs/spec/api.md 缺少自动生成段标记（先跑 --write 初始化）']
    actual_body = text.split(MARKER_START, 1)[1].split(MARKER_END, 1)[0]
    expected_body = expected.split(MARKER_START, 1)[1].split(MARKER_END, 1)[0]
    if actual_body != expected_body:
        return ['  docs/spec/api.md 的自动段与实现不一致（改路由后请重跑 --write）']
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description='API 约定守卫：尾斜杠 + api.md 覆盖率（#1611）')
    parser.add_argument('--write', action='store_true', help='重新生成 api.md 自动段（幂等）')
    args = parser.parse_args()

    if not DOMAINS_DIR.is_dir() or not API_MD.exists():
        print(f'ERROR: 缺少 {DOMAINS_DIR} 或 {API_MD}', file=sys.stderr)
        return 2

    routes = collect_routes()
    if args.write:
        check_api_md(routes, write=True)
        return 0

    problems: list[str] = []
    bad_slash = check_trailing_slash(routes)
    if bad_slash:
        problems.append('以下端点缺尾斜杠且不在豁免清单（conventions.md §2.6）：')
        problems.extend(bad_slash)
    problems.extend(check_api_md(routes, write=False))

    if problems:
        print('FAIL: API 约定不一致：')
        for line in problems:
            print(line)
        print('\n修复：给路由补尾斜杠（前端调用同步），再 python scripts/check_api_conventions.py --write')
        return 1

    print(f'OK: API 约定一致（{len(routes)} 个路由尾斜杠合规；api.md 自动段与实现逐条一致）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
