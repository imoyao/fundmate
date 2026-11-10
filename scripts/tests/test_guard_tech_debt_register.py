#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归网：``scripts/guard_tech_debt_register.py``（技术债务登记表守卫，2026-11-10）。

覆盖：
1. 真实仓库 27 条债务状态全部可判定（exit 0）；
2. ``--self-check`` 的 10 态变异自检自身通过；
3. 登记表规模：条目数 >= 20 且五态齐全（防「删掉一堆条目守卫照样绿」）；
4. 把任一 ``done`` 改成 ``open`` ⇒ 红（僵尸 open：判据已满足）；
5. 删掉一条 ``criterion`` ⇒ 红（判据不许退化成自然语言）；
6. 顶层 ``updated_at`` 过期 ⇒ 红（新鲜度闸门）；
7. 删头部 ``STATUS_AUTHORITY`` / 删 index 导航登记 ⇒ 红（双真源一致性）；
8. 空登记表 / 登记表缺失 / 判据引用文件不存在 ⇒ **exit 2**（不得冒充通过）；
9. P1 三卡（TD-018/019/020）判据反向验证：把锚点推到「满足态」⇒ 僵尸 open 红。

反向验证：所有变异都先断言锚点真的落在文件里（``_mutate`` 的 assert），
再跑守卫 —— 变异没落盘时用例会自己报错，而不是「全绿假象」（#2739 教训）。
日期固定 2026-11-10，避免 90 天后测试因新鲜度自然过期而变红。
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import shutil
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO / 'scripts' / 'guard_tech_debt_register.py'
REGISTER_REL = 'docs/spec/tech-debt-register.toml'
FIXED_TODAY = dt.date(2026, 11, 10)

# 真实登记表判据 / doc_ref 引用的最小文件集合，复制到临时仓库后做变异。
CLONE_FILES = (
    'docs/spec/tech-debt.md',
    'docs/spec/index.md',
    REGISTER_REL,
    'docs/spec/decisions.md',
    'docs/spec/roadmap.md',
    'docs/working-notes/issue-triage/auto/2026-11-06.md',
    'docs/working-notes/auto-merge-attribution-and-events-2026-11-01.md',
    'docs/working-notes/amac-encoding-incident-2026-08-17.md',
    'backend/app/services/money_fund_income.py',
    'frontend/src/style/dark.scss',
    'backend/app/services/today_pnl.py',
    'backend/app/services/position_display.py',
    'backend/app/services/ledger_service.py',
    'frontend/src/api/summary.ts',
    # TD-012 的 done 判据是 guard 类型，会在最小仓库里真跑一遍接线守卫；
    # 这三份缺一，探针就会把「脚本/文件不存在」误读成守卫逻辑生效。
    'scripts/guard_pg_migration_ci.py',
    '.github/workflows/ci.yml',
    'backend/tests/core/test_migrations_positions_state_check_pg.py',
    # TD-010/TD-011 的 done 判据同为 guard 类型，跑 scripts/guard_basis_unification.py；
    # 该脚本静态 grep 这三份源码，缺任一即 InputError → 克隆不绿（exit 2）。
    'scripts/guard_basis_unification.py',
    'backend/app/services/summary_service.py',
    'backend/app/services/position_aggregation.py',
    'backend/app/domains/summary/models.py',
    # P1 三卡判据纠偏后新增的 grep 目标 / doc_ref 依赖：grep 判据的文件缺失会抛
    # InputError（exit 2），doc_ref 指向的文件缺失 R1 也会判红，缺任一克隆都不绿。
    'docs/dev/auth-audit.md',
    'docs/spec/api.md',
    'backend/app/domains/auth/views.py',
)


def _load_guard():
    spec = importlib.util.spec_from_file_location('guard_tech_debt_register_under_test', GUARD)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _clone(root: pathlib.Path) -> pathlib.Path:
    for rel in CLONE_FILES:
        src, dst = REPO / rel, root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return root


def _mutate(root: pathlib.Path, old: str, new: str, rel: str = REGISTER_REL, count: int = 1) -> None:
    path = root / rel
    text = path.read_text(encoding='utf-8')
    assert old in text, f'变异锚点不存在（变异没落盘会伪装成全绿）：{old!r}'
    path.write_text(text.replace(old, new, count), encoding='utf-8')


class GuardOnRealRepoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.guard = _load_guard()

    def test_real_repo_passes(self) -> None:
        self.assertEqual(self.guard.run(REPO, today=FIXED_TODAY), 0)

    def test_self_check_passes(self) -> None:
        self.assertEqual(self.guard.self_check(), 0)

    def test_register_has_expected_scale(self) -> None:
        data = self.guard.load_register(REPO)
        debts = data['debt']
        self.assertGreaterEqual(len(debts), 20, '登记表被删掉一大半也能全绿？')
        statuses = {d['status'] for d in debts}
        self.assertEqual(
            statuses,
            {'open', 'done', 'blocked', 'deferred', 'wontfix'},
            '五态必须都有实例，否则状态机退化成摆设',
        )

    def test_strip_comment_lines_ignores_code_comments(self) -> None:
        """#2453：判据文本只写在代码注释里时，不得算命中。"""
        src = '# NavService.get_latest_navs 只写在注释里\nrow.nav_per_10k = 1\n'
        stripped = self.guard.strip_comment_lines(src, pathlib.Path('x.py'))
        self.assertNotIn('NavService.get_latest_navs', stripped)
        self.assertIn('row.nav_per_10k', stripped)
        web = '// html.dark 只写在注释里\nhtml.dark { color: red; }\n'
        self.assertNotIn('// html.dark', self.guard.strip_comment_lines(web, pathlib.Path('x.scss')))
        self.assertIn('html.dark {', self.guard.strip_comment_lines(web, pathlib.Path('x.scss')))

    def test_strip_comment_lines_keeps_docs(self) -> None:
        """.md 正文就是判据要读的内容（TD-004 的 U+FFFD），不能剥。"""
        src = '# 标题\n\ufffd 乱码\n'
        self.assertEqual(self.guard.strip_comment_lines(src, pathlib.Path('x.md')), src)


class MutationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.guard = _load_guard()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _clone(pathlib.Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self) -> int:
        return self.guard.run(self.root, today=FIXED_TODAY)

    def test_clone_baseline_is_green(self) -> None:
        self.assertEqual(self._run(), 0, '最小克隆本身要先绿，否则变异结论不可信')

    def test_done_flipped_to_open_is_red(self) -> None:
        _mutate(self.root, 'status = "done"', 'status = "open"')
        self.assertEqual(self._run(), 1)

    def test_missing_criterion_is_red(self) -> None:
        _mutate(
            self.root,
            'criterion = { type = "grep", path = "backend/app/services/money_fund_income.py", '
            'text = "nav_per_10k", present = true }',
            '',
        )
        self.assertEqual(self._run(), 1)

    def test_empty_words_in_command_is_red(self) -> None:
        _mutate(
            self.root,
            'run = "for n in 937 933 934 825 913; do gh issue view $n',
            'run = "待排期再说; for n in 937 933 934 825 913; do gh issue view $n',
        )
        self.assertEqual(self._run(), 1)

    def test_stale_updated_at_is_red(self) -> None:
        _mutate(self.root, 'updated_at = "2026-11-10"', 'updated_at = "2020-01-01"')
        self.assertEqual(self._run(), 1)

    def test_authority_mark_removed_is_red(self) -> None:
        _mutate(
            self.root,
            '> STATUS_AUTHORITY: tech-debt-register.toml',
            '> 状态见登记表',
            rel='docs/spec/tech-debt.md',
        )
        self.assertEqual(self._run(), 1)

    def test_index_registration_removed_is_red(self) -> None:
        index = self.root / 'docs/spec/index.md'
        lines = index.read_text(encoding='utf-8').splitlines(keepends=True)
        kept = [line for line in lines if 'tech-debt-register.toml' not in line]
        self.assertLess(len(kept), len(lines), '删登记行没生效')
        index.write_text(''.join(kept), encoding='utf-8')
        self.assertEqual(self._run(), 1)

    def test_empty_register_is_exit2(self) -> None:
        (self.root / REGISTER_REL).write_text('', encoding='utf-8')
        self.assertEqual(self._run(), 2)

    def test_missing_register_is_exit2(self) -> None:
        (self.root / REGISTER_REL).unlink()
        self.assertEqual(self._run(), 2)

    def test_criterion_missing_path_is_exit2(self) -> None:
        _mutate(
            self.root,
            'path = "backend/app/services/money_fund_income.py"',
            'path = "backend/app/services/no_such_file.py"',
        )
        self.assertEqual(self._run(), 2)

    def test_natural_language_grep_text_is_red(self) -> None:
        """判据不许退化成中文注释文案：删注释即假绿。"""
        _mutate(
            self.root,
            'text = "nav_per_10k", present = true',
            'text = "只声明被消费的字段", present = true',
        )
        self.assertEqual(self._run(), 1)

    def test_grep_text_only_in_comment_is_red(self) -> None:
        """集成层：把判据符号只留在注释里，done 必须判「假闭环」。"""
        target = self.root / 'backend/app/services/money_fund_income.py'
        target.write_text('# nav_per_10k 只写在注释里\n', encoding='utf-8')
        self.assertEqual(self._run(), 1)

    def test_guard_criterion_script_missing_is_exit2(self) -> None:
        """guard 判据引用的脚本不存在 ⇒ 输入不可信，不得降级成「债务还没做」。"""
        (self.root / 'scripts/guard_pg_migration_ci.py').unlink()
        self.assertEqual(self._run(), 2)

    def test_td018_checklist_cleared_is_red(self) -> None:
        """TD-018：§8 三项未完成清单清零 ⇒ 判据转满足 ⇒ 僵尸 open 红。"""
        _mutate(self.root, '- [ ]', '- [x]', rel='docs/dev/auth-audit.md', count=3)
        self.assertNotIn('- [ ]', (self.root / 'docs/dev/auth-audit.md').read_text(encoding='utf-8'))
        self.assertEqual(self._run(), 1)

    def test_td019_dual_dimension_limit_is_red(self) -> None:
        """TD-019：单维度 IP 键换成双维度 ⇒ 锚点消失 ⇒ 红。"""
        _mutate(
            self.root,
            "ratelimit.check(f'resolve:{ip}'",
            "ratelimit.check(f'resolve:{ip}:{identifier}'",
            rel='backend/app/domains/auth/views.py',
        )
        self.assertEqual(self._run(), 1)

    def test_td020_entitlement_endpoint_lands_is_red(self) -> None:
        """TD-020：独立权益端点进 api.md 自动段 ⇒ 判据转满足 ⇒ 红。"""
        _mutate(
            self.root,
            '| POST | `/api/agent/chat/` | `agent_chat` |',
            '| GET | `/api/me/entitlements/` | `me_entitlements` |\n| POST | `/api/agent/chat/` | `agent_chat` |',
            rel='docs/spec/api.md',
        )
        self.assertEqual(self._run(), 1)


if __name__ == '__main__':
    unittest.main()
