#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""设计文档索引守卫：``docs/design/*.md`` 与 ``index.md`` 的索引表必须**集合相等**（#2981）。

## WHY（2026-11-08 实测）

``docs/design/`` 顶层 16 篇设计文档里有 10 篇没登记在 ``index.md`` 的「设计资产索引」表里
（``account-dialog-form.md`` / ``reconcile-workbench-redesign-v2.md`` / ``trade-rules.md`` …）。
后果不是排版问题：这张表是这批设计资产的**唯一入口**，没登记就等于「存在但看不见」——
人和 AI 都只能靠 ``ls`` 盲猜文件名，同一个坑会被重新讨论一遍。

而失修是**必然**的：写一篇新文档不需要改任何被 CI 覆盖的文件，所以「顺手补一行索引」
永远不会被任何检查提醒。这类「完整性」缺口只能靠集合相等判据来钉。

## 判据（为什么不是全文 includes）

    A = ``docs/design/`` 顶层的 ``*.md``（排除 ``index.md`` 自身；``archive/`` 不递归）
    B = ``index.md`` 里「设计资产索引」小节内**表格首列**出现的 ``*.md`` 文件名

    A - B 非空 ⇒ 红：文档存在但没人登记（读者不知道它存在）
    B - A 非空 ⇒ 红：登记了不存在的文档（点进去 404，比不登记更贵）

**只看表格首列，不看全文**：index.md 正文里故意交叉引用着目录外的
``docs/features/watchlist.md``、``roadmap.md``、``about.md`` 等，全文 ``includes``
会把它们当成「已登记」，于是删掉真正的登记行守卫照样绿——#2453 就是这么被骗的
（注释/正文喂饱守卫）。所以这里按**结构**取：先切小节，再只认表格行的首列。

**集合为空不算通过**：解析出 0 条登记时按「一个都没登记」判红，而不是「没有差异」；
A 为空则直接退出码 2——那说明仓库结构变了（或路径传错），不能拿空集合冒充全绿。

## 自检探针

``--self-check`` 在临时目录里造一个最小 ``docs/design``，依次跑「登记齐全 / 删一行 /
加一行幽灵文档 / 改掉小节标题」四态，断言 0 / 1 / 1 / 2。**它验的是「守卫真的会红」**，
而不是守卫的输出长得像对的——没有这一步，一个把 B 恒算成 A 的实现也能长期全绿。

## 用法

    python scripts/check_design_doc_index.py              # 0 通过 / 1 集合不等 / 2 环境异常
    python scripts/check_design_doc_index.py --self-check # 变异自检
    python scripts/check_design_doc_index.py --root <repo>

回归网：``scripts/tests/test_check_design_doc_index.py``（真实仓库通过 + 两种变异回退探针 + exit 2）。
"""

from __future__ import annotations

import argparse
import contextlib
import io
import pathlib
import re
import sys
import tempfile

INDEX_NAME = 'index.md'
SECTION_KEYWORD = '设计资产索引'
DOC_TOKEN = re.compile(r'[A-Za-z0-9._-]+\.md')
HEADING = re.compile(r'^(#{1,6})\s*(.+?)\s*$')
DIVIDER = re.compile(r'^[\s\-:|]+$')


def section_lines(index_text: str) -> list[str] | None:
    """切出「设计资产索引」小节正文（到下一个同级或更高级标题为止）；找不到返回 ``None``。"""
    lines = index_text.splitlines()
    start: int | None = None
    level = 0
    for i, raw in enumerate(lines):
        m = HEADING.match(raw.strip())
        if m and SECTION_KEYWORD in m.group(2):
            start, level = i + 1, len(m.group(1))
            continue
        if start is not None and m and len(m.group(1)) <= level:
            return lines[start:i]
    return None if start is None else lines[start:]


def registered_docs(index_text: str) -> set[str] | None:
    """索引小节里**表格首列**登记的文档名集合；小节缺失返回 ``None``。

    只认表格首列是刻意的：正文里的交叉引用（``docs/features/*.md``、``roadmap.md``）
    不算登记，否则删掉真登记行也发现不了。
    """
    lines = section_lines(index_text)
    if lines is None:
        return None
    out: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if not line.startswith('|'):
            continue
        first = line.strip('|').split('|')[0].strip()
        if not first or DIVIDER.match(first):
            continue
        out.update(DOC_TOKEN.findall(first))
    return out


def design_docs(root: pathlib.Path) -> set[str] | None:
    """``docs/design/`` 顶层的文档名集合（不含 ``index.md``，不递归 ``archive/``）。"""
    design = root / 'docs' / 'design'
    if not design.is_dir():
        return None
    return {p.name for p in design.glob('*.md') if p.name != INDEX_NAME}


def compare(root: pathlib.Path) -> tuple[tuple[list[str], list[str]] | None, str | None]:
    """返回 ``((未登记, 失效登记), None)``，环境异常时返回 ``(None, 原因)``。"""
    files = design_docs(root)
    if files is None:
        return None, '找不到 docs/design/ 目录（--root 传错了？）'
    if not files:
        return None, 'docs/design/ 下没有任何 .md——结构异常，不能当成「全部已登记」'
    index = root / 'docs' / 'design' / INDEX_NAME
    if not index.is_file():
        return None, '找不到 docs/design/index.md'
    registered = registered_docs(index.read_text(encoding='utf-8'))
    if registered is None:
        return None, f'index.md 里找不到「{SECTION_KEYWORD}」小节（标题被改名或删了？）'
    return (sorted(files - registered), sorted(registered - files)), None


def run(root: pathlib.Path) -> int:
    result, error = compare(root)
    if error is not None:
        print(f'[check_design_doc_index] 环境异常，不冒充通过：{error}', file=sys.stderr)
        return 2
    assert result is not None  # error 为 None 时必然有结果
    missing, stale = result
    if not missing and not stale:
        total = len(design_docs(root) or ())
        print(f'[check_design_doc_index] OK：{total} 篇设计文档全部登记，无失效登记。')
        return 0

    print('[check_design_doc_index] 索引与目录不一致（判据：集合相等）：', file=sys.stderr)
    if missing:
        print(f'  未登记（docs/design/ 下有文件，index.md「{SECTION_KEYWORD}」表里没有）：', file=sys.stderr)
        for name in missing:
            print(f'    - docs/design/{name}', file=sys.stderr)
    if stale:
        print('  失效登记（表里写了，文件不存在）：', file=sys.stderr)
        for name in stale:
            print(f'    - {name}', file=sys.stderr)
    print('  修法：补一行表格（| `文件名.md` | 内容一句话 | 状态 |），或删掉失效行。', file=sys.stderr)
    return 1


GOOD_INDEX = """# 索引

## 设计资产索引（design assets）

| 文档 | 内容 | 状态 |
|:---|:---|:---|
| `alpha.md` | 甲 | 定稿 |
| `beta.md` | 乙 | 定稿 |

## 交叉引用

- 另见 `docs/features/gamma.md`、`roadmap.md`（目录外，故意引用，不算登记）
"""


def _probe_repo(index_text: str, docs: tuple[str, ...] = ('alpha.md', 'beta.md')) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        design = pathlib.Path(tmp) / 'docs' / 'design'
        design.mkdir(parents=True)
        for doc in docs:
            (design / doc).write_text('# x\n', encoding='utf-8')
        (design / 'index.md').write_text(index_text, encoding='utf-8')
        return run(pathlib.Path(tmp))


def self_check() -> int:
    """四个变异态，断言守卫真的会红——这是守卫本身唯一的「反向验证」。"""
    cases = [
        ('登记齐全 + 正文交叉引用不误判', GOOD_INDEX, 0),
        ('删掉一行 ⇒ 未登记', GOOD_INDEX.replace('| `beta.md` | 乙 | 定稿 |\n', ''), 1),
        (
            '加一行幽灵文档 ⇒ 失效登记',
            GOOD_INDEX.replace('| `beta.md` | 乙 | 定稿 |', '| `beta.md` | 乙 | 定稿 |\n| `ghost.md` | 幽灵 | 定稿 |'),
            1,
        ),
        ('改掉小节标题 ⇒ 环境异常', GOOD_INDEX.replace('设计资产索引', '随便什么标题'), 2),
    ]
    failed = 0
    for name, index_text, want in cases:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            got = _probe_repo(index_text)
        flag = 'OK' if got == want else 'FAIL'
        print(f'  [{flag}] {name}：期望退出码 {want}，实得 {got}')
        if got != want:
            failed += 1
    print(f'[check_design_doc_index] 自检{"通过" if not failed else f"失败 {failed} 项"}（{len(cases)} 态）')
    return 0 if not failed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='设计文档索引守卫：docs/design/*.md 与 index.md 索引表集合相等')
    parser.add_argument('--root', default=str(pathlib.Path(__file__).resolve().parents[1]), help='仓库根目录')
    parser.add_argument('--self-check', action='store_true', help='跑四个变异态，验证守卫真的会红')
    args = parser.parse_args(argv)
    if args.self_check:
        return self_check()
    return run(pathlib.Path(args.root))


if __name__ == '__main__':
    sys.exit(main())
