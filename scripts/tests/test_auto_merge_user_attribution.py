#!/usr/bin/env python3
"""`scripts/guard_auto_merge_user_attribution.py` 的回归用例（源 #2799）。

## WHY 有这份文件

这条守卫守的是「门禁绿灯、但门禁下游的守卫全哑」——一种**看不出**的失效：
PR 照常自动合入、`质量门禁汇总` 照常 success，但 issue 不再自动关闭、
乱码守卫与 lockfile 守卫在那条路径上从不运行。门禁是绿的，人也就放心了。

所以判据必须把「这条通道用哪个凭据归因」钉死，且每条边界都要有**变异探针**：
把实现改坏（改回 GITHUB_TOKEN、加回落、去掉显式失败），守卫必须转红——
否则守卫本身就是一句「写了但不会发生」的话。

## 怎么跑

    python -m unittest scripts.tests.test_auto_merge_user_attribution -v
    # 或根目录 `pnpm test:scripts`（node --test 只收 *.test.js，本文件走 unittest discover）

依赖：**零新依赖**（只用标准库；被测守卫需要 pyyaml，CI 的 scripts_test 已安装）。
"""

from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.guard_auto_merge_user_attribution import (
    PAT_SECRET,
    WORKFLOW_REL,
    check,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# 一份「正确实现」的 workflow 骨架：所有探针都在它上面做单点变异。
#
# 触发器刻意是 `pull_request` 而非 `pull_request_target`：
# 后者的 workflow 定义**一律取自默认分支**（本仓是 `main`），无视 PR 的 base 分支，
# ⇒ dev 上这份文件里的 PAT 改动根本不会被执行（#2799 的第二层根因）。
# `pull_request` 取 merge commit（dev tip + PR head）⇒ dev 上的改动立刻生效。
GOOD_WORKFLOW = """\
name: PR 自动合并（绿灯即合）

on:
  pull_request:
    types: [opened, synchronize, reopened, labeled]

permissions:
  contents: write
  pull-requests: write

jobs:
  enable-auto-merge:
    runs-on: ubuntu-latest
    if: >-
      github.event.pull_request.base.ref == 'dev' &&
      contains(toJson(github.event.pull_request.labels), 'automerge')
    steps:
      - name: 启用自动合并（门禁转绿即合）
        env:
          GH_TOKEN: ${{ secrets.AUTO_MERGE_PAT }}
          PR_URL: ${{ github.event.pull_request.html_url }}
          HEAD_REPO: ${{ github.event.pull_request.head.repo.full_name }}
          BASE_REPO: ${{ github.repository }}
        run: |
          set -euo pipefail
          if [ "$HEAD_REPO" != "$BASE_REPO" ]; then
            echo "跳过：PR 来自 fork"
            exit 0
          fi
          if [ -z "${GH_TOKEN:-}" ]; then
            echo "::error::未配置 secret AUTO_MERGE_PAT" >&2
            exit 1
          fi
          actor=$(gh api user --jq .login 2>/dev/null || echo "")
          if [ -z "$actor" ]; then
            echo "::error::AUTO_MERGE_PAT 无效或已过期" >&2
            exit 1
          fi
          echo "合并将归因到 $actor"
          if gh pr merge --auto --merge "$PR_URL" 2>/tmp/automerge.err; then
            echo "已启用 auto-merge"
          else
            echo "auto-merge 暂未启用："
            cat /tmp/automerge.err
          fi
"""


class AutoMergeAttributionGuardTest(unittest.TestCase):
    """守卫的判据边界。"""

    def _check_with(self, workflow_text: str):
        """把给定 workflow 放进临时仓，跑守卫，返回违规项列表。"""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            wf = root / WORKFLOW_REL
            wf.parent.mkdir(parents=True, exist_ok=True)
            wf.write_text(textwrap.dedent(workflow_text), encoding='utf-8')
            return check(root)

    # ------------------------------------------------------------------
    # 一、正向：正确的实现必须通过
    # ------------------------------------------------------------------

    def test_正确实现通过(self):
        problems = self._check_with(GOOD_WORKFLOW)
        self.assertEqual(problems, [], f'正确实现不该被判红：{problems}')

    def test_仓库现状文件本身通过(self):
        """守仓库里真实的那个文件——守卫自身跑不过自己等于没装。"""
        problems = check(REPO_ROOT)
        self.assertEqual(problems, [], f'仓库里的 workflow 不该被判红：{problems}')

    # ------------------------------------------------------------------
    # 二、变异探针：把实现改坏，守卫必须转红
    # ------------------------------------------------------------------

    def test_变异_改回GITHUB_TOKEN转红(self):
        """**最核心的一条**：用 GITHUB_TOKEN 启用 auto-merge ⇒ 事件被抑制 ⇒ 假绿。"""
        bad = GOOD_WORKFLOW.replace(
            'GH_TOKEN: ${{ secrets.AUTO_MERGE_PAT }}',
            'GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}',
        )
        problems = self._check_with(bad)
        self.assertTrue(
            any('GITHUB_TOKEN' in p for p in problems),
            f'改回 GITHUB_TOKEN 必须被判红：{problems}',
        )

    def test_变异_加回落转红(self):
        """PAT 与 GITHUB_TOKEN 用 `||` 串起来 ⇒ PAT 缺失时静默退化 ⇒ 假绿复现。"""
        bad = GOOD_WORKFLOW.replace(
            'GH_TOKEN: ${{ secrets.AUTO_MERGE_PAT }}',
            'GH_TOKEN: ${{ secrets.AUTO_MERGE_PAT || secrets.GITHUB_TOKEN }}',
        )
        problems = self._check_with(bad)
        self.assertTrue(
            any('||' in p for p in problems),
            f'含 `||` 回落必须被判红：{problems}',
        )

    def test_变异_完全没设token转红(self):
        bad = GOOD_WORKFLOW.replace(
            '          GH_TOKEN: ${{ secrets.AUTO_MERGE_PAT }}\n', ''
        )
        problems = self._check_with(bad)
        self.assertTrue(
            any('GH_TOKEN' in p for p in problems),
            f'没设 token 必须被判红：{problems}',
        )

    def test_变异_删掉显式失败路径转红(self):
        """PAT 缺失若不失败，会被当成「PR 有冲突」一直重试，直到没人发现合并从不发生。

        两种实现路径都算「未拦截」：整段删掉（没有空值检查）、
        或保留检查但把 `exit 1` 换成不失败的写法（检查形同虚设）。
        """
        for bad, why in (
            (
                GOOD_WORKFLOW.replace(
                    """          if [ -z "${GH_TOKEN:-}" ]; then
            echo "::error::未配置 secret AUTO_MERGE_PAT" >&2
            exit 1
          fi
""",
                    '',
                ),
                '整段删掉空值检查',
            ),
            (
                GOOD_WORKFLOW.replace(
                    '            exit 1\n          fi\n          actor=',
                    '            echo "缺少 PAT，继续"\n          fi\n          actor=',
                ),
                '保留检查但去掉硬失败',
            ),
        ):
            with self.subTest(why=why):
                problems = self._check_with(bad)
                self.assertTrue(
                    any(('显式失败' in p) or ('GH_TOKEN 是否为空' in p) for p in problems),
                    f'{why} 必须被判红：{problems}',
                )

    def test_变异_删掉归因说明转红(self):
        """配置回潮时（后人顺手改回 GITHUB_TOKEN）没有线索可循 ⇒ 必须留说明。"""
        bad = GOOD_WORKFLOW.replace('echo "合并将归因到 $actor"', 'echo "ok"')
        problems = self._check_with(bad)
        self.assertTrue(
            any('归因' in p for p in problems),
            f'删掉归因说明必须被判红：{problems}',
        )

    def test_变异_删掉gh_pr_merge转红(self):
        """没有 gh pr merge ⇒ 自动合并通道没有入口（#564 同族）。"""
        bad = GOOD_WORKFLOW.replace('gh pr merge --auto --merge "$PR_URL"', 'echo "nothing"')
        problems = self._check_with(bad)
        self.assertTrue(
            any('gh pr merge' in p for p in problems),
            f'删掉 gh pr merge 必须被判红：{problems}',
        )

    def test_变异_把gh_pr_merge藏进注释转红(self):
        """注释里提到 `gh pr merge` 不算命中——否则守卫被自己的说明文字骗过去。"""
        bad = GOOD_WORKFLOW.replace(
            'if gh pr merge --auto --merge "$PR_URL" 2>/tmp/automerge.err; then',
            '# 曾经是 gh pr merge --auto --merge "$PR_URL"\n          if true; then',
        )
        problems = self._check_with(bad)
        self.assertTrue(
            any('gh pr merge' in p for p in problems),
            f'注释里的 gh pr merge 不该算命中：{problems}',
        )

    # ------------------------------------------------------------------
    # 二之二、第二层根因：触发器不得是 pull_request_target
    # ------------------------------------------------------------------

    def test_变异_触发器改回pull_request_target转红(self):
        """**第二层根因**：pull_request_target 的定义只取自默认分支（main），无视 base 分支。

        于是 dev 上这份文件里的 PAT 改动、守卫、日志全部不会被执行——
        跑的还是 main 上那份旧版（仍用 secrets.GITHUB_TOKEN ⇒ 事件仍被抑制）。
        守卫必须拦住这个形态，否则第一层修复就是个「写了但不会发生」的话。
        """
        bad = GOOD_WORKFLOW.replace(
            '  pull_request:\n    types: [opened, synchronize, reopened, labeled]',
            '  pull_request_target:\n    types: [opened, synchronize, reopened, labeled]',
        )
        problems = self._check_with(bad)
        self.assertTrue(
            any('pull_request_target' in p for p in problems),
            f'改回 pull_request_target 必须被判红：{problems}',
        )

    def test_变异_两个触发器并存转红(self):
        """并存时也要判红：`pull_request_target` 那一路仍会跑默认分支上的定义。"""
        bad = GOOD_WORKFLOW.replace(
            '  pull_request:\n    types: [opened, synchronize, reopened, labeled]',
            '  pull_request_target:\n  pull_request:\n'
            '    types: [opened, synchronize, reopened, labeled]',
        )
        problems = self._check_with(bad)
        self.assertTrue(
            any('pull_request_target' in p for p in problems),
            f'两个触发器并存必须被判红：{problems}',
        )

    def test_变异_触发器整个删掉转红(self):
        bad = GOOD_WORKFLOW.replace(
            'on:\n  pull_request:\n    types: [opened, synchronize, reopened, labeled]',
            'on: []',
        )
        problems = self._check_with(bad)
        self.assertTrue(
            any('触发器' in p for p in problems),
            f'触发器缺失必须被判红：{problems}',
        )

    def test_变异_删掉fork跳过分支转红(self):
        """fork 的 pull_request 拿不到 secrets ⇒ 不显式跳过就会误报成「没配 PAT」而误红。"""
        bad = GOOD_WORKFLOW.replace(
            """          if [ "$HEAD_REPO" != "$BASE_REPO" ]; then
            echo "跳过：PR 来自 fork"
            exit 0
          fi
""",
            '',
        )
        problems = self._check_with(bad)
        self.assertTrue(
            any('fork' in p for p in problems),
            f'删掉 fork 跳过分支必须被判红：{problems}',
        )

    def test_变异_fork分支只打提示不退出转红(self):
        """只打一行提示然后继续 ⇒ 拿着空的 GH_TOKEN 去调 gh pr merge ⇒ 报错含糊、语义被掩盖。"""
        bad = GOOD_WORKFLOW.replace(
            '            echo "跳过：PR 来自 fork"\n            exit 0',
            '            echo "跳过：PR 来自 fork"',
        )
        problems = self._check_with(bad)
        self.assertTrue(
            any('fork' in p for p in problems),
            f'fork 分支不显式退出必须被判红：{problems}',
        )

    def test_变异_fork判定写在注释里转红(self):
        """注释里提到 fork 不算——守卫不能被自己的说明文字骗过去。"""
        bad = GOOD_WORKFLOW.replace(
            """          if [ "$HEAD_REPO" != "$BASE_REPO" ]; then
            echo "跳过：PR 来自 fork"
            exit 0
          fi
""",
            '          # 若 HEAD_REPO != BASE_REPO 则跳过 fork PR\n',
        )
        problems = self._check_with(bad)
        self.assertTrue(
            any('fork' in p for p in problems),
            f'注释里的 fork 判定不该算命中：{problems}',
        )

    # ------------------------------------------------------------------
    # 三、输入不可信时不得当成通过
    # ------------------------------------------------------------------

    def test_文件不存在时判红(self):
        with TemporaryDirectory() as tmp:
            problems = check(Path(tmp))
            self.assertTrue(problems, 'workflow 缺失必须判红，不得当成通过')

    def test_YAML坏了时判红(self):
        bad = GOOD_WORKFLOW + "\n  bad: [unclosed\n"
        problems = self._check_with(bad)
        self.assertTrue(problems, 'YAML 解析失败必须判红（结论不可信不得当成通过）')


class AutoMergeAttributionGuardConstantsTest(unittest.TestCase):
    """常量本身不能被后人改歪。"""

    def test_PAT_secret名固定(self):
        self.assertEqual(PAT_SECRET, 'AUTO_MERGE_PAT')

    def test_工作流路径固定(self):
        self.assertEqual(WORKFLOW_REL, '.github/workflows/pr-auto-merge.yml')


if __name__ == '__main__':
    unittest.main()
