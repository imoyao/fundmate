#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归网：changelog 分类徽章（#1996 验收：categories 徽章 New/Improved/Fixed）。

覆盖：
1. Conventional Commits type 的解析（``feat(x): y`` / ``fix: y`` / 合并提交 / 非规范格式）；
2. type → 徽章映射（feat→new、fix→fixed、perf/refactor/style→improved；
   ``docs`` / ``chore`` / ``test`` 等用户不可感知的 type **不进**徽章）；
3. 输出只含白名单取值，且顺序固定（new → improved → fixed）；
4. 行为级：``create_changelog_entry`` 把徽章写进 **categories 与 published_categories 两列**
   （FeedLog 列表接口读的是 published_categories，只写一列就看不到徽章）；
5. 行为级：``release_categories`` 从「上一版 → 本版」的 commit 推导徽章；
   没有基线 / API 失败时返回空列表（**不猜**、不阻断发版）。

反向验证：把 ``TYPE_TO_CATEGORY`` 改回空字典，或把 ``categories_from_messages`` 改成
恒返回 ``['new']``，本文件的用例会立刻转红。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import pathlib
import sys
import types
import unittest
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from feedlog_test_support import FakeConn, load_bridge_module  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
CATEGORIES_MODULE = REPO / 'scripts' / 'bridge' / 'changelog_categories.py'


@contextlib.contextmanager
def quiet():
    """吞掉被测函数里的 print。

    桥接脚本会打 emoji（☂️ / 🏷️），在 Windows GBK 控制台上直接崩——
    那是**打印**的问题，不是逻辑的问题；测试里把输出收走即可。
    """
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


def _load_categories_module():
    spec = importlib.util.spec_from_file_location('changelog_categories_under_test', CATEGORIES_MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ParseCommitTypeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_categories_module()

    def test_parses_type_with_scope(self) -> None:
        self.assertEqual(self.mod.parse_commit_type('feat(pro): 端点权益校验'), 'feat')

    def test_parses_type_without_scope(self) -> None:
        self.assertEqual(self.mod.parse_commit_type('fix: 修复 500'), 'fix')

    def test_parses_breaking_marker(self) -> None:
        self.assertEqual(self.mod.parse_commit_type('feat(api)!: 破坏性变更'), 'feat')

    def test_ignores_merge_commit(self) -> None:
        self.assertIsNone(self.mod.parse_commit_type('Merge pull request #12 from x/y'))

    def test_ignores_freeform_message(self) -> None:
        self.assertIsNone(self.mod.parse_commit_type('随手改一行'))

    def test_ignores_empty(self) -> None:
        self.assertIsNone(self.mod.parse_commit_type(''))

    def test_only_first_line_matters(self) -> None:
        self.assertEqual(
            self.mod.parse_commit_type('fix: 标题\n\n正文里出现 feat: 也不算数'),
            'fix',
        )


class CategoriesFromMessagesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_categories_module()

    def test_maps_feat_and_fix(self) -> None:
        result = self.mod.categories_from_messages(['feat(a): 新功能', 'fix: 修 bug'])
        self.assertEqual(result, ['new', 'fixed'])

    def test_maps_refactor_to_improved(self) -> None:
        result = self.mod.categories_from_messages(['refactor: 重构', 'perf: 提速'])
        self.assertEqual(result, ['improved'])

    def test_ignores_non_user_visible_types(self) -> None:
        result = self.mod.categories_from_messages(['docs: 写文档', 'chore: 清理', 'test: 补测试'])
        self.assertEqual(result, [])

    def test_deduplicates_and_keeps_fixed_order(self) -> None:
        result = self.mod.categories_from_messages(
            ['fix: a', 'feat: b', 'fix: c', 'perf: d'],
        )
        self.assertEqual(result, ['new', 'improved', 'fixed'])

    def test_output_only_contains_whitelisted_values(self) -> None:
        result = self.mod.categories_from_messages(['feat: a', 'fix: b', 'docs: c'])
        for value in result:
            self.assertIn(value, self.mod.CATEGORY_VALUES)

    def test_empty_input(self) -> None:
        self.assertEqual(self.mod.categories_from_messages([]), [])


class CreateChangelogEntryCategoriesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = load_bridge_module()

    def test_writes_categories_to_both_columns(self) -> None:
        conn = FakeConn()
        self.bridge.create_changelog_entry(
            conn,
            'org-1',
            'v0.2.0',
            '说明',
            '2026-10-20T00:00:00Z',
            stable_key='v0.2.0',
            categories=['new', 'fixed'],
        )

        inserts = conn.statements('INSERT')
        self.assertEqual(len(inserts), 1)
        params = inserts[0][1]
        # categories 与 published_categories 两列都写（列表接口读的是后者）
        self.assertIn('["new", "fixed"]', params)
        self.assertEqual(params.count('["new", "fixed"]'), 2)

    def test_defaults_to_empty_array(self) -> None:
        conn = FakeConn()
        self.bridge.create_changelog_entry(conn, 'org-1', 'v0.3.0', '说明', '2026-10-20T00:00:00Z')
        inserts = conn.statements('INSERT')
        self.assertIn('[]', inserts[0][1])

    def test_drops_unknown_category_values(self) -> None:
        conn = FakeConn()
        self.bridge.create_changelog_entry(
            conn,
            'org-1',
            'v0.4.0',
            '说明',
            '2026-10-20T00:00:00Z',
            categories=['new', '不存在的分类'],
        )
        inserts = conn.statements('INSERT')
        self.assertIn('["new"]', inserts[0][1])
        self.assertNotIn('不存在的分类', inserts[0][1])

    def test_update_path_also_writes_categories(self) -> None:
        conn = FakeConn()
        first = self.bridge.create_changelog_entry(
            conn, 'org-1', 'v0.5.0', '说明', '2026-10-20T00:00:00Z', stable_key='v0.5.0'
        )
        conn.existing = {'id': first}
        self.bridge.create_changelog_entry(
            conn,
            'org-1',
            'v0.5.0',
            '改过的说明',
            '2026-10-20T01:00:00Z',
            stable_key='v0.5.0',
            categories=['improved'],
        )
        updates = conn.statements('UPDATE')
        self.assertEqual(len(updates), 1)
        self.assertIn('["improved"]', updates[0][1])


class _FakeCommit:
    def __init__(self, message: str):
        self.commit = types.SimpleNamespace(message=message)


class _FakeComparison:
    def __init__(self, commits):
        self.commits = commits


class _FakeRelease:
    def __init__(self, tag_name: str, created_at: datetime | None):
        self.tag_name = tag_name
        self.created_at = created_at


class _FakeRepo:
    def __init__(self, releases, commits=(), compare_error: Exception | None = None):
        self._releases = releases
        self._commits = list(commits)
        self._compare_error = compare_error
        self.compare_calls: list[tuple[str, str]] = []

    def get_releases(self):
        return list(self._releases)

    def compare(self, base, head):
        self.compare_calls.append((base, head))
        if self._compare_error is not None:
            raise self._compare_error
        return _FakeComparison(self._commits)


class ReleaseCategoriesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = load_bridge_module()

    def test_derives_from_commits_between_releases(self) -> None:
        repo = _FakeRepo(
            releases=[
                _FakeRelease('v0.2.0', datetime(2026, 10, 20, tzinfo=timezone.utc)),
                _FakeRelease('v0.1.0', datetime(2026, 10, 9, tzinfo=timezone.utc)),
            ],
            commits=[_FakeCommit('feat: 新功能'), _FakeCommit('fix: 修 bug'), _FakeCommit('docs: 文档')],
        )
        with quiet():
            result = self.bridge.release_categories(repo, 'v0.2.0')
        self.assertEqual(result, ['new', 'fixed'])
        self.assertEqual(repo.compare_calls, [('v0.1.0', 'v0.2.0')])

    def test_no_previous_release_gives_empty(self) -> None:
        repo = _FakeRepo(releases=[_FakeRelease('v0.1.0', datetime(2026, 10, 9, tzinfo=timezone.utc))])
        with quiet():
            self.assertEqual(self.bridge.release_categories(repo, 'v0.1.0'), [])
        self.assertEqual(repo.compare_calls, [])

    def test_compare_failure_gives_empty_and_does_not_raise(self) -> None:
        repo = _FakeRepo(
            releases=[
                _FakeRelease('v0.2.0', datetime(2026, 10, 20, tzinfo=timezone.utc)),
                _FakeRelease('v0.1.0', datetime(2026, 10, 9, tzinfo=timezone.utc)),
            ],
            compare_error=RuntimeError('boom'),
        )
        with quiet():
            self.assertEqual(self.bridge.release_categories(repo, 'v0.2.0'), [])

    def test_releases_without_created_at_do_not_crash(self) -> None:
        repo = _FakeRepo(
            releases=[
                _FakeRelease('v0.3.0', None),
                _FakeRelease('v0.2.0', None),
            ],
            commits=[_FakeCommit('feat: a')],
        )
        # created_at 全为 None 时排序不能炸
        with quiet():
            self.assertEqual(self.bridge.release_categories(repo, 'v0.3.0'), ['new'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
