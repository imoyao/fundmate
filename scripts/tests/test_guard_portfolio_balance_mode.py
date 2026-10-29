#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归网：``scripts/guard_portfolio_balance_mode.py``（D70 / #2740 验收「守卫 + 探针」）。

覆盖：
1. 真实仓库通过（守卫上线当天必须对现有代码绿）；
2. **真实代码探针**：把仓库里真实的 ``position_service.py`` 去掉那段 ``portfolio``
   约束后喂守卫，必须转红——守卫绿 ≠ 守卫有效；
3. 只删 ``and not is_balance``（保留分支与 raise）⇒ 红：约束退化成「凡组合就报错」或
   根本不看模式；
4. 把 ``raise`` 换成日志（约束只剩注释的「看」而不执行）⇒ 红；
5. 写入函数被改名 / 搬走 ⇒ **退出码 2**（输入不可信，不得读成「通过」）；
6. 真实 ``asset_types.py`` 里塞回旧表述「portfolio 不进 positions」⇒ 红；
7. 真实 ``asset_types.py`` 去掉所有 balance 提及 ⇒ 红（代码强制、文档不写）；
8. ``decisions.md`` 删掉 D70 行 ⇒ 红；
9. 文件缺失 ⇒ **退出码 2**；
10. 合成绿样本（``!= ValuationMode.BALANCE`` 写法）⇒ 绿：判据不认某一种拼法。

跑法：``python scripts/tests/test_guard_portfolio_balance_mode.py``
或 ``python -m unittest scripts.tests.test_guard_portfolio_balance_mode``。
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import re
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO / 'scripts' / 'guard_portfolio_balance_mode.py'

SERVICE_REL = 'backend/app/services/position_service.py'
ASSET_TYPES_REL = 'backend/app/core/asset_types.py'
DECISIONS_REL = 'docs/spec/decisions.md'

FUNC = 'process_buy_or_deposit'
STALE_LINE = '    # manager / portfolio：不进 positions，仅 watchlist 引用\n'


def _load_guard():
    spec = importlib.util.spec_from_file_location('guard_portfolio_balance_mode', GUARD)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _find_portfolio_if(source: str) -> ast.If:
    """定位真实代码里那段「portfolio 非 balance ⇒ raise」的 If 节点。"""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        texts = [
            child.value
            for child in ast.walk(node.test)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)
        ]
        if 'portfolio' in texts:
            return node
    raise AssertionError('真实 position_service.py 里找不到 portfolio 的 If 分支（守卫判据需同步）')


def _drop_lines(source: str, start: int, end: int) -> str:
    """按 1-based 行号区间删行（含端点），其余原样保留。"""
    lines = source.splitlines(keepends=True)
    return ''.join(lines[: start - 1] + lines[end:])


def _mutate_body(source: str, node: ast.AST, pattern: str, repl: str) -> str:
    """只在目标节点覆盖的行范围内做一次文本替换——避免误伤文件里别的 raise。"""
    lines = source.splitlines(keepends=True)
    start, end = node.lineno - 1, (node.end_lineno or node.lineno)
    segment = ''.join(lines[start:end])
    mutated = re.sub(pattern, repl, segment, count=1)
    assert mutated != segment, f'行范围内找不到待替换文本：{pattern}'
    return ''.join(lines[:start] + [mutated] + lines[end:])


def _run(root: pathlib.Path) -> int:
    module = _load_guard()
    return module.run(root)


class RealRepoTest(unittest.TestCase):
    def test_repository_passes(self):
        self.assertEqual(_run(REPO), 0)


class WriteGuardProbeTest(unittest.TestCase):
    """写入侧判据：拿**真实代码**做回退探针。"""

    def setUp(self):
        self.module = _load_guard()
        self.source = (REPO / SERVICE_REL).read_text(encoding='utf-8')
        self.path = pathlib.Path(SERVICE_REL)

    def test_constraint_removed_turns_red(self):
        node = _find_portfolio_if(self.source)
        broken = _drop_lines(self.source, node.lineno, node.end_lineno or node.lineno)
        findings = self.module.check_write_guard(broken, self.path)
        self.assertTrue(findings, '删掉整段 portfolio 约束后守卫仍绿 —— 守卫无效')

    def test_balance_check_removed_turns_red(self):
        # 只删 `and not is_balance`：分支与 raise 都还在，但不再看计价模式。
        broken = re.sub(r'\s+and\s+not\s+is_balance', '', self.source, count=1)
        self.assertNotEqual(broken, self.source, '真实代码里没有 `and not is_balance`（守卫判据需同步）')
        findings = self.module.check_write_guard(broken, self.path)
        self.assertTrue(findings, '去掉 balance 判定后守卫仍绿 —— 它只看有没有 raise')

    def test_raise_replaced_by_log_turns_red(self):
        node = _find_portfolio_if(self.source)
        broken = _mutate_body(self.source, node, r'raise ValueError\(', 'logger.warning(')
        findings = self.module.check_write_guard(broken, self.path)
        self.assertTrue(findings, '把 raise 换成日志后守卫仍绿 —— 约束没被执行')

    def test_function_missing_is_input_error(self):
        broken = self.source.replace(f'def {FUNC}(', 'def some_other_entry(')
        self.assertNotEqual(broken, self.source)
        with self.assertRaises(self.module.InputError):
            self.module.check_write_guard(broken, self.path)

    def test_synthetic_balance_neq_spelling_passes(self):
        source = (
            'def process_buy_or_deposit(db, data, force_create_position=False):\n'
            "    asset_type = data.get('asset_type')\n"
            "    mode = data.get('valuation_mode')\n"
            "    if asset_type == 'portfolio' and mode != ValuationMode.BALANCE.value:\n"
            "        raise ValueError('组合必须 balance')\n"
            '    return None\n'
        )
        self.assertEqual(self.module.check_write_guard(source, self.path), [])

    def test_synthetic_missing_raise_turns_red(self):
        source = (
            'def process_buy_or_deposit(db, data, force_create_position=False):\n'
            "    asset_type = data.get('asset_type')\n"
            "    if asset_type == 'portfolio' and not is_balance:\n"
            "        logger.warning('组合应走 balance')\n"
            '    return None\n'
        )
        self.assertTrue(self.module.check_write_guard(source, self.path))


class AssetTypesTextTest(unittest.TestCase):
    """规范侧判据：旧表述回归 / 新口径被删，都必须红。"""

    def setUp(self):
        self.module = _load_guard()
        self.text = (REPO / ASSET_TYPES_REL).read_text(encoding='utf-8')
        self.path = pathlib.Path(ASSET_TYPES_REL)

    def test_real_file_passes(self):
        self.assertEqual(self.module.check_asset_types_text(self.text, self.path), [])

    def test_stale_phrase_regression_turns_red(self):
        broken = self.text.replace(
            "    'manager': '基金经理',", STALE_LINE + "    'manager': '基金经理',", 1
        )
        self.assertNotEqual(broken, self.text)
        findings = self.module.check_asset_types_text(broken, self.path)
        self.assertTrue(any('不进 positions' in item for item in findings), findings)

    def test_missing_balance_mention_turns_red(self):
        # 删掉所有含 balance 的注释行：代码约束还在，但文档不再说明为什么。
        kept = [
            line
            for line in self.text.splitlines(keepends=True)
            if not (line.strip().startswith('#') and 'balance' in line)
        ]
        broken = ''.join(kept)
        self.assertNotEqual(broken, self.text)
        findings = self.module.check_asset_types_text(broken, self.path)
        self.assertTrue(any('balance' in item for item in findings), findings)


class DecisionsTest(unittest.TestCase):
    def setUp(self):
        self.module = _load_guard()
        self.path = pathlib.Path(DECISIONS_REL)
        self.text = (REPO / DECISIONS_REL).read_text(encoding='utf-8')

    def test_real_file_passes(self):
        self.assertEqual(self.module.check_decisions_text(self.text, self.path), [])

    def test_dropping_decision_row_turns_red(self):
        kept = [line for line in self.text.splitlines(keepends=True) if 'D70' not in line]
        broken = ''.join(kept)
        self.assertNotEqual(broken, self.text)
        self.assertTrue(self.module.check_decisions_text(broken, self.path))


class InputTrustTest(unittest.TestCase):
    def test_missing_file_exits_two(self):
        module = _load_guard()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(module.InputError):
                module.run(pathlib.Path(tmp))

    def test_main_returns_two_on_missing_root(self):
        module = _load_guard()
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(module.main(['--root', tmp]), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
