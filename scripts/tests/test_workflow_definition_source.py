#!/usr/bin/env python3
"""workflow 定义来源守卫的回归网（#2803）。

本文件是 `scripts/guard_workflow_definition_source.py` 的变异探针集。
每个用例都在一份**最小骨架**上做**单点变异**，验证守卫真的会红（或不该红）。

为什么要有这一层：守卫最危险的失败模式不是「误报」而是**「漏报但自己绿」**——
判据写错了、或者注释里的说明文字把守卫骗过去，它照样 success，
于是「以为钉住了」实际没钉住。本仓判据被自己的说明文字咬过多次
（`guard_schedule_checkout_ref.py` 记在案），故每个判据都必须有对应的变异探针。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_REL = 'scripts/guard_workflow_definition_source.py'

# 一份「正确实现」的 workflow 骨架：所有探针都在它上面做单点变异。
# 刻意选 `pr-four-questions-guard.yml`——它执行仓库里的守卫脚本，
# 正是「必须显式 ref: dev」那一条判据的适用范围。
GUARD_WF = 'pr-four-questions-guard.yml'

GOOD_WORKFLOW = """\
name: PR 四问格式守卫

on:
  pull_request:
    types: [opened, edited, reopened, ready_for_review]

permissions:
  contents: read
  pull-requests: read

jobs:
  four-questions:
    name: 四问格式检查
    runs-on: ubuntu-latest
    steps:
      - name: 检出守卫脚本（不检出 PR 代码）
        uses: actions/checkout@v4
        with:
          ref: dev
          sparse-checkout: scripts
          sparse-checkout-cone-mode: false

      - name: 判定
        run: node scripts/guard_pr_four_questions.mjs
"""


class GuardWorkflowDefinitionSourceTest(unittest.TestCase):
    """变异探针集：每个用例验证守卫的一处判据。"""

    def _run_guard(self, workflow_text: str, filename: str = GUARD_WF):
        """在临时目录里放一份 workflow + 守卫脚本，跑守卫，返回 (退出码, 输出)。"""
        tmp = Path(tempfile.mkdtemp(prefix='wf_def_src_'))
        try:
            (tmp / '.github/workflows').mkdir(parents=True)
            (tmp / '.github/workflows' / filename).write_text(workflow_text, encoding='utf-8')
            shutil.copytree(REPO_ROOT / 'scripts', tmp / 'scripts')
            proc = subprocess.run(
                [sys.executable, str(tmp / 'scripts' / Path(GUARD_REL).name)],
                capture_output=True, text=True, cwd=str(tmp),
            )
            return proc.returncode, proc.stdout
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ── 判据 1：不得有 pull_request_target ────────────────────────────────

    def test_变异_触发器改回pull_request_target转红(self):
        """把触发器改回 `pull_request_target` ⇒ 判红。"""
        bad = GOOD_WORKFLOW.replace('  pull_request:', '  pull_request_target:')
        code, out = self._run_guard(bad)
        self.assertEqual(code, 1, f'应判红，实际退出码 {code}：\n{out}')
        self.assertIn('pull_request_target', out)

    def test_变异_触发器全删不转红但退出守卫生效(self):
        """触发器全删 ⇒ **不该**由本守卫判红。

        本守卫守的是「定义被锁死在默认分支」，而 `on: []` 的问题是
        「这个工作流没有入口」——那是另一类缺陷，不该由这条守卫越界去管
        （守卫越界 = 误报 = 让人开始无视它）。

        但它确实暴露了一个**真实缺口**：没有 `pull_request` 触发器的工作流
        会悄悄退出本守卫的视野。这不是本守卫该管的（见上），
        但必须由**另一条**判据兜住——本仓已有 `guard_workflow_inputs_interpolation`
        等守卫覆盖 workflow 的结构完整性，不在此重复实现。
        """
        bad = GOOD_WORKFLOW.replace(
            'on:\n  pull_request:\n    types: [opened, edited, reopened, ready_for_review]\n',
            'on: []\n',
        )
        code, out = self._run_guard(bad)
        self.assertEqual(code, 0, f'触发器全删不属于本守卫判据范围：\n{out}')

    def test_注释里提到pull_request_target不转红(self):
        """注释里说明「为什么不用 pull_request_target」不该被判红。

        这条是本仓判据最容易被咬的地方：文件头那段解释若被当成命中，
        守卫就会对自己的说明文字报错——那等于让人没法写清楚「为什么」。
        """
        text = '# 本文件刻意不用 pull_request_target，因为它的定义只取默认分支。\n' + GOOD_WORKFLOW
        code, out = self._run_guard(text)
        self.assertEqual(code, 0, f'注释里的 pull_request_target 不该算命中：\n{out}')

    def test_注释里藏着pull_request_target触发器不转红(self):
        """把 `pull_request_target:` 写在注释行上 —— YAML 解析后不是真触发器。"""
        text = GOOD_WORKFLOW.replace(
            'on:\n  pull_request:',
            'on:\n  pull_request:\n  # pull_request_target:\n    # types: [opened]',
        )
        code, out = self._run_guard(text)
        self.assertEqual(code, 0, f'注释里的触发器不该算命中：\n{out}')

    # ── 判据 2：守卫类工作流的 checkout 必须显式 ref ──────────────────────

    def test_变异_删掉ref转红(self):
        """删掉 `ref: dev` ⇒ 判红。

        这是迁移最容易漏的一处：`pull_request` 下 checkout 默认检出 merge commit
        （含 PR 代码），PR 作者就能改掉自己的守卫脚本。
        """
        bad = GOOD_WORKFLOW.replace('          ref: dev\n', '')
        code, out = self._run_guard(bad)
        self.assertEqual(code, 1, f'应判红，实际退出码 {code}：\n{out}')
        self.assertIn('with.ref', out)

    def test_变异_ref改成默认分支转红(self):
        """`ref: main` ⇒ 判红（检出的还是默认分支上那份旧代码）。"""
        bad = GOOD_WORKFLOW.replace('ref: dev', 'ref: main')
        code, out = self._run_guard(bad)
        self.assertEqual(code, 1, f'应判红，实际退出码 {code}：\n{out}')

    def test_变异_ref指向PR自己分支转红(self):
        """`ref: ${{ github.event.pull_request.head.ref }}` ⇒ 判红。

        那等于把执行内容完全交给 PR 作者。
        """
        bad = GOOD_WORKFLOW.replace(
            'ref: dev',
            'ref: ${{ github.event.pull_request.head.ref }}',
        )
        code, out = self._run_guard(bad)
        self.assertEqual(code, 1, f'应判红，实际退出码 {code}：\n{out}')

    def test_变异_ref指向github_head_ref转红(self):
        """`ref: ${{ github.head_ref }}` ⇒ 判红（同上，另一种写法）。"""
        bad = GOOD_WORKFLOW.replace('ref: dev', 'ref: ${{ github.head_ref }}')
        code, out = self._run_guard(bad)
        self.assertEqual(code, 1, f'应判红，实际退出码 {code}：\n{out}')

    def test_变异_表达式ref放行(self):
        """`ref: ${{ env.X }}` 这类表达式放行——静态判据不该猜运行时取值。

        与 `guard_schedule_checkout_ref.py` 的口径一致。
        """
        ok = GOOD_WORKFLOW.replace('ref: dev', 'ref: ${{ env.SOMETHING }}')
        code, out = self._run_guard(ok)
        self.assertEqual(code, 0, f'表达式 ref 不该判红：\n{out}')

    # ── 判据 4：concurrency.group 必须带过渡期后缀 ──────────────────
    #
    # 判据要防的故障（实测 PR #2807）：过渡期内 `main` 旧版（pull_request_target）
    # 与 `dev` 新版（pull_request）同时触发，若 group 名相同 ⇒
    # `cancel-in-progress: true` 的一方把另一方取消 ⇒ 新版挂在 PR head 上的
    # check 被 cancelled ⇒ GitHub 记成 check 失败 ⇒ PR 假红。
    # ⚠️ 只把新版改成 `cancel-in-progress: false` 不够——取消是旧版发起的。
    # ⇒ 唯一可靠的修法是**让两者的 group 名不同**。

    def test_变异_group名缺过渡期后缀转红(self):
        """group 名与 `main` 旧版相同（无过渡期后缀）⇒ 判红。"""
        wf = GOOD_WORKFLOW.replace(
            'jobs:',
            'concurrency:\n  group: pr-four-questions-guard-${{ github.event.pull_request.number }}\n'
            '  cancel-in-progress: false\n\njobs:',
        )
        code, out = self._run_guard(wf)
        self.assertEqual(code, 1, f'应判红，实际退出码 {code}：\n{out}')
        self.assertIn('过渡期后缀', out)

    def test_变异_group名带过渡期后缀不转红(self):
        """group 名带 `-pr-` 过渡期后缀 ⇒ 不该判红（新旧两组并存，互不取消）。"""
        wf = GOOD_WORKFLOW.replace(
            'jobs:',
            'concurrency:\n  group: pr-four-questions-guard-pr-${{ github.event.pull_request.number }}\n'
            '  cancel-in-progress: false\n\njobs:',
        )
        code, out = self._run_guard(wf)
        self.assertEqual(code, 0, f'带过渡期后缀不该判红：\n{out}')

    def test_变异_group名带后缀且cancel为true不转红(self):
        """带后缀时，`cancel-in-progress: true` 也不该判红。

        判据盯的是**group 名是否与旧版撞车**，不是 `cancel-in-progress` 的取值：
        撞车了才需要后缀；不撞车时 `cancel-in-progress: true` 是正常的去重语义
        （同一 PR 的连续事件互相取消，正是 `issue-claim-sync` 想要的串行行为）。
        """
        wf = GOOD_WORKFLOW.replace(
            'jobs:',
            'concurrency:\n  group: pr-four-questions-guard-pr-${{ github.event.pull_request.number }}\n'
            '  cancel-in-progress: true\n\njobs:',
        )
        code, out = self._run_guard(wf)
        self.assertEqual(code, 0, f'带后缀时不该判红：\n{out}')

    def test_变异_无concurrency段不转红(self):
        """没有 `concurrency` 段 ⇒ 不该判红（没有互斥，也就没有互斥风险）。

        `pr-overlap-guard` / `pr-auto-rebase` / `pr-auto-merge` 三家在 `main`
        旧版上就没有 concurrency ⇒ 它们不存在「被静默取消」这个故障。
        代价是**副作用会重复**（重复评论 / 重复 force-push），那靠后缀解决不了
        （后缀只能分开新版彼此，不能让旧版消失），只能等发版自然消失。
        """
        code, out = self._run_guard(GOOD_WORKFLOW)
        self.assertEqual(code, 0, f'无 concurrency 段不该判红：\n{out}')

    def test_变异_concurrency有段但无group转红(self):
        """有 `concurrency` 段却没有 `group` ⇒ 判红（判据无从判断，需显式表态）。

        形态：`concurrency:` 下只有 `cancel-in-progress`，没有 `group`。
        这时无法判断它是否与旧版撞车 ⇒ 要求写清（要么给 group，要么整段删掉）。
        """
        wf = GOOD_WORKFLOW.replace(
            'jobs:',
            'concurrency:\n  cancel-in-progress: false\n\njobs:',
        )
        code, out = self._run_guard(wf)
        self.assertEqual(code, 1, f'应判红，实际退出码 {code}：\n{out}')
        self.assertIn('没有 `group`', out)

    def test_变异_concurrency字符串简写缺后缀转红(self):
        """`concurrency: 名字` 这种字符串简写也要判（不能只认字典形态）。

        YAML 允许 `concurrency: my-group`；守卫若只处理字典形态，
        就会在这种写法上**静默放行**——那正是本守卫要防的失败模式
        （「以为钉住了」实际没钉住）。
        """
        wf = GOOD_WORKFLOW.replace(
            'jobs:',
            'concurrency: pr-four-questions-guard-${{ github.event.pull_request.number }}\n\njobs:',
        )
        code, out = self._run_guard(wf)
        self.assertEqual(code, 1, f'应判红，实际退出码 {code}：\n{out}')
        self.assertIn('过渡期后缀', out)

    def test_变异_concurrency字符串简写带后缀不转红(self):
        """字符串简写 + 带后缀 ⇒ 不该判红。"""
        wf = GOOD_WORKFLOW.replace(
            'jobs:',
            'concurrency: pr-four-questions-guard-pr-${{ github.event.pull_request.number }}\n\njobs:',
        )
        code, out = self._run_guard(wf)
        self.assertEqual(code, 0, f'字符串简写带后缀不该判红：\n{out}')

    # ── 边界：CI 类工作流检出 PR 代码是职责所在，不该判红 ────────────────

    def test_CI类工作流检出PR代码不转红(self):
        """`ci.yml` 这类 CI 工作流检出 PR 代码**不该**被判红。

        CI 的职责就是测 PR 的代码；要求它写 `ref: dev` 反而会让 CI 测错东西。
        这条用例守住守卫的判据边界，防止它日后膨胀成「全仓所有 pull_request
        都得写 ref」的过度判据。
        """
        ci = """\
name: 质量门禁 CI

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - run: pytest
"""
        code, out = self._run_guard(ci, filename='ci.yml')
        self.assertEqual(code, 0, f'CI 类工作流不该判红：\n{out}')

    # ── 豁免机制：依赖 bot 触发的两个工作流可合法保留 pull_request_target ──

    def test_依赖bot工作流保留pull_request_target不转红(self):
        """`dependabot-auto-merge.yml` 保留 `pull_request_target` ⇒ **不该**判红。

        它由依赖 bot 触发，而 GitHub 把 Dependabot 的 PR **按 fork 对待**
        （官方文档：*"Workflows triggered by Dependabot pull requests are treated as
        though they are from a forked repository"*）⇒ `pull_request` 下 token 只读、
        `gh pr merge --auto` 必然失败 ⇒ 它**必须**留在 `pull_request_target`。
        """
        wf = """\
name: Dependabot Auto Merge

on:
  pull_request_target:
    types: [opened, synchronize, reopened]

permissions:
  contents: write
  pull-requests: write

jobs:
  auto-merge:
    runs-on: ubuntu-latest
    if: github.actor == 'dependabot[bot]'
    steps:
      - run: gh pr merge --auto --squash "$PR_URL"
"""
        code, out = self._run_guard(wf, filename='dependabot-auto-merge.yml')
        self.assertEqual(code, 0, f'依赖 bot 工作流保留 pull_request_target 不该判红：\n{out}')

    def test_豁免项被迁走后守卫要求删豁免(self):
        """豁免项若被迁到 `pull_request`（不再用 `pull_request_target`），
        守卫要求把这条豁免删掉——否则豁免清单会变成藏污纳垢的地方。

        这条用例验证「豁免清单自身也被治理」，而不只是「豁免能生效」。
        """
        sys.path.insert(0, str(REPO_ROOT))
        try:
            from scripts.guard_workflow_definition_source import (
                _GUARD_WORKFLOWS, _PRT_EXEMPT, check,
            )
        finally:
            sys.path.pop(0)

        # 构造一个「已迁移但豁免还在」的假想状态：把 _PRT_EXEMPT 里的某个名字
        # 指向一个仓库里**不存在**的文件名（模拟被迁走后文件仍登记豁免）。
        # 守卫对「豁免项不在 _GUARD_WORKFLOWS 里」没有独立判据——本用例改为
        # 断言「豁免清单里的每个条目都必须在 _GUARD_WORKFLOWS 里」这条不变式。
        self.assertTrue(
            set(_PRT_EXEMPT).issubset(set(_GUARD_WORKFLOWS)),
            f'豁免清单的每个条目都必须在 _GUARD_WORKFLOWS 里（否则它的 checkout '
            f'不受判据 2 约束）：豁免={sorted(_PRT_EXEMPT)} '
            f'守卫清单={sorted(_GUARD_WORKFLOWS)}',
        )

    def test_豁免清单里的文件都存在(self):
        """豁免清单里的文件必须真实存在（否则豁免指向空气）。"""
        sys.path.insert(0, str(REPO_ROOT))
        try:
            from scripts.guard_workflow_definition_source import _PRT_EXEMPT
        finally:
            sys.path.pop(0)
        wf_dir = REPO_ROOT / '.github/workflows'
        missing = [n for n in _PRT_EXEMPT if not (wf_dir / n).is_file()]
        self.assertEqual(missing, [], f'豁免清单里的文件不存在：{missing}')

    # ── 常量与仓库现状 ──────────────────────────────────────────────────

    def test_守卫清单里的工作流都存在(self):
        """守卫的 `_GUARD_WORKFLOWS` 清单里列的每个文件都必须真实存在。

        清单项指向不存在的文件 = 判据形同虚设（永远不会被触发）。
        """
        sys.path.insert(0, str(REPO_ROOT))
        try:
            from scripts.guard_workflow_definition_source import _GUARD_WORKFLOWS
        finally:
            sys.path.pop(0)
        wf_dir = REPO_ROOT / '.github/workflows'
        missing = [n for n in _GUARD_WORKFLOWS if not (wf_dir / n).is_file()]
        self.assertEqual(missing, [], f'清单里的文件不存在：{missing}')

    def test_仓库现状文件本身通过(self):
        """仓库现状必须通过守卫——否则 CI 会红，且说明迁移没做完。"""
        sys.path.insert(0, str(REPO_ROOT))
        try:
            from scripts.guard_workflow_definition_source import check
        finally:
            sys.path.pop(0)
        problems = check(REPO_ROOT)
        self.assertEqual(problems, [], f'仓库现状应通过守卫，实际：{problems}')

    def test_共用组豁免清单是守卫清单的子集(self):
        """`_SAME_GROUP_EXEMPT` 的每个条目都必须在 `_GUARD_WORKFLOWS` 里。

        为什么需要这条不变式：豁免「允许与旧版共用同一个 group 名」时，
        该工作流就**不受判据 4 约束**。若它不在 `_GUARD_WORKFLOWS` 里，
        它的 checkout 也不受判据 2 约束 ⇒ 一个豁免顺手放开了两条判据。
        这与 `_PRT_EXEMPT ⊆ _GUARD_WORKFLOWS` 是同一条纪律。
        """
        sys.path.insert(0, str(REPO_ROOT))
        try:
            from scripts.guard_workflow_definition_source import (
                _GUARD_WORKFLOWS, _SAME_GROUP_EXEMPT,
            )
        finally:
            sys.path.pop(0)
        self.assertTrue(
            set(_SAME_GROUP_EXEMPT).issubset(set(_GUARD_WORKFLOWS)),
            f'共用组豁免清单的每个条目都必须在 _GUARD_WORKFLOWS 里：'
            f'豁免={sorted(_SAME_GROUP_EXEMPT)} 守卫清单={sorted(_GUARD_WORKFLOWS)}',
        )


if __name__ == '__main__':
    unittest.main()
