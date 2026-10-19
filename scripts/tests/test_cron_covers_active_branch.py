#!/usr/bin/env python3
"""`scripts/guard_cron_covers_active_branch.py` 的回归网（源 CNB #564，2026-10-18）。  <!-- cross-repo-ref-allow -->

钉住四件事：

1. **判据方向**：cron 挂 `main` ⇒ 红；挂 `dev` ⇒ 绿；两份都挂 ⇒ 也红（用户明确反对）；
2. **迁移做一半**：`dev` 下一个 cron 都没有 ⇒ 红（作业等于没在跑）；
3. **失败态**（#171）：活跃分支名不存在 / 重复键遮蔽 ⇒ 判「结论不可信」，
   **不得**退化成「没问题」；
4. **回退验证**：拿 `origin/dev` 上**修复前**的真实 `.cnb.yml`（cron 在 `main:` 下）
   喂给判据，确认它真的转红 —— 守卫绿只能证明「它不认识的东西不存在」，
   证明不了它能认出那个 bug（#573 / #450 都栽过这一步）。

跑法：`python scripts/tests/test_cron_covers_active_branch.py`，
或在 `ci.yml` 的 scripts_test 里随 `unittest discover` 一起跑。
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO / 'scripts' / 'guard_cron_covers_active_branch.py'
CNB_YML = REPO / '.cnb.yml'


def _load():
    spec = importlib.util.spec_from_file_location('cron_active_branch_guard', GUARD)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


CRON = 'crontab: 0 18 * * *'


def _cron_job(name: str = 'j') -> dict:
    return {'name': name, 'stages': [{'name': f'{name}-stage', 'script': 'true'}]}


class TestDirection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = _load()

    def test_cron_under_main_is_red(self):
        """本卡的正体：整组 cron 曾挂在 `main:` 下。"""
        problems = self.g.check_data(
            {'main': {CRON: [_cron_job()]}, 'dev': {CRON: [_cron_job()]}}
        )
        self.assertTrue(any('`main:` 段下挂了定时事件' in p for p in problems), problems)

    def test_cron_under_dev_only_is_green(self):
        self.assertEqual(self.g.check_data({'dev': {CRON: [_cron_job()]}}), [])

    def test_duplicated_on_both_branches_is_red(self):
        """两份一起挂也不许：每轮跑两遍、标签与评论重复（用户明确反对）。"""
        problems = self.g.check_data(
            {'dev': {CRON: [_cron_job()]}, 'main': {CRON: [_cron_job('mirror')]}}
        )
        self.assertTrue(problems, '两份都挂必须红')

    def test_cron_event_name_variants(self):
        """`cron:` 与 `crontab:` 一视同仁 —— 否则换个键名就绕过。"""
        problems = self.g.check_data({'main': {'cron: 0 18 * * *': [_cron_job()]}, 'dev': {CRON: [_cron_job()]}})
        self.assertTrue(any('`main:`' in p for p in problems), problems)


class TestHalfMigration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = _load()

    def test_dev_without_any_cron_is_red(self):
        """迁移做了一半（main 的删了、dev 没搬过来）⇒ 作业等于停摆，必须红。"""
        problems = self.g.check_data({'dev': {'push': [{'name': 'p'}]}})
        self.assertTrue(any('没有任何定时事件' in p for p in problems), problems)

    def test_pr_guard_under_main_is_not_cron(self):
        """`main:` 段只剩 PR 守卫是合法的（不是 cron，不重复执行）。"""
        data = {
            'main': {'pull_request.mergeable': [{'name': 'g'}]},
            'dev': {CRON: [_cron_job()]},
        }
        self.assertEqual(self.g.check_data(data), [])


class TestFailureModes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = _load()

    def test_active_branch_missing_is_untrusted(self):
        """活跃分支改名/删除时，判据拿不到输入 ⇒ 说「不可信」，不得说「没问题」。"""
        problems = self.g.check_data({'trunk': {CRON: [_cron_job()]}})
        self.assertTrue(any('不可信' in p for p in problems), problems)

    def test_duplicate_keys_are_untrusted(self):
        text = 'dev:\n  "crontab: 0 18 * * *":\n    - name: a\ndev:\n  push: []\n'
        problems = self.g.check_text(text)
        self.assertTrue(any('不可信' in p and '重复键' in p for p in problems), problems)

    def test_self_check_passes(self):
        self.assertEqual(self.g.self_check(), [])

    def test_cli_exit_codes(self):
        """读不到文件 ⇒ 退 2（不是 0），且 stdout 不得出现「✅」。"""
        r = subprocess.run(
            [sys.executable, str(GUARD), '--file', str(REPO / 'no-such-file.yml')],
            capture_output=True, text=True, encoding='utf-8',
        )
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertNotIn('✅', r.stdout)


class TestRollbackProbe(unittest.TestCase):
    """回退验证：修复前的真实配置必须转红。"""

    def test_real_pre_fix_config_turns_red(self):
        # 116ea8b6 = 本次改动引入之前的 `dev` HEAD，cron 仍在 `main:` 下。
        # ⚠️ 换字面 SHA 前先 `git show <sha>:.cnb.yml | grep -n '^main:'` 确认它真的是修复前形态，
        #    否则这条会退化成「拿一份本来就是对的配置喂守卫，当然绿」。
        rev = '116ea8b6:.cnb.yml'
        r = subprocess.run(
            ['git', '-C', str(REPO), 'show', rev],
            capture_output=True, text=True, encoding='utf-8',
        )
        if r.returncode != 0:
            self.skipTest(f'拿不到 {rev}（浅克隆？）—— 跳过回退验证，不代表判据有效')
        guard = _load()
        problems = guard.check_text(r.stdout)
        self.assertTrue(
            any('`main:` 段下挂了定时事件' in p for p in problems),
            f'修复前的真实配置没被拦下 —— 守门失效。problems={problems}',
        )


class TestRealRepo(unittest.TestCase):
    """当前仓库的 `.cnb.yml` 必须通过（否则 CI 里这条就是红的，不必猜原因）。"""

    def test_current_cnb_yml_passes(self):
        if not CNB_YML.is_file():
            self.skipTest('.cnb.yml 不存在')
        guard = _load()
        problems = guard.check_text(CNB_YML.read_text(encoding='utf-8'))
        self.assertEqual(problems, [])


if __name__ == '__main__':
    unittest.main()
