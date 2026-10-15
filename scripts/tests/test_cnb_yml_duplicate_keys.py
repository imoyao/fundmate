"""`.cnb.yml` 重复键守卫的回归网（源 CNB #458）<!-- cross-repo-ref-allow -->。

## WHY 有这份文件

CNB #458 的故障形态是「**本地判据全绿、平台判据全拒**」：跨仓收敛合并（`5633d04c`）把<!-- cross-repo-ref-allow -->
两侧各写一份的 `main:` / `dev:` / `pull_request:` 并进同一层，`.cnb.yml` 于是带了
两个 `dev:` 键与两个 `pull_request` 键。而：

- YAML 规范**允许**重复键（后者覆盖前者）⇒ PyYAML `safe_load` 解析通过；
- 本仓三个 `.cnb.yml` 守卫（`check_cnb_events` / `guard_git_sync_push_scope` /
  `guard_secret_imports`）全走 `safe_load` ⇒ **全绿**；
- CNB 平台用严格解析器 ⇒ **直接拒绝**（`YAMLException: duplicated mapping key (240:3)`），
  构建死在 Prepare，`duration: 0`、`pipelineFailCount: 0`。

差的就是「严格 vs 宽松解析器」这一行，而这一行此前没有任何判据在管。故本文件钉三件事：

1. **守卫咬得住真重复键**（正探针）；
2. **守卫不误报合法配置**（反探针，含 YAML 锚点 / `<<:` merge —— `.cnb.yml` 自己就在用）；
3. **拿不到输入 ≠ 没有问题**（#171 的失败态纪律）：文件缺失 / 不可读 / 解析失败
   一律退 2 并声明「结论不可信」，**不得**退化成看起来正常的「无重复」。

## 怎么跑

    python -m unittest discover -s scripts/tests -p "test_*.py"

零新依赖（只用标准库）；不拉网络。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import guard_cnb_yml_duplicate_keys as guard  # noqa: E402

GUARD_PATH = ROOT / 'scripts' / 'guard_cnb_yml_duplicate_keys.py'
REPO_CNB_YML = ROOT / '.cnb.yml'

# 出问题的那个提交（CNB #458 的构建 cnb-l9m-1k4v28ls0 推的 ref）。
BROKEN_COMMIT = '5633d04c'


class FindDuplicatesTest(unittest.TestCase):
    """判据本身：重复键检得出、合法配置不误报、锚点/merge 不误报。"""

    def test_detects_duplicate_key_with_position(self) -> None:
        dups = guard.find_duplicates('main:\n  pull_request:\n    - name: a\n  pull_request:\n    - name: b\n')
        self.assertEqual([(k, line) for k, line, _col in dups], [('pull_request', 4)])

    def test_legal_mapping_is_clean(self) -> None:
        self.assertEqual(guard.find_duplicates('main:\n  push:\n    - name: a\ndev:\n  push:\n    - name: b\n'), [])

    def test_anchor_and_merge_are_not_duplicates(self) -> None:
        text = '.base: &base\n  image: python:3.12-slim\nmain:\n  push:\n    - name: x\n      <<: *base\n'
        self.assertEqual(guard.find_duplicates(text), [])

    def test_collector_is_not_leaked_between_calls(self) -> None:
        """上一次调用的结果不得污染下一次（判据自己造假阳性比漏报更贵）。"""
        self.assertTrue(guard.find_duplicates('a:\n  b: 1\n  b: 2\n'))
        self.assertEqual(guard.find_duplicates('a:\n  b: 1\n  c: 2\n'), [])

    def test_self_check_passes(self) -> None:
        self.assertEqual(guard.self_check(), [])


class CheckFileTest(unittest.TestCase):
    """失败态纪律（#171）：拿不到输入不得退化成「无重复」。"""

    def test_missing_file_is_input_failure_not_clean(self) -> None:
        problems = guard.check_file(Path('<nonexistent>/.cnb.yml'))
        self.assertTrue(problems and all(p.startswith('__MISSING__') for p in problems))

    def test_unparseable_yaml_is_input_failure_not_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / '.cnb.yml'
            bad.write_text('main:\n  push: [unclosed\n', encoding='utf-8')
            problems = guard.check_file(bad)
        self.assertTrue(problems and all(p.startswith('__PARSE_ERROR__') for p in problems))

    def test_missing_file_exits_2(self) -> None:
        rc = guard.main(['--file', '<nonexistent>/.cnb.yml'])
        self.assertEqual(rc, 2)

    def test_duplicate_exits_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / '.cnb.yml'
            bad.write_text('dev:\n  pull_request:\n    - name: a\ndev:\n  pull_request:\n    - name: b\n', encoding='utf-8')
            rc = guard.main(['--file', str(bad)])
        self.assertEqual(rc, 1)

    def test_clean_exits_0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ok = Path(tmp) / '.cnb.yml'
            ok.write_text('dev:\n  push:\n    - name: a\n', encoding='utf-8')
            rc = guard.main(['--file', str(ok)])
        self.assertEqual(rc, 0)


class RepoStateTest(unittest.TestCase):
    """仓库现状：修好后必须干净；修复前的提交必须能被判据咬住（变异探针）。"""

    def test_repo_cnb_yml_is_clean(self) -> None:
        self.assertEqual(guard.check_file(REPO_CNB_YML), [])

    def test_guard_bites_broken_commit(self) -> None:
        """把 CNB #458 那个提交的 `.cnb.yml` 喂给守卫 —— 必须转红。

        探针钉在**不可变 SHA** 上，不能读 `origin/dev`：修复合入后 origin/dev 就是
        修复后的代码，探针会随分支推进自行失效（AGENTS.md「探针不能读可变 ref」）。
        """
        proc = subprocess.run(
            ['git', '-C', str(ROOT), 'show', f'{BROKEN_COMMIT}:.cnb.yml'],
            capture_output=True, text=True, check=True,
        )
        dups = guard.find_duplicates(proc.stdout)
        keys = sorted(str(k) for k, _line, _col in dups)
        self.assertEqual(keys, ['dev', 'pull_request'])


if __name__ == '__main__':
    unittest.main()
