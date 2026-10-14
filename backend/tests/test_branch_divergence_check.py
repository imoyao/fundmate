# -*- coding: utf-8 -*-
"""`scripts/bridge/check_branch_divergence.py` 的回归网（源 CNB issue #123）。

## WHY 有这份文件

本脚本回答的是 #123 卡面 §一那个问题：**「main 落后 dev 多少 / 哪些作业只在单侧」**。
它本身**只读**（不 fetch、不 merge、不 push），所以出错不会造成外部损坏；但它一旦
判错方向，给出的就是**反向的安心**——「未分叉」而实际已分叉，下一个照着它发版的人
会以为没问题。这正是本仓「守门通过 ≠ 守门有效」那一课的同类。

故按四类钉死：

1. **方向语义**：`git diff --name-status left right` 里 `D` = 只在 `left`、`A` = 只在 `right`。
   这条曾是**真 bug**：初版把 `A` 和 `D` 都算「只在 right」，于是 `.cnb.yml` 与
   `cnb-github-backfill.yml` 同时出现在两侧列表里，报告自相矛盾；
2. **分叉判定**：`main` 独有提交 > 0 ⇒ 分叉；两侧一致 ⇒ 不分叉（退出码 1 / 0）；
3. **独有提交清单**：分叉时报告须列出两侧各自的提交 SHA（照抄即可救援），
   跳过 merge commit、超限截断带注记 —— 清单是断链卡面（`notify_mirror_divergence.py`）的原料；
4. **只读**：出现 `fetch` / `merge` / `push` 即越界。

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


def test_compute_lists_unique_commits(mod, diverged_repo):
    """清单 = 救援照抄的 SHA：main 侧须含 `main-only`、dev 侧须含 `dev-only`。

    没有清单功能的旧版在这里必须红 —— 只报数字修不了根因（CNB #118 卡面同诉求）。
    """
    res = mod.compute('main', 'dev', str(diverged_repo))
    assert any('main-only' in c for c in res['left_only_commits']), (
        f'main 独有提交清单缺 main-only：{res["left_only_commits"]}'
    )
    assert any('dev-only' in c for c in res['right_only_commits']), (
        f'dev 独有提交清单缺 dev-only：{res["right_only_commits"]}'
    )
    # 方向不能反：main-only 不得出现在 dev 侧清单里
    assert not any('main-only' in c for c in res['right_only_commits']), '清单方向反了'
    assert not any('dev-only' in c for c in res['left_only_commits']), '清单方向反了'


def test_commit_list_skips_merge_commits(mod, diverged_repo):
    """merge commit 只是症状不是内容，不进清单（否则把业务提交挤下去）。"""
    import os

    env = {
        'GIT_AUTHOR_NAME': 't',
        'GIT_AUTHOR_EMAIL': 't@e',
        'GIT_COMMITTER_NAME': 't',
        'GIT_COMMITTER_EMAIL': 't@e',
        'PATH': os.environ['PATH'],
    }
    repo = diverged_repo
    # 在 main 上造一个 merge commit（合并 dev 的历史但不含其 tip）
    subprocess.run(['git', 'checkout', '-q', 'main'], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(
        ['git', 'merge', '-q', '--no-ff', '-m', 'merge dev', 'dev~0'],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )
    res = mod.compute('main', 'dev', str(repo))
    assert not any('merge dev' in c for c in res['left_only_commits']), (
        f'merge commit 不该进清单：{res["left_only_commits"]}'
    )


def test_commit_list_truncated_with_note(mod, diverged_repo):
    """超 LIMIT 截断 + 「还有 N 条」注记：救援照抄最近的足够定位，别把报告撑爆。"""
    import os

    env = {
        'GIT_AUTHOR_NAME': 't',
        'GIT_AUTHOR_EMAIL': 't@e',
        'GIT_COMMITTER_NAME': 't',
        'GIT_COMMITTER_EMAIL': 't@e',
        'PATH': os.environ['PATH'],
    }
    repo = diverged_repo
    subprocess.run(['git', 'checkout', '-q', 'main'], cwd=repo, check=True, capture_output=True, env=env)
    limit = mod.COMMIT_LIST_LIMIT
    for i in range(limit + 3):
        (repo / f'f{i}.txt').write_text(f'{i}\n', encoding='utf-8')
        subprocess.run(['git', 'add', '.'], cwd=repo, check=True, capture_output=True, env=env)
        subprocess.run(
            ['git', 'commit', '-q', '-m', f'main-bulk-{i}'], cwd=repo, check=True, capture_output=True, env=env
        )
    res = mod.compute('main', 'dev', str(repo))
    listed = res['left_only_commits']
    assert len(listed) == limit + 1, f'应截断到 {limit} 条 + 1 行注记，实际 {len(listed)} 条'
    # 注记里的「还有 N 条」必须与 git 自己的计数对账：
    # fixture 已有 1 条 main 独有提交，本测试又加了 limit+3 条 ⇒ 共 limit+4 条，剩 4 条。
    real = subprocess.run(
        ['git', 'rev-list', '--count', '--no-merges', 'dev..main'],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()
    assert f'还有 {int(real) - limit} 条' in listed[-1], f'末行应是「还有 N 条」注记：{listed[-1]}'


def test_report_marks_diverged(mod, diverged_repo):
    res = mod.compute('main', 'dev', str(diverged_repo))
    report = mod.build_report(res)
    assert '已分叉' in report
    assert '.cnb.yml' in report
    assert 'cnb-github-backfill.yml' in report


def test_report_lists_unique_commits(mod, diverged_repo):
    """报告须含两侧独有提交的 SHA 行（救援照抄清单，不是只给数字）。"""
    res = mod.compute('main', 'dev', str(diverged_repo))
    report = mod.build_report(res)
    assert 'main-only' in report, '报告缺 main 侧独有提交'
    assert 'dev-only' in report, '报告缺 dev 侧独有提交'
    assert 'cherry-pick' in report, '报告须说明清单用途（照抄 cherry-pick）'


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

    args = argparse.Namespace(
        left='main', right='dev', cwd=str(diverged_repo), out=None, report=True, jobs_only=False, explain=False
    )
    assert mod.run(args) == 1, '分叉必须以退出码 1 表达（供 CI 当信号）'


def test_run_returns_0_when_same(mod, diverged_repo):
    import argparse

    args = argparse.Namespace(
        left='dev', right='dev', cwd=str(diverged_repo), out=None, report=True, jobs_only=False, explain=False
    )
    assert mod.run(args) == 0


def test_run_returns_2_on_missing_ref(mod, diverged_repo):
    import argparse

    args = argparse.Namespace(
        left='no-such-branch',
        right='dev',
        cwd=str(diverged_repo),
        out=None,
        report=True,
        jobs_only=False,
        explain=False,
    )
    assert mod.run(args) == 2, '取不到分支要用独立退出码，别混进「已分叉」'


def test_explain_dry_runs_the_release_merge(mod, diverged_repo):
    """`--explain` 必须真的跑 merge-tree 试算，并给出可执行的结论。

    没有 `--explain` 的旧版在这里必须红 —— `.cnb.yml` 一直在调这个参数，
    旧版 argparse 直接报错、被 `|| true` 吞掉，自检从未真正生效过。
    """
    import argparse

    args = argparse.Namespace(
        left='main', right='dev', cwd=str(diverged_repo), out=None, report=True, jobs_only=False, explain=True
    )
    assert mod.run(args) == 1
    res = mod.compute('main', 'dev', str(diverged_repo))
    res['merge_dry_run'] = mod.merge_dry_run('main', 'dev', str(diverged_repo))
    report = mod.build_report(res)
    # fixture 两侧改的是不同文件 ⇒ 可干净合并
    assert res['merge_dry_run']['ok'] is True, f'不同文件的合并应可干净进行：{res["merge_dry_run"]}'
    assert '可干净合并' in report, '报告须给出合并试算结论'


def test_explain_reports_conflicts(mod, diverged_repo):
    """两侧改**同一个文件** ⇒ 试算须报冲突并列出文件（发版前知道要解哪）。"""
    import os
    import subprocess

    env = {
        'GIT_AUTHOR_NAME': 't',
        'GIT_AUTHOR_EMAIL': 't@e',
        'GIT_COMMITTER_NAME': 't',
        'GIT_COMMITTER_EMAIL': 't@e',
        'PATH': os.environ['PATH'],
    }
    repo = diverged_repo
    subprocess.run(['git', 'checkout', '-q', 'main'], cwd=repo, check=True, capture_output=True, env=env)
    (repo / 'shared.txt').write_text('main-side\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(
        ['git', 'commit', '-q', '-m', 'main edits shared'], cwd=repo, check=True, capture_output=True, env=env
    )
    subprocess.run(['git', 'checkout', '-q', 'dev'], cwd=repo, check=True, capture_output=True, env=env)
    (repo / 'shared.txt').write_text('dev-side\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(
        ['git', 'commit', '-q', '-m', 'dev edits shared'], cwd=repo, check=True, capture_output=True, env=env
    )
    dry = mod.merge_dry_run('main', 'dev', str(repo))
    assert dry['ok'] is False, f'同文件双改必须判冲突：{dry}'
    assert 'shared.txt' in dry['conflicts'], f'冲突清单须含 shared.txt：{dry["conflicts"]}'


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
    # 清单对账：main 独有的**非 merge**提交存在时，脚本清单第一条须与 git log 第一条逐字相同。
    # 注意两处计数口径不同（有意为之）：`left_only` 用 rev-list（含 merge，回答「落后几个」）；
    # 清单用 --no-merges（镜像断链场景里 merge 只是症状不是内容，见 list_unique_commits docstring）。
    # 故卫句必须落在同一口径上——曾按含 merge 的计数放行，真实仓 main 独有全是 merge 时
    # `git log --no-merges` 输出为空，`splitlines()[0]` 直接 IndexError。
    real_lines = subprocess.run(
        ['git', 'log', '--oneline', '--no-decorate', '--no-merges', 'origin/dev..origin/main'],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if real_lines:
        assert res['left_only_commits'], f'git 能列出 {len(real_lines)} 条，脚本清单却是空的'
        assert res['left_only_commits'][0] == real_lines[0], (
            f'脚本清单首条 {res["left_only_commits"][:1]} 与 git 的 {real_lines[0]!r} 不一致'
        )
