# -*- coding: utf-8 -*-
"""`scripts/cnb_yml_loader.py` 的回归网（源 CNB #460）。

## WHY

2026-10-15 跨仓收敛合并把两段同名分支键并进同一个 `.cnb.yml`，CNB 平台直接报
`YAMLException: duplicated mapping key`，整条流水线死在 Prepare。而三个本地守卫
**全部放行**——根因是 PyYAML 的 `safe_load` 与平台口径相反（前者「后值覆盖」，
后者「语法错」）。`check_cnb_events.py` 已修自己那一份，但逐个守卫打补丁意味着
**下一个新守卫会原样再栽一次**，故把口径收进共享 loader，这份用例钉住它。

钉三类边界：

1. **重复 key 必须被拒**（这是平台的口径，不是 PyYAML 的）；
2. **合并键 `<<: *anchor` 必须仍然可用** —— 本仓 `.cnb.yml` 用了它
   （`.mirror-job` / `claim-sync`），守卫自己先崩比判据失效更贵；
3. **`describe_yaml_error` 必须把「重复 key」说清楚** —— 裸 YAML 错误信息
   指向不了「本地全绿、平台全挂」这类事故，说清楚才有人知道往哪看。

怎么跑
------
    python -m unittest discover -s scripts/tests -p "test_*.py"

零网络、零新依赖。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from cnb_yml_loader import describe_yaml_error, load_cnb_yml  # noqa: E402


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding='utf-8')
    return p


# 事故形态（源 CNB #460）：收敛合并把两段 `dev:` 并进同一文件。
DUP_TOP_KEY = 'main:\n  push: []\ndev:\n  push: []\ndev:\n  pull_request: []\n'

# 事故形态二：同一个分支键下两个 `pull_request:`（`main:` 段内，CNB 平台报 240:3）。
DUP_EVENT_KEY = (
    'main:\n'
    '  pull_request:\n'
    '    - name: a\n'
    '      stages: []\n'
    '  pull_request:\n'
    '    - name: b\n'
    '      stages: []\n'
)

# 本仓真实用法：`<<: *anchor` 合并键。
ANCHOR_FORM = '.mirror-job: &mj\n  runner:\n    cpus: 2\nmain:\n  "crontab: 0 18 * * *":\n    - <<: *mj\n      stages: []\n'


class TestRejectsDuplicateKeys(unittest.TestCase):
    def test_duplicate_top_level_branch_key_is_rejected(self):
        """两段 `dev:` 必须被拒 —— 这是平台真实拒绝过的形态。"""
        with tempfile.TemporaryDirectory() as td:
            p = _write(Path(td), 'dup.yml', DUP_TOP_KEY)
            with self.assertRaises(yaml.YAMLError) as cm:
                load_cnb_yml(p)
            self.assertIn("duplicated mapping key 'dev'", str(cm.exception))

    def test_duplicate_event_key_under_branch_is_rejected(self):
        """同一分支键下两个 `pull_request:` 同样必须被拒。"""
        with tempfile.TemporaryDirectory() as td:
            p = _write(Path(td), 'dup2.yml', DUP_EVENT_KEY)
            with self.assertRaises(yaml.YAMLError) as cm:
                load_cnb_yml(p)
            self.assertIn("duplicated mapping key 'pull_request'", str(cm.exception))

    def test_safe_load_would_have_passed_it(self):
        """反向确认 PyYAML 默认口径确实放行 —— 否则本判据没有存在的意义。

        这条不是测试 loader，是测试**「为什么需要这个 loader」**这个前提：
        若哪天 PyYAML 改成严格模式，前提消失，这里的断言会提醒我们重新评估。
        """
        with tempfile.TemporaryDirectory() as td:
            p = _write(Path(td), 'dup.yml', DUP_TOP_KEY)
            data = yaml.safe_load(p.read_text(encoding='utf-8'))
            self.assertIsInstance(data, dict)
            self.assertIn('dev', data)


class TestMergeKeyStillWorks(unittest.TestCase):
    def test_anchor_merge_key_is_preserved(self):
        """`<<: *anchor` 必须仍可用（本仓 `.cnb.yml` 用了 `.mirror-job` / `claim-sync`）。"""
        with tempfile.TemporaryDirectory() as td:
            p = _write(Path(td), 'anchor.yml', ANCHOR_FORM)
            data = load_cnb_yml(p)
            self.assertIn('main', data)
            job = data['main']['crontab: 0 18 * * *'][0]
            # merge 键生效 ⇒ runner.cpus 从锚点带过来
            self.assertEqual(job['runner']['cpus'], 2)


class TestDescribeYamlError(unittest.TestCase):
    def test_duplicate_key_message_names_cause_and_fix(self):
        """「重复 key」要说清成因与后果，不能只丢一句裸 YAML 错误。"""
        with tempfile.TemporaryDirectory() as td:
            p = _write(Path(td), 'dup.yml', DUP_TOP_KEY)
            try:
                load_cnb_yml(p)
            except yaml.YAMLError as exc:
                msg = describe_yaml_error(exc)
            else:
                self.fail('应当抛错')
        self.assertIn('Prepare', msg)
        self.assertIn('跨仓收敛合并', msg)

    def test_non_duplicate_error_passes_through(self):
        """非重复 key 的错误不得被特判改写成误导信息。"""
        msg = describe_yaml_error(yaml.YAMLError('some other problem'))
        self.assertEqual(msg, 'some other problem')


if __name__ == '__main__':
    unittest.main()
