#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归网：``scripts/check_design_doc_index.py``（设计文档索引集合相等守卫， #2981）。

覆盖：
1. 真实仓库通过（16 篇设计文档全部登记在 ``index.md`` 的「设计资产索引」表里）；
2. 文件存在但没登记 ⇒ 红，且点名该文件（正是修复前的形态：10 篇未登记）；
3. 登记了不存在的文档 ⇒ 红，且点名该幽灵名（点进去 404，比不登记更贵）；
4. **正文交叉引用不算登记**：正是「全文 includes 会被自己的正文喂饱」的反向验证——
   把 ``docs/features/gamma.md`` 写进正文但表格只登记 alpha/beta，仍须判绿；
5. 索引表一行都没登记 ⇒ 红（集合为空不算通过，否则删表就能骗过守卫）；
6. ``archive/`` 下的文档不参与比对（不递归）；
7. 小节标题被改名 / ``docs/design/`` 不存在 ⇒ 退出码 **2**（不冒充通过）；
8. ``--self-check`` 的四态自检自身通过。

反向验证：删掉 ``docs/design/index.md`` 里任意一行登记（或用例 2 的临时仓库形态），
本守卫与 ``test_real_repo_passes`` 都会同时转红。
"""

from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO / 'scripts' / 'check_design_doc_index.py'

INDEX = """# 索引

## 设计资产索引（design assets）

| 文档 | 内容 | 状态 |
|:---|:---|:---|
| `alpha.md` | 甲 | 定稿 |
| `beta.md` | 乙 | 定稿 |

## 交叉引用

- 另见 `docs/features/gamma.md`、`roadmap.md`（目录外，故意引用，不算登记）
"""


def _load_guard():
    spec = importlib.util.spec_from_file_location('check_design_doc_index_under_test', GUARD)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _make_repo(
    tmp: str,
    index_text: str,
    docs: tuple[str, ...] = ('alpha.md', 'beta.md'),
    extra: dict[str, str] | None = None,
) -> pathlib.Path:
    """造一个最小仓库：``docs/design/{index.md, docs...}``，``extra`` 可加子目录文件。"""
    design = pathlib.Path(tmp) / 'docs' / 'design'
    design.mkdir(parents=True)
    for name in docs:
        (design / name).write_text('# x\n', encoding='utf-8')
    for rel, text in (extra or {}).items():
        target = design / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    (design / 'index.md').write_text(index_text, encoding='utf-8')
    return pathlib.Path(tmp)


class GuardOnRealRepoTest(unittest.TestCase):
    def test_real_repo_passes(self) -> None:
        guard = _load_guard()
        self.assertEqual(guard.run(REPO), 0)

    def test_self_check_passes(self) -> None:
        guard = _load_guard()
        self.assertEqual(guard.self_check(), 0)


class VerdictTest(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = _load_guard()

    def test_complete_index_is_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_repo(tmp, INDEX)
            self.assertEqual(self.guard.run(root), 0)
            self.assertEqual(self.guard.compare(root), (([], []), None))

    def test_unregistered_doc_is_red(self) -> None:
        """修复前的形态：文件在，表里没有。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_repo(tmp, INDEX.replace('| `beta.md` | 乙 | 定稿 |\n', ''))
            missing, stale = self.guard.compare(root)[0]
            self.assertEqual(self.guard.run(root), 1)
        self.assertEqual(missing, ['beta.md'])
        self.assertEqual(stale, [])

    def test_stale_registration_is_red(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_repo(
                tmp,
                INDEX.replace('| `beta.md` | 乙 | 定稿 |', '| `beta.md` | 乙 | 定稿 |\n| `ghost.md` | 幽灵 | 定稿 |'),
            )
            missing, stale = self.guard.compare(root)[0]
            self.assertEqual(self.guard.run(root), 1)
        self.assertEqual(missing, [])
        self.assertEqual(stale, ['ghost.md'])

    def test_prose_cross_reference_is_not_registration(self) -> None:
        """正文提到目录外文档不算登记——全文 includes 会被正文喂饱（#2453 教训）。"""
        guard = self.guard
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_repo(tmp, INDEX)
            registered = guard.registered_docs((root / 'docs' / 'design' / 'index.md').read_text(encoding='utf-8'))
        self.assertEqual(registered, {'alpha.md', 'beta.md'})

    def test_empty_table_is_red_not_green(self) -> None:
        """索引表一行都没有时必须红：否则「把表格删掉」就成了绕过守卫的正解。"""
        empty_table = INDEX.replace('| `alpha.md` | 甲 | 定稿 |\n| `beta.md` | 乙 | 定稿 |\n', '')
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_repo(tmp, empty_table)
            self.assertEqual(self.guard.run(root), 1)

    def test_archive_is_not_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_repo(tmp, INDEX, extra={'archive/old.md': '# 旧稿\n'})
            self.assertEqual(self.guard.run(root), 0)

    def test_renamed_section_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_repo(tmp, INDEX.replace('设计资产索引', '随便什么标题'))
            self.assertEqual(self.guard.run(root), 2)

    def test_missing_design_dir_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.guard.run(pathlib.Path(tmp)), 2)

    def test_empty_design_dir_exits_2(self) -> None:
        """A 为空 = 仓库结构变了，不能拿空集合冒充全绿。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_repo(tmp, INDEX, docs=())
            self.assertEqual(self.guard.run(root), 2)


class SectionParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = _load_guard()

    def test_section_stops_at_next_peer_heading(self) -> None:
        lines = self.guard.section_lines(INDEX)
        self.assertIsNotNone(lines)
        self.assertTrue(all('交叉引用' not in line for line in lines))

    def test_section_allows_inner_headings(self) -> None:
        """小节内部出现 ### 子标题时不应提前截断。"""
        text = INDEX.replace('| `beta.md` | 乙 | 定稿 |', '### 子表\n\n| `beta.md` | 乙 | 定稿 |')
        self.assertEqual(self.guard.registered_docs(text), {'alpha.md', 'beta.md'})

    def test_missing_section_returns_none(self) -> None:
        self.assertIsNone(self.guard.section_lines('# 没有那个小节\n'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
