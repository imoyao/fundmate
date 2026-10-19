#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`scripts/guard_triage_reachable.py` 的回归网（源 CNB #564，2026-10-19）。  <!-- cross-repo-ref-allow -->

钉住五件事：

1. **判据方向**：`.cnb.yml` 的活跃分支段里，cron 真的调了分诊 ⇒ 绿；只是「脚本在仓库里」
   ⇒ 红（这正是 2026-10-18 合进去后的实际形态：**写了、测了、从不执行**）；
2. **stage 必须带 `name`**：CNB #167 实测，查不到 stage 的作业会「挂旧 sha、实际没跑、却报绿」；
3. **兜底通道必须固定在活跃分支上执行**：`schedule` 只读默认分支（main）上的定义（#1434）；
4. **失败态**（#171）：读不到兜底 workflow / 活跃分支名不存在 ⇒ 判「结论不可信」，
   **不得**退化成「没问题」；
5. **守卫自身自检**：`self_check()` 必须为空 —— 判据写坏了会全绿，这是本仓反复踩过的。

跑法：`python -m unittest scripts.tests.test_triage_reachable`。
"""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO / 'scripts' / 'guard_triage_reachable.py'
CNB_YML = REPO / '.cnb.yml'
GH_WF = REPO / '.github' / 'workflows' / 'issue-triage.yml'

CRON = 'crontab: 0 18 * * *'
GH_OK = (
    'schedule:\n  - cron: "0 19 * * *"\n'
    'env:\n  TRIAGE_REF: dev\n'
    'with:\n  ref: ${{ env.TRIAGE_REF }}\n'
    'issue_triage.py\n'
)


def _load():
    spec = importlib.util.spec_from_file_location('triage_reachable_guard', GUARD)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _job(script: str, *, name: str = '跑一下') -> dict:
    return {'name': '分诊', 'stages': [{'name': name, 'script': script}]}


class TestDirection(unittest.TestCase):
    def setUp(self):
        self.g = _load()

    def test_wired_cron_is_green(self):
        data = {'dev': {CRON: [_job('python scripts/triage/issue_triage.py --apply')]}}
        self.assertEqual(self.g.check_data(data, GH_OK), [])

    def test_script_elsewhere_but_no_cron_is_red(self):
        """「代码在仓库里 + 测试全绿」不等于「会跑」—— 2026-10-18 的实际形态。"""
        data = {'dev': {'push': [_job('python scripts/triage/issue_triage.py --apply')]}}
        problems = self.g.check_data(data, GH_OK)
        self.assertTrue(any('没有任何 cron' in p for p in problems), problems)

    def test_cron_without_triage_is_red(self):
        data = {'dev': {CRON: [_job('python scripts/bridge/github_cnb_issues.py --apply')]}}
        problems = self.g.check_data(data, GH_OK)
        self.assertTrue(any('没有任何 job 调用' in p for p in problems), problems)

    def test_stage_without_name_is_red(self):
        """CNB #167：没有 name 的 stage 在构建详情里查不到 ⇒ 可以「挂旧 sha 却报绿」。"""
        data = {
            'dev': {
                CRON: [
                    {'name': '分诊', 'stages': [{'script': 'python scripts/triage/issue_triage.py'}]}
                ]
            }
        }
        problems = self.g.check_data(data, GH_OK)
        self.assertTrue(any('没有 `name`' in p for p in problems), problems)

    def test_anchor_expanded_job_is_detected(self):
        """`<<: *anchor` 在 safe_load 之后已展开成 dict，判据必须能看到里面的 script。"""
        data = {
            'dev': {
                CRON: [
                    {
                        'name': '镜像',
                        'stages': [
                            {'name': '建卡', 'script': 'python scripts/bridge/github_cnb_issues.py'},
                            {'name': '分诊', 'script': 'python scripts/triage/issue_triage.py --apply'},
                        ],
                    }
                ]
            }
        }
        self.assertEqual(self.g.check_data(data, GH_OK), [])


class TestGithubFallback(unittest.TestCase):
    def setUp(self):
        self.g = _load()

    def test_checks_out_active_branch(self):
        data = {'dev': {CRON: [_job('python scripts/triage/issue_triage.py')]}}
        self.assertEqual(self.g.check_data(data, GH_OK), [])

    def test_fallback_without_schedule_is_red(self):
        """没有 schedule 的兜底通道只在手动触发时动 —— 不算兜底。"""
        data = {'dev': {CRON: [_job('python scripts/triage/issue_triage.py')]}}
        problems = self.g.check_data(data, 'on:\n  workflow_dispatch:\nissue_triage.py\n')
        self.assertTrue(any('没有 `schedule:`' in p for p in problems), problems)

    def test_checkout_ref_is_not_duplicated_here(self):
        """**判据不重叠**：兜底 workflow 的 checkout 分支由 `guard_schedule_checkout_ref.py` 管。

        「已有判据管过的事不重开第二份」不是洁癖：两处判据对同一件事迟早各说各话
        （一个放行、一个报红，下一个人不知道该信谁）。故这里显式钉住边界——
        本守卫**只**问「有没有 schedule」，不问「checkout 的哪条分支」。
        """
        data = {'dev': {CRON: [_job('python scripts/triage/issue_triage.py')]}}
        problems = self.g.check_data(
            data, 'schedule:\n  - cron: "0 19 * * *"\nwith:\n  ref: main\nissue_triage.py\n'
        )
        self.assertEqual(problems, [], 'checkout 分支不归本守卫判（那是 #586 守卫的事）')

    def test_missing_workflow_is_untrustworthy_not_green(self):
        """读不到兜底 workflow ⇒ 判「不可信」，不得退化成「没问题」（#171 的失败态纪律）。"""
        data = {'dev': {CRON: [_job('python scripts/triage/issue_triage.py')]}}
        problems = self.g.check_data(data, None)
        self.assertTrue(any('不可信' in p for p in problems), problems)

    def test_unknown_branch_is_untrustworthy(self):
        problems = self.g.check_data({'trunk': {CRON: []}}, GH_OK)
        self.assertTrue(any('不可信' in p for p in problems), problems)


class TestSelfCheck(unittest.TestCase):
    def test_guard_self_check_is_clean(self):
        """判据写坏了会全绿 —— 本仓反复踩过，故守卫自带正反探针。"""
        g = _load()
        self.assertEqual(g.self_check(), [])

    def test_real_repo_is_green(self):
        """仓库当前的真实文件必须通过（否则守卫只是在自娱自乐）。"""
        g = _load()
        import yaml

        data = yaml.safe_load(CNB_YML.read_text(encoding='utf-8'))
        gh = GH_WF.read_text(encoding='utf-8') if GH_WF.is_file() else None
        self.assertEqual(g.check_data(data, gh), [])


if __name__ == '__main__':
    unittest.main()
