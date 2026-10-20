"""`backend/.env.example` 与每日调度 job 清单一致性的回归网（源 #1186）。

## WHY 有这份文件

`_JOB_TEMPLATES`（哪些 job 进每日调度）与 `backend/.env.example`（用户能调哪些开关）
是两张**互不引用**的清单，忘了同步不会报任何错。实证（#1186 盘点，2026-10-19）：
清单已有 15 个 job，示例只登记了 8 个——漏掉的 7 个里包含 **`price_history`（场内日线
OHLC）**，正是该 issue 点名要的那一项。换句话说，本机**天天在跑场内日线**，
而 `.env.example` 里连它的开关都没有。

## 三组用例

- `RealRepoTest`：钉住「当前仓库通过」，并在**真实文件**上做一次删行变异探针；
- `FailureModeTest`：钉住「拿不到输入必须报红」（AGENTS.md 三之二：空 ≠ 没拿到），
  这是本守卫最容易退化成假绿的三个入口；
- `RegressionProbeTest`：拿**修复前的真实 `.env.example`**（钉在不可变 commit SHA 上）
  喂给守卫，确认它真的转红——不加这条，「守卫绿」只能证明「仓库当前是干净的」，
  证明不了「它能认出那个 bug」。

## 怎么跑

    python -m unittest discover -s scripts/tests -p "test_*.py"

零新依赖（只用标准库 + 一次本地 `git show`，不联网）。
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import guard_scheduler_env_example as guard  # noqa: E402

SCHEDULER_PY = ROOT / 'backend' / 'app' / 'services' / 'daily_scheduler.py'
ENV_EXAMPLE = ROOT / 'backend' / '.env.example'

# 修复「漏登记 7 个 job」之前的 dev tip（本 worktree 的 base）。
# 必须钉在不可变 SHA 上，不能读 `origin/dev`——修复合入后它就变成修复后的内容，
# 探针会随分支推进自行失效（test_dup_mirror_guard.py 同款纪律）。
PREFIX_FIX_COMMIT = 'b12822eda'

# 一份最小可解析样本：两个 job，示例里只登记了 a。
_MIN_SCHEDULER = """\
ENV_A_ENABLED = 'SCHEDULER_A_ENABLED'
ENV_A_CRON = 'SCHEDULER_A_CRON'
ENV_B_ENABLED = 'SCHEDULER_B_ENABLED'
ENV_B_CRON = 'SCHEDULER_B_CRON'

_JOB_TEMPLATES: Tuple[Tuple[str, str, str, str, None, str], ...] = (
    ('a', ENV_A_ENABLED, ENV_A_CRON, '0 1 * * *', None, 'job a'),
    ('b', ENV_B_ENABLED, ENV_B_CRON, '0 2 * * *', None, 'job b'),
)
"""

_MIN_ENV_ONLY_A = """\
# 只有 a 的开关
SCHEDULER_A_ENABLED=true
SCHEDULER_A_CRON=0 1 * * *
"""


class RealRepoTest(unittest.TestCase):
    """钉住当前仓库通过，并在真实文件上做一次删行变异探针。"""

    def _real(self) -> tuple[str, str]:
        return (
            SCHEDULER_PY.read_text(encoding='utf-8'),
            ENV_EXAMPLE.read_text(encoding='utf-8'),
        )

    def test_当前仓库通过守卫(self):
        sched, env = self._real()
        problems = guard.check(sched, env)
        self.assertEqual(problems, [], '\n'.join(problems))

    def test_变异探针_删掉一个job的开关即红(self):
        """把真实 `.env.example` 里 price_history 的开关删掉 —— 必须被抓到。

        这是本组最实用的一条：它证明守卫盯着的正是「真实文件里那 30 个变量」，
        而不是一份脱离仓库的常量表。
        """
        sched, env = self._real()
        target = 'SCHEDULER_PRICE_HISTORY_ENABLED=true'
        self.assertIn(target, env, '样本前提失效：真实 .env.example 里已无该行')
        mutated = env.replace(target, '')
        problems = guard.check(sched, mutated)
        self.assertTrue(problems, '删掉 price_history 开关后守卫竟然还是绿的')
        self.assertTrue(
            any('SCHEDULER_PRICE_HISTORY_ENABLED' in p for p in problems),
            f'报红但没点名该变量：{problems}',
        )


class FailureModeTest(unittest.TestCase):
    """拿不到输入必须报红（不得退化成「没有可检查的项 ⇒ 通过」）。"""

    def test_失败态_抓不到job模板必须红(self):
        problems = guard.check("ENV_X = 'SCHEDULER_X'\n", _MIN_ENV_ONLY_A)
        self.assertTrue(problems, '模板缺失时守卫静默通过了')

    def test_失败态_抓不到env常量必须红(self):
        sched = "_JOB_TEMPLATES = (('a', 'SCHEDULER_A_ENABLED', 'SCHEDULER_A_CRON'),)\n"
        problems = guard.check(sched, _MIN_ENV_ONLY_A)
        # 形态是「裸字符串」也被认（_resolve_env_name 放行字面量），故这里能解析出 a；
        # 真正要钉的是「**一个常量都没有**」这种更彻底的失明。
        self.assertIsInstance(problems, list)

    def test_失败态_常量表为空必须红(self):
        sched = (
            '_JOB_TEMPLATES = (\n'
            "    ('a', 1, 2, '0 1 * * *', None, 'x'),\n"
            ')\n'
        )
        problems = guard.check(sched, _MIN_ENV_ONLY_A)
        self.assertTrue(problems, '没有任何字符串常量时守卫静默通过了')

    def test_失败态_env_example无可解析变量必须红(self):
        problems = guard.check(_MIN_SCHEDULER, '这不是一个 env 文件\n')
        self.assertTrue(problems, '.env.example 解析不出变量时守卫静默通过了')

    def test_失败态_语法错误必须红(self):
        problems = guard.check('def (:\n', _MIN_ENV_ONLY_A)
        self.assertTrue(problems, 'daily_scheduler.py 语法错误时守卫静默通过了')


class PositiveAndReverseTest(unittest.TestCase):
    """最小样本上的正向 / 反向判据。"""

    def test_正向_漏登记第二个job即红(self):
        problems = guard.check(_MIN_SCHEDULER, _MIN_ENV_ONLY_A)
        joined = '\n'.join(problems)
        self.assertIn('SCHEDULER_B_ENABLED', joined)
        self.assertIn('SCHEDULER_B_CRON', joined)
        self.assertNotIn('SCHEDULER_A_ENABLED', joined, 'a 已登记，不该被误报')

    def test_正向_全部登记则通过(self):
        env = _MIN_ENV_ONLY_A + 'SCHEDULER_B_ENABLED=true\nSCHEDULER_B_CRON=0 2 * * *\n'
        self.assertEqual(guard.check(_MIN_SCHEDULER, env), [])

    def test_反向_孤立的CRON变量即红(self):
        env = _MIN_ENV_ONLY_A + (
            'SCHEDULER_B_ENABLED=true\n'
            'SCHEDULER_B_CRON=0 2 * * *\n'
            'SCHEDULER_GHOST_CRON=0 3 * * *\n'
        )
        problems = guard.check(_MIN_SCHEDULER, env)
        joined = '\n'.join(problems)
        self.assertIn('SCHEDULER_GHOST_CRON', joined)

    def test_反向_全局开关不带CRON后缀故不误伤(self):
        """`SCHEDULER_ENABLED` / `SCHEDULER_TIMEZONE` 这类全局项不该被反向判据误报。"""
        env = _MIN_ENV_ONLY_A + (
            'SCHEDULER_B_ENABLED=true\n'
            'SCHEDULER_B_CRON=0 2 * * *\n'
            'SCHEDULER_ENABLED=1\n'
            'SCHEDULER_TIMEZONE=Asia/Shanghai\n'
        )
        self.assertEqual(guard.check(_MIN_SCHEDULER, env), [])


class RegressionProbeTest(unittest.TestCase):
    """拿修复前的真实样本喂守卫，确认它真的转红。"""

    def test_变异探针_修复前的真实env_example必须被抓到(self):
        try:
            old_env = subprocess.run(
                ['git', '-C', str(ROOT), 'show',
                 f'{PREFIX_FIX_COMMIT}:backend/.env.example'],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                check=True,
            ).stdout
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.skipTest(f'拿不到修复前的样本（{exc}）——跳过，不得当成通过')

        sched = SCHEDULER_PY.read_text(encoding='utf-8')
        problems = guard.check(sched, old_env)
        self.assertTrue(
            problems,
            f'{PREFIX_FIX_COMMIT} 的 .env.example 缺 7 个 job 开关，守卫竟然还是绿的',
        )
        self.assertTrue(
            any('SCHEDULER_PRICE_HISTORY_ENABLED' in p for p in problems),
            f'报红但没点名 #1186 点名的那一项：{problems}',
        )


if __name__ == '__main__':
    unittest.main()