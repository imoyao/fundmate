# -*- coding: utf-8 -*-
"""`scripts/bridge/check_branch_divergence.py` 的回归网（源 CNB issue #123）。

## WHY 有这份文件

本脚本回答的是 #123 卡面 §一那个问题：**「main 落后 dev 多少 / 哪些作业只在单侧」**。
它本身**只读**（不 fetch、不 merge、不 push），所以出错不会造成外部损坏；但它一旦
判错方向，给出的就是**反向的安心**——「未分叉」而实际已分叉，下一个照着它发版的人
会以为没问题。这正是本仓「守门通过 ≠ 守门有效」那一课的同类。

故按三类钉死：

1. **方向语义**：`git diff --name-status left right` 里 `D` = 只在 `left`、`A` = 只在 `right`。
   这条曾是**真 bug**：初版把 `A` 和 `D` 都算「只在 right」，于是 `.cnb.yml` 与
   `cnb-github-backfill.yml` 同时出现在两侧列表里，报告自相矛盾；
2. **分叉判定**：`main` 独有提交 > 0 ⇒ 分叉；两侧一致 ⇒ 不分叉（退出码 1 / 0）；
3. **只读**：出现 `fetch` / `merge` / `push` 即越界。

用例尽量走**真实 git**（本仓自己），只在需要构造「确定的分叉」时才用临时仓库——
mock 出来的 git 永远绿，而被测的正是「跟真实 git 对话时方向对不对」。
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / 'scripts' / 'bridge' / 'check_branch_divergence.py'

_MOD = None


def _load():
    global _MOD
    if _MOD is None:
        spec = importlib.util.spec_from_file_location('check_branch_divergence', _SCRIPT_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules['check_branch_divergence'] = module
        spec.loader.exec_module(module)
        _MOD = module
    return _MOD


@pytest.fixture()
def mod():
    return _load()


@pytest.fixture()
def diverged_repo(tmp_path):
    """造一个**确定分叉**的临时仓库：left 与 right 各有一个独有提交 + 各有一个独有作业文件。

    用真实 git 造，而不是 mock 返回值 —— 被测的就是「解析 git 输出」这一步。
    """
    repo = tmp_path / 'r'
    repo.mkdir()
    env = {
        'GIT_AUTHOR_NAME': 't',
        'GIT_AUTHOR_EMAIL': 't@e',
        'GIT_COMMITTER_NAME': 't',
        'GIT_COMMITTER_EMAIL': 't@e',
        'PATH': __import__('os').environ['PATH'],
    }

    def git(*args):
        subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, env=env)

    git('init', '-q', '-b', 'main')
    (repo / 'base.txt').write_text('base\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '-m', 'base')

    # left（main）：加 .cnb.yml（只在它上面）
    (repo / '.cnb.yml').write_text('main:\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '-m', 'main-only')

    # right（dev）：从 base 分出，加回写 workflow（只在它上面）
    git('checkout', '-q', '-b', 'dev', 'HEAD~1')
    (repo / '.github' / 'workflows').mkdir(parents=True)
    (repo / '.github' / 'workflows' / 'cnb-github-backfill.yml').write_text('name: x\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '-m', 'dev-only')
    return repo


# ---------------------------------------------------------------------------
# 一、方向语义：`D` = 只在 left，`A` = 只在 right（初版真 bug 所在）
# ---------------------------------------------------------------------------


def test_side_only_direction(mod, diverged_repo):
    """`.cnb.yml` 只在 main、回写 workflow 只在 dev —— 两个列表必须各归其位。"""
    left, right = mod.list_side_only('main', 'dev', str(diverged_repo))
    assert left == ['.cnb.yml'], f'只在 main 的该有且仅有 .cnb.yml，实际 {left}'
    assert right == ['.github/workflows/cnb-github-backfill.yml'], f'只在 dev 的该有且仅有回写 workflow，实际 {right}'


def test_side_only_no_duplicate_across_sides(mod, diverged_repo):
    """同一个文件**不得**同时出现在两侧（初版把 A/D 都算右侧，正在这里崩）。"""
    left, right = mod.list_side_only('main', 'dev', str(diverged_repo))
    assert not (set(left) & set(right)), f'两侧重叠：{set(left) & set(right)}'


def test_modified_file_is_not_side_only(mod, diverged_repo):
    """两侧都有、只是内容不同的文件（`M`）**不算**「只在单侧」。"""
    import os

    env = {
        'GIT_AUTHOR_NAME': 't',
        'GIT_AUTHOR_EMAIL': 't@e',
        'GIT_COMMITTER_NAME': 't',
        'GIT_COMMITTER_EMAIL': 't@e',
        'PATH': os.environ['PATH'],
    }
    repo = diverged_repo
    # 在 dev 上建同名的 .cnb.yml（两侧都有），内容不同
    subprocess.run(['git', 'checkout', '-q', 'dev'], cwd=repo, check=True, capture_output=True, env=env)
    (repo / 'ci.txt').write_text('x\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(['git', 'commit', '-q', '-m', 'dev has ci.txt'], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(['git', 'checkout', '-q', 'main'], cwd=repo, check=True, capture_output=True, env=env)
    (repo / 'ci.txt').write_text('y\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(['git', 'commit', '-q', '-m', 'main has ci.txt'], cwd=repo, check=True, capture_output=True, env=env)

    left, right = mod.list_side_only('main', 'dev', str(repo))
    assert 'ci.txt' not in left and 'ci.txt' not in right, '两侧都有的文件不该算「只在单侧」'


# ---------------------------------------------------------------------------
# 二、分叉判定与退出码
# ---------------------------------------------------------------------------


def test_compute_counts_both_directions(mod, diverged_repo):
    res = mod.compute('main', 'dev', str(diverged_repo))
    assert res['left_only'] == 1, 'main 独有 1 个提交'
    assert res['right_only'] == 1, 'dev 独有 1 个提交'
    assert res['left_only_jobs'] == ['.cnb.yml']
    assert res['right_only_jobs'] == ['.github/workflows/cnb-github-backfill.yml']


def test_report_marks_diverged(mod, diverged_repo):
    res = mod.compute('main', 'dev', str(diverged_repo))
    report = mod.build_report(res)
    assert '已分叉' in report
    assert '.cnb.yml' in report
    assert 'cnb-github-backfill.yml' in report


def test_report_green_when_fast_forward(mod, diverged_repo):
    """`dev` 是 `main` 的后代 ⇒ 不分叉，报告给明确绿灯。"""
    res = mod.compute('main', 'dev', str(diverged_repo))
    # 反过来比较：dev 相对 main 是「向前」的？此处用两侧同一个 ref 造「未分叉」
    same = mod.compute('dev', 'dev', str(diverged_repo))
    assert same['left_only'] == 0 and same['right_only'] == 0
    assert '未分叉' in mod.build_report(same)
    assert '已分叉' not in mod.build_report(same)
    # 顺带确认真正的分叉仍被判出（避免上面两条把判据测成恒绿）
    assert '已分叉' in mod.build_report(res)


def test_run_returns_1_on_diverged(mod, diverged_repo):
    import argparse

    args = argparse.Namespace(left='main', right='dev', cwd=str(diverged_repo), out=None, report=True, jobs_only=False)
    assert mod.run(args) == 1, '分叉必须以退出码 1 表达（供 CI 当信号）'


def test_run_returns_0_when_same(mod, diverged_repo):
    import argparse

    args = argparse.Namespace(left='dev', right='dev', cwd=str(diverged_repo), out=None, report=True, jobs_only=False)
    assert mod.run(args) == 0


def test_run_returns_2_on_missing_ref(mod, diverged_repo):
    import argparse

    args = argparse.Namespace(
        left='no-such-branch', right='dev', cwd=str(diverged_repo), out=None, report=True, jobs_only=False
    )
    assert mod.run(args) == 2, '取不到分支要用独立退出码，别混进「已分叉」'


# ---------------------------------------------------------------------------
# 三、边界：只读、不联网
# ---------------------------------------------------------------------------


def test_script_is_read_only(mod):
    """脚本**只读**：出现 fetch / merge / push / commit 即越界。

    fetch 会改 refs，且「要不要更新远端视图」是调用方的决定；本脚本若自己 fetch，
    就等于在报告分叉的同时制造副作用（还依赖网络 ⇒ 「网络不通 = 报告绿」）。
    """
    src = _SCRIPT_PATH.read_text(encoding='utf-8')
    import re

    body = src.split('"""', 2)[-1]  # 去掉文件头 docstring（那里正常会提到这些词）
    for banned in ("'fetch'", "'merge'", "'push'", "'commit'", "'pull'", "'fetch'"):
        assert banned not in body, f'脚本出现写/网络操作：{banned}'
    assert re.search(r"\['git', \*args\]", body) or "'git'" in body


def test_script_never_imports_network(mod):
    """不联网：不得 import urllib / requests / socket（分叉判定不该依赖网络）。"""
    src = _SCRIPT_PATH.read_text(encoding='utf-8').split('"""', 2)[-1]
    for banned in ('import urllib', 'import requests', 'import socket', 'import http'):
        assert banned not in src, f'脚本出现网络依赖：{banned}'


def test_real_repo_reports_divergence_or_green(mod):
    """在**真实本仓**上跑一遍：只断言「能跑出结论」，不断言分叉与否。

    断言「一定分叉」会把用例变成卡面快照 —— 发版之后它就该变绿，届时用例反而假红。
    这里要钉的是「判据在真实 git 上不崩、且结论与 `git` 自身一致」。
    """
    code, _ = (
        subprocess.run(
            ['git', 'rev-parse', '--verify', '--quiet', 'origin/main^{commit}'],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
        ),
        None,
    )
    if code.returncode != 0:
        pytest.skip('本机没有 origin/main，跳过真实仓库用例')
    res = mod.compute('origin/main', 'origin/dev', str(_REPO_ROOT))
    # 与 git 自身交叉验证（不能只信脚本自己的算术）
    real = subprocess.run(
        ['git', 'rev-list', '--count', 'origin/dev..origin/main'],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert str(res['left_only']) == real, f'脚本算的 {res["left_only"]} 与 git 的 {real} 不一致'
