#!/usr/bin/env python3
"""`scripts/guard_cron_job_reachability.py` 的回归网（源 CNB #578，2026-10-18）。  <!-- cross-repo-ref-allow -->

这张卡来自一条**每小时都红、红在同一行**的构建（`cnb-ri6-1k57q4k9b`）：

    git fetch -v --force … origin "refs/heads/main"
    ! [rejected]  dev -> dev  (fetch first)

要钉住的四件事：

1. **判据方向**：定时作业的目标分支 ≠ 所在分支键 ⇒ 报红；== ⇒ 放行（不过宽）；
2. **`$` 段**：任何分支下指向具体分支 ⇒ 报红（那里没有「当前分支」上下文）；
3. **不猜运行时值**：`${CNB_BRANCH}` 这类动态值不判（判了就是拟合写法）；
4. **输入不可信须显式**：重复键遮蔽 / 文件读不到 ⇒ 退 2 或报「不可信」，
   **不得**退化成「没问题」（#171 的失败态纪律）。

最后一条是**回退验证**：拿 `origin/dev` 上**修复前的真实配置**喂给判据，
确认它真的转红——守卫绿只能证明「代码里没有它不认识的东西」，
证明不了它能认出那个 bug（#573 / #450 都栽过这一步）。

跑法：`python scripts/tests/test_cron_job_reachability.py`
或在 `ci.yml` 的 scripts_test 里随 `unittest discover` 一起跑。
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO / 'scripts' / 'guard_cron_job_reachability.py'


def _load():
    spec = importlib.util.spec_from_file_location('cron_reachability_guard', GUARD)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _job(name: str, branch: str | None = None, script: str | None = None) -> dict:
    stage: dict = {'name': f'{name}-stage'}
    if branch is not None:
        stage['settings'] = {'branch': branch}
    if script is not None:
        stage['script'] = script
    return {'name': name, 'stages': [stage]}


class TestDirection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = _load()

    def test_cron_under_main_pushing_dev_is_red(self):
        """判据 1（本卡的正体）：`main` 下的 cron 推 `dev` ⇒ 报红。

        探针：删掉 `check_data` 里 `target != branch_key` 那条分支 ⇒ 本用例转红。
        """
        data = {'main': {'crontab: 30 * * * *': [_job('每小时兜底', 'dev')]}}
        problems = self.g.check_data(data)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn('`dev`', problems[0])
        self.assertIn('`main`', problems[0])

    def test_cron_under_dev_pushing_dev_is_green(self):
        """判据不过宽：挂在 `dev` 下、推 `dev` ⇒ 放行。

        与上一条成对——只有两边都钉住，判据才既不是恒真也不是恒假。
        """
        data = {'dev': {'crontab: 30 * * * *': [_job('每小时兜底', 'dev')]}}
        self.assertEqual(self.g.check_data(data), [])

    def test_main_pushing_main_is_green(self):
        """`main` 下推 `main` 也是合法的（不是「只许 dev」这种写死的判据）。"""
        data = {'main': {'crontab: 0 3 * * *': [_job('推送 main', 'main')]}}
        self.assertEqual(self.g.check_data(data), [])

    def test_daily_cron_under_main_pushing_dev_is_red(self):
        """不止 `30 * * * *`：任何 crontab 形态一视同仁。"""
        data = {'main': {'crontab: 0 18 * * *': [_job('夜间同步', 'dev')]}}
        self.assertTrue(self.g.check_data(data))

    def test_push_event_is_not_judged(self):
        """`push` 事件不归本判据管（那是 `check_cnb_events.py` 的职责）。

        这条防的是「判据越界」：挂载位置对了、目标是当前分支，push 语义本来就不同。
        """
        data = {'main': {'push': [_job('推送', 'dev')]}}
        self.assertEqual(self.g.check_data(data), [])

    def test_dynamic_branch_is_not_judged(self):
        """`${CNB_BRANCH}` 不猜运行时值 —— 那是 `$` 段 / push 段的合法写法。"""
        data = {'$': {'push': [_job('功能分支同步', '${CNB_BRANCH}')]}}
        self.assertEqual(self.g.check_data(data), [])


class TestDollarSegment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = _load()

    def test_dollar_cron_with_concrete_branch_is_red(self):
        """判据 2：`$` 段（任何分支）下指向具体分支 ⇒ 报红。

        `$` 下没有「当前分支」上下文，`CNB_BRANCH` 在 cron/push 形态下不可靠，
        误推 `main` 就是分叉。
        """
        data = {'$': {'crontab: 30 * * * *': [_job('同步', 'dev')]}}
        problems = self.g.check_data(data)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn('`$`', problems[0])


class TestScriptTaskBranch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = _load()

    def test_cli_branch_flag_is_judged(self):
        """脚本任务的 `--branch dev` 也要判：这类作业同样驱动跨仓同步。"""
        data = {'main': {'crontab: 0 18 * * *': [_job('探针', script='python scripts/bridge/machine_branch.py --branch dev')]}}
        self.assertTrue(self.g.check_data(data))

    def test_cli_branch_flag_equal_to_key_is_green(self):
        data = {'dev': {'crontab: 0 18 * * *': [_job('探针', script='python x.py --branch dev')]}}
        self.assertEqual(self.g.check_data(data), [])

    def test_cli_branch_dynamic_is_skipped(self):
        data = {'dev': {'crontab: 0 18 * * *': [_job('探针', script='python x.py --branch ${CNB_BRANCH}')]}}
        self.assertEqual(self.g.check_data(data), [])


class TestInputTrust(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = _load()

    def test_duplicate_key_is_reported_as_untrusted(self):
        """重复键 ⇒ 判「输入不可信」：`safe_load` 会用后者覆盖前者，
        被覆盖段的 job 根本不在解析结果里，报出的「全部合规」是假绿。"""
        text = (
            'main:\n'
            '  "crontab: 30 * * * *":\n'
            '    - name: a\n'
            '      stages: []\n'
            'main:\n'
            '  "crontab: 30 * * * *":\n'
            '    - name: b\n'
            '      stages: []\n'
        )
        problems = self.g.check_text(text)
        self.assertTrue(problems, '重复键必须报「输入不可信」，不能静默放行')
        self.assertIn('不可信', problems[0])

    def test_cron_key_extraction_handles_quoted_form(self):
        """`.cnb.yml` 里的键带引号（`"crontab: 30 * * * *":`）。

        首版正则被开头的 `"` 挡掉 ⇒ 映射恒为空，报错信息退回到「原文里搜不到」的形态。
        """
        keys = self.g._cron_keys('  "crontab: 30 * * * *":\n')
        self.assertEqual(keys, ['crontab: 30 * * * *'])


class TestRealConfigRegression(unittest.TestCase):
    """回退验证：拿**修复前的真实配置**喂判据，确认它真的转红。

    取自 `git show origin/dev:.cnb.yml`（不含本卡的修复）——
    若哪天有人把判据写松了，这条会转红。git 取不到（浅克隆 / 无 origin）则跳过，
    但**不能**改成「跳过即通过」：跳过时用例状态是 skipped，CI 日志里看得见。
    """

    @classmethod
    def setUpClass(cls):
        cls.g = _load()

    def _show(self, ref_path: str) -> str | None:
        r = subprocess.run(
            ['git', 'show', ref_path],
            cwd=REPO,
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=False,
        )
        return r.stdout if r.returncode == 0 and r.stdout.strip() else None

    def test_current_config_passes(self):
        """本仓现状必须通过（否则守门一上线就恒红，没人会去修）。"""
        r = subprocess.run(
            [sys.executable, str(GUARD)], capture_output=True, text=True, encoding='utf-8', check=False
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_bug_fixture_is_caught(self):
        """把**缺陷形态**原样拼出来：`main:` 段里挂一条推 `dev` 的 cron。

        这是本卡正文那行 `! [rejected] dev -> dev (fetch first)` 的成因；
        用 fixture 而不是 `git show` 不可变 sha，是因为那条缺陷**从未**进过 `dev`
        （修复与发现同批），钉 sha 会钉到一条不存在的历史。
        """
        text = (
            'main:\n'
            '  # daily mirror\n'
            '  "crontab: 0 18 * * *":\n'
            '    - name: GitHub issue 增量镜像\n'
            '      stages:\n'
            '        - name: s\n'
            '          script: echo hi\n'
            '  # hourly fallback sync\n'
            '  "crontab: 30 * * * *":\n'
            '    - name: 同步到 GitHub（每小时兜底，仅 dev）\n'
            '      stages:\n'
            '        - name: 同步到 GitHub（每小时兜底，仅 dev）\n'
            '          settings:\n'
            '            branch: dev\n'
        )
        problems = self.g.check_text(text)
        self.assertTrue(problems, '修复前的形态必须被咬住（否则本守卫等于没装）')
        self.assertTrue(any('`main`' in p and '`dev`' in p for p in problems), problems)


if __name__ == '__main__':
    unittest.main(verbosity=2)
