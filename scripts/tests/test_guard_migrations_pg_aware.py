# -*- coding: utf-8 -*-
"""`scripts/guard_migrations_pg_aware.py` 的回归网（#2534）。

## 为什么需要它

该守卫治的是「迁移写成 SQLite-only，本地全绿、生产必崩」——#2469 与 #2532
两次停摆、两次都过了 review。守卫若只在「真实仓库跑一次绿」里活着，下次有人
写个新的「非 SQLite 就跳过」它不响，就等于没有。故每条探针都是**变异**：
把真实源码改坏，确认守卫真的会红。

探针清单（与守卫 `--self-test` 同源，但这里用 unittest 跑，进 CI 的
`python -m unittest discover -s scripts/tests` 通道）：

1. 真实仓库 + 当前基线 → 通过（不误伤）；
2. 往**基线外**函数注入新早退 → 必须报红（治「新写的还会犯」）；
3. 把**基线内**函数的早退改掉（模拟收敛）→ 必须提示收紧基线（治「代码改了
   基线挂着」的半贴合状态）；
4. 基线里塞一个不存在的函数名 → 陈旧条目必须报红；
5. `check()` 拿不到文件 → 返回问题而不是静默通过（「拿不到输入不得当成通过」）。
"""

import importlib.util
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARD_PATH = _REPO_ROOT / 'scripts' / 'guard_migrations_pg_aware.py'
_MIGRATIONS_REL = 'backend/app/core/migrations.py'


def _load_guard():
    spec = importlib.util.spec_from_file_location('guard_migrations_pg_aware', _GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestGuardOnRealRepo(unittest.TestCase):
    def test_real_repo_passes(self):
        problems = _load_guard().check(_REPO_ROOT)
        self.assertEqual(problems, [], f'真实仓库不应有违规：{problems}')


class TestGuardCatchesRegressions(unittest.TestCase):
    """每条探针对应一种「守卫静默失灵」的形态。"""

    @classmethod
    def setUpClass(cls):
        cls.guard = _load_guard()
        cls.real = (_REPO_ROOT / _MIGRATIONS_REL).read_text(encoding='utf-8')

    def test_probe1_new_skip_outside_baseline_is_caught(self):
        """探针 1：基线外函数新写「非 SQLite 就跳过」→ 红（#2532 同款事故）。"""
        mutated = self.guard._inject_new_skip(self.real)
        self.assertNotEqual(mutated, self.real, '探针未命中：文件结构已变')
        problems = self.guard.check_source(mutated)
        self.assertTrue(problems, '注入新早退后守卫未报红')
        self.assertTrue(any('不在' in p and '基线' in p for p in problems), problems)

    def test_probe2_converged_but_baseline_not_tightened_is_caught(self):
        """探针 2：基线内函数的早退已改掉、条目还在 → 红（防基线漂移）。"""
        mutated = self.guard._drop_baseline_skip(self.real)
        self.assertNotEqual(mutated, self.real, '探针未命中：文件结构已变')
        problems = self.guard.check_source(mutated)
        self.assertTrue(any('已无' in p for p in problems), f'未提示收紧基线：{problems}')

    def test_probe3_phantom_baseline_entry_is_caught(self):
        """探针 3：基线里的函数已不存在 → 红（陈旧条目）。"""
        original = self.guard.BASELINE_SKIP_FUNCTIONS
        try:
            self.guard.BASELINE_SKIP_FUNCTIONS = original | {'migrate_does_not_exist_anywhere'}
            problems = self.guard.check_source(self.real)
            self.assertTrue(any('陈旧' in p for p in problems), f'陈旧条目未报红：{problems}')
        finally:
            self.guard.BASELINE_SKIP_FUNCTIONS = original

    def test_probe4_missing_input_is_not_silent_pass(self):
        """探针 4：文件不存在 → 返回问题（拿不到输入不得当成通过）。"""
        problems = self.guard.check(_REPO_ROOT / 'no' / 'such' / 'dir')
        self.assertTrue(problems, '文件缺失时守卫不得静默通过')
        self.assertTrue(any('拿不到输入' in p for p in problems), problems)


if __name__ == '__main__':
    unittest.main()
