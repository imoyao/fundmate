# -*- coding: utf-8 -*-
"""`scripts/regen_pnpm_lockfile.mjs` + `scripts/guard_dependabot_lockfile_regen.py` 的回归网（#2434）。

两层判据，缺一层都会让通道静默失灵：

1. **通道层**（守卫）：workflow 是否真的执行脚本、带 `--apply`、推回、不吞失败态、
   按 dependabot + base=dev 设闸。每条都有一次**变异回退**，确认守卫真的会红
   ——「跑一次绿」不算数（#171 / #564 的教训）。
2. **脚本层**（纯函数）：`exactVersionOf` / `changedSpecifiers` / `summaryLine`。
   这三个决定「钉哪个版本」「汇总行是否可自证」，错了不会报错，只会静默装成别的版本。

脚本的端到端行为（坏锁 → 重生成 → `--frozen-lockfile` 自证）需要 pnpm + 网络，
放在 PR 描述里附实测记录，不塞进单测——否则这里会变成又一条「依赖外网、平时跳过」的假绿。
"""

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARD_PATH = _REPO_ROOT / 'scripts' / 'guard_dependabot_lockfile_regen.py'
_SCRIPT_PATH = _REPO_ROOT / 'scripts' / 'regen_pnpm_lockfile.mjs'
_WORKFLOW_REL = '.github/workflows/dependabot-lockfile-regen.yml'


def _load_guard():
    spec = importlib.util.spec_from_file_location('guard_dependabot_lockfile_regen', _GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_repo(tmp: Path, workflow_text: str) -> Path:
    """把真实 workflow / 脚本复制进临时仓库，只替换 workflow 文本。"""
    wf = tmp / _WORKFLOW_REL
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(workflow_text, encoding='utf-8')
    script = tmp / 'scripts' / 'regen_pnpm_lockfile.mjs'
    script.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_SCRIPT_PATH, script)
    return tmp


class TestGuardOnRealRepo(unittest.TestCase):
    def test_real_repo_passes(self):
        problems = _load_guard().check(_REPO_ROOT)
        self.assertEqual(problems, [], f'真实仓库不应有违规：{problems}')


class TestGuardCatchesRegressions(unittest.TestCase):
    """每条都是「通道已经死掉、但日志一片绿」的形态。"""

    def setUp(self):
        self.real = (_REPO_ROOT / _WORKFLOW_REL).read_text(encoding='utf-8')

    def _problems_after(self, mutated: str):
        with tempfile.TemporaryDirectory() as tmp:
            return _load_guard().check(_fake_repo(Path(tmp), mutated))

    def test_probe1_removing_invocation_is_caught(self):
        """探针 1：删掉 `node … regen_pnpm_lockfile.mjs`（备份行还在，守卫不得被它骗过）。"""
        mutated = self.real.replace(
            'node /tmp/regen_pnpm_lockfile.mjs --dir "$d" --base-ref origin/dev --apply',
            'echo "跳过重生成"',
        )
        self.assertNotEqual(mutated, self.real, '探针未命中：workflow 结构已变')
        problems = self._problems_after(mutated)
        self.assertTrue(any('未执行' in p for p in problems), problems)

    def test_probe2_dropping_apply_is_caught(self):
        """探针 2：去掉 `--apply` ⇒ 永远 dry-run，每次都成功、每次都什么都不写。"""
        mutated = self.real.replace(
            'node /tmp/regen_pnpm_lockfile.mjs --dir "$d" --base-ref origin/dev --apply',
            'node /tmp/regen_pnpm_lockfile.mjs --dir "$d" --base-ref origin/dev',
        )
        self.assertNotEqual(mutated, self.real, '探针未命中')
        problems = self._problems_after(mutated)
        self.assertTrue(any('--apply' in p for p in problems), problems)

    def test_probe3_dropping_push_is_caught(self):
        """探针 3：重生成却不推回 ⇒ PR 的锁仍然是坏的。"""
        mutated = self.real.replace('git push origin "HEAD:$PR_HEAD_REF"', 'true')
        self.assertNotEqual(mutated, self.real, '探针未命中')
        problems = self._problems_after(mutated)
        self.assertTrue(any('git push' in p for p in problems), problems)

    def test_probe4_swallowing_failure_is_caught(self):
        """探针 4：调用行加 `|| true` ⇒ 失败态被吞成绿灯（#171 同族）。"""
        mutated = self.real.replace(
            'node /tmp/regen_pnpm_lockfile.mjs --dir "$d" --base-ref origin/dev --apply',
            'node /tmp/regen_pnpm_lockfile.mjs --dir "$d" --base-ref origin/dev --apply || true',
        )
        self.assertNotEqual(mutated, self.real, '探针未命中')
        problems = self._problems_after(mutated)
        self.assertTrue(any('|| true' in p for p in problems), problems)

    def test_probe5_dropping_dependabot_gate_is_caught(self):
        """探针 5：去掉 dependabot 作者闸 ⇒ 对任意人开写权限。"""
        mutated = self.real.replace(
            "      github.event.pull_request.user.login == 'dependabot[bot]' &&\n", ''
        )
        self.assertNotEqual(mutated, self.real, '探针未命中')
        problems = self._problems_after(mutated)
        self.assertTrue(any('dependabot[bot]' in p for p in problems), problems)

    def test_probe6_pull_request_instead_of_target_is_caught(self):
        """探针 6：改成 `pull_request` ⇒ dependabot 下 token 只读，push 必然失败。"""
        mutated = self.real.replace('  pull_request_target:', '  pull_request:', 1)
        self.assertNotEqual(mutated, self.real, '探针未命中')
        problems = self._problems_after(mutated)
        self.assertTrue(any('pull_request_target' in p for p in problems), problems)

    def test_missing_workflow_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            problems = _load_guard().check(Path(tmp))
        self.assertTrue(any('不存在' in p for p in problems), problems)


_JS_PROBE = """
import {{ exactVersionOf, changedSpecifiers, summaryLine }} from {url};

const changed = changedSpecifiers(
  {{ dependencies: {{ axios: '^1.19.0', vue: '^3.5.44' }} }},
  {{
    dependencies: {{ axios: '^1.20.0', vue: '^3.5.44' }},
    devDependencies: {{ vitest: '^5.0.5' }},
  }},
);

console.log(JSON.stringify({{
  caret: exactVersionOf('^1.20.0'),
  tilde: exactVersionOf('~0.2.0'),
  range: exactVersionOf('>=1.0.0'),
  workspace: exactVersionOf('workspace:*'),
  changed,
  line: summaryLine({{
    dir: 'frontend',
    baseRef: 'origin/dev',
    changed: changed.length,
    pinned: '1/1',
    frozen: true,
    applied: true,
  }}),
}}));
"""


class TestScriptPureFunctions(unittest.TestCase):
    """钉住「钉哪个版本」「汇总行可自证」两个决定。"""

    def _run_probe(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node 不在 PATH（该 job 里由 setup-node 提供）')
        code = _JS_PROBE.format(url=json.dumps(_SCRIPT_PATH.as_uri()))
        result = subprocess.run(
            [node, '--input-type=module', '-e', code],
            capture_output=True,
            text=True,
            encoding='utf-8',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_strips_range_prefix(self):
        out = self._run_probe()
        self.assertEqual(out['caret'], '1.20.0')
        self.assertEqual(out['tilde'], '0.2.0')

    def test_non_numeric_specs_are_not_pinned(self):
        """`>=1.0.0` / `workspace:*` 都不是可钉的版本——返回 None，调用方跳过 pin。"""
        out = self._run_probe()
        self.assertIsNone(out['range'])
        self.assertIsNone(out['workspace'])

    def test_changed_specifiers_reports_only_real_changes(self):
        out = self._run_probe()
        keys = {(c['group'], c['name']) for c in out['changed']}
        self.assertEqual(keys, {('dependencies', 'axios'), ('devDependencies', 'vitest')})
        axios = next(c for c in out['changed'] if c['name'] == 'axios')
        self.assertEqual(axios['from'], '^1.19.0')
        self.assertEqual(axios['to'], '^1.20.0')

    def test_summary_line_is_self_evident(self):
        out = self._run_probe()
        line = out['line']
        for token in ('LOCKFILE_REGEN', 'dir=frontend', 'base=origin/dev', 'changed=2',
                      'pinned=1/1', 'frozen=pass', 'applied=yes'):
            self.assertIn(token, line)


if __name__ == '__main__':
    unittest.main()
