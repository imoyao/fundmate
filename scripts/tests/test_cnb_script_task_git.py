#!/usr/bin/env python3
"""`scripts/guard_cnb_script_task_git.py` 的回归网（源 CNB #517）。

钉四件事：
1. 判据方向：调用 **git 驱动脚本** 却不供给 git ⇒ 报红；供给 ⇒ 放行（不过宽）；
2. **推导逻辑**：`git_driven_scripts()` 必须能从源码认出 `machine_branch.py` 是 git 驱动
   —— 它若失效，整张网恒绿（本判据的关键假设，值得单独钉）；
3. **不调 git 的脚本不被误伤**（防判据过宽）；
4. **重复键遮蔽**（源 CNB #463）：`dev:` 出现两次时，被覆盖段的坏 job 在 `safe_load`
   后不存在 ⇒ 守卫对它一无所知、报一个看起来正常的 ✅。故必须转红；
5. 守卫自带 self_check：判据没接上时它会全绿，故每次都要跑。

跑法：`python -m unittest scripts.tests.test_cnb_script_task_git`（在仓库根）
或 `python scripts/tests/test_cnb_script_task_git.py`。
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO / 'scripts' / 'guard_cnb_script_task_git.py'

# 事故前真实 `.cnb.yml`：`origin/dev` 上「机器分支通道补了 image 但没补 git」的那一版。
# 钉**不可变 SHA**（本卡修复的父提交），不读 `origin/dev`：修复一合入，那里就是好的文件，
# 探针会随分支推进自己失效（恒绿）。
BEFORE_SHA = '7b833c4c1f39e87a9c51335039332609ff1ece04'

PROBE_BAD = (
    'dev:\n'
    '  push:\n'
    '    - name: 坏样本\n'
    '      docker:\n'
    '        image: python:3.12-slim\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: python scripts/bridge/machine_branch.py --apply\n'
)

PROBE_GOOD = (
    'dev:\n'
    '  push:\n'
    '    - name: 好样本\n'
    '      docker:\n'
    '        image: python:3.12-slim\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: |\n'
    '            command -v git >/dev/null 2>&1 || apt-get install -y -qq git\n'
    '            python scripts/bridge/machine_branch.py --apply\n'
)

# 调 python 但不调 git 脚本 ⇒ 不该被本判据管（防判据过宽）。
PROBE_NO_GIT = (
    'dev:\n'
    '  push:\n'
    '    - name: 非 git 脚本\n'
    '      docker:\n'
    '        image: python:3.12-slim\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: python scripts/bridge/github_cnb_issues.py --apply\n'
)

# 重复键遮蔽样本（源 CNB #463）：顶层 `dev:` 两次，第二个覆盖第一个，
# 被覆盖的那个 `dev:` 里正是「调 git 脚本却不供给 git」的 job。
PROBE_SHADOWED = (
    'dev:\n'
    '  push:\n'
    '    - name: shadowed-bad\n'
    '      docker:\n'
    '        image: python:3.12-slim\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: python scripts/bridge/machine_branch.py --apply\n'
    'dev:\n'
    '  push:\n'
    '    - name: winner\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: echo hi\n'
)


def run_guard(text: str, tmp: pathlib.Path) -> subprocess.CompletedProcess:
    p = tmp / 'probe.cnb.yml'
    p.write_text(text, encoding='utf-8')
    return subprocess.run(
        [sys.executable, str(GUARD), '--file', str(p)],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )


def _import_guard():
    sys.path.insert(0, str(REPO / 'scripts'))
    import guard_cnb_script_task_git as g  # noqa: PLC0415

    return g


class TestGuardCnbScriptTaskGit(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_git_provision_is_reported(self) -> None:
        r = run_guard(PROBE_BAD, self.tmp)
        self.assertEqual(r.returncode, 1, f'缺 git 供给没被报红：{r.stdout}{r.stderr}')
        self.assertIn('git', r.stdout + r.stderr)

    def test_git_provision_passes(self) -> None:
        r = run_guard(PROBE_GOOD, self.tmp)
        self.assertEqual(r.returncode, 0, f'合法形态被误报：{r.stdout}{r.stderr}')

    def test_non_git_script_passes(self) -> None:
        r = run_guard(PROBE_NO_GIT, self.tmp)
        self.assertEqual(r.returncode, 0, f'不调 git 的脚本被误报（判据过宽）：{r.stdout}{r.stderr}')

    def test_git_driven_scripts_derivation(self) -> None:
        """关键假设：推导逻辑必须认出 `machine_branch.py` 是 git 驱动。"""
        g = _import_guard()
        found = g.git_driven_scripts(REPO)
        self.assertIn(
            'scripts/bridge/machine_branch.py',
            found,
            'git_driven_scripts() 没认出 machine_branch.py —— 推导失效，后续判据都会恒绿',
        )
        self.assertIn('scripts/bridge/check_branch_divergence.py', found)

    def test_self_check_passes(self) -> None:
        r = subprocess.run(
            [sys.executable, str(GUARD), '--file', str(REPO / '.cnb.yml')],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        self.assertEqual(r.returncode, 0, f'守卫自检 / 真实配置失败：{r.stdout}{r.stderr}')

    def test_shadowed_input_is_not_green(self) -> None:
        """重复键遮蔽 ⇒ 必须报红，不得给出「git 均已供给」的假绿灯（源 CNB #463）。"""
        r = run_guard(PROBE_SHADOWED, self.tmp)
        self.assertEqual(r.returncode, 1, f'遮蔽输入被放行（假绿灯）：{r.stdout}{r.stderr}')
        self.assertIn('输入不可信', r.stdout + r.stderr)

    def test_before_fix_real_file_turns_red(self) -> None:
        """回退探针：修复前的真实 `.cnb.yml` 必须转红（钉不可变 SHA）。"""
        r = subprocess.run(
            ['git', 'show', f'{BEFORE_SHA}:.cnb.yml'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        self.assertEqual(r.returncode, 0, f'取不到修复前的 .cnb.yml：{r.stderr}')
        g = run_guard(r.stdout, self.tmp)
        self.assertEqual(g.returncode, 1, f'修复前的 .cnb.yml 没被守卫转红（判据恒绿）：{g.stdout}{g.stderr}')
        self.assertIn('git', g.stdout + g.stderr)

    def test_current_real_file_is_green(self) -> None:
        """修复后的真实 `.cnb.yml` 必须是绿的（防修复没接上判据）。"""
        r = run_guard((REPO / '.cnb.yml').read_text(encoding='utf-8'), self.tmp)
        self.assertEqual(r.returncode, 0, f'修复后的配置仍报红：{r.stdout}{r.stderr}')


if __name__ == '__main__':
    unittest.main()
