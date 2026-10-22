#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归网：``scripts/guard_db_backup_ignored.py``（数据库备份文件 ignore 防线）。

覆盖：
1. 真实仓库通过（规则齐、且工作区无漏网文件）；
2. 规则缺失（临时仓库里没有 ``*.db.bak*``）⇒ 红，且报出具体探针；
3. 规则齐但工作区里躺着未跟踪的 ``.db`` 文件 ⇒ 红，且报出该文件；
4. 不是 git 仓库 ⇒ 退出码 **2**（不冒充通过）；
5. 文件名判定函数的行为（``x.db`` / ``x.db.bak_2026`` 算危险，``x.csv`` 不算）。

反向验证：把 ``backend/.gitignore`` 里的 ``*.db.bak*`` 规则删掉
（或在真实仓库里造一个未跟踪的 ``foo.db``），本守卫与用例都会转红。
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO / 'scripts' / 'guard_db_backup_ignored.py'

GOOD_IGNORE = """\
*.db
*.db-wal
*.db-shm
*.db.bak*
*.db.backup*
*.sqbpro
"""


def _load_guard():
    spec = importlib.util.spec_from_file_location('guard_db_backup_ignored_under_test', GUARD)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _git(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['git', *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )


def _init_repo(root: pathlib.Path, ignore_content: str) -> pathlib.Path:
    _git(root, 'init', '--quiet')
    (root / '.gitignore').write_text(ignore_content, encoding='utf-8')
    return root


class GuardOnRealRepoTest(unittest.TestCase):
    def test_real_repo_passes(self) -> None:
        guard = _load_guard()
        self.assertEqual(guard.run(REPO), 0)


class NameMatcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = _load_guard()

    def test_flags_db_and_backups(self) -> None:
        for name in (
            'invest.db',
            'backend/invest.db',
            'backend/invest.db.bak_20261018_anchor',
            'backend/invest.db.backup-venue-1',
            'backend/invest.db-wal',
            'backend/invest.db-shm',
            'backend/invest.sqbpro',
        ):
            with self.subTest(name=name):
                self.assertTrue(self.guard.is_dangerous_name(name))

    def test_ignores_ordinary_files(self) -> None:
        for name in ('README.md', 'app.py', 'data.csv', 'all_pb.csv', 'x.dbx'):
            with self.subTest(name=name):
                self.assertFalse(self.guard.is_dangerous_name(name))


class GuardBehaviourTest(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = _load_guard()

    def test_missing_rule_is_red(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_repo(pathlib.Path(tmp), '*.csv\n')
            code = self.guard.run(root)
        self.assertEqual(code, 1)

    def test_missing_rule_reports_probe(self) -> None:
        guard = self.guard
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_repo(pathlib.Path(tmp), '*.csv\n')
            missed = guard.check_probes(root)
        self.assertIn('backend/invest.db.bak_probe', missed)
        self.assertIn('backend/invest.db', missed)

    def test_untracked_db_file_is_red(self) -> None:
        """规则只覆盖 backend/ 时，根目录躺着的 .db 文件就是漏网的（正是修复前的形态）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _git(root, 'init', '--quiet')
            (root / 'backend').mkdir()
            (root / 'backend' / '.gitignore').write_text('*.db\n', encoding='utf-8')
            (root / 'secret.db').write_text('x', encoding='utf-8')
            code = self.guard.run(root)
            leaked = self.guard.check_worktree(root)
        self.assertEqual(code, 1)
        self.assertIn('secret.db', leaked)

    def test_ignored_db_file_is_not_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_repo(pathlib.Path(tmp), GOOD_IGNORE)
            (root / 'secret.db').write_text('x', encoding='utf-8')
            leaked = self.guard.check_worktree(root)
        self.assertEqual(leaked, [])

    def test_good_ignore_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _init_repo(pathlib.Path(tmp), GOOD_IGNORE)
            code = self.guard.run(root)
        self.assertEqual(code, 0)

    def test_not_a_git_repo_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code = self.guard.run(pathlib.Path(tmp))
        self.assertEqual(code, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
