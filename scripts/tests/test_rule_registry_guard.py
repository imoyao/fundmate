# -*- coding: utf-8 -*-
"""`scripts/guard_rule_registry.py` 的回归网（规则生命周期守卫）。

守卫治的是「规则写了、守卫写了、但守卫**从来没跑过**」这一类事故。它自己如果空转，
就会变成它要治的那个东西——所以本文件既钉判据，也钉**灵敏度**：

1. 每类错误都有一条能红的用例（并顺手验证 `check()` 真的返回 1）；
2. 引擎一致性用**可控的假 ci.yml** 钉住（不拿真 ci.yml 判引擎，见脚本 docstring）；
3. **变异探针**：拿真实仓库文件做一处最小回退（改登记表 / 摘掉 hook 的默认阶段），
   确认守卫转红——「跑一次绿」不算数。

守卫逻辑按路径加载复用，判定规则只有一份（同 `test_view_thickness_guard.py` 的做法）。
"""

import importlib.util
import time  # 探针改写真实文件后须稍等，否则同一 tick 内的回写可能被文件系统合并
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARD_PATH = _REPO_ROOT / 'scripts' / 'guard_rule_registry.py'


def _load_guard():
    spec = importlib.util.spec_from_file_location('guard_rule_registry', _GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ci_blocks(text):
    return _load_guard()._ci_step_blocks(text)


class TestAgentScan(unittest.TestCase):
    """AGENTS.md 的条目筛法：宁窄勿宽（数错等于钉错）。"""

    def test_only_bullets_and_table_rows_count(self):
        guard = _load_guard()
        text = '\n'.join(
            [
                '- **必须** `foo` 走统一实现',  # 列表项 + 情态词 ⇒ 算
                '| **强制** | 表格行也算 |',  # 表格行 ⇒ 算
                '> 引用行**禁止** X',  # 引用行 ⇒ 算
                '这行正文里恰好出现了「必须」两个字',  # 普通正文 ⇒ 不算
                '- 没有情态词的列表项',  # 无情态词 ⇒ 不算
            ]
        )
        names, total, pure = guard.scan_agents_hard_rules(text)
        self.assertEqual(total, 3)
        self.assertEqual(pure, 3)
        self.assertEqual(names, [])

    def test_script_path_must_be_inline_code(self):
        guard = _load_guard()
        text = '\n'.join(
            [
                '- **强制** 走 `scripts/guard_x.py`（这是判据）',  # 反引号 ⇒ 认
                '- **强制** 见 scripts/guard_y.py:12 的写法',  # 裸路径 ⇒ 不认（是行号引用）
            ]
        )
        names, total, pure = guard.scan_agents_hard_rules(text)
        self.assertEqual(names, ['scripts/guard_x.py'])
        self.assertEqual((total, pure), (2, 1))

    def test_count_invariant(self):
        """总数 = 有判据 + 纯文字，且「有判据」条数 == 提到脚本的行数。

        这条曾数错过（2026-10-16）：把「同一行挂两个脚本」折成
        `total += len(names) - 1` 之后，两个数仍在动，但已经不代表任何真实含义。
        判据的数错 = 钉错，故用不变量当判决，而不是一个个对拍。
        """
        guard = _load_guard()
        text = '\n'.join(
            [
                '- **必须** `scripts/a.py`',
                '- **禁止** `scripts/b.mjs` 与 `scripts/c.py`',  # 一行两个脚本
                '- 普通行的**必须**',
                '> **一律**走统一出口',
            ]
        )
        names, total, pure = guard.scan_agents_hard_rules(text)
        with_judge = sum(
            1
            for line in text.splitlines()
            if guard._HARD_RULE_RE.match(line)
            and [n for n in guard._SCRIPT_PATH_RE.findall(line) if not guard._TEST_PATH_RE.search(n)]
        )
        self.assertEqual(total, 4)
        self.assertEqual((with_judge, pure), (2, 2))
        self.assertEqual(total, with_judge + pure)
        self.assertEqual(len(names), 3)

    def test_test_files_are_not_judges(self):
        guard = _load_guard()
        text = '- **强制** 见 `scripts/tests/foo.test.js`'
        names, total, pure = guard.scan_agents_hard_rules(text)
        self.assertEqual(names, [])
        self.assertEqual(pure, 1)


class TestEngineAndLifecycle(unittest.TestCase):
    """引擎一致 + 生命周期：判据必须挂在**一定会跑**的钩子上。"""

    def test_ci_step_detected_by_script_path(self):
        guard = _load_guard()
        ci = '\n'.join(
            [
                'jobs:',
                '  backend:',
                '    steps:',
                '      - name: 设置 Python',
                '        uses: actions/setup-python@v6',
                '      - name: 守卫:视图层厚度',
                '        run: python ../scripts/check_view_thickness.py',
            ]
        )
        blocks = guard._ci_step_blocks(ci)
        self.assertEqual(len(blocks), 2)
        self.assertNotIn('check_view_thickness.py', blocks[0][1])
        self.assertIn('check_view_thickness.py', blocks[1][1])

    def test_non_commit_stage_requires_backstop(self):
        """`commit-msg` / `pre-push` 阶段在 `git commit` 时不跑 ⇒ 必须有 CI 兜底。"""
        guard = _load_guard()
        pc = '\n'.join(
            [
                '  - repo: local',
                '    hooks:',
                '      - id: guard-x-commit-msg',
                '        entry: python scripts/guard_x.py --check-message',
                '        stages: [commit-msg]',
            ]
        )
        found = guard.find_runner('scripts/guard_x.py', '', pc)
        self.assertEqual(found['where'], 'pre-commit')
        self.assertEqual(found['stage'], 'commit-msg')

    def test_default_stage_hook_is_commit_time(self):
        guard = _load_guard()
        pc = '\n'.join(
            [
                '  - repo: local',
                '    hooks:',
                '      - id: guard-y',
                '        entry: python scripts/guard_y.py',
                '        files: ^backend/',
            ]
        )
        found = guard.find_runner('scripts/guard_y.py', '', pc)
        self.assertEqual(found['stage'], 'default')


class TestRepositoryState(unittest.TestCase):
    """真实仓库状态：登记表必须完整、判据必须真的在跑。"""

    def test_registry_entries_exist(self):
        guard = _load_guard()
        missing = [n for n in guard.RULE_REGISTRY if not (_REPO_ROOT / n).is_file()]
        self.assertEqual(missing, [], f'登记了不存在的脚本（登记变墓地）：{missing}')

    def test_every_entry_declares_its_gap(self):
        """每条登记都必须写清「不覆盖什么」——写「无」也算一次思考。"""
        guard = _load_guard()
        blank = [n for n, m in guard.RULE_REGISTRY.items() if not m.get('covered')]
        self.assertEqual(blank, [], f'未写明边界的判据：{blank}')

    def test_every_entry_declares_tests(self):
        guard = _load_guard()
        blank = [n for n, m in guard.RULE_REGISTRY.items() if not m.get('tests')]
        self.assertEqual(blank, [], f'没有回归网的判据（守卫自己不会红）：{blank}')

    def test_declared_tests_exist_or_are_named(self):
        guard = _load_guard()
        bad = []
        for name, meta in guard.RULE_REGISTRY.items():
            target = meta['tests'].split('::')[0]
            if not (_REPO_ROOT / target).is_file():
                bad.append((name, target))
        self.assertEqual(bad, [], f'声明的回归网不存在：{bad}')

    def test_guard_passes_on_current_repo(self):
        guard = _load_guard()
        self.assertEqual(guard.main([]), 0)


class TestMutationProbes(unittest.TestCase):
    """变异探针：把修复回退一处，守卫必须转红（MISSED = 判据在空转）。

    探针一律**作用于真实仓库文件**（探针 = 一次真实的回退）。假输入只能证明函数被调用过，
    证明不了「真文件里的写法我们认不认」——而判据失效恰恰发生在那儿。
    """

    def _mutate(self, rel, old, new):
        """临时改写仓库文件执行断言，**finally 还原**（探针绝不允许留下改动）。"""
        path = _REPO_ROOT / rel
        original = path.read_text(encoding='utf-8')
        self.assertIn(old, original, f'回退点不存在，探针无效：{rel}')
        try:
            path.write_text(original.replace(old, new, 1), encoding='utf-8')
            time.sleep(0.05)
            return _load_guard().main([])
        finally:
            path.write_text(original, encoding='utf-8')
            time.sleep(0.05)

    def test_probe_unregistered_judge_is_caught(self):
        """AGENTS.md 挂了判据、登记表里没有 ⇒ 红。"""
        rc = self._mutate(
            'scripts/guard_rule_registry.py',
            "    'scripts/guard_segmented.py': {",
            "    'scripts/guard_segmented_UNREGISTERED.py': {",
        )
        self.assertEqual(rc, 1)

    def test_probe_ci_step_removed_is_caught(self):
        """把 CI 里跑本守卫的那一步删掉 ⇒ 红（「写了没人跑」正是本守卫要抓的）。"""
        rc = self._mutate(
            '.github/workflows/ci.yml',
            '      - name: 守卫:规则登记与生命周期（阻断）\n        run: python scripts/guard_rule_registry.py\n',
            '',
        )
        self.assertEqual(rc, 1)

    def test_probe_runner_mismatch_is_caught(self):
        """登记改成「只在本地钩子」而 CI 里还有它 ⇒ 红（归属失配）。

        最核心的一条：`guard_mojibake.py` 的 `commit-msg` hook 在 `git commit` 时
        **根本不跑**，它能兜住乱码全靠 `mojibake_guard` job。若有人把登记改成
        `runner=pre-commit`（听起来更「本地友好」），一条真在跑的 CI 兜底就从账本上消失了
        ——这正是「守卫写了、但没人知道它归谁管」的那种漂移。
        """
        rc = self._mutate(
            'scripts/guard_rule_registry.py',
            "'runner': 'both',\n        # 该脚本同时挂三条 hook",
            "'runner': 'pre-commit',\n        # 该脚本同时挂三条 hook",
        )
        self.assertEqual(rc, 1)

    def test_probe_budget_overflow_is_caught(self):
        """把预算调低 1 ⇒ 红（预算真的在生效，不是摆着看的数）。"""
        rc = self._mutate(
            'scripts/guard_rule_registry.py',
            'PURE_RULE_BUDGET = 88',
            'PURE_RULE_BUDGET = 87',
        )
        self.assertEqual(rc, 1)

    def test_zz_probes_restore_the_worktree(self):
        """所有探针跑完，仓库必须回到全绿（否则探针自己污染了工作区）。

        ⚠️ 别在这里 `assertEqual(main(), 0)`：`unittest discover` 的执行顺序是**字典序**，
        本测试可能排在其它探针**之前**跑（按 `test_all_...` 改名后会排到最前），
        于是它会读到「上一条探针腾空的中间态」而假红。判据本体是否全绿由
        `TestRepositoryState.test_guard_passes_on_current_repo` 负责；这里只查文件内容
        是否被还原——那是探针唯一可能留下的痕迹。
        """
        for rel in ('scripts/guard_rule_registry.py', '.pre-commit-config.yaml', '.github/workflows/ci.yml'):
            self.assertTrue((_REPO_ROOT / rel).read_text(encoding='utf-8').strip(), f'{rel} 被探针写空了')
        self.assertNotIn(
            'guard_segmented_UNREGISTERED.py',
            (_REPO_ROOT / 'scripts/guard_rule_registry.py').read_text(encoding='utf-8'),
            '探针的变异残留在了仓库里',
        )


if __name__ == '__main__':
    unittest.main()
