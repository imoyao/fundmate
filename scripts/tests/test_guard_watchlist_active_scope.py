#!/usr/bin/env python3
"""回归网：``scripts/guard_watchlist_active_scope.py``（023887 收敛的机器化护栏）。

覆盖（守卫绿 ≠ 守卫有效，故大半是用例是**变异探针**）：
1.  真实仓库通过（守卫上线当天必须对现有代码绿）；
2.  **真实代码回退探针**：把某处 ``active_holdings()`` 包装拆掉 ⇒ 红；
3.  裸 ``'active'`` 字面量比较 ⇒ 红；``OwnershipStatus.ACTIVE.value`` 写法 ⇒ 绿；
4.  白名单外新增 ``query(Position...)`` / ``select(Position...)`` ⇒ 红；包装后 ⇒ 绿；
5.  **白名单陈旧** ⇒ 红（代码收敛了却留着白名单，与迁移守卫同规）；
6.  统一入口被掏空 / 被改名 ⇒ 红 / 退出码 2；
7.  import 接线被删 ⇒ 红；新增 watchlist 模块未登记 ⇒ 红；
8.  文件缺失 / 语法错误 ⇒ 退出码 2（不得降级成「通过」）。

跑法：``python scripts/tests/test_guard_watchlist_active_scope.py``
或 ``python -m unittest scripts.tests.test_guard_watchlist_active_scope``。
"""

from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest
from collections.abc import Callable

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO / 'scripts' / 'guard_watchlist_active_scope.py'


def _load_guard():
    spec = importlib.util.spec_from_file_location('guard_watchlist_active_scope', GUARD)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


Patch = Callable[[str, bytes], bytes]
FILES = (*_load_guard().TARGETS, _load_guard().SCOPE_REL)


def _build_root(tmp: pathlib.Path, patch: Patch | None = None, extra: dict[str, bytes] | None = None) -> pathlib.Path:
    """把守卫依赖的 3 个真实文件按字节复制进临时 root（保留各自 CRLF/LF）。"""
    for rel in FILES:
        dst = tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        data = (REPO / rel).read_bytes()
        dst.write_bytes(patch(rel, data) if patch else data)
    for name, data in (extra or {}).items():
        dst = tmp / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    return tmp


def _replace(rel: str, data: bytes, old: bytes, new: bytes) -> bytes:
    """单行字节替换，带命中数断言——探针没命中就等于没测到，必须当场失败。"""
    assert data.count(old) >= 1, f'{rel} 里找不到探针锚点 {old!r}（守卫或源码已变，探针需同步）'
    return data.replace(old, new, 1)


class RealRepoTest(unittest.TestCase):
    def test_repository_passes(self):
        self.assertEqual(_load_guard().run(REPO), 0)

    def test_all_allowlist_entries_are_hit(self):
        """白名单 5 条必须条条在真实代码里命中，否则 R3 会误报陈旧。"""
        module = _load_guard()
        used: set[tuple[str, str, str, str]] = set()
        for rel in module.TARGETS:
            _findings, keys = module.check_query_scope((REPO / rel).read_text(encoding='utf-8'), rel)
            used |= keys
        self.assertEqual(used, set(module.ALLOWLIST), '白名单与真实代码对不上')


class MutationProbeTest(unittest.TestCase):
    """拿**真实代码**做回退/绕过探针，证明守卫不是假绿。"""

    def setUp(self):
        self.module = _load_guard()

    def _run_patched(self, patch: Patch, extra: dict[str, bytes] | None = None) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            root = _build_root(pathlib.Path(tmp), patch, extra)
            return self.module.run(root)

    def test_wrapper_removed_turns_red(self):
        """最关键的一条：复现「改了一半」——拆掉一处包装，守卫必须红。"""
        def patch(rel, data):
            if rel.endswith('watchlist_service.py'):
                return _replace(
                    rel, data,
                    b'pos_q = active_holdings(db.query(Position.symbol)).filter(Position.family_id == family_id)',
                    b'pos_q = db.query(Position.symbol).filter(Position.family_id == family_id)',
                )
            return data

        self.assertEqual(self._run_patched(patch), 1)

    def test_bare_literal_reintroduced_turns_red(self):
        def patch(rel, data):
            if rel.endswith('watchlist_service.py'):
                return _replace(
                    rel, data,
                    b'pos_q = active_holdings(db.query(Position.symbol)).filter(Position.family_id == family_id)',
                    b"pos_q = db.query(Position.symbol).filter(\n"
                    b"        Position.family_id == family_id,\n"
                    b"        Position.ownership_status == 'active',\n"
                    b"    )",
                )
            return data

        self.assertEqual(self._run_patched(patch), 1)

    def test_allowlist_stale_turns_red(self):
        """白名单里的 has_position 查询被改写后，条目必须报陈旧。"""
        def patch(rel, data):
            if rel.endswith('watchlist_service.py'):
                return _replace(
                    rel, data,
                    b'has_position = db.query(Position).filter(',
                    b'has_position = db.query(WatchlistItem).filter(',
                )
            return data

        self.assertEqual(self._run_patched(patch), 1)

    def test_import_removed_turns_red(self):
        def patch(rel, data):
            if rel.endswith('watchlist_service.py'):
                return _replace(
                    rel, data,
                    b'from app.services.position_scope import active_holdings\n', b'',
                )
            return data

        self.assertEqual(self._run_patched(patch), 1)

    def test_scope_neutered_turns_red(self):
        """统一入口还在、但不再过滤 ⇒ 守卫必须红（否则全绿而语义已变）。"""
        def patch(rel, data):
            if rel.endswith('position_scope.py'):
                return _replace(
                    rel, data,
                    b'return query.filter(Position.ownership_status == OwnershipStatus.ACTIVE.value)',
                    b'return query',
                )
            return data

        self.assertEqual(self._run_patched(patch), 1)

    def test_new_watchlist_module_unregistered_turns_red(self):
        extra = {'backend/app/services/watchlist_extra.py': b'# new module\n'}
        self.assertEqual(self._run_patched(lambda _rel, data: data, extra), 1)

    def test_syntax_error_is_input_error(self):
        def patch(rel, data):
            if rel.endswith('watchlist_service.py'):
                return data + b'\ndef broken(:\n'
            return data

        with tempfile.TemporaryDirectory() as tmp:
            root = _build_root(pathlib.Path(tmp), patch)
            with self.assertRaises(self.module.InputError):
                self.module.run(root)

    def test_scope_func_renamed_is_input_error(self):
        def patch(rel, data):
            if rel.endswith('position_scope.py'):
                return _replace(
                    rel, data,
                    b'def active_holdings(query: Query) -> Query:',
                    b'def some_other_scope(query: Query) -> Query:',
                )
            return data

        with tempfile.TemporaryDirectory() as tmp:
            root = _build_root(pathlib.Path(tmp), patch)
            with self.assertRaises(self.module.InputError):
                self.module.run(root)

    def test_missing_file_is_input_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            with self.assertRaises(self.module.InputError):
                self.module.run(root)

    def test_main_returns_two_on_missing_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.module.main(['--root', tmp]), 2)

    def test_main_returns_one_on_violation(self):
        def patch(rel, data):
            if rel.endswith('watchlist_service.py'):
                return _replace(
                    rel, data,
                    b'pos_q = active_holdings(db.query(Position.symbol)).filter(Position.family_id == family_id)',
                    b'pos_q = db.query(Position.symbol).filter(Position.family_id == family_id)',
                )
            return data

        with tempfile.TemporaryDirectory() as tmp:
            _build_root(pathlib.Path(tmp), patch)
            self.assertEqual(self.module.main(['--root', tmp]), 1)


class SyntheticSourceTest(unittest.TestCase):
    """合成源码：判据边界（不能只认一种拼法，也不能放过等价写法）。"""

    def setUp(self):
        self.module = _load_guard()

    def test_bare_literal_comparison_turns_red(self):
        src = "q = db.query(Position).filter(Position.ownership_status == 'active')\n"
        self.assertTrue(self.module.check_ownership_literal(src, 'x.py'))

    def test_not_equal_literal_also_turns_red(self):
        src = "q = db.query(Position).filter(Position.ownership_status != 'shadow')\n"
        self.assertTrue(self.module.check_ownership_literal(src, 'x.py'))

    def test_enum_spelling_passes(self):
        src = 'q = db.query(Position).filter(Position.ownership_status == OwnershipStatus.ACTIVE.value)\n'
        self.assertEqual(self.module.check_ownership_literal(src, 'x.py'), [])

    def test_unrelated_string_literal_passes(self):
        src = "q = db.query(Position).filter(Position.symbol == 'active')\n"
        self.assertEqual(self.module.check_ownership_literal(src, 'x.py'), [])

    def test_unwrapped_query_turns_red(self):
        src = (
            'def f(db, family_id):\n'
            '    rows = db.query(Position.symbol).filter(Position.family_id == family_id).all()\n'
        )
        findings, _used = self.module.check_query_scope(src, 'backend/app/services/watchlist_extra.py')
        self.assertTrue(findings, '白名单外新增 query(Position...) 必须红')

    def test_unwrapped_select_turns_red(self):
        """2.x select() 写法同样要拦，否则新代码能用 select 绕开守卫。"""
        src = (
            'def f(db, family_id):\n'
            '    rows = select(Position.symbol).where(Position.family_id == family_id)\n'
        )
        findings, _used = self.module.check_query_scope(src, 'backend/app/services/watchlist_extra.py')
        self.assertTrue(findings, '白名单外新增 select(Position...) 必须红')

    def test_wrapped_query_passes(self):
        src = (
            'def f(db, family_id):\n'
            '    rows = active_holdings(db.query(Position.symbol)).filter(Position.family_id == family_id).all()\n'
        )
        findings, _used = self.module.check_query_scope(src, 'backend/app/services/watchlist_extra.py')
        self.assertEqual(findings, [])

    def test_non_position_query_is_out_of_scope(self):
        src = (
            'def f(db, family_id):\n'
            '    rows = db.query(WatchlistItem.symbol).filter(WatchlistItem.family_id == family_id).all()\n'
        )
        findings, _used = self.module.check_query_scope(src, 'backend/app/services/watchlist_extra.py')
        self.assertEqual(findings, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
