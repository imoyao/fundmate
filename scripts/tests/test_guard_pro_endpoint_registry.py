#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归网：``scripts/guard_pro_endpoint_registry.py``（#2324 验收第 2 条）。

覆盖：
1. 真实仓库通过（守卫上线当天必须对现有代码绿）；
2. 未登记 feature ⇒ 红（写错权益位名）；
3. Pro 形路由没挂装饰器 ⇒ 红（本卡要防的**真正**形态）；
4. 普通路由没挂装饰器 ⇒ 绿（别把「所有端点」都要求挂权益）；
5. 白名单里的公开端点（``/pro/``）⇒ 绿；
6. 白名单条目失效 ⇒ 红（路由改名后不许留永久豁免）；
7. ``PRO_FEATURES`` 文件缺失 / 不可解析 ⇒ **退出码 2**（不得退化成「通过」）；
8. 装饰器实参不是字符串常量 ⇒ 红（静态不可判定，fail-closed）；
9. **真实代码探针**：拿仓库里真实的 ``views.py`` 喂守卫，删掉其中一条
   ``@require_pro_feature`` 后必须转红——守卫绿 ≠ 守卫有效。

跑法：``python scripts/tests/test_guard_pro_endpoint_registry.py``
或 ``python -m unittest scripts.tests.test_guard_pro_endpoint_registry``。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import pathlib
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO / 'scripts' / 'guard_pro_endpoint_registry.py'

VIEWS_REL = 'backend/app/domains/products/views.py'
ENTITLEMENT_REL = 'backend/app/services/entitlement_check.py'

VIEWS_HEAD = """# -*- coding: utf-8 -*-
from flask import Blueprint

bp = Blueprint('products', __name__)


@bp.get('/pro/')
def pro_status():
    return {}


"""


def _load_guard():
    spec = importlib.util.spec_from_file_location('guard_pro_endpoint_registry', GUARD)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _build_tree(
    root: pathlib.Path,
    body: str,
    features: tuple[str, ...] = ('pro-insight', 'pro-risk', 'pro-allocation'),
    entitlement_source: str | None = None,
    include_views: bool = True,
) -> None:
    entitlement = root / ENTITLEMENT_REL
    entitlement.parent.mkdir(parents=True, exist_ok=True)
    if entitlement_source is None:
        members = ', '.join(repr(name) for name in features)
        entitlement_source = f'PRO_FEATURES = frozenset({{{members}}})\n'
    entitlement.write_text(entitlement_source, encoding='utf-8')

    if not include_views:
        return
    views = root / VIEWS_REL
    views.parent.mkdir(parents=True, exist_ok=True)
    views.write_text(VIEWS_HEAD + body, encoding='utf-8')


def _run(root: pathlib.Path) -> tuple[int, str, str]:
    module = _load_guard()
    out, err = io.StringIO(), io.StringIO()
    # 走 CLI 入口：`InputError -> 退出码 2` 的处理就在 main() 里，
    # 直接调 run() 会把「输入不可信」变成未捕获异常，测出来的行为不是真实行为。
    argv = ['--root', str(root)]
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = module.main(argv)
    return code, out.getvalue(), err.getvalue()


class GuardRegistrationTest(unittest.TestCase):
    def test_real_repo_passes(self) -> None:
        code, out, err = _run(REPO)
        self.assertEqual(code, 0, msg=f'stdout={out}\nstderr={err}')
        self.assertIn('Pro 端点权益接线通过', out)

    def test_unregistered_feature_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _build_tree(
                root,
                "@bp.get('/pro-new/')\n"
                "@require_pro_feature('pro-new')\n"
                'def pro_new():\n'
                '    return {}\n',
            )
            code, _, err = _run(root)
        self.assertEqual(code, 1)
        self.assertIn('未登记', err)

    def test_pro_route_without_decorator_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _build_tree(
                root,
                "@bp.get('/pro-new/')\n"
                'def pro_new():\n'
                '    return {}\n',
            )
            code, _, err = _run(root)
        self.assertEqual(code, 1)
        self.assertIn('/pro-new/', err)
        self.assertIn('没有 @require_pro_feature', err)

    def test_non_pro_route_without_decorator_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _build_tree(
                root,
                "@bp.get('/fund-profile/')\n"
                'def fund_profile():\n'
                '    return {}\n',
            )
            code, out, err = _run(root)
        self.assertEqual(code, 0, msg=f'stdout={out}\nstderr={err}')

    def test_public_allowlist_entry_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _build_tree(root, '')
            code, out, err = _run(root)
        self.assertEqual(code, 0, msg=f'stdout={out}\nstderr={err}')

    def test_stale_allowlist_entry_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            # 不建 /pro/ 路由 ⇒ 默认白名单条目失效。
            _build_tree(root, '', include_views=True)
            (root / VIEWS_REL).write_text(
                "from flask import Blueprint\n\nbp = Blueprint('products', __name__)\n",
                encoding='utf-8',
            )
            code, _, err = _run(root)
        self.assertEqual(code, 1)
        self.assertIn('已失效', err)

    def test_missing_entitlement_file_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / VIEWS_REL).parent.mkdir(parents=True, exist_ok=True)
            (root / 'backend/app/services').mkdir(parents=True, exist_ok=True)
            code, _, err = _run(root)
        self.assertEqual(code, 2)
        self.assertIn('输入不可信', err)

    def test_unparseable_pro_features_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _build_tree(
                root,
                "@bp.get('/pro-insight/')\n"
                "@require_pro_feature('pro-insight')\n"
                'def pro_insight():\n'
                '    return {}\n',
                entitlement_source='PRO_FEATURES = _build_from_db()\n',
            )
            code, _, err = _run(root)
        self.assertEqual(code, 2)
        self.assertIn('不可信', err)

    def test_dynamic_feature_arg_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _build_tree(
                root,
                "FEATURE = 'pro-insight'\n\n\n"
                "@bp.get('/pro-insight/')\n"
                '@require_pro_feature(FEATURE)\n'
                'def pro_insight():\n'
                '    return {}\n',
            )
            code, _, err = _run(root)
        self.assertEqual(code, 1)
        self.assertIn('静态无法判定', err)


class RealCodeMutationProbeTest(unittest.TestCase):
    """拿**真实代码**喂守卫：删掉装饰器后必须转红（守卫绿 ≠ 守卫有效）。"""

    def _copy_real_files(self, root: pathlib.Path) -> pathlib.Path:
        for relative in (ENTITLEMENT_REL, VIEWS_REL):
            source = REPO / relative
            if not source.is_file():
                self.skipTest(f'缺真实文件：{relative}')
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding='utf-8'), encoding='utf-8')
        return root / VIEWS_REL

    def test_real_views_pass_then_fail_after_removing_decorator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            views = self._copy_real_files(root)

            code, out, err = _run(root)
            self.assertEqual(code, 0, msg=f'真实代码本应通过：stdout={out}\nstderr={err}')

            original = views.read_text(encoding='utf-8')
            mutated = original.replace("@require_pro_feature('pro-risk')\n", '', 1)
            self.assertNotEqual(original, mutated, '探针没找到可删的装饰器，说明真实代码变了')
            views.write_text(mutated, encoding='utf-8')

            code, _, err = _run(root)
            self.assertEqual(code, 1, msg=f'删掉装饰器后守卫仍绿：{err}')
            self.assertIn('/pro-risk/', err)


if __name__ == '__main__':
    unittest.main(verbosity=2)
