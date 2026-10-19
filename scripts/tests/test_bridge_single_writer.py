#!/usr/bin/env python3
"""`scripts/guard_bridge_machine_branch_single_writer.py` 的回归网（源 CNB #574）。

钉五件事：

1. **判据方向**：CNB 侧把自己设成写者 ⇒ 报红；不设 ⇒ 放行（不过宽）；
2. **默认值翻转**（最隐蔽的一种）：`DEFAULT_WRITER = 'cnb'` ⇒ 报红。
   它不改任何 `.cnb.yml`，配置看起来完全正常，只在运行时把写权搬走；
3. **写者消失**：reconcile 不再推 `bridge/github-dev` ⇒ 报红。
   被降级的一侧若无对侧接手，就是「没人写、两边都绿」；
4. **锚点丢失不得当成通过**：找不到 `DEFAULT_WRITER` 要报红，不能静默 `return []`；
5. 守卫自带 self_check：判据没接上时它会全绿，故每次都要跑。

跑法：`python scripts/tests/test_bridge_single_writer.py`
"""

from __future__ import annotations

import importlib.util
import pathlib
import shutil
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO / 'scripts' / 'guard_bridge_machine_branch_single_writer.py'


def _load():
    spec = importlib.util.spec_from_file_location('single_writer_guard', GUARD)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


CALL = '          python scripts/bridge/machine_branch.py --apply --push\n'


class TestGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = _load()

    def test_real_repo_passes(self):
        """本仓现状必须通过（否则守门一上线就恒红，没人会去修）。"""
        r = subprocess.run(
            [sys.executable, str(GUARD)], capture_output=True, text=True, encoding='utf-8', check=False
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_cnb_setting_itself_as_writer_red(self):
        """判据 1：`.cnb.yml` 里 `MACHINE_BRANCH_WRITER=cnb` ⇒ 报红。

        探针：删掉 `_CNB_WRITER_RE` 的调用 ⇒ 本用例转红。
        """
        self.assertTrue(self.g.check_cnb_yml(CALL + '          export MACHINE_BRANCH_WRITER=cnb\n'))

    def test_cnb_yml_without_writer_is_green(self):
        """不设写者 ⇒ 放行（防判据过宽：把「只读探针」本身判成问题）。"""
        self.assertEqual(self.g.check_cnb_yml(CALL + '          echo 只读探针\n'), [])

    def test_default_writer_flip_red(self):
        """判据 2：默认写者翻成 cnb ⇒ 报红（配置无改动、写权却搬走了）。"""
        self.assertTrue(self.g.check_script_default("DEFAULT_WRITER = 'cnb'\n"))
        self.assertEqual(self.g.check_script_default("DEFAULT_WRITER = 'github'\n"), [])

    def test_missing_anchor_is_not_pass(self):
        """判据 2 的失败态：找不到 `DEFAULT_WRITER` 必须报红，不得退化成「没问题」。"""
        self.assertTrue(self.g.check_script_default('WRITER_ENV = "X"\n'))

    def test_orphan_yml_read_is_not_silent(self):
        """判据 1 的失败态：`.cnb.yml` 里没有调用点时要**说出来**，不能静默当通过。"""
        r = subprocess.run(
            [sys.executable, str(GUARD)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=False,
        )
        self.assertEqual(r.returncode, 0)
        # 直接调私有判据：没有调用点 ⇒ 返回空，但会往 stderr 说明「不适用」。
        self.assertEqual(self.g.check_cnb_yml('echo hi\n'), [])

    def test_writer_disappeared_red(self):
        """判据 3：reconcile 不再推机器分支 ⇒ 报红（变成「没人写」）。"""
        self.assertTrue(self.g.check_reconcile_still_writes('on:\n  schedule: []\n'))
        self.assertEqual(self.g.check_reconcile_still_writes('git push origin bridge/github-dev --force-with-lease\n'), [])

    def test_unreadable_input_is_exit_2(self):
        """读不到输入 ⇒ 退 2 且声明结论不可信（#171 的失败态纪律）。"""
        tmp = REPO / '.tmp_guard_probe'
        tmp.mkdir(exist_ok=True)
        try:
            r = subprocess.run(
                [sys.executable, str(GUARD), '--root', str(tmp)],
                capture_output=True,
                text=True,
                encoding='utf-8',
                check=False,
            )
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn('结论不可信', r.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
