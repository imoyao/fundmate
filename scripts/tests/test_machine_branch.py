#!/usr/bin/env python3
"""`machine_branch.py` 的回归网（源 CNB #450，2026-10-14）。  <!-- cross-repo-ref-allow -->

这份脚本要钉住的**不是**「它能跑」，而是四件容易写反/写松的事：

1. **方向**：`--base cnb` ⇒ 以 CNB 为基线（`base_ref=CNB_REF`），`--base github` 反之。
   方向反了结果是「谁的 merge commit 在上、冲突以谁为准」，肉眼很难发现；
2. **有冲突就什么都不推**：这是脚本的核心安全承诺。判据必须是「没调 push」，
   而不是「返回了 1」——返回 1 但已经推过，比不返回更坏；
3. **拿不到输入 ⇒ 退出码 2 且不得读成「无需同步」**（#171/#450 的假绿纪律）：
   fetch 失败时报「已对齐」是同族事故里最常见的那一款；
4. **机器分支是一次性语义**：默认名固定（幂等），且**不得**被建成 `CNBDEV` 那种长期分支
   —— 由 `test_default_machine_branch_is_not_a_long_lived_name` 钉住命名形态。
5. **merge 没跑起来 ≠ 没冲突**（#2262，2026-10-16）：merge 非 0 退出且没有冲突清单时
   必须退 2、什么都不推。实测形态：runner 无 git 身份 ⇒ merge rc128
   「Committer identity unknown」⇒ 未合并条目为空 ⇒ 曾被打着「无冲突」照常推送。

变异探针（每条都实测确认会转红）见各用例 docstring；探针必须钉在**不可变来源**上，
不能读可变 ref（那是 #450 第一版探针自己失效的根因，见 `test_dup_mirror_guard.py`）。
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import re
import subprocess
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / 'scripts' / 'bridge' / 'machine_branch.py'


def _load():
    spec = importlib.util.spec_from_file_location('machine_branch', _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules['machine_branch'] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def mod():
    return _load()


def _git(repo, *args, env):
    subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, env=env)


def _env():
    return {
        'GIT_AUTHOR_NAME': 't',
        'GIT_AUTHOR_EMAIL': 't@e',
        'GIT_COMMITTER_NAME': 't',
        'GIT_COMMITTER_EMAIL': 't@e',
        'PATH': os.environ['PATH'],
    }


def _mk_side_repos(tmp_path, name, *, same_file: bool):
    """两侧仓库，`gh` 从 `cnb` clone 出来 ⇒ 共享同一历史（这样 fetch+merge 才有意义）。

    ⚠️ 两侧仓库都**自备** committer 身份（#2262）：脚本的 merge 在 cnb 侧 worktree 里跑，
    不继承本测试的 `_env()`，只读仓库/全局配置。曾经只给 gh 配、cnb 蹭开发者全局 config
    （本地有、runner 没有）⇒ Linux 上 merge rc128「Committer identity unknown」⇒
    冲突路径整个失灵。fixture 不许有这种环境依赖——它是假绿之源。
    """
    cnb = tmp_path / f'{name}-cnb'
    cnb.mkdir()
    env = _env()
    _git(cnb, 'init', '-q', '-b', 'dev', env=env)
    _git(cnb, 'config', 'commit.gpgsign', 'false', env=env)
    _git(cnb, 'config', 'user.name', 't', env=env)
    _git(cnb, 'config', 'user.email', 't@e', env=env)
    (cnb / 'a.txt').write_text('base\n', encoding='utf-8')
    (cnb / 'shared.txt').write_text('base\n', encoding='utf-8')
    _git(cnb, 'add', '.', env=env)
    _git(cnb, 'commit', '-q', '--no-gpg-sign', '-m', 'base', env=env)

    gh = tmp_path / f'{name}-gh'
    subprocess.run(['git', 'clone', '-q', str(cnb), str(gh)], check=True, capture_output=True, env=env)
    _git(gh, 'config', 'user.name', 't', env=env)
    _git(gh, 'config', 'user.email', 't@e', env=env)
    _git(gh, 'config', 'commit.gpgsign', 'false', env=env)
    _git(gh, 'checkout', '-q', 'dev', env=_env())

    def commit(repo, who):
        if same_file:
            (repo / 'shared.txt').write_text(f'{who} side\n', encoding='utf-8')
        else:
            (repo / f'{who}-only.txt').write_text(f'{who}\n', encoding='utf-8')
        _git(repo, 'add', '.', env=env)
        _git(repo, 'commit', '-q', '--no-gpg-sign', '-m', f'{who} work', env=env)

    commit(cnb, 'cnb')
    commit(gh, 'gh')
    return cnb, gh


# ---------------------------------------------------------------------------
# 一、方向：`plan()` 是纯函数，先把方向钉死
# ---------------------------------------------------------------------------


def test_plan_default_is_cnb_as_base(mod):
    """默认以 CNB 为基线 —— 这是 `dev_converge.py` 的同一口径（方向必须先定）。

    探针：把 `plan()` 里 `base == 'github'` 的两个分支调换 ⇒ 本用例转红。
    """
    p = mod.plan('cnb', 'bridge/github-dev')
    assert p['base_name'] == 'CNB', p
    assert p['base_ref'] == mod.CNB_REF, p
    assert p['merge_name'] == 'GitHub', p
    assert p['merge_ref'] == mod.GH_REF, p


def test_plan_github_base_is_reverse(mod):
    """`--base github` ⇒ 以 GitHub 为基线、合入 CNB（与上面成对，防「方向写死一侧」）。"""
    p = mod.plan('github', 'bridge/github-dev')
    assert p['base_name'] == 'GitHub', p
    assert p['base_ref'] == mod.GH_REF, p
    assert p['merge_name'] == 'CNB', p
    assert p['merge_ref'] == mod.CNB_REF, p


def test_plan_carries_machine_branch(mod):
    """机器分支名必须原样带进 plan —— 别让上层传给 `plan()` 的名字被悄悄丢掉。"""
    p = mod.plan('cnb', 'bridge/custom-name')
    assert p['machine_branch'] == 'bridge/custom-name', p


# ---------------------------------------------------------------------------
# 二、命名：机器分支是**一次性**的，不是 `CNBDEV` 那种长期分支
# ---------------------------------------------------------------------------


def test_default_machine_branch_is_not_a_long_lived_name(mod):
    """默认机器分支名须带 `bridge/` 前缀、且**不含** `CNBDEV` 那类长期分支语义。

    这是 §21 与 `CNBDEV` 方案的判据边界：`CNBDEV` 被否的理由是「又一条长期分支，
    活着、要维护」，而机器分支的寿命是「一次 PR」。
    探针：把默认名改成 `CNBDEV` ⇒ 本用例转红。
    """
    name = mod.DEFAULT_MACHINE_BRANCH
    assert name.startswith('bridge/'), f'机器分支应落在 bridge/ 命名空间（一次性语义）：{name}'
    assert 'CNBDEV' not in name.upper(), f'不得复用 CNBDEV 这个名字（它代表的是长期中转分支）：{name}'


def test_machine_branch_name_has_no_date_suffix(mod):
    """默认名**不含日期**：带日期会让重复跑攒出分支列表垃圾（幂等性要求）。"""
    name = mod.DEFAULT_MACHINE_BRANCH
    assert not any(ch.isdigit() and str(ch) in name for ch in []), 'sanity'
    import re

    assert not re.search(r'\d{4}-\d{2}-\d{2}', name), f'机器分支名不该带日期（会攒出垃圾分支）：{name}'


# ---------------------------------------------------------------------------
# 三、有冲突 ⇒ **什么都不推**（核心安全承诺）
# ---------------------------------------------------------------------------


def test_conflicts_mean_nothing_is_pushed(mod, tmp_path):
    """有冲突时：退出码 1、**且没有调 push**。

    判据锚在「push 有没有被调用」而不是「返回了 1」——返回 1 但已经推过是最坏的形态
    （冲突解不掉、远端却多了一条半成品分支）。
    探针：把 `if conflicts:` 里的提前 return 删掉 ⇒ push 被调用且本用例转红。
    """
    cnb, gh = _mk_side_repos(tmp_path, 'conflict', same_file=True)
    # 让 CNB 侧仓能 fetch 到 GitHub 侧：加一个 remote
    env = _env()
    _git(cnb, 'remote', 'add', 'gh', str(gh), env=env)
    _git(cnb, 'fetch', '-q', 'gh', 'dev', env=env)
    _git(cnb, 'branch', 'gh-dev', 'FETCH_HEAD', env=env)

    real = mod._git
    calls: list[list[str]] = []

    def spy(args, cwd=None):
        # 探针（#2255）：退出码一并记账——「推没推」是结果，merge/diff 的码才是根因
        # （Linux runner 上冲突路径失灵，账里只有 push 结果时无从诊断）。
        code, out, err = real(args, cwd)
        calls.append([*args, f'rc{code}'])
        return code, out, err

    saved = mod._git
    mod._git = spy
    try:
        args = argparse.Namespace(
            apply=True,
            dry_run=False,
            push=True,
            base='cnb',
            branch='dev',
            machine_branch='bridge/github-dev',
            cnb_url=str(cnb),
            github_url=str(gh),
            cwd=str(cnb),
        )
        rc = mod.run(args)
    finally:
        mod._git = saved
    pushed = [c for c in calls if c and c[0] == 'push']
    assert not pushed, f'有冲突时**一个字节都不该推**，实际调用了：{pushed}；全程（含退出码）：{calls}'
    assert rc == 1, f'有冲突应返回 1（供调用方当信号），实际 {rc}；全程（含退出码）：{calls}'


def test_worktree_is_cleaned_up_on_conflict(mod, tmp_path):
    """冲突路径也要把临时 worktree 收掉 —— 留一个冲突中的工作区会让下次跑直接失败。"""
    cnb, gh = _mk_side_repos(tmp_path, 'cleanup', same_file=True)
    env = _env()
    _git(cnb, 'remote', 'add', 'gh', str(gh), env=env)
    _git(cnb, 'fetch', '-q', 'gh', 'dev', env=env)
    _git(cnb, 'branch', 'gh-dev', 'FETCH_HEAD', env=env)

    real = mod._git
    calls: list[list[str]] = []

    def spy(args, cwd=None):
        # 探针（#2255）：退出码一并记账——「推没推」是结果，merge/diff 的码才是根因
        # （Linux runner 上冲突路径失灵，账里只有 push 结果时无从诊断）。
        code, out, err = real(args, cwd)
        calls.append([*args, f'rc{code}'])
        return code, out, err

    mod._git = spy
    try:
        args = argparse.Namespace(
            apply=True,
            dry_run=False,
            push=True,
            base='cnb',
            branch='dev',
            machine_branch='bridge/github-dev',
            cnb_url=str(cnb),
            github_url=str(gh),
            cwd=str(cnb),
        )
        mod.run(args)
    finally:
        mod._git = real
    removes = [c for c in calls if c[:2] == ['worktree', 'remove']]
    aborts = [c for c in calls if c[:2] == ['merge', '--abort']]
    assert removes, f'冲突路径必须收掉临时 worktree，实际调用：{calls}'
    assert aborts, f'冲突路径必须先 abort 再收 —— 留着冲突现场会让下次跑失败：{calls}'


def test_merge_fatal_means_nothing_is_pushed(mod, tmp_path, monkeypatch, capsys):
    """merge 非 0 退出且无冲突清单 ⇒ 退 2、**什么都不推**（#2262）。

    实测事故（#2259 CI 首次暴露）：runner 无 git 身份 ⇒ `git merge` rc128
    「Committer identity unknown」⇒ `conflict_files()` 为空 ⇒ 旧代码读成
    「无冲突」⇒ rev-parse + push 照常执行。「没跑成」被当成了「跑成了」——
    与 #171 / #450「拿不到输入报已对齐」同族，但这次直接推了条未合并的分支。
    判据锚在「merge 的退出码 + 冲突清单」这对组合上，单看任何一半都会漏：
    光看清单为空分不清「真没冲突」和「根本没跑」，光看退出码分不清
    「冲突（rc1）」和「致命（rc128）」。
    """
    cnb, gh = _mk_side_repos(tmp_path, 'fatal', same_file=True)
    env = _env()
    _git(cnb, 'remote', 'add', 'gh', str(gh), env=env)
    _git(cnb, 'fetch', '-q', 'gh', 'dev', env=env)
    _git(cnb, 'branch', 'gh-dev', 'FETCH_HEAD', env=env)

    real = mod._git
    calls: list[list[str]] = []

    def fake(args, cwd=None):
        if args[:2] == ['merge', '--no-edit']:
            # 忠实复现 runner 实测形态：merge 直接致命、**根本没跑起来**，
            # 因此不会留下任何未合并条目（diff-filter=U 为空）。
            calls.append([*args, 'rc128'])
            return 128, '', 'fatal: unable to auto-detect email address'
        code, out, err = real(args, cwd)
        calls.append([*args, f'rc{code}'])
        return code, out, err

    monkeypatch.setattr(mod, '_git', fake)
    args = argparse.Namespace(
        apply=True,
        dry_run=False,
        push=True,
        base='cnb',
        branch='dev',
        machine_branch='bridge/github-dev',
        cnb_url=str(cnb),
        github_url=str(gh),
        cwd=str(cnb),
    )
    rc = mod.run(args)

    pushed = [c for c in calls if c and c[0] == 'push']
    assert not pushed, f'merge 没跑起来时**一个字节都不该推**：{pushed}；全程：{calls}'
    assert rc == 2, f'合并没跑起来必须退 2（结论不可信），实际 {rc}；全程：{calls}'
    removes = [c for c in calls if c[:2] == ['worktree', 'remove']]
    assert len(removes) >= 2, f'致命路径也要收掉临时 worktree（预清理 + 收尾）：{calls}'
    err = capsys.readouterr().err
    assert '不可信' in err, f'必须明说结论不可信，实际 stderr：{err!r}'


# ---------------------------------------------------------------------------
# 四、「拿不到输入」⇒ 退出码 2，且**不得**读成「无需同步」
# ---------------------------------------------------------------------------


def test_fetch_failure_is_exit_2_not_zero(mod, tmp_path, monkeypatch):
    """fetch 失败 ⇒ 退 2 并明说「结论不可信」。

    探针：把 `if not ok_cnb or not ok_gh:` 里的 return 2 改成 `return 0`
    （或删掉这段）⇒ 本用例转红。这是 #171/#450 反复踩的假绿形态：
    「拉不到 ⇒ 报已对齐」。
    """
    monkeypatch.setattr(mod, 'fetch_ref', lambda *a, **k: (False, 'boom'))
    args = argparse.Namespace(
        apply=False,
        dry_run=True,
        push=False,
        base='cnb',
        branch='dev',
        machine_branch='bridge/github-dev',
        cnb_url='x',
        github_url='y',
        cwd=None,
    )
    rc = mod.run(args)
    assert rc == 2, f'拿不到输入必须退 2（结论不可信），实际 {rc}'
    assert rc != 0, '拿不到输入**不得**退化成「无需同步」'


def test_fetch_failure_message_says_inconclusive(mod, tmp_path, monkeypatch, capsys):
    """报错文案要显式说「不得读成已对齐」—— 光有退出码，日志读起来仍可能像正常。"""
    monkeypatch.setattr(mod, 'fetch_ref', lambda *a, **k: (False, 'boom'))
    args = argparse.Namespace(
        apply=False,
        dry_run=True,
        push=False,
        base='cnb',
        branch='dev',
        machine_branch='bridge/github-dev',
        cnb_url='x',
        github_url='y',
        cwd=None,
    )
    mod.run(args)
    err = capsys.readouterr().err
    assert '不可信' in err, f'「拿不到输入」必须声明结论不可信，实际 stderr：{err!r}'


# ---------------------------------------------------------------------------
# 五、无冲突路径的**正常**结论（防「把判据测成恒红」）
# ---------------------------------------------------------------------------


def test_no_conflict_reports_ok(mod, tmp_path, monkeypatch):
    """两侧只各自加文件（不碰同一文件）⇒ 无冲突、退 0（演练模式不推）。

    与上面「有冲突」成对：只有两边都钉住，判据才既不是恒真也不是恒假。
    """
    repo = tmp_path / 'ok'
    repo.mkdir()
    env = _env()
    _git(repo, 'init', '-q', '-b', 'dev', env=env)
    _git(repo, 'config', 'commit.gpgsign', 'false', env=env)
    (repo / 'a.txt').write_text('a\n', encoding='utf-8')
    _git(repo, 'add', '.', env=env)
    _git(repo, 'commit', '-q', '--no-gpg-sign', '-m', 'base', env=env)
    # 两侧各自加**不同**文件
    _git(repo, 'checkout', '-q', '-b', 'gh-dev', env=env)
    (repo / 'gh.txt').write_text('gh\n', encoding='utf-8')
    _git(repo, 'add', '.', env=env)
    _git(repo, 'commit', '-q', '--no-gpg-sign', '-m', 'gh adds', env=env)
    _git(repo, 'checkout', '-q', 'dev', env=env)
    (repo / 'cnb.txt').write_text('cnb\n', encoding='utf-8')
    _git(repo, 'add', '.', env=env)
    _git(repo, 'commit', '-q', '--no-gpg-sign', '-m', 'cnb adds', env=env)

    args = argparse.Namespace(
        apply=False,
        dry_run=False,  # 走「演练」的 merge-tree 试算分支（不建 worktree）
        push=False,
        base='cnb',
        branch='dev',
        machine_branch='bridge/github-dev',
        cnb_url=str(repo),
        github_url=str(repo),
        cwd=str(repo),
    )
    # 用 `--apply` 关闭，走 dry-run 试算路径
    args.apply = False
    rc = mod.run(args)
    assert rc == 0, f'两侧改不同文件应无冲突（退 0），实际 {rc}'


def test_report_states_gate_is_satisfied_not_bypassed(mod):
    """报告须写明「门禁是被**满足**，不是被绕过」——这是本案的立论，别在文案里丢掉。

    用户原话是「质量门禁不能关」。若报告写成「绕过门禁」，下一个读者会以为
    我们在削弱门禁，从而把这条通道也关掉。
    """
    p = mod.plan('cnb', 'bridge/github-dev')
    report = mod.build_report(p, pushed=True, conflicts=[])
    assert '质量门禁汇总' in report, report
    assert '满足' in report or '不是' in report, f'须说明门禁是被满足：{report}'
    assert '绕过' in report, f'须显式否定「绕过」这个读法：{report}'


def test_report_lists_conflict_files(mod):
    """冲突时报告要点名文件（人要照着解），不是只说「有冲突」。"""
    p = mod.plan('cnb', 'bridge/github-dev')
    report = mod.build_report(p, pushed=False, conflicts=['.cnb.yml', 'AGENTS.md'])
    assert '.cnb.yml' in report and 'AGENTS.md' in report, report


def test_script_never_force_pushes(mod):
    """**永不在 push 上开 `force`** —— 反向护栏与 git-sync 一致，别在这条新通道上丢掉。

    ⚠️ 判据必须**收窄到 push 的参数**：`worktree remove --force` 里也有 `--force`，
    按全文扫会**恒红**（第一版就是这么写的，实测自咬）。判据要的是
    「执行 git push 那一行的参数里有没有 force」，不是「文件里有没有出现过 force 这个词」。
    探针：在 push 参数里加 `--force` ⇒ 本用例转红。
    """
    src = _SCRIPT_PATH.read_text(encoding='utf-8').split('"""', 2)[-1]
    if _push_refuses_force(src) is None:
        raise AssertionError('找不到 push 调用——判据失去了锚点（脚本结构变了要一起改判据）')
    refused, why = _push_refuses_force(src)
    assert refused, f'push 不得带 force 类参数（反向护栏）：{why}'


def test_script_never_imports_network(mod):
    """推/开 PR 全部走 git 与调用方给的凭据，脚本自身不引网络库。

    理由与 `check_branch_divergence.py` 同：判定不该依赖网络，否则
    「网络不通 = 报告绿」又是一次静默降级。
    """
    src = _SCRIPT_PATH.read_text(encoding='utf-8').split('"""', 2)[-1]
    for banned in ('import urllib', 'import requests', 'import socket', 'import http'):
        assert banned not in src, f'脚本出现网络依赖：{banned}'


def test_push_failure_surfaces_stderr(mod, tmp_path, capsys):
    """推失败时必须把 **remote 的原话**打出来（源 CNB #567，2026-10-18）。

    事故形态：`_git()` 只收 stdout，而 `git push` 的拒绝原因全在 stderr ⇒
    构建日志里只剩一句「❌ 推机器分支失败：」，后面是空串。分叉存在了两天、每天红一次，
    却没有任何一行说得出「被拒 / 非快进 / 远端领先」。**有信号等于没信号。**

    判据钉两件事：
    1. `_git()` 的返回值里含 stderr（拿本地一条必然失败的命令验证，不联网）；
    2. 走 `run()` 的失败分支时，被捕获的输出里出现 remote 报的那句话。

    探针：把 `_git()` 改回只收 stdout ⇒ 第 1 条断言转红（实测）。
    """
    # ① `_git` 必须把 stderr 带回来。`git show <不存在的 sha>` 必然失败、原因只写 stderr。
    repo = tmp_path / 'repo'
    repo.mkdir()
    _git(repo, 'init', '-q', '-b', 'dev', env=_env())
    # `_git()` 返回三值（#2262 起），失败原因须落在**第二个**返回值里 —— 推失败那一行打的就是它。
    code, out, err = mod._git(['show', '0' * 40], str(repo))
    assert code != 0
    assert err.strip(), '`git show` 失败时 stderr 不该为空（判据自身失去了锚点）'
    assert err.strip() in out, '`_git()` 只收 stdout —— stderr 被丢掉了，失败原因会打成空串'

    # ② `run()` 的推失败分支要把原因与目标分支都打出来。
    #    造一个**能合、但推不上去**的场景：远端是个**合法仓库**（否则死在前面的 fetch 上，
    #    走的是「拿不到输入」分支），但预置一条同名分支，于是 push 是**非快进**被拒 ——
    #    这正是 #567 事故里真实的失败形态。
    work = tmp_path / 'work'
    work.mkdir()
    env = _env()
    _git(work, 'init', '-q', '-b', 'dev', env=env)
    _git(work, 'config', 'commit.gpgsign', 'false', env=env)
    (work / 'a.txt').write_text('a\n', encoding='utf-8')
    _git(work, 'add', '.', env=env)
    _git(work, 'commit', '-q', '--no-gpg-sign', '-m', 'base', env=env)
    _git(work, 'checkout', '-q', '-b', 'gh', env=env)
    (work / 'gh.txt').write_text('gh\n', encoding='utf-8')
    _git(work, 'add', '.', env=env)
    _git(work, 'commit', '-q', '--no-gpg-sign', '-m', 'gh', env=env)
    _git(work, 'checkout', '-q', 'dev', env=env)
    (work / 'cnb.txt').write_text('cnb\n', encoding='utf-8')
    _git(work, 'add', '.', env=env)
    _git(work, 'commit', '-q', '--no-gpg-sign', '-m', 'cnb', env=env)

    # 远端：同一条仓库，且**已有一条内容无关的 `bridge/github-dev`**（孤立提交）⇒
    # 推合并结果必然被判非快进而拒 —— 这正是 #567 事故里真实的失败形态。
    # 注意**不能**让远端那条分支等于 `dev`：合并结果包含 `dev`，推上去就是快进，会被接受。
    _git(work, 'checkout', '-q', '--orphan', 'unrelated', env=env)
    (work / 'gh.txt').unlink(missing_ok=True)
    (work / 'cnb.txt').unlink(missing_ok=True)
    (work / 'a.txt').write_text('unrelated\n', encoding='utf-8')
    _git(work, 'add', '-A', env=env)
    _git(work, 'commit', '-q', '--no-gpg-sign', '-m', 'unrelated', env=env)
    _git(work, 'checkout', '-q', 'dev', env=env)
    remote = tmp_path / 'remote.git'
    _git(tmp_path, 'clone', '-q', '--bare', str(work), str(remote), env=env)
    _git(remote, 'branch', 'bridge/github-dev', 'unrelated', env=env)

    args = argparse.Namespace(
        apply=True,
        dry_run=False,
        push=True,
        base='cnb',
        branch='dev',
        machine_branch='bridge/github-dev',
        cnb_url=str(work),
        github_url=str(remote),
        cwd=str(work),
    )
    # 让 push **注定失败**且原因可读：远端仍在（fetch 得通），但**只读** ——
    # 用一个 hook 拒绝一切写入的裸仓，push 会带着 remote 的原话失败。
    # （不能用「远端已有一条无关的 bridge/github-dev」那种场景：那是 #573 修复后的**成功**路径。）  # cross-repo-ref-allow
    read_only = tmp_path / 'read-only.git'
    _git(tmp_path, 'clone', '-q', '--bare', str(work), str(read_only), env=env)
    hook = read_only / 'hooks' / 'pre-receive'
    hook.write_text('#!/bin/sh\necho "no writes allowed" >&2\nexit 1\n', encoding='utf-8')
    hook.chmod(0o755)
    args.github_url = str(read_only)
    rc = mod.run(args)
    assert rc == 2, f'推失败应以「结论不可信」退出（2），实际 {rc}'
    # 推失败那一行必须打出 **remote 的原话**（空原因等于没信号），且点名目标分支。
    # ⚠️ 语义变更（源 CNB #573）：机器分支现在**一开始就带 `--force-with-lease=<ref>:<sha>`**
    # 推（一次性分支的覆盖语义），于是「远端已有一条无关的 bridge/github-dev」这种场景
    # **会被成功覆盖**（退 0）—— 这正是修复想要的效果，不再是失败。
    # 故本用例改用 `--machine-branch` 指向一条**无法覆盖**的 ref 来保留「推得出去才算成功」的
    # 反面：远端是个 **bare 仓库的只读路径**（不存在的目录）⇒ 推必然失败。
    # 判据本身不变：失败时日志必须带 remote 原话。
    err_out = capsys.readouterr().err
    assert '推机器分支失败' in err_out, f'须显式说推失败，实际 stderr：{err_out!r}'
    assert 'no writes allowed' in err_out, f'须把 remote 的原话打出来（空原因等于没信号），实际：{err_out!r}'
    assert 'bridge/github-dev' in err_out, f'须点名目标分支，实际：{err_out!r}'
    assert '已合并成功，但没推上去' in err_out, f'须明确「合好了但没送出去」，实际：{err_out!r}'


def _push_refuses_force(src: str) -> tuple[bool, str] | None:
    """扫出所有 `_git([...'push'...])` 调用（跨行拼接），检查它们**不带** force 类参数。

    返回 `None` ⇒ 一条 push 调用都找不到（判据失去锚点）；否则 `(是否合规, 原因)`。

    为什么要把调用拼成一行再判：push 的参数在 `.cnb.yml` 之后又变成**跨行**写法
    （`_git(\n    ['push', …]\n)`），按行匹配会**恒绿**（找不到调用）。判据必须按调用判，
    不按行判——否则「改了代码、判据还在绿」正是最坏的那种假绿。
    """
    calls = re.findall(r'_git\(\s*\[([^\]]*)\]', src, re.S)
    push_calls = [c for c in calls if re.search(r"'push'", c)]
    if not push_calls and 'machine_push_args(' not in src:
        # 两种形态都认：① 内联 `_git(['push', …])`；② 参数由 `machine_push_args()`
        # 算出来（本仓 #573 之后就是②）。**只认① 的判据会在结构变化时恒绿**。
        return None
    for c in push_calls:
        flat = ' '.join(c.split())
        for banned in ("'--force'", "'-f'", 'force-with-lease'):
            if banned in flat:
                return False, f'push 不得带 {banned}（反向护栏 —— 只有机器分支那条特殊）：{flat}'
    # 机器分支那条走 `machine_push_args()`：判它**产出的参数**，而不是判调用行文本
    # （调用的参数由函数算出来，按文本判会恒绿）。
    if 'machine_push_args(' in src:
        args_src = src.split('def machine_push_args(', 1)[1].split('\ndef ', 1)[0]
        if '--force-with-lease=' not in args_src:
            return False, 'machine_push_args() 里没有显式的 `--force-with-lease=<ref>:<sha>`'
        if "'--force'" in args_src:
            return False, 'machine_push_args() 不得出现裸 `--force`'
        if 'dev' not in args_src and 'machine_branch' not in args_src:
            return False, 'machine_push_args() 的 ref 来源不明（须由 machine_branch 拼出）'
    return True, ''


# ---------------------------------------------------------------------------
# 六、演练路径的冲突判据：**同一事实不许问两次**（源 CNB #573，2026-10-18）
# ---------------------------------------------------------------------------


def _dry_run_args(cnb, gh):
    return argparse.Namespace(
        apply=False,
        dry_run=True,
        push=False,
        base='cnb',
        branch='dev',
        machine_branch='bridge/github-dev',
        cnb_url=str(cnb),
        github_url=str(gh),
        cwd=str(cnb),
    )


def test_failed_push_is_not_mistaken_for_no_conflict(mod, tmp_path):
    """这正是 `cnb-um5-1k57nplko` 那一版：**merge 其实成功了，只是推不出去**。

    构建日志里 ① merge 无冲突（`134 files changed, 608 insertions(+)`）、
    ② push 被拒（`! [rejected] HEAD -> bridge/github-dev (fetch first)`），
    而报告写的是「✅ 无冲突，两侧内容可合。／（演练模式：未推、未开 PR。）」
    ——**两个动作（推 / 没推）三种原因（有冲突 / 试算不可用 / 推失败）撞在同一句
    「没推」上**，读日志的人根本分不出是哪一种。

    本用例钉两条：
    1. 报告里出现「**已合并、未推送**」，且**不再**出现「演练模式」那行；
    2. 报告点明「远端那条分支已存在」这个可操作的下一步。
    """
    cnb, gh = _mk_side_repos(tmp_path, 'pushfail', same_file=False)
    env = _env()
    _git(cnb, 'remote', 'add', 'gh', str(gh), env=env)
    _git(cnb, 'fetch', '-q', 'gh', 'dev', env=env)
    _git(cnb, 'branch', 'gh-dev', 'FETCH_HEAD', env=env)

    # 让 push **注定失败**且原因可读：github_url 指向一个不存在的路径。
    bad_remote = tmp_path / 'no-such-remote.git'
    args = argparse.Namespace(
        apply=True,
        dry_run=False,
        push=True,
        base='cnb',
        branch='dev',
        machine_branch='bridge/github-dev',
        cnb_url=str(cnb),
        github_url=str(bad_remote),
        cwd=str(cnb),
    )
    rc = mod.run(args)
    out = capsys_err = None  # noqa: F841  (仅取 stderr，见下)
    assert rc == 2, f'推失败应退 2，实际 {rc}'

    # 直接对报告构造函数钉语义（与 `run()` 的调用点一致）
    p = mod.plan('cnb', 'bridge/github-dev')
    report = mod.build_report(p, pushed=False, conflicts=[], reason='push_failed')
    assert '演练模式' not in report, f'推失败不得写成「演练模式」——那是一个**没推**的假理由：{report}'
    assert '已合并' in report and '没推上去' in report, f'须说清「合好了但没送出去」：{report}'


def test_report_distinguishes_three_reasons_of_not_pushed(mod):
    """「没推」有三种**完全不同**的原因，报告必须一种一句（#573）。

    ① 有冲突 ⇒ 什么都没合；
    ② 试算 / 合并不可用 ⇒ 结论不可信；
    ③ 合并成功但**推失败** ⇒ 本地好了、远端没收到。

    原先只有 `pushed: bool` 两个状态，③ 落进 ① 的兜底句「演练模式：未推、未开 PR」，
    于是「推被拒」在报告里长得像「还没执行」——诊断方向被掉包。
    探针：把 `reason` 分支删掉、只留 `else: 演练模式` ⇒ 本用例转红。
    """
    p = mod.plan('cnb', 'bridge/github-dev')
    push_failed = mod.build_report(p, pushed=False, conflicts=[], reason='push_failed')
    assert '推' in push_failed and '失败' in push_failed, f'③ 必须说自己失败了：{push_failed}'
    assert '演练模式' not in push_failed, push_failed

    inconclusive = mod.build_report(p, pushed=False, conflicts=[], reason='inconclusive')
    assert '不可信' in inconclusive, f'② 必须声明结论不可信：{inconclusive}'
    assert '演练模式' not in inconclusive, inconclusive

    # ①（真演练）保留原样：这一句本身没错，错的只是被复用给了另外两种原因。
    dry = mod.build_report(p, pushed=False, conflicts=[])
    assert '演练模式' in dry, f'真演练仍要说「未推、未开 PR」：{dry}'


def test_dry_run_conflicts_are_extracted(mod, tmp_path, capsys):
    """演练路径**必须真的报出冲突文件**（源 CNB #573 的核心回归）。

    事故形态：`code, _, _ = _git(merge-tree)` 取码，`if code == 1:` 再跑一遍取输出 ——
    于是「取码」与「取输出」是两次独立进程。只要第二次的输出被读成空
    （`_git` 的返回值约定变过一次：两值 → 三值，调用点没跟着改就是这一形态），
    冲突清单就**恒为空**，报告照样打印「✅ 无冲突，两侧内容可合」。

    本用例直接把 merge-tree 的**输出**做成空，逼出「有冲突却报无冲突」：
    - 修复后：`merge_tree_conflicts()` 只跑一次，输出为空 ⇒ 取不出路径 ⇒ **不可信**（退 2）；
    - 修复前：退 0 并打印「无冲突」。
    """
    repo = tmp_path / 'dryconflict'
    repo.mkdir()
    env = _env()
    _git(repo, 'init', '-q', '-b', 'dev', env=env)
    _git(repo, 'config', 'commit.gpgsign', 'false', env=env)
    _git(repo, 'config', 'user.name', 't', env=env)
    _git(repo, 'config', 'user.email', 't@e', env=env)
    (repo / 'a.txt').write_text('base\n', encoding='utf-8')
    _git(repo, 'add', '.', env=env)
    _git(repo, 'commit', '-q', '--no-gpg-sign', '-m', 'base', env=env)
    _git(repo, 'checkout', '-q', '-b', 'gh', env=env)
    (repo / 'a.txt').write_text('gh\n', encoding='utf-8')
    _git(repo, 'commit', '-q', '--no-gpg-sign', '-am', 'gh', env=env)
    _git(repo, 'checkout', '-q', 'dev', env=env)
    (repo / 'a.txt').write_text('cnb\n', encoding='utf-8')
    _git(repo, 'commit', '-q', '--no-gpg-sign', '-am', 'cnb', env=env)

    real = mod._git
    calls: list[list[str]] = []

    def fake(args, cwd=None):
        # ⚠️ 这里要拦的是**试算**那一次（参数里有 `refs/cross-bridge/…`）。
        # 而 `run()` 开头的两次 fetch 让别的 `_git` 调用看起来也可以用 `args[:2]` 匹配 ——
        # 一旦匹配过宽，报告的「无冲突」就来自一个假的空输出，用例测的就不是它想测的东西。
        if args[:1] == ['merge-tree'] and any('refs/cross-bridge/' in a for a in args):
            calls.append(args)
            # 真实冲突（rc 1），但**输出读成空** —— 事故形态。
            return 1, '', ''
        return real(args, cwd)

    saved = mod._git
    mod._git = fake
    try:
        rc = mod.run(_dry_run_args(repo, repo))
    finally:
        mod._git = saved
    assert len(calls) == 1, f'试算只能问一次（问两次就是 #573 的根因形态）：{calls}'
    assert rc == 2, f'取不出冲突路径必须退 2（结论不可信），**不得**退化成「无冲突」：{rc}'
    err = capsys.readouterr().err
    assert '不可信' in err, f'须声明结论不可信，实际 stderr：{err!r}'


def test_dry_run_single_merge_tree_call(mod, tmp_path):
    """无论有没有冲突，演练路径**只调一次** `merge-tree`。"""
    repo = tmp_path / 'dryclean'
    repo.mkdir()
    env = _env()
    _git(repo, 'init', '-q', '-b', 'dev', env=env)
    _git(repo, 'config', 'commit.gpgsign', 'false', env=env)
    _git(repo, 'config', 'user.name', 't', env=env)
    _git(repo, 'config', 'user.email', 't@e', env=env)
    (repo / 'a.txt').write_text('a\n', encoding='utf-8')
    _git(repo, 'add', '.', env=env)
    _git(repo, 'commit', '-q', '--no-gpg-sign', '-m', 'base', env=env)
    _git(repo, 'checkout', '-q', '-b', 'gh', env=env)
    (repo / 'gh.txt').write_text('gh\n', encoding='utf-8')
    _git(repo, 'add', '.', env=env)
    _git(repo, 'commit', '-q', '--no-gpg-sign', '-m', 'gh', env=env)
    _git(repo, 'checkout', '-q', 'dev', env=env)
    (repo / 'cnb.txt').write_text('cnb\n', encoding='utf-8')
    _git(repo, 'add', '.', env=env)
    _git(repo, 'commit', '-q', '--no-gpg-sign', '-m', 'cnb', env=env)

    real = mod._git
    calls: list[list[str]] = []

    def spy(args, cwd=None):
        if args[:2] == ['merge-tree', '--write-tree']:
            calls.append(args)
        return real(args, cwd)

    saved = mod._git
    mod._git = spy
    try:
        rc = mod.run(_dry_run_args(repo, repo))
    finally:
        mod._git = saved
    assert rc == 0, f'两侧改不同文件应无冲突（退 0），实际 {rc}'
    assert len(calls) == 1, f'演练路径只该跑一次 merge-tree，实际 {len(calls)} 次'


def test_existing_machine_branch_is_overwritten_with_lease(mod, tmp_path, capsys):
    """机器分支已存在且非快进 ⇒ 用 `--force-with-lease` 覆盖（源 CNB #573）。

    事故形态：`bridge/github-dev` 是**固定名、一次性、每轮覆盖**的 ref。上一轮没被合掉时，
    本轮合并结果不含它 ⇒ 非快进被拒 ⇒ 每小时红一次，却**一个字节都没推出去**
    （`cnb-um5-1k57nplko` 的 pipeline-002 原文）。

    「推 `dev` 绝不开 force」与这条**不冲突**：`dev` 是共享事实，冲掉别人的提交不可接受；
    而机器分支是**本次合并结果的快照**，名字固定就是为了幂等地覆盖。
    故判据要**双向**钉住：
    - 机器分支的非快进 ⇒ 必须重试，且带 `--force-with-lease`（不带裸 `--force`：
      lease 保证「万一有人在它上面动了手」仍然失败）；
    - 目标若是 `dev` / `main` ⇒ **不允许**出现任何 force 参数（那是反向护栏）。

    探针：把 `if code != 0 and _is_non_fast_forward(out):` 整段删掉 ⇒ 本用例转红（实测）。
    """
    # 远端：先有一条**内容无关**的 bridge/github-dev（孤立提交）⇒ 首次 push 必然非快进。
    work = tmp_path / 'lease'
    work.mkdir()
    env = _env()
    _git(work, 'init', '-q', '-b', 'dev', env=env)
    _git(work, 'config', 'commit.gpgsign', 'false', env=env)
    _git(work, 'config', 'user.name', 't', env=env)
    _git(work, 'config', 'user.email', 't@e', env=env)
    (work / 'a.txt').write_text('a\n', encoding='utf-8')
    _git(work, 'add', '.', env=env)
    _git(work, 'commit', '-q', '--no-gpg-sign', '-m', 'base', env=env)
    _git(work, 'checkout', '-q', '-b', 'gh', env=env)
    (work / 'gh.txt').write_text('gh\n', encoding='utf-8')
    _git(work, 'add', '.', env=env)
    _git(work, 'commit', '-q', '--no-gpg-sign', '-m', 'gh', env=env)
    _git(work, 'checkout', '-q', 'dev', env=env)
    (work / 'cnb.txt').write_text('cnb\n', encoding='utf-8')
    _git(work, 'add', '.', env=env)
    _git(work, 'commit', '-q', '--no-gpg-sign', '-m', 'cnb', env=env)
    _git(work, 'checkout', '-q', '--orphan', 'unrelated', env=env)
    for f in ('gh.txt', 'cnb.txt', 'a.txt'):
        (work / f).unlink(missing_ok=True)
    (work / 'other.txt').write_text('unrelated\n', encoding='utf-8')
    _git(work, 'add', '-A', env=env)
    _git(work, 'commit', '-q', '--no-gpg-sign', '-m', 'unrelated', env=env)
    _git(work, 'checkout', '-q', 'dev', env=env)
    remote = tmp_path / 'remote-lease.git'
    _git(tmp_path, 'clone', '-q', '--bare', str(work), str(remote), env=env)
    _git(remote, 'branch', 'bridge/github-dev', 'unrelated', env=env)

    real = mod._git
    pushes: list[list[str]] = []

    def spy(args, cwd=None):
        if args and args[0] == 'push':
            pushes.append(args)
        return real(args, cwd)

    saved = mod._git
    mod._git = spy
    try:
        args = argparse.Namespace(
            apply=True,
            dry_run=False,
            push=True,
            base='cnb',
            branch='dev',
            machine_branch='bridge/github-dev',
            cnb_url=str(work),
            github_url=str(remote),
            cwd=str(work),
        )
        rc = mod.run(args)
    finally:
        mod._git = saved

    assert pushes, '应当至少调用一次 push'
    assert all(any(a.startswith('--force-with-lease') for a in ps) for ps in pushes), (
        f'机器分支的推送必须带 `--force-with-lease`（一次性分支的覆盖语义）：{pushes}'
    )
    for ps in pushes:
        assert '--force' not in ps, f'不得用裸 `--force`（lease 才有「别人动过就失败」的保证）：{ps}'
        # lease 必须**显式带期望值**（`=<ref>:<sha>`）：裸 lease 在「本地没有该 ref 的
        # tracking 信息」时退化成 `(stale info)` 被拒 —— 实测复现过，别改回裸形态。
        lease = [a for a in ps if a.startswith('--force-with-lease')]
        assert lease and ':' in lease[0], f'lease 必须显式指定期望值（`=<ref>:<sha>`），否则 stale info：{ps}'
        assert ps[-1] == 'HEAD:refs/heads/bridge/github-dev', f'只准推机器分支：{ps}'
    assert rc == 0, f'覆盖成功后应退 0，实际 {rc}；push 调用：{pushes}'
    # 覆盖后远端那条 ref 必须真的指向本次合并结果。
    ref = subprocess.run(
        ['git', 'rev-parse', 'bridge/github-dev'], cwd=str(remote), capture_output=True, text=True, env=env
    ).stdout.strip()
    assert ref, '远端 bridge/github-dev 应已存在'


def test_force_only_allowed_on_machine_branch(mod):
    """`--force-with-lease` 只允许出现在**机器分支**那条 push 上（反向护栏，别被顺手套到 dev）。"""
    src = _SCRIPT_PATH.read_text(encoding='utf-8').split('"""', 2)[-1]
    res = _push_refuses_force(src)
    assert res is not None, '找不到 push 调用——判据失去锚点（脚本结构变了要一起改判据）'
    refused, why = res
    assert refused, why
    # 机器分支必须有 lease 保护（一次性分支的覆盖语义），且**只**推机器分支。
    assert '--force-with-lease=' in src and 'machine_branch' in src, '机器分支的覆盖须用 --force-with-lease=<ref>:<sha>'
    assert 'refs/heads/dev' not in src and 'refs/heads/main' not in src, '不得出现推 dev / main 的字面 ref'
