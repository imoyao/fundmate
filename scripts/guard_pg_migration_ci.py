#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI 真 Postgres 迁移验证的**接线守卫**（TD-012 / 2026-11-10 P0 批次）。

## WHY

``backend/tests/core/migrations_pg_fake.py`` 的假引擎只把 SQL 记进列表、不连库，
``backend/tests/conftest.py`` 又在 import 期把 DEV_DATABASE_URL 钉成临时 sqlite。
于是「PG 侧加了 CHECK」这件事只被验证到「DDL 文本长什么样」，证不了三件事：
PG 是否接受该 DDL、``inspect.get_check_constraints()`` 是否真回约束名、
违规写入是否被 PG 的 ``IntegrityError`` 拦下。#2469 / #2532 两次停摆都是方言问题
等生产才发现。

修法是给 CI 的 backend job 挂一个真 PG service + 串行跑真库用例。但**接线本身
会腐烂**：注释里写一句 ``services: postgres`` 就能把 ``grep -n 'postgres' ci.yml``
喂绿（#2453），step 被合并冲突弄丢也不会有人发现。本守卫把「接线在不在」
变成结构化判据，用 PyYAML 解析 job、用 AST 解析测试文件，注释一律不算数。

## 判据

1. ``ci.yml`` 的 ``jobs.backend.services.postgres.image`` 以 ``postgres:`` 开头；
2. 真 PG step 的 ``env.TEST_POSTGRES_URL`` 是 postgresql 连接串，且**不得挂到 job 级**
   （job 级会让常规 ``pytest -n auto`` 分片也收集这份用例，并发撞反射判重）；
3. ``jobs.backend.steps`` 里有一个 step 的 ``run`` 同时含真 PG 用例文件名与 ``-n 0``
   （串行：``_pg_add_check_constraints`` 的反射判重非原子，8 worker 并发会撞 ``already exists``）；
4. 真 PG 用例存在，且其 AST 里真的出现 ``create_engine`` / ``IntegrityError`` /
   ``get_check_constraints`` / ``migrate_positions_state_check_constraints`` 四个标识符；
5. 用例不得有**模块级无条件** ``pytest.skip`` —— 否则 CI 上全 skip，守卫绿、门禁假绿。

## 不判什么

不连 PG、不判 PG 语义（由 pytest 用例承担），不判 service 的健康检查参数是否最优。
本机无 Docker / psql 时用例 skip 是**设计内**行为，语义结论只以 CI 日志为准。

## 用法

    python scripts/guard_pg_migration_ci.py                 # 0 绿 / 1 红 / 2 输入不可信
    python scripts/guard_pg_migration_ci.py --self-test     # 5 态变异自检
    python scripts/guard_pg_migration_ci.py --root <repo>  # 测试用

回归网：``scripts/tests/test_guard_pg_migration_ci.py``。
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys
import tempfile

import yaml

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CI_REL = '.github/workflows/ci.yml'
PG_TEST_REL = 'backend/tests/core/test_migrations_positions_state_check_pg.py'
PG_TEST_NAME = 'test_migrations_positions_state_check_pg.py'

#: 真库用例必须真的调用这四个标识符；只写在注释/docstring 里不算（AST 收 Name/Attribute）。
REQUIRED_IDENTIFIERS = frozenset(
    {
        'create_engine',
        'IntegrityError',
        'get_check_constraints',
        'migrate_positions_state_check_constraints',
    }
)


class InputError(Exception):
    """输入不可信（ci.yml / 测试文件缺失或解析失败）⇒ exit 2，不冒充通过。"""


def backend_job(root: pathlib.Path) -> dict:
    """读 ci.yml 取 jobs.backend；YAML 1.1 会把 ``on:`` 解析成 True，但此处只取 jobs。"""
    path = root / CI_REL
    if not path.is_file():
        raise InputError(f'找不到 {CI_REL}')
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
    except yaml.YAMLError as exc:
        raise InputError(f'{CI_REL} 解析失败：{exc}') from exc
    jobs = (data or {}).get('jobs') or {}
    job = jobs.get('backend')
    if not isinstance(job, dict):
        raise InputError(f'{CI_REL} 找不到 jobs.backend')
    return job


def check(root: pathlib.Path) -> list[str]:
    """返回红灯原因列表；空列表 = 接线完整。"""
    errors: list[str] = []
    try:
        job = backend_job(root)
    except InputError as exc:
        return [f'输入不可信：{exc}']

    services = job.get('services') or {}
    pg = services.get('postgres') or {}
    image = str(pg.get('image', ''))
    if not image.startswith('postgres:'):
        errors.append(f'jobs.backend.services.postgres.image 缺失或非 postgres 镜像（实得 {image!r}）')

    if (job.get('env') or {}).get('TEST_POSTGRES_URL'):
        errors.append('TEST_POSTGRES_URL 不得挂在 job 级：常规 -n auto 分片会收集真 PG 用例并并发撞约束')

    steps = job.get('steps') or []
    pg_steps = [
        s
        for s in steps
        if isinstance(s, dict) and PG_TEST_NAME in str(s.get('run', '')) and '-n 0' in str(s.get('run', ''))
    ]
    if not pg_steps:
        errors.append(f'jobs.backend.steps 缺「{PG_TEST_NAME} + -n 0」的串行执行步骤')
    urls = [str((s.get('env') or {}).get('TEST_POSTGRES_URL', '')) for s in pg_steps]
    if not any('postgresql' in url for url in urls):
        errors.append('真 PG step 的 env.TEST_POSTGRES_URL 缺失或不是 postgresql 连接串')

    test_path = root / PG_TEST_REL
    if not test_path.is_file():
        errors.append(f'真 PG 用例不存在：{PG_TEST_REL}')
        return errors
    try:
        tree = ast.parse(test_path.read_text(encoding='utf-8'))
    except SyntaxError as exc:
        errors.append(f'{PG_TEST_REL} 语法错误：{exc}')
        return errors

    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    missing = REQUIRED_IDENTIFIERS - (names | attrs)
    if missing:
        errors.append(f'真 PG 用例缺真连接标识符 {sorted(missing)}（只写在注释里不算）')

    for node in tree.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if isinstance(func, ast.Attribute) and func.attr == 'skip':
            errors.append('真 PG 用例有模块级无条件 pytest.skip ⇒ CI 上会静默全绿')
            break
    return errors


def run(root: pathlib.Path) -> int:
    errors = check(root)
    if errors:
        for msg in errors:
            print(f'RED: {msg}')
        print(f'[guard_pg_migration_ci] {len(errors)} 项接线不成立')
        return 2 if any('输入不可信' in e for e in errors) else 1
    print('[guard_pg_migration_ci] OK：CI 真 Postgres 迁移验证接线完整且结构化')
    return 0


def self_test() -> int:
    """5 态变异自检：接线被删/被注释替换/用例被掏空/URL 挂错层级，守卫都必须红。

    变异走**结构化 dict 改写**再 dump，不依赖 ci.yml 的具体缩进文本 —— 否则
    调整 YAML 格式就会让探针悄悄失效（#2739 变异没落盘的同类坑）。
    """
    root = REPO_ROOT
    base = run(root)
    if base != 0:
        print(f'SELF-TEST FAIL: 基线必须先绿，实得 {base}')
        return 1
    failures: list[str] = []
    ci_text = (root / CI_REL).read_text(encoding='utf-8')
    test_text = (root / PG_TEST_REL).read_text(encoding='utf-8')

    def probe(name: str, mutate, *, comment_only: bool = False, gut_test: bool = False) -> None:
        data = yaml.safe_load(ci_text)
        mutate(data['jobs']['backend'])
        rendered = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        if comment_only:
            rendered += '# services: postgres（只写在注释里，不算接线）\n'
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = pathlib.Path(tmp)
            (tmp_root / '.github' / 'workflows').mkdir(parents=True)
            (tmp_root / 'backend' / 'tests' / 'core').mkdir(parents=True)
            (tmp_root / CI_REL).write_text(rendered, encoding='utf-8')
            (tmp_root / PG_TEST_REL).write_text(
                '# create_engine / IntegrityError / get_check_constraints 只写在注释里\n' if gut_test else test_text,
                encoding='utf-8',
            )
            actual = run(tmp_root)
            if actual == 0:
                failures.append(f'{name}: 变异后仍绿，守卫没咬住')

    probe('删 services.postgres', lambda job: job.pop('services', None))
    probe(
        '删 PG step',
        lambda job: job.update(steps=[s for s in job['steps'] if PG_TEST_NAME not in str(s.get('run', ''))]),
    )
    probe('注释冒充实接线', lambda job: job.pop('services', None), comment_only=True)
    probe('掏空真 PG 用例', lambda job: None, gut_test=True)

    def move_url_to_job(job):
        for step in job['steps']:
            if PG_TEST_NAME in str(step.get('run', '')):
                url = (step.pop('env', None) or {}).get('TEST_POSTGRES_URL', '')
                job['env'] = {'TEST_POSTGRES_URL': url}
                break

    probe('URL 挂回 job 级', move_url_to_job)

    if failures:
        for msg in failures:
            print(f'SELF-TEST FAIL: {msg}')
        return 1
    print('[guard_pg_migration_ci] self-test OK：5 态变异全部咬住')
    return 0


def default_root() -> pathlib.Path:
    """优先用 cwd：台账守卫以 ``cwd=<临时仓库>`` 调本脚本，变异探针须检查那份 ci.yml。

    从仓库子目录手工跑时 cwd 里没有 ci.yml，回退到脚本所在仓库根。
    """
    cwd = pathlib.Path.cwd()
    return cwd if (cwd / CI_REL).is_file() else REPO_ROOT


def main() -> int:
    ap = argparse.ArgumentParser(description='CI 真 Postgres 迁移验证接线守卫')
    ap.add_argument('--root', type=pathlib.Path, default=None)
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    return run((args.root or default_root()).resolve())


if __name__ == '__main__':
    sys.exit(main())
