#!/usr/bin/env python3
"""`scripts/guard_schedule_checkout_ref.py` 的回归网（源 CNB #586）。

钉四件事：
1. **判据方向**：定时跑仓库脚本却没写 `ref` ⇒ 红；写了 `ref: dev` ⇒ 绿；
2. **`ref: main` 等于没写**（`schedule` 下默认就落在那儿）⇒ 必须红；
3. **表达式放行**（`ref: ${{ … }}`）：静态判据不猜运行时值；
4. **不跑仓库脚本 / 非定时作业不被误伤**（防判据过宽）；
5. **回退探针**：拿修复前 `dev` 上真实的 `e2e.yml`（`aeb75df9`）喂给判据，确认它真的转红
   —— 「守门绿」只能证明「代码里没有它不认识的东西」，证明不了它能认出那个 bug。
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO / 'scripts' / 'guard_schedule_checkout_ref.py'

# 修复前的真实文件（`dev` 上 `aeb75df9` 的 `e2e.yml`：checkout 没写 ref）。
# 钉**不可变 SHA**：修复一合入 `origin/dev` 就是好的，读它会让探针自己失效（恒绿）。
BEFORE_SHA = 'aeb75df9eaeff12a941700c32e4ba1e31a558e62'

PROBE_BAD = '''on:
  schedule:
    - cron: '0 19 * * *'
jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: 跑
        run: python scripts/bridge/check_branch_divergence.py
'''

PROBE_BAD_MAIN = '''on:
  schedule:
    - cron: '0 19 * * *'
jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          ref: main
      - name: 跑
        run: python scripts/bridge/check_branch_divergence.py
'''

PROBE_GOOD = '''on:
  schedule:
    - cron: '0 19 * * *'
jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          ref: dev
      - name: 跑
        run: python scripts/bridge/check_branch_divergence.py
'''

PROBE_NO_SCRIPT = '''on:
  schedule:
    - cron: '0 19 * * *'
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: ping
        run: curl -fsS https://example.com/ping
'''

PROBE_NOT_SCHEDULED = '''on:
  pull_request: {}
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: 跑
        run: python scripts/bridge/check_branch_divergence.py
'''


def _import_guard():
    sys.path.insert(0, str(REPO / 'scripts'))
    import guard_schedule_checkout_ref as g  # noqa: PLC0415

    return g


class TestScheduleCheckoutRef(unittest.TestCase):
    def test_missing_ref_is_red(self) -> None:
        g = _import_guard()
        self.assertTrue(g.check_workflow(PROBE_BAD), '没写 ref 的定时作业没被报出来')

    def test_ref_main_is_red(self) -> None:
        """`ref: main` 等于没写 —— `schedule` 下默认就检出默认分支。"""
        g = _import_guard()
        problems = g.check_workflow(PROBE_BAD_MAIN)
        self.assertTrue(problems, '`ref: main` 被放行 —— 那和没写是同一件事')
        self.assertIn('默认分支', problems[0])

    def test_ref_dev_is_green(self) -> None:
        g = _import_guard()
        self.assertEqual(g.check_workflow(PROBE_GOOD), [])

    def test_non_script_job_is_green(self) -> None:
        g = _import_guard()
        self.assertEqual(g.check_workflow(PROBE_NO_SCRIPT), [], '不跑仓库脚本的作业被误伤')

    def test_not_scheduled_is_green(self) -> None:
        g = _import_guard()
        self.assertEqual(g.check_workflow(PROBE_NOT_SCHEDULED), [], '非定时作业被误伤')

    def test_real_repo_is_green(self) -> None:
        r = subprocess.run(
            [sys.executable, str(GUARD)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        self.assertEqual(r.returncode, 0, f'真实仓库报红：{r.stdout}{r.stderr}')

    def test_before_fix_real_file_turns_red(self) -> None:
        """回退探针：修复前的真实 `e2e.yml` 必须转红（钉不可变 SHA）。"""
        r = subprocess.run(
            ['git', 'show', f'{BEFORE_SHA}:.github/workflows/e2e.yml'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        if r.returncode != 0:
            self.skipTest(f'取不到 {BEFORE_SHA}（浅克隆）—— 跳过回退探针')
        g = _import_guard()
        problems = g.check_workflow(r.stdout)
        self.assertTrue(
            problems,
            '修复前的 e2e.yml 没被转红 —— 判据认不出那个真实形态（恒绿）',
        )
        self.assertIn('默认分支', problems[0])

    def test_self_check_passes(self) -> None:
        """守卫自带 self_check：判据没接上时它会全绿，故每次都要跑。"""
        r = subprocess.run(
            [sys.executable, str(GUARD), '--no-self-check'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        self.assertEqual(r.returncode, 0, f'{r.stdout}{r.stderr}')


if __name__ == '__main__':
    unittest.main()
