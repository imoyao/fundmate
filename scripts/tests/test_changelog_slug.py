#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归网：changelog slug 稳定性与「重复触发不重复插入」（#1996 反向验证项 3）。

覆盖：
1. ``slugify`` 的既有语义（小写 / 连字符 / 保留中文 / 截断 / 空值兜底）；
2. 稳定键：同一 ``stable_key`` + 同一标题 ⇒ **同一 slug**（重复触发才能命中已有条目）；
3. 无稳定键：每次 slug 不同（保留旧行为，非发布路径不假装幂等）；
4. **行为级**：``create_changelog_entry`` 传 ``stable_key`` 时，
   第二次调用必须走 UPDATE 而不是再 INSERT —— 用内存假连接记录 SQL，
   **不需要 psycopg2 / 数据库**（CI 的 scripts_test 只有 pyyaml + pytest）。

反向验证（本文件的由来）：把 ``changelog_slug`` 改回
``f"{slugify(title)}-{uuid4()[:8]}"``（即修复前的真实写法），
``test_release_retrigger_updates_instead_of_inserting`` 与两条稳定性用例
会立刻转红——它们咬的正是「slug 每次都变 ⇒ 幂等分支永远不命中」。
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

# 共享的桩与假连接（见 feedlog_test_support.py 的说明：为什么需要它）
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from feedlog_test_support import FakeConn, load_bridge_module  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
SLUG_MODULE = REPO / 'scripts' / 'bridge' / 'changelog_slug.py'


def _load_slug_module():
    spec = importlib.util.spec_from_file_location('changelog_slug_under_test', SLUG_MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_bridge_module():
    """导入真实 ``feedlog_bridge``（psycopg2 / PyGithub 由 support 模块打桩）。"""
    return load_bridge_module()


class SlugifyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.slug_module = _load_slug_module()

    def test_lowercase_and_hyphenate(self) -> None:
        self.assertEqual(self.slug_module.slugify('Hello World!'), 'hello-world')

    def test_keeps_chinese(self) -> None:
        # 线上既有多条中文 slug，改语义会让旧链接失效。
        self.assertEqual(self.slug_module.slugify('多多贝 0.1.0'), '多多贝-0-1-0')

    def test_empty_falls_back_to_item(self) -> None:
        self.assertEqual(self.slug_module.slugify('   '), 'item')

    def test_truncates(self) -> None:
        self.assertLessEqual(len(self.slug_module.slugify('a' * 200, max_len=10)), 10)


class ChangelogSlugTest(unittest.TestCase):
    def setUp(self) -> None:
        self.slug_module = _load_slug_module()

    def test_stable_key_is_deterministic(self) -> None:
        first = self.slug_module.changelog_slug('多多贝 0.1.0', 'v0.1.0')
        second = self.slug_module.changelog_slug('多多贝 0.1.0', 'v0.1.0')
        self.assertEqual(first, second)
        self.assertIn('v0-1-0', first)

    def test_different_tags_differ(self) -> None:
        self.assertNotEqual(
            self.slug_module.changelog_slug('release', 'v0.1.0'),
            self.slug_module.changelog_slug('release', 'v0.2.0'),
        )

    def test_without_stable_key_keeps_random_suffix(self) -> None:
        first = self.slug_module.changelog_slug('release')
        second = self.slug_module.changelog_slug('release')
        self.assertNotEqual(first, second)

    def test_stable_key_survives_title_change(self) -> None:
        # 改标题（Release 改名）不应造成第二条：slug 只由 key 决定后半段。
        a = self.slug_module.changelog_slug('v0.1.0 初版', 'v0.1.0')
        b = self.slug_module.changelog_slug('多多贝 0.1.0', 'v0.1.0')
        self.assertTrue(a.endswith('v0-1-0'))
        self.assertTrue(b.endswith('v0-1-0'))


class CreateChangelogEntryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = _load_bridge_module()

    def test_release_retrigger_updates_instead_of_inserting(self) -> None:
        conn = FakeConn()
        expected_slug = self.bridge.changelog_slug('v0.1.0', 'v0.1.0')

        first_id = self.bridge.create_changelog_entry(
            conn,
            'org-1',
            'v0.1.0',
            '首发说明',
            '2026-10-09T13:06:35Z',
            stable_key='v0.1.0',
        )

        inserts = conn.statements('INSERT')
        self.assertEqual(len(inserts), 1)
        self.assertIn(expected_slug, inserts[0][1])

        # 第二次触发：DB 里已有同 slug 条目。
        conn.existing = {'id': first_id}
        second_id = self.bridge.create_changelog_entry(
            conn,
            'org-1',
            'v0.1.0',
            '改过的说明',
            '2026-10-09T13:30:00Z',
            stable_key='v0.1.0',
        )

        self.assertEqual(second_id, first_id)
        self.assertEqual(len(conn.statements('INSERT')), 1, '重复触发又插了一条')
        self.assertEqual(len(conn.statements('UPDATE')), 1)
        selects = conn.statements('SELECT')
        self.assertEqual(selects[-1][1][1], expected_slug, '第二次查询用的 slug 变了')

    def test_without_stable_key_query_uses_fresh_slug(self) -> None:
        conn = FakeConn()
        self.bridge.create_changelog_entry(conn, 'org-1', '手动条目', '内容', None)
        self.bridge.create_changelog_entry(conn, 'org-1', '手动条目', '内容', None)
        slugs = [q[1][1] for q in conn.statements('SELECT')]
        self.assertNotEqual(slugs[0], slugs[1])


if __name__ == '__main__':
    unittest.main(verbosity=2)
