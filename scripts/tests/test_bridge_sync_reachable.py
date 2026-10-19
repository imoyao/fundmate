#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`scripts/guard_bridge_sync_reachable.py` 的回归网（源 CNB #552）。  <!-- cross-repo-ref-allow -->

用户的原话：「分诊侧不用做，回流侧需要做。就是说你关卡或者是说留下评论的时候，
一定要判有判据，不然我会感觉到很困惑。」

钉四件事：

1. **判据 1 的方向**：`dev:` 的 cron 与 `$:` 的 `web_trigger` 跑的脚本集合必须相等，
   且都非空 —— 只有一边不相等才红（不过宽、不过窄）；
2. **判据 2 的回退验证**：把 `mirror_state_sync.py` 里那行
   `return 1 if not complete else 0` 删掉 ⇒ **必须转红**。
   这是本仓 #171 的假绿形态，也是**没有任何测试在管**的那一条；
3. **判据 3**：`export GITHUB_TOKEN=""` 占位后再说 PAT ⇒ 红（后者静默不生效）；
4. **拿不到输入不得当通过**：读不到回流脚本 ⇒ 报「结论不可信」（#171 的失败态纪律）。

最后一条是**真实回退探针**：拿当前工作区里的 `mirror_state_sync.py` 源码，
把失败态那一行删掉后喂给判据 —— 守卫绿只证明「代码里没有它不认识的东西」，
证明不了它能认出那个 bug（#573 / #450 都栽过这一步）。

跑法：`python -m unittest scripts.tests.test_bridge_sync_reachable`
（`ci.yml` 的 `scripts_test` 里随 `unittest discover` 一起跑）。
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO / 'scripts' / 'guard_bridge_sync_reachable.py'
SYNC_SCRIPT = REPO / 'scripts' / 'bridge' / 'mirror_state_sync.py'

SCRIPT = 'python scripts/bridge/mirror_state_sync.py --apply'
SRC_OK = {
    'scripts/bridge/mirror_state_sync.py': 'def f():\n    return 1 if not complete else 0\n',
    'scripts/bridge/claim_detect.py': 'def f():\n    return 1 if (failed or not complete) else 0\n',
}


def _load():
    spec = importlib.util.spec_from_file_location('bridge_sync_reachable_guard', GUARD)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _stage(script: str, name: str = 's') -> dict:
    return {'name': name, 'script': script}


def _job(script: str, name: str = 'j') -> dict:
    return {'name': name, 'stages': [_stage(script)]}


def _cfg(dev_script: str = SCRIPT, web_script: str = SCRIPT) -> dict:
    return {
        'dev': {'crontab: 0 18 * * *': [_job(dev_script)]},
        '$': {'web_trigger': [_job(web_script, 'GitHub issue 增量镜像（手动）')]},
    }


class TestParity(unittest.TestCase):
    """判据 1：两条触发方式必须跑同一套脚本。"""

    def setUp(self):
        self.g = _load()

    def test_same_set_is_green(self):
        self.assertEqual(self.g.check_parity(_cfg()), [])

    def test_web_trigger_missing_script_is_red(self):
        """手动通道空转：构建会绿，但什么都没做。"""
        problems = self.g.check_parity(_cfg(web_script='echo hi'))
        self.assertTrue(problems)
        self.assertTrue(any('web_trigger' in p for p in problems), problems)

    def test_dev_cron_missing_script_is_red(self):
        """cron 才是常态通道（每天一次）；漏在 cron 外的那一个只在有人手点时跑。"""
        problems = self.g.check_parity(_cfg(dev_script='echo hi'))
        self.assertTrue(problems)
        self.assertTrue(any('cron' in p for p in problems), problems)

    def test_empty_both_sides_is_red(self):
        """两侧都空 ⇒ 报「没有」而不是「相等」。**空 == 空**是本仓反复踩的假绿。"""
        problems = self.g.check_parity({'dev': {'push': []}, '$': {}})
        self.assertEqual(len(problems), 2, problems)


class TestFailureState(unittest.TestCase):
    """判据 2：数据不完整时必须非 0 退出（#171）。"""

    def setUp(self):
        self.g = _load()

    def test_mirror_sync_line_is_recognised(self):
        src = 'def run():\n    return 1 if not complete else 0\n'
        self.assertEqual(self.g.check_failure_state(src, 'x.py'), [])

    def test_claim_detect_form_is_recognised(self):
        src = 'def run():\n    return 1 if (failed or not complete) else 0\n'
        self.assertEqual(self.g.check_failure_state(src, 'x.py'), [])

    def test_deleted_failure_state_is_red(self):
        self.assertTrue(self.g.check_failure_state('def run():\n    return 0\n', 'x.py'))

    def test_real_file_regression_probe(self):
        """回退验证：把**当前工作区那份真实源码**里的失败态删掉，判据必须转红。

        这是本文件最重的一条 —— 守卫绿只说明「守卫认识这份文件」，
        不说明「它能认出那个 bug」。探针是在**改生产代码的副本**上跑的，
        原文件不动（#573 的教训：探针改错了地方，红在一个你没预期的地方）。
        """
        original = SYNC_SCRIPT.read_text(encoding='utf-8')
        self.assertIn('return 1 if not complete else 0', original, '源文件形态变了，本探针需同步更新')

        broken = original.replace('return 1 if not complete else 0', 'return 0')
        with tempfile.TemporaryDirectory() as tmp:
            probe = pathlib.Path(tmp) / 'mirror_state_sync.py'
            probe.write_text(broken, encoding='utf-8')
            problems = self.g.check_data(
                _cfg(),
                {'scripts/bridge/mirror_state_sync.py': broken,
                 'scripts/bridge/claim_detect.py': SRC_OK['scripts/bridge/claim_detect.py']},
            )
        self.assertTrue(problems, '失败态被删掉却没红 —— 判据没咬住 #171 的形态')
        self.assertTrue(any('非 0 退出' in p for p in problems), problems)
        # 原文件必须原样（探针不该改生产代码）
        self.assertEqual(SYNC_SCRIPT.read_text(encoding='utf-8'), original)


class TestTokenWiring(unittest.TestCase):
    """判据 3：`GITHUB_TOKEN` 的第一次赋值必须来自 `GITHUB_PAT`。"""

    def setUp(self):
        self.g = _load()

    def test_pat_first_is_green(self):
        body = f'export GITHUB_TOKEN="$GITHUB_PAT"\n{SCRIPT}\n'
        self.assertEqual(self.g.check_token_wiring(body, 'x'), [])

    def test_empty_placeholder_shadows_pat(self):
        """空串占位是**合法值**：后面的 PAT 导出静默不生效，脚本仍按匿名跑。"""
        body = f'export GITHUB_TOKEN=""\nexport GITHUB_TOKEN="$GITHUB_PAT"\n{SCRIPT}\n'
        problems = self.g.check_token_wiring(body, 'x')
        self.assertTrue(problems)
        self.assertIn('GITHUB_PAT', problems[0])

    def test_stage_without_token_is_not_judged(self):
        """不读 GitHub 的 stage（没写 `GITHUB_TOKEN`）不该被本判据管 —— 防过宽。"""
        self.assertEqual(self.g.check_token_wiring(SCRIPT, 'x'), [])


class TestInputTrust(unittest.TestCase):
    """拿不到输入 ⇒ 「结论不可信」，**不得**退化成「没问题」（#171）。"""

    def setUp(self):
        self.g = _load()

    def test_missing_script_is_untrustworthy(self):
        problems = self.g.check_data(_cfg(), {})
        self.assertTrue(any('不可信' in p for p in problems), problems)


class TestSelfCheckAndRealRepo(unittest.TestCase):
    def test_guard_self_check_is_clean(self):
        self.assertEqual(_load().self_check(), [])

    def test_real_repo_is_green(self):
        """仓库当前的真实文件必须通过（否则守卫一上线就恒红，没人会去修）。"""
        r = subprocess.run(
            [sys.executable, str(GUARD)],
            cwd=REPO,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=False,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
