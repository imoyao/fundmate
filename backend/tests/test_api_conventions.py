# -*- coding: utf-8 -*-
"""API 约定一致性测试（#1611）。

三条不变量（与 `scripts/check_api_conventions.py` 同源，脚本按路径加载，不重复实现）：

1. **尾斜杠**：除规范明文豁免（`/api/health` + 四个 `/api/temperature/*` 探市接口）外，
   所有路由定义必须以 `/` 结尾（`conventions.md` §2.6 冻结区）；
2. **静态口径 == 运行时权威**：守卫用 AST 静态解析（零依赖，pre-commit/CI 裸 `python` 可跑），
   本用例用运行时 `app.url_map` 交叉校验——**逐条必须相等**。若有人用 `add_url_rule()` 等
   非 `@<bp>.<method>` 范式注册路由，AST 会漏，本用例即红灯（这正是「静态快 + 运行时权威」的分工）；
3. **迁移期容忍**：本批补齐尾斜杠的端点带 `strict_slashes=False`，旧的无斜杠写法仍须可用
   （避免线上旧 bundle / 外部调用方在切换瞬间 404）；规范写法（带斜杠）也必须可用且不重定向。
"""

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARD_PATH = _REPO_ROOT / 'scripts' / 'check_api_conventions.py'


def _load_guard():
    spec = importlib.util.spec_from_file_location('check_api_conventions', _GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _url_map_routes(app) -> set[tuple[str, str]]:
    """运行时权威口径：(path, METHOD) 集合（排除框架自带路由）。"""
    skip = ('/static', '/openapi', '/docs', '/favicon', '/redoc')
    routes = set()
    for rule in app.url_map.iter_rules():
        path = str(rule)
        if path.startswith(skip):
            continue
        for method in rule.methods:
            if method not in ('HEAD', 'OPTIONS'):
                routes.add((path, method))
    return routes


def test_static_and_runtime_route_sets_identical(app):
    """AST 守卫的路由集合 == 运行时 url_map（逐条相等，防非范式注册漏检）。"""
    guard = _load_guard()
    ast_routes = {(p, m) for p, m, _ in guard.collect_routes()}
    runtime_routes = _url_map_routes(app)

    assert ast_routes == runtime_routes, (
        'AST 与 url_map 不一致：\n'
        f'  仅 AST 有: {sorted(ast_routes - runtime_routes)}\n'
        f'  仅 url_map 有: {sorted(runtime_routes - ast_routes)}\n'
        '（新增路由请沿用 @<bp>.<method>(\'<path>/\') 范式，或同步更新守卫解析）'
    )


def test_all_routes_have_trailing_slash_except_allowlist(app):
    """除豁免清单外，所有路由必须以 `/` 结尾（conventions.md §2.6）。"""
    guard = _load_guard()
    allowlist = guard.NO_TRAILING_SLASH_ALLOWLIST
    offenders = sorted(
        f'{m} {p}' for p, m in _url_map_routes(app) if not p.endswith('/') and p not in allowlist
    )
    assert offenders == [], '以下端点缺尾斜杠：\n  ' + '\n  '.join(offenders)


def test_trailing_slash_allowlist_entries_exist(app):
    """豁免清单不得留死条目（端点改名/删除后须同步清理）。"""
    guard = _load_guard()
    runtime_paths = {p for p, _ in _url_map_routes(app)}
    stale = sorted(p for p in guard.NO_TRAILING_SLASH_ALLOWLIST if p not in runtime_paths)
    assert stale == [], f'豁免清单里的端点已不存在：{stale}'


def test_canonical_and_legacy_paths_both_resolve(client):
    """规范写法（带斜杠）与迁移期旧写法（无斜杠）都必须可用；旧的不得 404 / 308。"""
    canonical = client.get('/api/auth/me/')
    assert canonical.status_code == 200, '规范写法（带尾斜杠）不可用'

    legacy = client.get('/api/auth/me')
    assert legacy.status_code == 200, '迁移期旧写法（无尾斜杠）被破坏：应为 200，而非 404/308'


def test_api_md_auto_section_is_in_sync():
    """api.md 的自动端点段必须与实现一致（文档漂移即红灯）。"""
    guard = _load_guard()
    problems = guard.check_api_md(guard.collect_routes(), write=False)
    assert problems == [], '文档漂移：' + '；'.join(problems) + '（跑 `python scripts/check_api_conventions.py --write`）'
