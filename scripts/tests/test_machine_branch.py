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
import subprocess
import sys
import pathlib

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
            apply=True, dry_run=False, push=True,
            base='cnb', branch='dev', machine_branch='bridge/github-dev',
            cnb_url=str(cnb), github_url=str(gh), cwd=str(cnb),
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
            apply=True, dry_run=False, push=True,
            base='cnb', branch='dev', machine_branch='bridge/github-dev',
            cnb_url=str(cnb), github_url=str(gh), cwd=str(cnb),
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
        apply=True, dry_run=False, push=True,
        base='cnb', branch='dev', machine_branch='bridge/github-dev',
        cnb_url=str(cnb), github_url=str(gh), cwd=str(cnb),
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
    import re

    src = _SCRIPT_PATH.read_text(encoding='utf-8').split('"""', 2)[-1]
    push_lines = [ln for ln in src.splitlines() if re.search(r"_git\(\s*\[\s*'push'", ln)]
    assert push_lines, '找不到 push 调用——判据失去了锚点（脚本结构变了要一起改判据）'
    for ln in push_lines:
        for banned in ('--force', '-f', 'force-with-lease'):
            assert banned not in ln, f'push 不得带 {banned}（反向护栏）：{ln.strip()}'


def test_script_never_imports_network(mod):
    """推/开 PR 全部走 git 与调用方给的凭据，脚本自身不引网络库。

    理由与 `check_branch_divergence.py` 同：判定不该依赖网络，否则
    「网络不通 = 报告绿」又是一次静默降级。
    """
    src = _SCRIPT_PATH.read_text(encoding='utf-8').split('"""', 2)[-1]
    for banned in ('import urllib', 'import requests', 'import socket', 'import http'):
        assert banned not in src, f'脚本出现网络依赖：{banned}'
