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
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "bridge" / "machine_branch.py"


def _load():
    spec = importlib.util.spec_from_file_location("machine_branch", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["machine_branch"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load()


def _git(repo, *args, env):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)


def _env():
    return {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e",
        "PATH": os.environ["PATH"],
    }


def _mk_side_repos(tmp_path, name, *, same_file: bool):
    """两侧仓库，`gh` 从 `cnb` clone 出来 ⇒ 共享同一历史（这样 fetch+merge 才有意义）。

    ⚠️ 两侧仓库都**自备** committer 身份（#2262）：脚本的 merge 在 cnb 侧 worktree 里跑，
    不继承本测试的 `_env()`，只读仓库/全局配置。曾经只给 gh 配、cnb 蹭开发者全局 config
    （本地有、runner 没有）⇒ Linux 上 merge rc128「Committer identity unknown」⇒
    冲突路径整个失灵。fixture 不许有这种环境依赖——它是假绿之源。
    """
    cnb = tmp_path / f"{name}-cnb"
    cnb.mkdir()
    env = _env()
    _git(cnb, "init", "-q", "-b", "dev", env=env)
    _git(cnb, "config", "commit.gpgsign", "false", env=env)
    _git(cnb, "config", "user.name", "t", env=env)
    _git(cnb, "config", "user.email", "t@e", env=env)
    (cnb / "a.txt").write_text("base\n", encoding="utf-8")
    (cnb / "shared.txt").write_text("base\n", encoding="utf-8")
    _git(cnb, "add", ".", env=env)
    _git(cnb, "commit", "-q", "--no-gpg-sign", "-m", "base", env=env)

    gh = tmp_path / f"{name}-gh"
    subprocess.run(
        ["git", "clone", "-q", str(cnb), str(gh)],
        check=True,
        capture_output=True,
        env=env,
    )
    _git(gh, "config", "user.name", "t", env=env)
    _git(gh, "config", "user.email", "t@e", env=env)
    _git(gh, "config", "commit.gpgsign", "false", env=env)
    _git(gh, "checkout", "-q", "dev", env=_env())

    def commit(repo, who):
        if same_file:
            (repo / "shared.txt").write_text(f"{who} side\n", encoding="utf-8")
        else:
            (repo / f"{who}-only.txt").write_text(f"{who}\n", encoding="utf-8")
        _git(repo, "add", ".", env=env)
        _git(repo, "commit", "-q", "--no-gpg-sign", "-m", f"{who} work", env=env)

    commit(cnb, "cnb")
    commit(gh, "gh")
    return cnb, gh


# ---------------------------------------------------------------------------
# 一、方向：`plan()` 是纯函数，先把方向钉死
# ---------------------------------------------------------------------------


def test_plan_default_is_cnb_as_base(mod):
    """默认以 CNB 为基线 —— 这是 `dev_converge.py` 的同一口径（方向必须先定）。

    探针：把 `plan()` 里 `base == 'github'` 的两个分支调换 ⇒ 本用例转红。
    """
    p = mod.plan("cnb", "bridge/github-dev")
    assert p["base_name"] == "CNB", p
    assert p["base_ref"] == mod.CNB_REF, p
    assert p["merge_name"] == "GitHub", p
    assert p["merge_ref"] == mod.GH_REF, p


def test_plan_github_base_is_reverse(mod):
    """`--base github` ⇒ 以 GitHub 为基线、合入 CNB（与上面成对，防「方向写死一侧」）。"""
    p = mod.plan("github", "bridge/github-dev")
    assert p["base_name"] == "GitHub", p
    assert p["base_ref"] == mod.GH_REF, p
    assert p["merge_name"] == "CNB", p
    assert p["merge_ref"] == mod.CNB_REF, p


def test_plan_carries_machine_branch(mod):
    """机器分支名必须原样带进 plan —— 别让上层传给 `plan()` 的名字被悄悄丢掉。"""
    p = mod.plan("cnb", "bridge/custom-name")
    assert p["machine_branch"] == "bridge/custom-name", p


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
    assert name.startswith("bridge/"), (
        f"机器分支应落在 bridge/ 命名空间（一次性语义）：{name}"
    )
    assert "CNBDEV" not in name.upper(), (
        f"不得复用 CNBDEV 这个名字（它代表的是长期中转分支）：{name}"
    )


def test_machine_branch_name_has_no_date_suffix(mod):
    """默认名**不含日期**：带日期会让重复跑攒出分支列表垃圾（幂等性要求）。"""
    name = mod.DEFAULT_MACHINE_BRANCH
    assert not any(ch.isdigit() and str(ch) in name for ch in []), "sanity"
    import re

    assert not re.search(r"\d{4}-\d{2}-\d{2}", name), (
        f"机器分支名不该带日期（会攒出垃圾分支）：{name}"
    )


# ---------------------------------------------------------------------------
# 三、有冲突 ⇒ **什么都不推**（核心安全承诺）
# ---------------------------------------------------------------------------


def test_conflicts_mean_nothing_is_pushed(mod, tmp_path):
    """有冲突时：退出码 1、**且没有调 push**。

    判据锚在「push 有没有被调用」而不是「返回了 1」——返回 1 但已经推过是最坏的形态
    （冲突解不掉、远端却多了一条半成品分支）。
    探针：把 `if conflicts:` 里的提前 return 删掉 ⇒ push 被调用且本用例转红。
    """
    cnb, gh = _mk_side_repos(tmp_path, "conflict", same_file=True)
    # 让 CNB 侧仓能 fetch 到 GitHub 侧：加一个 remote
    env = _env()
    _git(cnb, "remote", "add", "gh", str(gh), env=env)
    _git(cnb, "fetch", "-q", "gh", "dev", env=env)
    _git(cnb, "branch", "gh-dev", "FETCH_HEAD", env=env)

    real = mod._git
    calls: list[list[str]] = []

    def spy(args, cwd=None):
        # 探针（#2255）：退出码一并记账——「推没推」是结果，merge/diff 的码才是根因
        # （Linux runner 上冲突路径失灵，账里只有 push 结果时无从诊断）。
        code, out, err = real(args, cwd)
        calls.append([*args, f"rc{code}"])
        return code, out, err

    saved = mod._git
    mod._git = spy
    try:
        args = argparse.Namespace(
            apply=True,
            dry_run=False,
            push=True,
            merge_sync=False,
            base="cnb",
            branch="dev",
            machine_branch="bridge/github-dev",
            cnb_url=str(cnb),
            github_url=str(gh),
            cwd=str(cnb),
        )
        rc = mod.run(args)
    finally:
        mod._git = saved
    pushed = [c for c in calls if c and c[0] == "push"]
    assert not pushed, (
        f"有冲突时**一个字节都不该推**，实际调用了：{pushed}；全程（含退出码）：{calls}"
    )
    assert rc == 1, (
        f"有冲突应返回 1（供调用方当信号），实际 {rc}；全程（含退出码）：{calls}"
    )


def test_worktree_is_cleaned_up_on_conflict(mod, tmp_path):
    """冲突路径也要把临时 worktree 收掉 —— 留一个冲突中的工作区会让下次跑直接失败。"""
    cnb, gh = _mk_side_repos(tmp_path, "cleanup", same_file=True)
    env = _env()
    _git(cnb, "remote", "add", "gh", str(gh), env=env)
    _git(cnb, "fetch", "-q", "gh", "dev", env=env)
    _git(cnb, "branch", "gh-dev", "FETCH_HEAD", env=env)

    real = mod._git
    calls: list[list[str]] = []

    def spy(args, cwd=None):
        # 探针（#2255）：退出码一并记账——「推没推」是结果，merge/diff 的码才是根因
        # （Linux runner 上冲突路径失灵，账里只有 push 结果时无从诊断）。
        code, out, err = real(args, cwd)
        calls.append([*args, f"rc{code}"])
        return code, out, err

    mod._git = spy
    try:
        args = argparse.Namespace(
            apply=True,
            dry_run=False,
            push=True,
            merge_sync=False,
            base="cnb",
            branch="dev",
            machine_branch="bridge/github-dev",
            cnb_url=str(cnb),
            github_url=str(gh),
            cwd=str(cnb),
        )
        mod.run(args)
    finally:
        mod._git = real
    removes = [c for c in calls if c[:2] == ["worktree", "remove"]]
    aborts = [c for c in calls if c[:2] == ["merge", "--abort"]]
    assert removes, f"冲突路径必须收掉临时 worktree，实际调用：{calls}"
    assert aborts, f"冲突路径必须先 abort 再收 —— 留着冲突现场会让下次跑失败：{calls}"


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
    cnb, gh = _mk_side_repos(tmp_path, "fatal", same_file=True)
    env = _env()
    _git(cnb, "remote", "add", "gh", str(gh), env=env)
    _git(cnb, "fetch", "-q", "gh", "dev", env=env)
    _git(cnb, "branch", "gh-dev", "FETCH_HEAD", env=env)

    real = mod._git
    calls: list[list[str]] = []

    def fake(args, cwd=None):
        if args[:2] == ["merge", "--no-edit"]:
            # 忠实复现 runner 实测形态：merge 直接致命、**根本没跑起来**，
            # 因此不会留下任何未合并条目（diff-filter=U 为空）。
            calls.append([*args, "rc128"])
            return 128, "", "fatal: unable to auto-detect email address"
        code, out, err = real(args, cwd)
        calls.append([*args, f"rc{code}"])
        return code, out, err

    monkeypatch.setattr(mod, "_git", fake)
    args = argparse.Namespace(
        apply=True,
        dry_run=False,
        push=True,
        base="cnb",
        branch="dev",
        machine_branch="bridge/github-dev",
        cnb_url=str(cnb),
        github_url=str(gh),
        cwd=str(cnb),
    )
    rc = mod.run(args)

    pushed = [c for c in calls if c and c[0] == "push"]
    assert not pushed, f"merge 没跑起来时**一个字节都不该推**：{pushed}；全程：{calls}"
    assert rc == 2, f"合并没跑起来必须退 2（结论不可信），实际 {rc}；全程：{calls}"
    removes = [c for c in calls if c[:2] == ["worktree", "remove"]]
    assert len(removes) >= 2, f"致命路径也要收掉临时 worktree（预清理 + 收尾）：{calls}"
    err = capsys.readouterr().err
    assert "不可信" in err, f"必须明说结论不可信，实际 stderr：{err!r}"


# ---------------------------------------------------------------------------
# 四、「拿不到输入」⇒ 退出码 2，且**不得**读成「无需同步」
# ---------------------------------------------------------------------------


def test_fetch_failure_is_exit_2_not_zero(mod, tmp_path, monkeypatch):
    """fetch 失败 ⇒ 退 2 并明说「结论不可信」。

    探针：把 `if not ok_cnb or not ok_gh:` 里的 return 2 改成 `return 0`
    （或删掉这段）⇒ 本用例转红。这是 #171/#450 反复踩的假绿形态：
    「拉不到 ⇒ 报已对齐」。
    """
    monkeypatch.setattr(mod, "fetch_ref", lambda *a, **k: (False, "boom"))
    args = argparse.Namespace(
        apply=False,
        dry_run=True,
        push=False,
        base="cnb",
        branch="dev",
        machine_branch="bridge/github-dev",
        cnb_url="x",
        github_url="y",
        cwd=None,
    )
    rc = mod.run(args)
    assert rc == 2, f"拿不到输入必须退 2（结论不可信），实际 {rc}"
    assert rc != 0, "拿不到输入**不得**退化成「无需同步」"


def test_fetch_failure_message_says_inconclusive(mod, tmp_path, monkeypatch, capsys):
    """报错文案要显式说「不得读成已对齐」—— 光有退出码，日志读起来仍可能像正常。"""
    monkeypatch.setattr(mod, "fetch_ref", lambda *a, **k: (False, "boom"))
    args = argparse.Namespace(
        apply=False,
        dry_run=True,
        push=False,
        base="cnb",
        branch="dev",
        machine_branch="bridge/github-dev",
        cnb_url="x",
        github_url="y",
        cwd=None,
    )
    mod.run(args)
    err = capsys.readouterr().err
    assert "不可信" in err, f"「拿不到输入」必须声明结论不可信，实际 stderr：{err!r}"


# ---------------------------------------------------------------------------
# 五、无冲突路径的**正常**结论（防「把判据测成恒红」）
# ---------------------------------------------------------------------------


def test_no_conflict_reports_ok(mod, tmp_path, monkeypatch):
    """两侧只各自加文件（不碰同一文件）⇒ 无冲突、退 0（演练模式不推）。

    与上面「有冲突」成对：只有两边都钉住，判据才既不是恒真也不是恒假。
    """
    repo = tmp_path / "ok"
    repo.mkdir()
    env = _env()
    _git(repo, "init", "-q", "-b", "dev", env=env)
    _git(repo, "config", "commit.gpgsign", "false", env=env)
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", ".", env=env)
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", "base", env=env)
    # 两侧各自加**不同**文件
    _git(repo, "checkout", "-q", "-b", "gh-dev", env=env)
    (repo / "gh.txt").write_text("gh\n", encoding="utf-8")
    _git(repo, "add", ".", env=env)
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", "gh adds", env=env)
    _git(repo, "checkout", "-q", "dev", env=env)
    (repo / "cnb.txt").write_text("cnb\n", encoding="utf-8")
    _git(repo, "add", ".", env=env)
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", "cnb adds", env=env)

    args = argparse.Namespace(
        apply=False,
        dry_run=False,  # 走「演练」的 merge-tree 试算分支（不建 worktree）
        push=False,
        base="cnb",
        branch="dev",
        machine_branch="bridge/github-dev",
        cnb_url=str(repo),
        github_url=str(repo),
        cwd=str(repo),
    )
    # 用 `--apply` 关闭，走 dry-run 试算路径
    args.apply = False
    rc = mod.run(args)
    assert rc == 0, f"两侧改不同文件应无冲突（退 0），实际 {rc}"


def test_report_states_gate_is_satisfied_not_bypassed(mod):
    """报告须写明「门禁是被**满足**，不是被绕过」——这是本案的立论，别在文案里丢掉。

    用户原话是「质量门禁不能关」。若报告写成「绕过门禁」，下一个读者会以为
    我们在削弱门禁，从而把这条通道也关掉。
    """
    p = mod.plan("cnb", "bridge/github-dev")
    report = mod.build_report(p, pushed=True, conflicts=[])
    assert "质量门禁汇总" in report, report
    assert "满足" in report or "不是" in report, f"须说明门禁是被满足：{report}"
    assert "绕过" in report, f"须显式否定「绕过」这个读法：{report}"


def test_report_lists_conflict_files(mod):
    """冲突时报告要点名文件（人要照着解），不是只说「有冲突」。"""
    p = mod.plan("cnb", "bridge/github-dev")
    report = mod.build_report(p, pushed=False, conflicts=[".cnb.yml", "AGENTS.md"])
    assert ".cnb.yml" in report and "AGENTS.md" in report, report


def test_script_never_force_pushes(mod):
    """**永不在 push 上开 `force`** —— 反向护栏与 git-sync 一致，别在这条新通道上丢掉。

    ⚠️ 判据必须**收窄到 push 的参数**：`worktree remove --force` 里也有 `--force`，
    按全文扫会**恒红**（第一版就是这么写的，实测自咬）。判据要的是
    「执行 git push 那一行的参数里有没有 force」，不是「文件里有没有出现过 force 这个词」。
    探针：在 push 参数里加 `--force` ⇒ 本用例转红。
    """
    src = _SCRIPT_PATH.read_text(encoding="utf-8").split('"""', 2)[-1]
    if _push_refuses_force(src) is None:
        raise AssertionError(
            "找不到 push 调用——判据失去了锚点（脚本结构变了要一起改判据）"
        )
    refused, why = _push_refuses_force(src)
    assert refused, f"push 不得带 force 类参数（反向护栏）：{why}"


def test_script_never_imports_network(mod):
    """推/开 PR 全部走 git 与调用方给的凭据，脚本自身不引网络库。

    理由与 `check_branch_divergence.py` 同：判定不该依赖网络，否则
    「网络不通 = 报告绿」又是一次静默降级。
    """
    src = _SCRIPT_PATH.read_text(encoding="utf-8").split('"""', 2)[-1]
    for banned in ("import urllib", "import requests", "import socket", "import http"):
        assert banned not in src, f"脚本出现网络依赖：{banned}"


def test_push_failure_surfaces_stderr(mod, tmp_path, capsys, monkeypatch):
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
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "dev", env=_env())
    # `_git()` 返回三值（#2262 起），失败原因须落在**第二个**返回值里 —— 推失败那一行打的就是它。
    code, out, err = mod._git(["show", "0" * 40], str(repo))
    assert code != 0
    assert err.strip(), "`git show` 失败时 stderr 不该为空（判据自身失去了锚点）"
    assert err.strip() in out, (
        "`_git()` 只收 stdout —— stderr 被丢掉了，失败原因会打成空串"
    )

    # ② `run()` 的推失败分支要把原因与目标分支都打出来。
    #    造一个**能合、但推不上去**的场景：远端是个**合法仓库**（否则死在前面的 fetch 上，
    #    走的是「拿不到输入」分支），但预置一条同名分支，于是 push 是**非快进**被拒 ——
    #    这正是 #567 事故里真实的失败形态。
    work = tmp_path / "work"
    work.mkdir()
    env = _env()
    _git(work, "init", "-q", "-b", "dev", env=env)
    _git(work, "config", "commit.gpgsign", "false", env=env)
    (work / "a.txt").write_text("a\n", encoding="utf-8")
    _git(work, "add", ".", env=env)
    _git(work, "commit", "-q", "--no-gpg-sign", "-m", "base", env=env)
    _git(work, "checkout", "-q", "-b", "gh", env=env)
    (work / "gh.txt").write_text("gh\n", encoding="utf-8")
    _git(work, "add", ".", env=env)
    _git(work, "commit", "-q", "--no-gpg-sign", "-m", "gh", env=env)
    _git(work, "checkout", "-q", "dev", env=env)
    (work / "cnb.txt").write_text("cnb\n", encoding="utf-8")
    _git(work, "add", ".", env=env)
    _git(work, "commit", "-q", "--no-gpg-sign", "-m", "cnb", env=env)

    # 远端：同一条仓库，且**已有一条内容无关的 `bridge/github-dev`**（孤立提交）⇒
    # 推合并结果必然被判非快进而拒 —— 这正是 #567 事故里真实的失败形态。
    # 注意**不能**让远端那条分支等于 `dev`：合并结果包含 `dev`，推上去就是快进，会被接受。
    _git(work, "checkout", "-q", "--orphan", "unrelated", env=env)
    (work / "gh.txt").unlink(missing_ok=True)
    (work / "cnb.txt").unlink(missing_ok=True)
    (work / "a.txt").write_text("unrelated\n", encoding="utf-8")
    _git(work, "add", "-A", env=env)
    _git(work, "commit", "-q", "--no-gpg-sign", "-m", "unrelated", env=env)
    _git(work, "checkout", "-q", "dev", env=env)
    remote = tmp_path / "remote.git"
    _git(tmp_path, "clone", "-q", "--bare", str(work), str(remote), env=env)
    _git(remote, "branch", "bridge/github-dev", "unrelated", env=env)

    args = argparse.Namespace(
        apply=True,
        dry_run=False,
        push=True,
        base="cnb",
        branch="dev",
        machine_branch="bridge/github-dev",
        cnb_url=str(work),
        github_url=str(remote),
        cwd=str(work),
    )
    # 让 push **注定失败**且原因可读：远端仍在（fetch 得通），但**只读** ——
    # 用一个 hook 拒绝一切写入的裸仓，push 会带着 remote 的原话失败。
    # （不能用「远端已有一条无关的 bridge/github-dev」那种场景：那是 #573 修复后的**成功**路径。）  # cross-repo-ref-allow
    read_only = tmp_path / "read-only.git"
    _git(tmp_path, "clone", "-q", "--bare", str(work), str(read_only), env=env)
    hook = read_only / "hooks" / "pre-receive"
    hook.write_text(
        '#!/bin/sh\necho "no writes allowed" >&2\nexit 1\n', encoding="utf-8"
    )
    hook.chmod(0o755)
    args.github_url = str(read_only)
    # 源 CNB #574 起默认**不是**写者（默认只读探针，根本不推）。本用例钉的是「写者身份下
    # 推失败」的报错形态，故必须显式把自己声明成写者；否则用例会退化成「没调 push、恒绿」。
    # ⚠️ 同时保留源 CNB #573 的「让 push 注定失败且原因可读」：远端是只读裸仓，push 带着 remote
    # 的原话失败（不能用「远端已有一条无关的 bridge/github-dev」那种场景：那是 CNB #573 修复后的）  # cross-repo-ref-allow
    # **成功**路径。  # cross-repo-ref-allow
    monkeypatch.setenv(mod.WRITER_ENV, "cnb")
    rc = mod.run(args)
    assert rc == 2, f"推失败应以「结论不可信」退出（2），实际 {rc}"
    # 推失败那一行必须打出 **remote 的原话**（空原因等于没信号），且点名目标分支。
    # ⚠️ 语义变更（源 CNB #573）：机器分支现在**一开始就带 `--force-with-lease=<ref>:<sha>`**
    # 推（一次性分支的覆盖语义），于是「远端已有一条无关的 bridge/github-dev」这种场景
    # **会被成功覆盖**（退 0）—— 这正是修复想要的效果，不再是失败。
    # 故本用例改用 `--machine-branch` 指向一条**无法覆盖**的 ref 来保留「推得出去才算成功」的
    # 反面：远端是个 **bare 仓库的只读路径**（不存在的目录）⇒ 推必然失败。
    # 判据本身不变：失败时日志必须带 remote 原话。
    err_out = capsys.readouterr().err
    assert "推机器分支失败" in err_out, f"须显式说推失败，实际 stderr：{err_out!r}"
    assert "no writes allowed" in err_out, (
        f"须把 remote 的原话打出来（空原因等于没信号），实际：{err_out!r}"
    )
    assert "bridge/github-dev" in err_out, f"须点名目标分支，实际：{err_out!r}"
    assert "已合并成功，但没推上去" in err_out, (
        f"须明确「合好了但没送出去」，实际：{err_out!r}"
    )


def _push_refuses_force(src: str) -> tuple[bool, str] | None:
    """扫出所有 `_git([...'push'...])` 调用（跨行拼接），检查它们**不带** force 类参数。

    返回 `None` ⇒ 一条 push 调用都找不到（判据失去锚点）；否则 `(是否合规, 原因)`。

    为什么要把调用拼成一行再判：push 的参数在 `.cnb.yml` 之后又变成**跨行**写法
    （`_git(\n    ['push', …]\n)`），按行匹配会**恒绿**（找不到调用）。判据必须按调用判，
    不按行判——否则「改了代码、判据还在绿」正是最坏的那种假绿。
    """
    calls = re.findall(r"_git\(\s*\[([^\]]*)\]", src, re.S)
    push_calls = [c for c in calls if re.search(r"'push'", c)]
    if not push_calls and "machine_push_args(" not in src:
        # 两种形态都认：① 内联 `_git(['push', …])`；② 参数由 `machine_push_args()`
        # 算出来（本仓 #573 之后就是②）。**只认① 的判据会在结构变化时恒绿**。
        return None
    for c in push_calls:
        flat = " ".join(c.split())
        for banned in ("'--force'", "'-f'", "force-with-lease"):
            if banned in flat:
                return (
                    False,
                    f"push 不得带 {banned}（反向护栏 —— 只有机器分支那条特殊）：{flat}",
                )
    # 机器分支那条走 `machine_push_args()`：判它**产出的参数**，而不是判调用行文本
    # （调用的参数由函数算出来，按文本判会恒绿）。
    if "machine_push_args(" in src:
        args_src = src.split("def machine_push_args(", 1)[1].split("\ndef ", 1)[0]
        if "--force-with-lease=" not in args_src:
            return (
                False,
                "machine_push_args() 里没有显式的 `--force-with-lease=<ref>:<sha>`",
            )
        if "'--force'" in args_src:
            return False, "machine_push_args() 不得出现裸 `--force`"
        if "dev" not in args_src and "machine_branch" not in args_src:
            return (
                False,
                "machine_push_args() 的 ref 来源不明（须由 machine_branch 拼出）",
            )
    return True, ""


# ---------------------------------------------------------------------------
# 六、演练路径的冲突判据：**同一事实不许问两次**（源 CNB #573，2026-10-18）
# ---------------------------------------------------------------------------


def _dry_run_args(cnb, gh):
    return argparse.Namespace(
        apply=False,
        dry_run=True,
        push=False,
        base="cnb",
        branch="dev",
        machine_branch="bridge/github-dev",
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
    cnb, gh = _mk_side_repos(tmp_path, "pushfail", same_file=False)
    env = _env()
    _git(cnb, "remote", "add", "gh", str(gh), env=env)
    _git(cnb, "fetch", "-q", "gh", "dev", env=env)
    _git(cnb, "branch", "gh-dev", "FETCH_HEAD", env=env)

    # 让 push **注定失败**且原因可读：github_url 指向一个不存在的路径。
    bad_remote = tmp_path / "no-such-remote.git"
    args = argparse.Namespace(
        apply=True,
        dry_run=False,
        push=True,
        base="cnb",
        branch="dev",
        machine_branch="bridge/github-dev",
        cnb_url=str(cnb),
        github_url=str(bad_remote),
        cwd=str(cnb),
    )
    rc = mod.run(args)
    out = capsys_err = None  # noqa: F841  (仅取 stderr，见下)
    assert rc == 2, f"推失败应退 2，实际 {rc}"

    # 直接对报告构造函数钉语义（与 `run()` 的调用点一致）
    p = mod.plan("cnb", "bridge/github-dev")
    report = mod.build_report(p, pushed=False, conflicts=[], reason="push_failed")
    assert "演练模式" not in report, (
        f"推失败不得写成「演练模式」——那是一个**没推**的假理由：{report}"
    )
    assert "已合并" in report and "没推上去" in report, (
        f"须说清「合好了但没送出去」：{report}"
    )


def test_report_distinguishes_three_reasons_of_not_pushed(mod):
    """「没推」有三种**完全不同**的原因，报告必须一种一句（#573）。

    ① 有冲突 ⇒ 什么都没合；
    ② 试算 / 合并不可用 ⇒ 结论不可信；
    ③ 合并成功但**推失败** ⇒ 本地好了、远端没收到；
    ④ 合并成功但**写者不在本侧**（只读探针）⇒ 结论是观测，不是已送达（源 CNB #574）。

    「没推」原本只有一句兜底 `（演练模式：未推、未开 PR）`，③ 落进去之后
    「推被拒」在报告里长得像「还没执行」——诊断方向被掉包；④ 落进去则是**反向**的误导：
    读者以为「加个 `--apply --push` 就会推」，而本侧根本没写权。
    故**默认参数不许落到这两句之一**，必须显式声明是哪一种。

    探针（两条，任一即转红）：
    - 删掉 `elif reason == 'push_failed'` 分支 ⇒ ③ 复用「演练模式」；
    - 把 `elif dry_run:` 挪到 `else:` 之后（或直接删）⇒ ④ 冒充「演练模式」。
    """
    p = mod.plan("cnb", "bridge/github-dev")
    push_failed = mod.build_report(p, pushed=False, conflicts=[], reason="push_failed")
    assert "推" in push_failed and "失败" in push_failed, (
        f"③ 必须说自己失败了：{push_failed}"
    )
    assert "演练模式" not in push_failed, push_failed

    inconclusive = mod.build_report(
        p, pushed=False, conflicts=[], reason="inconclusive"
    )
    assert "不可信" in inconclusive, f"② 必须声明结论不可信：{inconclusive}"
    assert "演练模式" not in inconclusive, inconclusive

    # ④ 只读探针：**想写但写者不在本侧**，不能说成「演练模式」（那会误导人加 `--push`）。
    readonly = mod.build_report(p, pushed=False, conflicts=[], dry_run=False)
    assert "演练模式" not in readonly, f"只读探针不是演练，别共用那句：{readonly}"
    assert "只做**读探针**" in readonly, readonly

    # ①（真演练）保留原样：这一句本身没错，错的只是被复用给了另外三种原因。
    dry = mod.build_report(p, pushed=False, conflicts=[], dry_run=True)
    assert "演练模式" in dry, f"真演练仍要说「未推、未开 PR」：{dry}"
    assert "只做**读探针**" not in dry, f"演练与只读是两件事：{dry}"


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
    repo = tmp_path / "dryconflict"


# ---------------------------------------------------------------------------
# 源 CNB #574（2026-10-19，机制说明）：`bridge/github-dev` 只能有**一个写者**。  <!-- cross-repo-ref-allow -->
# GitHub 侧 `.github/workflows/dev-reconcile.yml` 每日 `--force-with-lease` 重建
# 并开 PR + automerge；CNB 侧只会每轮换个 base 重推 ⇒ 非快进被拒、且会把
# reconcile 铺好的合并结果冲掉。故 CNB 侧默认降级为**只读探针**。
# ---------------------------------------------------------------------------


def test_default_writer_is_github(mod, monkeypatch):
    """默认写者是 GitHub reconcile，不是 CNB —— 这是「降级为只读」的开关本身。

    探针：把 `DEFAULT_WRITER` 改成 `'cnb'` ⇒ 本用例转红。
    """
    monkeypatch.delenv(mod.WRITER_ENV, raising=False)
    assert mod.writer() == "github", (
        "默认必须**不是** CNB —— 否则两个写者并存（源 CNB #574）"
    )  # cross-repo-ref-allow


def test_writer_env_can_hand_over_but_only_explicitly(mod, monkeypatch):
    """只有显式 `MACHINE_BRANCH_WRITER=cnb` 才接管写权；其余取值一律回到默认（不猜）。"""
    monkeypatch.setenv(mod.WRITER_ENV, "cnb")
    assert mod.writer() == "cnb"
    for junk in ("", "github", "yes", "TRUE", "nonsense"):
        monkeypatch.setenv(mod.WRITER_ENV, junk)
        assert mod.writer() == "github", f"`{junk}` 不该被读成接管写权"


def test_readonly_probe_never_pushes(mod, tmp_path, monkeypatch, capsys):
    """默认身份下：合并照跑、结论照报，但**一次 push 都不发**。

    判据锚在「push 有没有被调用」，而不是「返回了 0」——返回 0 却推过，正是本卡要消灭的形态。
    探针：把 `run()` 里 `if writer() != 'cnb':` 那段删掉 ⇒ push 会被调用且本用例转红。
    """
    repo = tmp_path / "probe"
    repo.mkdir()
    env = _env()
    _git(repo, "init", "-q", "-b", "dev", env=env)
    _git(repo, "config", "commit.gpgsign", "false", env=env)
    _git(repo, "config", "user.name", "t", env=env)
    _git(repo, "config", "user.email", "t@e", env=env)
    (repo / "a.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", ".", env=env)
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", "base", env=env)
    _git(repo, "checkout", "-q", "-b", "gh", env=env)
    (repo / "a.txt").write_text("gh\n", encoding="utf-8")
    _git(repo, "commit", "-q", "--no-gpg-sign", "-am", "gh", env=env)
    _git(repo, "checkout", "-q", "dev", env=env)
    (repo / "a.txt").write_text("cnb\n", encoding="utf-8")
    _git(repo, "commit", "-q", "--no-gpg-sign", "-am", "cnb", env=env)

    monkeypatch.delenv(mod.WRITER_ENV, raising=False)
    # 合并要在临时 worktree 里真的跑起来 ⇒ 需要 git 身份（#2262 的同款前置）。
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@e")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@e")

    calls: list[list[str]] = []
    real = mod._git

    def spy(args, cwd=None):
        calls.append(list(args))
        return real(args, cwd)

    monkeypatch.setattr(mod, "_git", spy)

    args = argparse.Namespace(
        apply=True,
        dry_run=False,
        push=True,  # 调用方**要求**推，但写者身份不是 CNB ⇒ 仍然不推
        base="cnb",
        branch="dev",
        machine_branch="bridge/github-dev",
        cnb_url=str(repo),
        github_url=str(repo),
        cwd=str(repo),
    )
    rc = mod.run(args)
    out = capsys.readouterr().out

    pushed = [c for c in calls if c and c[0] == "push"]
    assert not pushed, f"默认（非写者）身份下**一个字节都不该推**，实际：{pushed}"
    assert rc == 0, f"无冲突应退 0（含义已收窄为「可合（观测）」），实际 {rc}"
    # 只读态必须**说人话**：报告里不能只写「无冲突」就完事，否则读者会以为已送达。
    assert "只读探针" in out, f"须明说这是只读探针，实际输出：{out!r}"
    assert "未推送" in out or "未动" in out, f"须明说没有推送，实际输出：{out!r}"


def test_dry_run_single_merge_tree_call(mod, tmp_path):
    """无论有没有冲突，演练路径**只调一次** `merge-tree`。"""
    repo = tmp_path / "dryclean"
    repo.mkdir()
    env = _env()
    _git(repo, "init", "-q", "-b", "dev", env=env)
    _git(repo, "config", "commit.gpgsign", "false", env=env)
    _git(repo, "config", "user.name", "t", env=env)
    _git(repo, "config", "user.email", "t@e", env=env)
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", ".", env=env)
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", "base", env=env)
    _git(repo, "checkout", "-q", "-b", "gh", env=env)
    (repo / "gh.txt").write_text("gh\n", encoding="utf-8")
    _git(repo, "add", ".", env=env)
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", "gh", env=env)
    _git(repo, "checkout", "-q", "dev", env=env)
    (repo / "cnb.txt").write_text("cnb\n", encoding="utf-8")
    _git(repo, "add", ".", env=env)
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", "cnb", env=env)

    real = mod._git
    calls: list[list[str]] = []

    def spy(args, cwd=None):
        if args[:2] == ["merge-tree", "--write-tree"]:
            calls.append(args)
        return real(args, cwd)

    saved = mod._git
    mod._git = spy
    try:
        rc = mod.run(_dry_run_args(repo, repo))
    finally:
        mod._git = saved
    assert rc == 0, f"两侧改不同文件应无冲突（退 0），实际 {rc}"
    assert len(calls) == 1, f"演练路径只该跑一次 merge-tree，实际 {len(calls)} 次"


def test_existing_machine_branch_is_overwritten_with_lease(
    mod, tmp_path, monkeypatch, capsys
):
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
    work = tmp_path / "lease"
    work.mkdir()
    env = _env()
    _git(work, "init", "-q", "-b", "dev", env=env)
    _git(work, "config", "commit.gpgsign", "false", env=env)
    _git(work, "config", "user.name", "t", env=env)
    _git(work, "config", "user.email", "t@e", env=env)
    (work / "a.txt").write_text("a\n", encoding="utf-8")
    _git(work, "add", ".", env=env)
    _git(work, "commit", "-q", "--no-gpg-sign", "-m", "base", env=env)
    _git(work, "checkout", "-q", "-b", "gh", env=env)
    (work / "gh.txt").write_text("gh\n", encoding="utf-8")
    _git(work, "add", ".", env=env)
    _git(work, "commit", "-q", "--no-gpg-sign", "-m", "gh", env=env)
    _git(work, "checkout", "-q", "dev", env=env)
    (work / "cnb.txt").write_text("cnb\n", encoding="utf-8")
    _git(work, "add", ".", env=env)
    _git(work, "commit", "-q", "--no-gpg-sign", "-m", "cnb", env=env)
    _git(work, "checkout", "-q", "--orphan", "unrelated", env=env)
    for f in ("gh.txt", "cnb.txt", "a.txt"):
        (work / f).unlink(missing_ok=True)
    (work / "other.txt").write_text("unrelated\n", encoding="utf-8")
    _git(work, "add", "-A", env=env)
    _git(work, "commit", "-q", "--no-gpg-sign", "-m", "unrelated", env=env)
    _git(work, "checkout", "-q", "dev", env=env)
    remote = tmp_path / "remote-lease.git"
    _git(tmp_path, "clone", "-q", "--bare", str(work), str(remote), env=env)
    _git(remote, "branch", "bridge/github-dev", "unrelated", env=env)

    real = mod._git
    pushes: list[list[str]] = []

    def spy(args, cwd=None):
        if args and args[0] == "push":
            pushes.append(args)
        return real(args, cwd)

    saved = mod._git
    mod._git = spy
    # ⚠️ 源 CNB #574 起默认**不是**写者（默认只读探针，根本不推）。本用例钉的是「写者身份下
    # 用 `--force-with-lease` 覆盖自己那条一次性分支」，故必须显式把自己声明成写者；
    # 否则用例会退化成「没调 push、恒绿」——**探针删掉修复也不会红**。
    monkeypatch.setenv(mod.WRITER_ENV, "cnb")
    try:
        args = argparse.Namespace(
            apply=True,
            dry_run=False,
            push=True,
            merge_sync=False,
            base="cnb",
            branch="dev",
            machine_branch="bridge/github-dev",
            cnb_url=str(work),
            github_url=str(remote),
            cwd=str(work),
        )
        rc = mod.run(args)
    finally:
        mod._git = saved

    assert pushes, "应当至少调用一次 push"
    assert all(any(a.startswith("--force-with-lease") for a in ps) for ps in pushes), (
        f"机器分支的推送必须带 `--force-with-lease`（一次性分支的覆盖语义）：{pushes}"
    )
    for ps in pushes:
        assert "--force" not in ps, (
            f"不得用裸 `--force`（lease 才有「别人动过就失败」的保证）：{ps}"
        )
        # lease 必须**显式带期望值**（`=<ref>:<sha>`）：裸 lease 在「本地没有该 ref 的
        # tracking 信息」时退化成 `(stale info)` 被拒 —— 实测复现过，别改回裸形态。
        lease = [a for a in ps if a.startswith("--force-with-lease")]
        assert lease and ":" in lease[0], (
            f"lease 必须显式指定期望值（`=<ref>:<sha>`），否则 stale info：{ps}"
        )
        assert ps[-1] == "HEAD:refs/heads/bridge/github-dev", f"只准推机器分支：{ps}"
    assert rc == 0, f"覆盖成功后应退 0，实际 {rc}；push 调用：{pushes}"
    # 覆盖后远端那条 ref 必须真的指向本次合并结果。
    ref = subprocess.run(
        ["git", "rev-parse", "bridge/github-dev"],
        cwd=str(remote),
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()
    assert ref, "远端 bridge/github-dev 应已存在"


def test_force_only_allowed_on_machine_branch(mod):
    """`--force-with-lease` 只允许出现在**机器分支**那条 push 上（反向护栏，别被顺手套到 dev）。"""
    src = _SCRIPT_PATH.read_text(encoding="utf-8").split('"""', 2)[-1]
    res = _push_refuses_force(src)
    assert res is not None, "找不到 push 调用——判据失去锚点（脚本结构变了要一起改判据）"
    refused, why = res
    assert refused, why
    # 机器分支必须有 lease 保护（一次性分支的覆盖语义），且**只**推机器分支。
    assert "--force-with-lease=" in src and "machine_branch" in src, (
        "机器分支的覆盖须用 --force-with-lease=<ref>:<sha>"
    )
    assert "refs/heads/main" not in src, "不得出现推 main 的字面 ref"
    # `refs/heads/dev` **允许出现一次**：merge-sync 模式（源 CNB #577）要靠它推「两侧合并结果」，
    # 且那条 push **不带任何 force**（否则上面的 `_push_refuses_force` 已经先红）。
    # ⚠️ 判据收窄成「不计 --force 的那一条之外，别的 push 不得碰 dev」= 这条 push 必须是
    #    由 `args.branch` 拼出来的同名分支，而不是硬写死的 ref —— 见下一条断言。
    # 只认 `HEAD:` 前缀（别钉引号形态：`ruff format` 会把单引号改双引号，
    # 钉死写法 = 判据自己先崩，这是本仓判据踩过的第 N 次）。
    assert 'HEAD:{ref}' in src, 'merge-sync 必须推当前分支（`HEAD:{ref}`），不得硬写远端 ref 名'


def test_readonly_report_does_not_claim_pushed(mod):
    """报告文案层面也要区分「可合（观测）」与「已推送」——退 0 的语义已被收窄。"""
    p = mod.plan("cnb", "bridge/github-dev")
    readonly = mod.build_report(p, pushed=False, conflicts=[], dry_run=False)
    dry = mod.build_report(p, pushed=False, conflicts=[], dry_run=True)
    pushed = mod.build_report(p, pushed=True, conflicts=[])
    assert "只做**读探针**" in readonly, readonly
    assert "只做**读探针**" not in dry, f"演练与只读是两件事，别混：{dry}"
    assert "已推成" in pushed, pushed
    assert "已推成" not in readonly, (readonly, pushed)


# ---------------------------------------------------------------------------
# 九、merge-sync（源 CNB #577，2026-10-19）：替代 git-sync 直推 dev
# ---------------------------------------------------------------------------


def _run_merge_sync(mod, tmp_path, *, remote, cwd, monkeypatch, capsys):
    """跑一次 `--apply --push --merge-sync`，返回 (退出码, stdout, stderr, push 参数清单)。"""
    real = mod._git
    pushes: list[list[str]] = []

    def spy(args, wd=None):
        if args and args[0] == "push":
            pushes.append(list(args))
        return real(args, wd)

    monkeypatch.setattr(mod, "_git", spy)
    args = argparse.Namespace(
        apply=True,
        dry_run=False,
        push=True,
        merge_sync=True,
        base="cnb",
        branch="dev",
        machine_branch=mod.DEFAULT_MACHINE_BRANCH,
        cnb_url=str(tmp_path / "conflict-cnb")
        if (tmp_path / "conflict-cnb").exists()
        else str(cwd),
        github_url=str(remote),
        cwd=str(cwd),
    )
    rc = mod.run(args)
    out = capsys.readouterr()
    return rc, out.out, out.err, pushes


def test_merge_sync_pushes_merge_result_fast_forward(
    mod, tmp_path, monkeypatch, capsys
):
    """merge-sync：推的是**合并结果**，于是快进成立；`dev` 上 `我比你新` 的矛盾就此消失。

    这是 #577 的核心替换：git-sync 直推裸 ref ⇒ GitHub 侧快一步就 `(fetch first)` 被拒，  # cross-repo-ref-allow
    且**永不自愈**；推合并结果 ⇒ 对方的提交已在祖先里 ⇒ 快进必然成立。

    探针：把 `_push_merge_sync` 改成推 `p['base_ref']`（只推本侧）⇒ 远端 `dev`
    不再包含 GitHub 侧那笔 ⇒ 下面两条断言同时转红。
    """
    cnb, gh = _mk_side_repos(tmp_path, "mergesync", same_file=False)
    env = _env()
    # 两侧各有独有提交（`same_file=False` ⇒ 无冲突），正是 #577 的现场形态。
    # ⚠️ 这个 fixture 的 `gh` 有 `cnb` 作为 origin 且**本地 dev 就是 origin/dev**
    # （clone ⇒ 本地分支即跟踪分支），直接读 `rev-parse dev` 读到的是远端 ref ——
    # 于是「推完再读」两边一样、断言恒真（第一版就是这么写的，实测空转）。
    # 故用 `ls-remote` 取**真实远端 ref** 作基线。
    # fixture 的 `gh` 是**非裸**仓库且正检出着 `dev`，而 git 默认拒绝推「当前检出分支」
    # （`receive.denyCurrentBranch`）。真实远端是裸仓，这里补上同样的姿态，
    # 否则测到的是 fixture 的限制、不是被测代码的行为（第一版就掉这个坑里）。
    _git(gh, "config", "receive.denyCurrentBranch", "ignore", env=env)

    def remote_dev() -> str:
        out = subprocess.run(
            ["git", "ls-remote", str(gh), "refs/heads/dev"],
            capture_output=True,
            text=True,
            env=env,
        ).stdout
        return out.split()[0].strip()

    gh_sha = remote_dev()
    assert gh_sha, "fixture 失效：找不到远端 dev"

    _run_merge_sync(
        mod, tmp_path, remote=gh, cwd=cnb, monkeypatch=monkeypatch, capsys=capsys
    )

    remote_sha = remote_dev()
    assert remote_sha != gh_sha, "GitHub 的 dev 应被推进（否则就是「合了但没搬」）"
    # 快进 = 原来的 dev 是新 dev 的祖先 ⇒ 推送**不需要** force 就成立。
    # ⚠️ 这里**刻意不**再断言 `gh_sha` 是新 dev 的祖先（探针实测：删掉它一个用例都不红）。
    # 原因：merge-sync 推的是 `HEAD`（合并提交），它的第一个父就是本侧旧 dev ——
    # 而推成功本身就要求快进，于是「祖先关系」是 push 成功的结果，不是独立判据。
    # 真正需要独立钉住的是「**内容**两侧都在」：只推本侧（丢掉合并结果）也会是快进，
    # 那才是会静默丢提交的形态 —— 下面那条 `cnb-only.txt` 断言就是它（探针 P2 实测会红）。
    # 且两侧内容都在（CNB 独有的那笔也过去了）。
    _git(gh, "fetch", "-q", "origin", "dev", env=env)
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", remote_sha],
        cwd=str(gh),
        capture_output=True,
        text=True,
        env=env,
    ).stdout
    assert "cnb-only.txt" in listing, f"CNB 侧独有内容必须一起搬过去，实际：{listing}"


def test_merge_sync_never_forces(mod, tmp_path, monkeypatch, capsys):
    """merge-sync 的 push **不带任何 force 参数** —— `dev` 是共享事实，覆盖别人不可接受。

    探针：在 `_push_merge_sync` 的 push 参数里加 `--force-with-lease` ⇒ 本用例转红
    （哪怕 `_push_refuses_force` 那条静态判据漏掉，这条动态判据也咬得住）。
    """
    cnb, gh = _mk_side_repos(tmp_path, "mergesync-force", same_file=False)
    _git(gh, "config", "receive.denyCurrentBranch", "ignore", env=_env())
    calls: list[list[str]] = []
    real = mod._git

    def spy(args, wd=None):
        if args and args[0] == "push":
            calls.append(list(args))
        return real(args, wd)

    monkeypatch.setattr(mod, "_git", spy)
    args = argparse.Namespace(
        apply=True,
        dry_run=False,
        push=True,
        merge_sync=True,
        base="cnb",
        branch="dev",
        machine_branch=mod.DEFAULT_MACHINE_BRANCH,
        cnb_url=str(cnb),
        github_url=str(gh),
        cwd=str(cnb),
    )
    mod.run(args)
    assert calls, "merge-sync 必须真的 push（否则本用例空转）"
    for ps in calls:
        # 只判 force 类参数（`--force` / `--force-with-lease`）。别用 `'force' in a` 之外
        # 的模糊匹配，也别把路径里偶然含 force 的片段算进来 —— 判据错方向比不判更坏。
        assert not any(
            a == "--force" or a.startswith("--force-with-lease") for a in ps
        ), f"merge-sync 不得带任何 force 类参数：{ps}"
        assert ps[-1] == "HEAD:refs/heads/dev", (
            f"merge-sync 推的目标必须是 HEAD:refs/heads/dev：{ps}"
        )


def test_merge_sync_conflict_still_pushes_nothing(mod, tmp_path, monkeypatch, capsys):
    """有冲突时 merge-sync 与机器分支通道**同样一个字节都不推**（安全承诺与模式无关）。

    探针：把 `run()` 里 `if conflicts:` 的提前 return 删掉 ⇒ push 出现、本用例转红。
    """
    cnb, gh = _mk_side_repos(tmp_path, "mergesync-conflict", same_file=True)
    before = (
        subprocess.run(
            ["git", "ls-remote", str(gh), "refs/heads/dev"],
            capture_output=True,
            text=True,
            env=_env(),
        )
        .stdout.split()[0]
        .strip()
    )
    calls: list[list[str]] = []
    real = mod._git

    def spy(args, wd=None):
        if args and args[0] == "push":
            calls.append(list(args))
        return real(args, wd)

    monkeypatch.setattr(mod, "_git", spy)
    args = argparse.Namespace(
        apply=True,
        dry_run=False,
        push=True,
        merge_sync=True,
        base="cnb",
        branch="dev",
        machine_branch=mod.DEFAULT_MACHINE_BRANCH,
        cnb_url=str(cnb),
        github_url=str(gh),
        cwd=str(cnb),
    )
    rc = mod.run(args)
    assert rc == 1, f"冲突应退 1，实际 {rc}"
    assert calls == [], f"冲突时不得有任何 push，实际：{calls}"
    after = (
        subprocess.run(
            ["git", "ls-remote", str(gh), "refs/heads/dev"],
            capture_output=True,
            text=True,
            env=_env(),
        )
        .stdout.split()[0]
        .strip()
    )
    assert before == after, "冲突时远端 dev 不得被改动"


# ---------------------------------------------------------------------------
# 十、分支保护拒绝 ⇒ 改走 PR 通道（源 CNB #586，2026-10-19 构建 cnb-68p-1k58q97a8）
# ---------------------------------------------------------------------------
#
# 现场原文（照抄构建日志）：
#     ❌ 推 `dev` 失败：remote: error: GH006: Protected branch update failed for refs/heads/dev.
#        remote: - Required status check "质量门禁汇总" is expected.
#      ! [remote rejected]   HEAD -> dev (protected branch hook declined)
#
# 合并**是成功的**，被拒的只有推。根因不是分叉没解——是「直推」在有保护规则的分支上
# 恒不可达（`质量门禁汇总` 只在 PR 上产生）。故这一支要**换通道**，不是重跑。


def _run_merge_sync_with_fake_push(mod, tmp_path, monkeypatch, capsys, push_result):
    """跑 merge-sync，但把 `_push_merge_sync` 换成「直接返回给定结果」。

    刻意不走真实 remote：本组用例要钉的是**推送被拒之后的处置**，
    真 remote 造不出「GH006 分支保护」这种远端行为。
    """
    cnb, gh = _mk_side_repos(tmp_path, "protect", same_file=False)
    pushed_refs: list[str] = []

    def fake_push(github_url, branch, cwd):
        pushed_refs.append(branch)
        return push_result

    monkeypatch.setattr(mod, "_push_merge_sync", fake_push)
    args = argparse.Namespace(
        apply=True,
        dry_run=False,
        push=True,
        merge_sync=True,
        base="cnb",
        branch="dev",
        machine_branch=mod.DEFAULT_MACHINE_BRANCH,
        cnb_url=str(cnb),
        github_url=str(gh),
        cwd=str(cnb),
    )
    rc = mod.run(args)
    out = capsys.readouterr()
    return rc, out, pushed_refs, gh


GH006 = (
    "remote: error: GH006: Protected branch update failed for refs/heads/dev.\n"
    'remote: - Required status check "质量门禁汇总" is expected.\n'
    " ! [remote rejected]   HEAD -> dev (protected branch hook declined)"
)


def test_protection_markers_cover_the_real_logline(mod):
    """分类判据必须认得住**构建日志里的原话**，而不是我们想象中的措辞。

    探针：从 `PROTECTION_REJECTION_MARKERS` 里删掉 `GH006` ⇒ 本用例转红
    （单独断言它，是为免别的标记把它的缺失掩盖掉——第一版就是这样 MISSED 的）。
    """
    assert "GH006" in mod.PROTECTION_REJECTION_MARKERS, (
        "GH006 是现场原文（构建 cnb-68p-1k58q97a8），不得从判据里删掉"
    )
    for marker in mod.PROTECTION_REJECTION_MARKERS:
        assert mod.is_protection_rejection(f"remote: {marker} ..."), marker
    # 三种失败形态**不得**互相冒充（处置完全不同：换通道 / 重跑 / 换 token）。
    assert not mod.is_protection_rejection(
        "! [rejected]  dev -> dev  (fetch first)"
    ), "非快进不是分支保护问题，开 PR 只会往看板添重复卡"
    assert not mod.is_protection_rejection(
        "fatal: Authentication failed for 'https://github.com/x/y.git'"
    ), "凭据失效不该被当成分支保护"


def test_protection_rejection_pushes_fallback_ref_and_exits_3(
    mod, tmp_path, monkeypatch, capsys
):
    """GH006 ⇒ 合并结果落到**一次性分支**、退 3，并把 head 印给 stage（不自己开 PR）。

    为什么退 3 而不是 2：2 的语义是「结论不可信」，而这一支结论**是有效的**
    （两侧确实无冲突、合成了）。两者混成一个数，日志里的人就只能靠猜（#567 的教训）。

    探针：把 `run()` 里 `return 3` 改成 `return 2` ⇒ 第一条断言转红；
    删掉 `push_fallback_ref` 调用 ⇒ 第二条断言转红。
    """
    rc, out, pushed_refs, gh = _run_merge_sync_with_fake_push(
        mod, tmp_path, monkeypatch, capsys, (False, GH006)
    )
    assert rc == 3, f"分支保护拒绝应退 3（结论有效、通道不对），实际 {rc}"
    assert f"FALLBACK_HEAD={mod.FALLBACK_BRANCH}" in out.out, out.out
    assert "FALLBACK_BASE=dev" in out.out, out.out
    assert "分支保护" in out.err, out.err
    # 一次性分支**真的被推了**（否则 stage 拿去开 PR 只会 404）。
    refs = subprocess.run(
        ["git", "ls-remote", str(gh), "refs/heads/" + mod.FALLBACK_BRANCH],
        capture_output=True,
        text=True,
        env=_env(),
    ).stdout
    assert refs.strip(), f"兜底分支应已推上远端，实际：{refs!r}"
    # merge-sync 的直推只试了一次 `dev`，之后就换通道 —— 不该对着 `dev` 反复重试。
    assert pushed_refs == ["dev"], pushed_refs


def test_non_protection_failure_still_exits_2(mod, tmp_path, monkeypatch, capsys):
    """**非快进 / 凭据失效照旧退 2**，不得顺手开 PR。

    探针：把判据改成「只要推失败就走 PR」⇒ 本用例转红
    （那时会退 3 并推出一条 `fix/cnb-dev-merge`，正是要防的「每轮都开 PR」）。
    """
    rc, out, _, gh = _run_merge_sync_with_fake_push(
        mod, tmp_path, monkeypatch, capsys, (False, "! [rejected]  dev -> dev  (fetch first)")
    )
    assert rc == 2, f"非快进应退 2，实际 {rc}"
    assert "FALLBACK_HEAD=" not in out.out, "非快进不该开 PR 兜底"
    refs = subprocess.run(
        ["git", "ls-remote", str(gh), "refs/heads/" + mod.FALLBACK_BRANCH],
        capture_output=True,
        text=True,
        env=_env(),
    ).stdout
    assert not refs.strip(), "非快进时不得推兜底分支"


def test_fallback_branch_name_has_no_date(mod):
    """兜底分支名**不得带日期**：带日期会攒出 `…-2026-10-19` 这种分支列表垃圾。

    （与 `test_default_machine_branch_is_not_a_long_lived_name` 同源。）
    """
    assert not re.search(r"\d{4}-\d{2}-\d{2}", mod.FALLBACK_BRANCH), mod.FALLBACK_BRANCH


def test_stage_reads_branch_name_from_script(mod):
    """`.cnb.yml` 里的兜底分支名必须**从脚本读**，不得自己再抄一份。

    两处真相的代价很具体：改了一处，另一处不会红，于是 stage 拿着旧分支名去开 PR ⇒
    PR 里的 head 是一条不存在的分支（#118 的契约谎言同族）。

    探针：把 stage 里的 `${headref}` 换成字面量 `fix/cnb-dev-merge` ⇒ 本用例转红。
    """
    yml = (_REPO_ROOT / ".cnb.yml").read_text(encoding="utf-8")
    assert "--print-fallback-target" in yml, "stage 应通过 --print-fallback-target 取分支名"
    assert "branch_protection_pr.py" in yml, "stage 应调用 PR 兜底脚本"
    assert '--head "${headref}"' in yml, "开 PR 的 head 必须取自脚本输出，不得写死"


def test_merge_sync_refetches_both_sides_before_pushing(mod, tmp_path, monkeypatch, capsys):
    """推之前必须**重新抓两侧**，并据此重做合并（源 CNB #600，构建 `cnb-32g-1k59n02e8`）。

    现场：功能分支 `fix/552-…` 的 push 构建红在

        ! [rejected]  fix/552-close-must-carry-criterion -> … (non-fast-forward)

    而同一分支 15 分钟前推成功过。差别只有一处：GitHub 侧那条分支此后被推前了一笔
    （`1484d348` → `276cf875`，同一个提交 rebase 成另一个 sha），而插件推的是
    **本地检出**、从不 fetch 目标分支 ⇒ 永远追不上，被拒之后也不会自愈。

    ⚠️ **判据直接钉「有没有重抓」，不绕道远端内容。** 这条路试错过两次，记下来：
    ① 「远端树里必须有 cnb-only.txt」——探针不红：被测代码从工作区推 HEAD，只要工作区
       是对的，合一次两次都能把内容送上去，那是**假判据**；
    ② 「用本地非裸仓库模拟远端被推前」——`fetch` / `worktree add` / 追踪分支三者会互相
       带偏本地 ref，被测代码「不重抓」也能歪打正着，同样不红。
    git 的本地语义模拟不出「远端单独前进」，那就别模拟：直接观测脚本**有没有真的去抓**，
    以及**合并用的是不是刚抓到的那对 ref**。这一条同时挡住两种退化 ——
    删掉重抓、或重抓了却仍拿旧 ref 去合。
    """
    cnb, gh = _mk_side_repos(tmp_path, "mergesync-refetch", same_file=False)
    _git(gh, "config", "receive.denyCurrentBranch", "ignore", env=_env())

    real_fetch = mod.fetch_ref
    fetch_calls: list[str] = []

    def spy_fetch(url, branch, dest_ref, cwd=None):
        fetch_calls.append(dest_ref)
        return real_fetch(url, branch, dest_ref, cwd)

    monkeypatch.setattr(mod, "fetch_ref", spy_fetch)

    real_git = mod._git
    pushes: list[list[str]] = []
    merge_refs: list[str] = []

    def spy_git(args, wd=None):
        if args and args[0] == "push":
            pushes.append(list(args))
        if args and args[0] == "merge" and len(args) > 1:
            merge_refs.append(args[-1])
        return real_git(args, wd)

    monkeypatch.setattr(mod, "_git", spy_git)

    rc, _, err, _ = _run_merge_sync(
        mod, tmp_path, remote=gh, cwd=cnb, monkeypatch=monkeypatch, capsys=capsys
    )
    assert rc == 0, f"merge-sync 应成功，实际 rc={rc} / {err}"
    assert pushes, "本轮必须真的推过（否则是空转的假绿）"

    # ① 推之前必须再抓一次**两侧**。第一轮开头那两次是既有行为，故看「总数」：
    #    两侧各 ≥2 次。用计数而非「最后一条 == PUSH_*」是为了不钉死实现细节。
    cnb_hits = fetch_calls.count(mod.CNB_REF) + fetch_calls.count(mod.PUSH_CNB_REF)
    gh_hits = fetch_calls.count(mod.GH_REF) + fetch_calls.count(mod.PUSH_GH_REF)
    assert cnb_hits >= 2, f"推之前没有重新抓 CNB 侧（旧快照推 dev 必然非快进）：{fetch_calls}"
    assert gh_hits >= 2, f"推之前没有重新抓 GitHub 侧（源 CNB `#600` 的根因）：{fetch_calls}"

    # ② 最后一次合并必须用**推之前抓的那对 ref** —— 否则「重抓」只是摆设。
    assert merge_refs and merge_refs[-1] in {mod.PUSH_CNB_REF, mod.PUSH_GH_REF}, (
        f"最后一次合并用的仍是旧 ref，重抓了却没重做合并：merge_refs={merge_refs}"
    )
