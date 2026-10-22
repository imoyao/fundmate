#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归网：`scripts/release.py`（#1996 发版流程固化）。

只测**纯函数**（不碰 git / gh / 网络）：
1. tag 规范（接受 `v0.1.1` / `v0.1.0-beta.1`，拒绝裸 `0.1.0` 与两段式）；
2. notes 文件校验（缺失 / 空白 = 失败，有内容 = 读入并去首尾空白）；
3. 命令顺序与关键参数（先 tag → 再 push → 最后 `gh release create --verify-tag`）。

反向探针：删掉 `--verify-tag` 或把顺序改成「先建 Release 再推 tag」，
`test_command_order_and_verify_tag` 会立即转红——这两点正是「tag 指向你没看过的
提交」与「Release 先于 tag 存在」两类事故的判据。
"""

from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / 'scripts' / 'release.py'


def _load():
    spec = importlib.util.spec_from_file_location('release_helper_under_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ValidateTagTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load()

    def test_accepts_semver(self) -> None:
        for tag in ('v0.1.0', 'v1.2.3', 'v0.1.0-beta.1', 'v2.0.0-rc1'):
            with self.subTest(tag=tag):
                self.assertIsNone(self.mod.validate_tag(tag))

    def test_rejects_bare_semver(self) -> None:
        self.assertIsNotNone(self.mod.validate_tag('0.1.0'))

    def test_rejects_two_segments(self) -> None:
        self.assertIsNotNone(self.mod.validate_tag('v0.1'))

    def test_rejects_trailing_dot(self) -> None:
        self.assertIsNotNone(self.mod.validate_tag('v0.1.0.'))

    def test_rejects_empty(self) -> None:
        self.assertIsNotNone(self.mod.validate_tag(''))


class ValidateNotesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load()

    def test_missing_file(self) -> None:
        notes, error = self.mod.validate_notes(pathlib.Path('does-not-exist.md'))
        self.assertIsNone(notes)
        self.assertIn('找不到', error)

    def test_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'notes.md'
            path.write_text('   \n\n', encoding='utf-8')
            notes, error = self.mod.validate_notes(path)
        self.assertIsNone(notes)
        self.assertIn('为空', error)

    def test_reads_and_strips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'notes.md'
            path.write_text('\n首发说明\n', encoding='utf-8')
            notes, error = self.mod.validate_notes(path)
        self.assertIsNone(error)
        self.assertEqual(notes, '首发说明')


class BuildCommandsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load()

    def test_command_order_and_verify_tag(self) -> None:
        commands = self.mod.build_commands('v0.1.1', 'v0.1.1', pathlib.Path('notes.md'), 'abc123')

        self.assertEqual(len(commands), 3)
        self.assertEqual(commands[0][:4], ['git', 'tag', '-a', 'v0.1.1'])
        self.assertIn('abc123', commands[0])
        self.assertEqual(commands[1][:2], ['git', 'push'])
        self.assertEqual(commands[1][-1], 'refs/tags/v0.1.1')
        self.assertEqual(commands[2][:4], ['gh', 'release', 'create', 'v0.1.1'])
        # 这两条是判据本体：没有 --verify-tag 就可能让 GitHub 自己挑提交。
        self.assertIn('--verify-tag', commands[2])
        self.assertIn('--notes-file', commands[2])

    def test_title_is_passed(self) -> None:
        commands = self.mod.build_commands('v0.1.1', '多多贝 0.1.1', pathlib.Path('n.md'), 'abc')
        self.assertEqual(commands[2][commands[2].index('--title') + 1], '多多贝 0.1.1')


if __name__ == '__main__':
    unittest.main(verbosity=2)
