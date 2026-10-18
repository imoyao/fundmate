#!/usr/bin/env python3
"""`guard_ask_git_once.py` 的回归网（源 CNB #573，2026-10-18）。

这条守卫要钉住的是**形状**而不是某个 bug 的具体写法：同一函数里同一个 git 询问
出现两次、且第二遍丢掉退出码 ⇒ 报红。它的价值全在「能不能认出真实代码」，
所以最重的两条用例都喂**真实来源**（一个不可变的历史提交），而不是我手搓的片段。
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_GUARD = _REPO_ROOT / 'scripts' / 'guard_ask_git_once.py'

sys.path.insert(0, str(_REPO_ROOT / 'scripts'))
import guard_ask_git_once as guard  # noqa: E402


def test_catches_the_real_pre_fix_code():
    """拿**修复前**的真实代码喂守卫 ⇒ 必须报红。

    来源锚在不可变提交 `871816f2` 的父提交（即 `origin/dev` 上 #573 之前的那一版）。
    钉历史而不是钉工作区：工作区会被下一个人改，判据自己就失效了（#450 的教训）。
    """
    rev = '871816f2^:scripts/bridge/machine_branch.py'
    proc = subprocess.run(['git', 'show', rev], cwd=_REPO_ROOT, capture_output=True, text=True, encoding='utf-8')
    if proc.returncode != 0:
        pytest.skip(f'取不到历史版本 {rev}（浅克隆？）：{proc.stderr[:120]}')
    problems = guard.scan_source(proc.stdout, 'machine_branch.py')
    assert problems, '守卫认不出 #573 的原始形态 —— 整张网恒绿'
    assert any('merge-tree' in p or '两次' in p for p in problems), problems


def test_current_tree_is_clean():
    """当前仓库必须干净 —— 否则这条守卫会变成「一直在喊、没人再听」。"""
    problems, unreadable = guard.scan_paths(sorted((_REPO_ROOT / 'scripts').rglob('*.py')))
    assert not unreadable, unreadable
    assert not problems, problems


def test_asks_once_then_reads_second_output_is_flagged():
    """最小可携形态：`code=_git(X)` → `_, out = _git(X)`。"""
    src = """
def run(cwd):
    code, _, _ = _git(['merge-tree', '--write-tree', 'a', 'b'], cwd)
    if code == 1:
        _, out, _ = _git(['merge-tree', '--write-tree', 'a', 'b'], cwd)
"""
    problems = guard.scan_source(src, 'x.py')
    assert len(problems) == 1, problems
    assert 'run' in problems[0], problems


def test_retry_that_keeps_the_status_is_allowed():
    """重试本身不违法：两遍都读退出码 ⇒ 不报。

    判据要的是「把两次结果拼成一个结论」，不是「不许问两遍」——
    把合法的重试也拦下来，守卫就会成为绕路动力。
    """
    src = """
def run(cwd):
    code, out, _ = _git(['push', 'origin', 'HEAD'], cwd)
    if code != 0:
        code, out, _ = _git(['push', 'origin', 'HEAD'], cwd)
    return code, out
"""
    assert guard.scan_source(src, 'x.py') == []


def test_different_queries_are_allowed():
    """参数不同就是两个不同的询问（形状不同 ⇒ 不报）。"""
    src = """
def run(cwd):
    _, out, _ = _git(['merge-tree', '--write-tree', 'a', 'b'], cwd)
    _, out2, _ = _git(['merge-tree', '--write-tree', 'b', 'a'], cwd)
    return out, out2
"""
    assert guard.scan_source(src, 'x.py') == []


def test_syntax_error_is_reported_not_ignored():
    """读不懂的源码必须**说出来**，不得静默通过（#171 的失败态纪律）。"""
    problems = guard.scan_source('def run(:\n  pass\n', 'broken.py')
    assert problems and '语法' in problems[0], problems


def test_guard_self_check_on_unreadable_path(tmp_path):
    """读不到的文件 ⇒ 退 2 且声明不可信（不得读成「没问题」）。"""
    missing = tmp_path / 'nope.py'
    rc = guard.main(['--file', str(missing)])
    assert rc == 2, f'读不到输入时必须退 2，实际 {rc}'
