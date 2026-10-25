# -*- coding: utf-8 -*-
"""上游列名契约守卫的回归网（#2543）。

守卫绿 ≠ 守卫有效。本文件用**变异探针**证明每条判据真的会转红——
把修法改回事故形态（摘断言 / 吞异常 / 删常量 / 硬编码列名），守卫必须拦下。

跑法（仓库根）：
    python -m unittest scripts.tests.test_upstream_column_contract -v
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / 'scripts' / 'guard_upstream_column_contract.py'
ADAPTER_REL = Path('backend/app/services/adapters/akshare_adapter.py')
CONTRACT_REL = Path('backend/app/services/adapters/contract.py')

# ── 变异探针：每条对应守卫里的一条判据 ──

# R2：摘掉 assert_columns 调用 → 直接退回「静默空列表」的事故形态
MUT_DROP_ASSERT = (
    """            assert_columns(
                df.columns,
                required=FUND_SCALE_REQUIRED_COLUMNS,
                known=FUND_SCALE_KNOWN_COLUMNS,
                source='akshare.fund_scale_open_sina',
            )
""",
    '            pass\n',
)

# R4：except 分支改回 `return []`（吞掉失败态）
MUT_SWALLOW = (
    """            self.logger.error(f'获取基金规模失败: {e}')
            raise""",
    """            self.logger.error(f'获取基金规模失败: {e}')
            return []""",
)

# R1：删掉模块级必填列常量
MUT_DROP_CONST = (
    "FUND_SCALE_REQUIRED_COLUMNS = ('基金代码', '最近总份额', '单位净值')",
    '# FUND_SCALE_REQUIRED_COLUMNS 被删（探针）',
)

# R3：就地硬编码列名，不再引用契约常量
MUT_HARDCODE = (
    'required=FUND_SCALE_REQUIRED_COLUMNS,',
    "required=('基金代码', '最近总份额', '单位净值'),",
)

# 失败态探针：语法破坏 ⇒ 必须 exit 2，不得退化成「通过」
MUT_SYNTAX = (
    'class AkshareAdapter(DataSourceAdapter):',
    'class AkshareAdapter(DataSourceAdapter:',
)


class _GuardCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='wtcontract-'))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for rel in (ADAPTER_REL, CONTRACT_REL):
            dst = self.tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, dst)

    def run_guard(self):
        p = subprocess.run(
            [sys.executable, str(GUARD), '--root', str(self.tmp)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        return p.returncode, p.stdout + p.stderr

    def mutate(self, old, new):
        f = self.tmp / ADAPTER_REL
        src = f.read_text(encoding='utf-8')
        self.assertIn(old, src, f'探针前提不成立：源码里找不到待变异片段 {old[:48]!r}')
        f.write_text(src.replace(old, new, 1), encoding='utf-8')


class TestGuardPassesOnRealSource(_GuardCase):
    def test_real_source_is_green(self):
        """基线：当前仓库源码必须通过守卫（否则下面的探针毫无意义）。"""
        rc, out = self.run_guard()
        self.assertEqual(rc, 0, out)
        self.assertIn('1/1 个契约达标', out)


class TestMutationProbes(_GuardCase):
    def test_drop_assert_columns_turns_red(self):
        """R2：摘掉契约断言 ⇒ 守卫必须红。"""
        self.mutate(*MUT_DROP_ASSERT)
        rc, out = self.run_guard()
        self.assertEqual(rc, 1, out)
        self.assertIn('R2', out)

    def test_swallow_exception_turns_red(self):
        """R4：把异常吞回 [] ⇒ 守卫必须红（这是本次事故的原形态）。"""
        self.mutate(*MUT_SWALLOW)
        rc, out = self.run_guard()
        self.assertEqual(rc, 1, out)
        self.assertIn('R4', out)

    def test_drop_contract_const_turns_red(self):
        """R1：删掉契约常量 ⇒ 守卫必须红。"""
        self.mutate(*MUT_DROP_CONST)
        rc, out = self.run_guard()
        self.assertEqual(rc, 1, out)
        self.assertIn('R1', out)

    def test_hardcoded_columns_turn_red(self):
        """R3：就地硬编码列名（契约重新散落回函数）⇒ 守卫必须红。"""
        self.mutate(*MUT_HARDCODE)
        rc, out = self.run_guard()
        self.assertEqual(rc, 1, out)
        self.assertIn('R3', out)


class TestFailureModes(_GuardCase):
    def test_missing_file_exits_two(self):
        """拿不到输入 ⇒ exit 2，不得读成「通过」。"""
        (self.tmp / ADAPTER_REL).unlink()
        rc, out = self.run_guard()
        self.assertEqual(rc, 2, out)
        self.assertIn('拿不到输入', out)

    def test_syntax_error_exits_two(self):
        self.mutate(*MUT_SYNTAX)
        rc, out = self.run_guard()
        self.assertEqual(rc, 2, out)


if __name__ == '__main__':
    unittest.main()
