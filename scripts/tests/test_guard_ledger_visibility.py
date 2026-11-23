# -*- coding: utf-8 -*-
"""回归网：``scripts/guard_ledger_visibility.py``（#3246 第三段 可见性判定单点守卫）。

四组用例，缺一不可（与 ``test_guard_net_assets_source.py`` 同款）：
  · **合成命中样本** —— V1 读列 / V2 比较 / V3 取值字面量各自能抓到；
  · **合成放行样本** —— 不得误报。最危险的两种真实形态是
    ``ledgers/views.py`` 的 ``visibility, owner_user_id, err = resolve_ledger_scope(...)``
    （创建账户时解析待落库的取值）和 docstring 里的说明文字；
  · **真实文件回退探针** —— 往副本里注回一句散落判定，守卫必须转红。
    没有这条，「守卫是绿的」只能证明「它没扫到东西」；
  · **失败态** —— 扫不到输入必须 exit 2，不得读成「无事发生」。

⚠️ 用 ``unittest.TestCase`` 写法：CI 的 ``scripts_test`` job 以
``python -m unittest scripts.tests.test_guard_ledger_visibility -v`` 显式收，
pytest 风格裸函数不会被收集。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / 'scripts' / 'guard_ledger_visibility.py'
REAL_VIEWS = REPO_ROOT / 'backend' / 'app' / 'domains' / 'ledgers' / 'views.py'
TMP_ROOT = Path(tempfile.gettempdir()).resolve()

# V1：直接读列（原始缺陷形态）
HIT_READ_COLUMN = """
def list_things(db, ledger):
    if ledger.visibility == 'private':
        return []
    return db.query(Thing).filter(Thing.ledger_id == ledger.id).all()
"""

# V2：列值存进局部变量再比（换个写法也躲不掉）
HIT_COMPARE = """
def guard(ledger):
    v = ledger.visibility
    if v == 'shared':
        return True
    return False
"""

# V3：绕开属性名，直接比取值字面量
HIT_LITERAL = """
def guard(kind):
    return kind == 'private' or kind == 'shared'
"""

# 放行：创建账户时解析待落库的取值（真实形态）
PASS_RESOLVE_SCOPE = """
def create(db, user_id):
    visibility, owner_user_id, scope_error = resolve_ledger_scope(data, user_id)
    return ledger_write_service.create_ledger(db, 1, data, visibility=visibility, owner_user_id=owner_user_id)
"""

# 放行：docstring 里提到判定入口（散文守卫按行正则会误伤，AST 不会）
PASS_DOCSTRING = '''
def list_positions(db):
    """可见性判定收口在 ``visibility.restrict_visible``，视图不写 ``visibility ==`` 比较。"""
    return restrict_visible(db.query(Position), Position.ledger_id, visible_ledger_id_set(db)).all()
'''

# 放行：调单点出口
PASS_SINGLE_ENTRY = """
def list_ledgers(db):
    ids = visible_ledger_id_set(db)
    return db.query(Ledger).filter(Ledger.id.in_(ids)).all()
"""


def _run(paths: list[Path]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *[str(p) for p in paths]],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )


class GuardLedgerVisibilityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=TMP_ROOT, prefix='guard_visibility_'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, body: str) -> Path:
        p = self.tmp / name
        p.write_text(body, encoding='utf-8')
        return p

    # ── 命中 ────────────────────────────────────────────────────────────
    def test_reads_column_is_reported(self):
        r = _run([self._write('a_views.py', HIT_READ_COLUMN)])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('V1', r.stderr)

    def test_compare_on_visibility_is_reported(self):
        r = _run([self._write('b_views.py', HIT_COMPARE)])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('V1', r.stderr, '读列本身已违规，不必等比较')

    def test_bare_visibility_compare_is_reported(self):
        body = """
def guard(visibility):
    return visibility != 'private'
"""
        r = _run([self._write('c_views.py', body)])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('V2', r.stderr)

    def test_literal_compare_is_reported(self):
        r = _run([self._write('d_views.py', HIT_LITERAL)])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('V3', r.stderr)

    # ── 放行 ────────────────────────────────────────────────────────────
    def test_resolve_scope_is_allowed(self):
        r = _run([self._write('e_views.py', PASS_RESOLVE_SCOPE)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_docstring_mention_is_allowed(self):
        r = _run([self._write('f_views.py', PASS_DOCSTRING)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_single_entry_call_is_allowed(self):
        r = _run([self._write('g_views.py', PASS_SINGLE_ENTRY)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # ── 真实文件回退探针 ────────────────────────────────────────────────
    def test_real_views_regress_when_a_stray_check_is_added(self):
        """往真实文件的副本里注回一句散落判定，守卫必须转红."""
        copy = self._write('ledgers_views.py', REAL_VIEWS.read_text(encoding='utf-8'))
        self.assertEqual(_run([copy]).returncode, 0, '基线副本应当是绿的（否则探针无意义）')
        with copy.open('a', encoding='utf-8') as fh:
            fh.write("\n\ndef _stray(ledger):\n    return ledger.visibility == 'private'\n")
        r = _run([copy])
        self.assertEqual(r.returncode, 1, '注回散落判定后守卫仍绿 ⇒ 这条守卫没在工作')

    # ── 失败态 ──────────────────────────────────────────────────────────
    def test_no_input_is_not_success(self):
        r = _run([self.tmp])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_syntax_error_is_not_success(self):
        r = _run([self._write('broken_views.py', 'def f(:\n')])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
