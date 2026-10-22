# -*- coding: utf-8 -*-
"""`.github/workflows/governance-direction-guard.yml` 的**输入语义**回归网（GitHub #2482）。

WHY 有这份文件
--------------
2026-10-21 实测：GitHub PR #2436（一次性空提交验证 PR，`gh api .../pulls/2436/files` 返回 `[]`）
在「治理文件改动方向提示」workflow 上红了（run ``39563404301``）：

    改动文件数：0
    ##[error]未取到 PR 改动文件列表 —— 本轮结论不可信，不得当作「未改动治理文件」

成因是该 workflow 第二步曾有一句：

    if [ ! -s /tmp/pr_files.txt ]; then
      echo "::error::未取到 PR 改动文件列表 ……"
      exit 1
    fi

它把「**列表为空**」当「**输入缺失**」。但空列表有两种来源：

    - **拉取失败** ⇒ 早已被第一步的 ``set -euo pipefail`` 中断作业 ⇒ 那条分支**走不到**；
    - **PR 确实零文件改动** ⇒ 那条分支**唯一能**触发的场景。

即：**该分支永远不做本职工作（拉取失败早被 set -e 处理），只制造假红**。
这是 AGENTS.md §三之二「空 ≠ 没拿到」的镜像形态——把「事实为空」误判成「取不到」，
报出一个比真实情况更响亮的结论；红灯与真实风险脱钩（与 #171 / #450 同型）。

判据（两层，缺一层都会让形态复发）
----------------------------------
1. **空列表不得判成致命**：任何 ``if [ ! -s <file> ]`` 分支体内不得出现非零 ``exit``
   （空列表要么是「零文件改动」⇒ 正常，要么是「拉取失败」⇒ 已在拉取处显式红）。
2. **拉取失败必须有显式失败态**：``gh api --paginate`` 必须被失败分支包住，
   且该分支里有 ``::error::`` 注解 + 非零退出（不得靠调用方自行解读退出码）。

跑一次绿不算数（AGENTS.md §三之三）：下面两条**变异探针**分别把修复前的真实写法注回去、
把拉取失败的包装去掉，断言判据**必须**报出问题——否则判据是恒真的假绿。

怎么跑
------
    python -m unittest discover -s scripts/tests -p "test_governance_direction_input.py" -v

依赖：标准库 + PyYAML（CI 的 ``scripts_test`` job 已 ``pip install pyyaml pytest``），纯离线。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_REL = '.github/workflows/governance-direction-guard.yml'
_WORKFLOW_PATH = _REPO_ROOT / _WORKFLOW_REL

# 「文件为空」判定：if [ ! -s <path> ]（允许 "$path" / [[ ]] 等常见写法）
RE_EMPTY_TEST = re.compile(r'if\s+\[+\s*!\s*-s\s+(?P<path>[^\]\s]+)\s*\]+')
# 拉取调用（必须显式带 --paginate，避免多页漏抓）
RE_FETCH = re.compile(r'gh\s+api\s+--paginate')
# 拉取被失败分支包住的形态：if ! gh api ...
RE_FETCH_GUARD = re.compile(r'if\s+!\s+gh\s+api\b')
# 非零退出（exit 0 不算失败）
RE_EXIT_NONZERO = re.compile(r'\bexit\s+(?!0\b)\S+')
# GitHub Actions 错误注解
RE_ERROR_ANNOTATION = re.compile(r'::error::')

# 修复前真实存在的分支（探针 1 要把它原样注回去）
_OLD_BUGGY_BLOCK = (
    '          if [ ! -s /tmp/pr_files.txt ]; then\n'
    '            echo "::error::未取到 PR 改动文件列表 —— 本轮结论不可信，不得当作「未改动治理文件」"\n'
    '            exit 1\n'
    '          fi\n'
)
# 修复后的拉取块（探针 2 要把它退回裸调用）
_GUARDED_FETCH_BLOCK = (
    '          if ! gh api --paginate "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/files" \\\n'
    "            --jq '.[].filename' > /tmp/pr_files.txt; then\n"
    '            echo "::error::拉取 PR 改动文件列表失败 —— 本轮结论不可信，不得当作「未改动治理文件」"\n'
    '            exit 1\n'
    '          fi\n'
)
_BARE_FETCH_BLOCK = (
    '          gh api --paginate "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/files" \\\n'
    "            --jq '.[].filename' > /tmp/pr_files.txt\n"
)
_ANCHOR = '          node - <<' + "'NODE' > /tmp/governance_result.txt\n"


def _run_blocks(text: str) -> list[str]:
    """取出 workflow 里所有 step 的 ``run:`` 文本。"""
    doc = yaml.safe_load(text)
    runs: list[str] = []
    for job in (doc.get('jobs') or {}).values():
        for step in job.get('steps') or []:
            run = step.get('run')
            if isinstance(run, str):
                runs.append(run)
    return runs


def _block_span(text: str, start: int) -> tuple[str, int]:
    """返回 (分支体, 分支结束位置)：从 ``start`` 到同缩进的 ``fi``（找不到就取到文末）。"""
    rest = text[start:]
    m = re.search(r'^\s*fi\s*$', rest, re.MULTILINE)
    if not m:
        return rest, len(text)
    return rest[: m.start()], start + m.end()


def find_empty_list_as_fatal(runs: list[str]) -> list[str]:
    """判据 1：把「列表为空」判成输入缺失并让作业失败 ⇒ 假红（零文件改动 PR 必中）。"""
    problems: list[str] = []
    for run in runs:
        for m in RE_EMPTY_TEST.finditer(run):
            body, _ = _block_span(run, m.end())
            if RE_EXIT_NONZERO.search(body):
                problems.append(
                    f'把空列表（{m.group("path")}）判成「输入缺失」并让作业失败'
                    '（分支内非零 exit）——零文件改动的 PR 会被误报红'
                )
    return problems


def find_fetch_failure_without_explicit_fatal(runs: list[str]) -> list[str]:
    """判据 2：拉取失败没有显式失败态（既没被失败分支包住，或分支里缺注解 / 非零退出）。"""
    problems: list[str] = []
    for run in runs:
        fetch_positions = [m.start() for m in RE_FETCH.finditer(run)]
        if not fetch_positions:
            continue
        covered = False
        explicit = False
        for gm in RE_FETCH_GUARD.finditer(run):
            body, end = _block_span(run, gm.end())
            if not any(gm.start() < pos < end for pos in fetch_positions):
                continue
            covered = True
            if RE_ERROR_ANNOTATION.search(body) and RE_EXIT_NONZERO.search(body):
                explicit = True
        if not covered:
            problems.append('gh api --paginate 未被失败分支包住 ⇒ 拉取失败时没有显式失败态')
        elif not explicit:
            problems.append(
                'gh api --paginate 的失败分支缺少 ::error:: 注解或非零退出 ⇒ 失败态不可见'
            )
    return problems


class TestGovernanceDirectionInput(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.original = _WORKFLOW_PATH.read_text(encoding='utf-8')
        cls.runs = _run_blocks(cls.original)

    def test_real_repo_has_no_input_misclassification(self) -> None:
        """真实仓库：两层判据都干净。"""
        self.assertEqual(find_empty_list_as_fatal(self.runs), [])
        self.assertEqual(find_fetch_failure_without_explicit_fatal(self.runs), [])

    def test_workflow_still_actually_does_the_job(self) -> None:
        """防「文件被清空 ⇒ 检测恒绿」：判据依赖的两处内容必须还在。"""
        joined = '\n'.join(self.runs)
        self.assertIn('gh api --paginate', joined)
        self.assertIn('checkGovernanceDirection', joined)
        self.assertIn('governance-direction-guard', joined)

    def test_probe_old_buggy_block_is_detected(self) -> None:
        """探针 1：把修复前的真实分支注回去，判据必须报出问题（否则是恒真的假绿）。"""
        mutated = self.original.replace(_ANCHOR, _OLD_BUGGY_BLOCK + '\n' + _ANCHOR, 1)
        self.assertNotEqual(mutated, self.original, '探针未命中：锚点文本已变')
        # 变异后的 YAML 必须仍能解析，否则这条探针证明不了任何事
        yaml.safe_load(mutated)
        problems = find_empty_list_as_fatal(_run_blocks(mutated))
        self.assertTrue(problems, '旧写法（空列表 ⇒ exit 1）未被判据抓到')

    def test_probe_missing_fetch_failure_guard_is_detected(self) -> None:
        """探针 2：把拉取失败包装去掉（退回裸调用），判据必须报出问题。"""
        self.assertIn(_GUARDED_FETCH_BLOCK, self.original, '探针未命中：拉取块形状已变')
        mutated = self.original.replace(_GUARDED_FETCH_BLOCK, _BARE_FETCH_BLOCK, 1)
        self.assertNotEqual(mutated, self.original, '探针未命中：拉取块文本未匹配')
        yaml.safe_load(mutated)
        problems = find_fetch_failure_without_explicit_fatal(_run_blocks(mutated))
        self.assertTrue(problems, '拉取失败没有显式失败态时，判据未抓到')


if __name__ == '__main__':
    unittest.main()
