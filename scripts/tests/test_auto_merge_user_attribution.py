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
GOOD_WORKFLOW = """\
name: PR 自动合并（绿灯即合）

on:
  pull_request_target:
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
        run: |
          set -euo pipefail
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
