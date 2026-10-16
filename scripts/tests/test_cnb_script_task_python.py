#!/usr/bin/env python3
"""`scripts/guard_cnb_script_task_python.py` 的回归网（源 CNB #461）。

钉三件事：
1. 判据方向：跑 python 却不声明 image ⇒ 报红；声明了 ⇒ 放行（不过宽）；
2. 探针咬得住：拿**修复前的真实 `.cnb.yml`**（不可变 SHA `b3e64717`，机器分支 job
   还没补 `docker.image` 的那一版）喂守卫 ⇒ 必须转红。钉 SHA 而不读 `origin/dev`：
   修复一合入，`origin/dev` 里就是修好的文件，探针会随分支推进自己失效（恒绿）；
3. **重复键遮蔽**（源 CNB #463）：`dev:` 出现两次时，被覆盖段的坏 job 在
   `safe_load` 后不存在 ⇒ 守卫会对它一无所知。拿 `origin/dev` 那份真实坏配置
   （跨仓收敛合并 `5633d04c` 留下的重复键）喂守卫，**必须转红**，不得报 ✅；
4. 守卫自带 self_check：判据没接上时它会全绿，故每次都要跑。

跑法：`python -m unittest scripts.tests.test_cnb_script_task_python`（在仓库根）
或 `python scripts/tests/test_cnb_script_task_python.py`。
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO / 'scripts' / 'guard_cnb_script_task_python.py'

# 事故前真实 `.cnb.yml`：机器分支 job 上线时漏写 `docker.image`。
# （`5633d04c` 那次收敛合并反而把第一段 `dev:` 覆盖没了，机器分支 job 在
#  `safe_load` 后消失 ⇒ 拿它喂守卫是**假绿**，必须用 b3e64717。）
BEFORE_SHA = 'b3e64717396bcd2f98e56a87a1c55640ef611bda'

PROBE_BAD = (
    'dev:\n'
    '  push:\n'
    '    - name: 坏样本\n'
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
    '          script: python scripts/bridge/machine_branch.py --apply\n'
)

# 纯 shell 任务不该被本判据管（默认镜像跑 sh 没问题）——防判据过宽。
PROBE_SHELL_ONLY = (
    'dev:\n'
    '  push:\n'
    '    - name: 纯 sh\n'
    '      stages:\n'
    '        - name: echo\n'
    '          script: echo hi\n'
)

# image 是运行期变量时无从静态求值 ⇒ 放行（与 git_sync_push_scope 判据 5 同口径）。
PROBE_VAR_IMAGE = (
    'dev:\n'
    '  push:\n'
    '    - name: 变量镜像\n'
    '      docker:\n'
    '        image: ${IMG}\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: python scripts/x.py\n'
)


# 重复键遮蔽样本（源 CNB #463）：顶层 `dev:` 两次，第二个覆盖第一个，
# 被覆盖的那个 `dev:` 里正是「跑 python 却不带 image」的 job。
PROBE_SHADOWED = (
    'dev:\n'
    '  push:\n'
    '    - name: shadowed-bad\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: python scripts/x.py\n'
    'dev:\n'
    '  push:\n'
    '    - name: winner\n'
    '      docker:\n'
    '        image: python:3.12-slim\n'
    '      stages:\n'
    '        - name: run\n'
    '          script: python scripts/y.py\n'
)

# `5633d04c`（跨仓收敛合并）那一版的真实 `.cnb.yml`：`main:` 下两个
# `pull_request`、顶层两个 `dev:`。**不可变 SHA**（不读 origin/dev：修好后那里就是好的）。
SHADOWED_SHA = '5633d04c55ab57642324234c350944fb0343e803'


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


class TestGuardCnbScriptTaskPython(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_image_is_reported(self) -> None:
        r = run_guard(PROBE_BAD, self.tmp)
        self.assertEqual(r.returncode, 1, f'跑 python 不声明 image 没被报红：{r.stdout}{r.stderr}')
        self.assertIn('command not found', r.stdout)

    def test_declared_image_passes(self) -> None:
        r = run_guard(PROBE_GOOD, self.tmp)
        self.assertEqual(r.returncode, 0, f'合法形态被误报：{r.stdout}{r.stderr}')

    def test_shell_only_task_passes(self) -> None:
        r = run_guard(PROBE_SHELL_ONLY, self.tmp)
        self.assertEqual(r.returncode, 0, f'纯 shell 任务被误报（判据过宽）：{r.stdout}{r.stderr}')

    def test_var_image_passes(self) -> None:
        r = run_guard(PROBE_VAR_IMAGE, self.tmp)
        self.assertEqual(r.returncode, 0, '${IMG} 形态被误报（守卫不猜运行时值）：' + r.stdout + r.stderr)

    def test_self_check_passes(self) -> None:
        r = subprocess.run(
            [sys.executable, '-c',
             f'import sys; sys.path.insert(0, {str(REPO / "scripts")!r});'
             'import guard_cnb_script_task_python as g;'
             'errs = g.self_check();'
             'print("\\n".join(errs));'
             'sys.exit(1 if errs else 0)'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        self.assertEqual(r.returncode, 0, f'守卫自检失败：{r.stdout}{r.stderr}')

    def test_shadowed_input_is_not_green(self) -> None:
        """重复键遮蔽 ⇒ 必须报红，不得给出「均自带镜像」的假绿灯（源 CNB #463）。"""
        r = run_guard(PROBE_SHADOWED, self.tmp)
        self.assertEqual(
            r.returncode, 1, f'遮蔽输入被放行（假绿灯）：{r.stdout}{r.stderr}'
        )
        self.assertIn('输入不可信', r.stdout)

    def test_real_shadowed_config_turns_red(self) -> None:
        """回退探针：`5633d04c` 那份真实坏配置必须转红（钉不可变 SHA）。"""
        r = subprocess.run(
            ['git', 'show', f'{SHADOWED_SHA}:.cnb.yml'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        self.assertEqual(r.returncode, 0, f'取不到 5633d04c 的 .cnb.yml：{r.stderr}')
        g = run_guard(r.stdout, self.tmp)
        self.assertEqual(
            g.returncode, 1,
            f'重复键的真实坏配置没被转红（守卫在看不见的输入上给了绿）：{g.stdout}{g.stderr}',
        )
        self.assertIn('输入不可信', g.stdout)

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
        self.assertEqual(
            g.returncode, 1, f'修复前的 .cnb.yml 没被守卫转红（判据恒绿）：{g.stdout}{g.stderr}'
        )
        self.assertIn('command not found', g.stdout)


if __name__ == '__main__':
    unittest.main()
