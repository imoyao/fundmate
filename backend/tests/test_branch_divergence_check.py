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
2. **分叉判定（2026-10-14 起改为内容级，源 CNB #167 规则 1）**：
   **`main` 有没有 `dev` 没有的代码**才算分叉——发版 merge commit（内容 diff 为空）
   不算。旧口径「`main` 独有提交 > 0 ⇒ 分叉」会把每次发版都报成假红；
3. **判据不可用**（拿不到 `git cherry` / `git log`）⇒ 红、退出码 1，**不得降级成「正常」**（#171 教训）；
4. **只读**：出现 `fetch` / `merge` / `push` 即越界。

用例尽量走**真实 git**（本仓自己），只在需要构造「确定的分叉」时才用临时仓库——
mock 出来的 git 永远绿，而被测的正是「跟真实 git 对话时方向对不对」。
"""

import importlib.util
import pathlib
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


def _head(mod, repo, branch):
    """取某分支的 tip sha（临时仓库用）。"""
    out = subprocess.run(['git', 'rev-parse', branch], cwd=repo, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


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
# 二、提交级二分（源 CNB #179）：合规发版 vs 新形态
# ---------------------------------------------------------------------------


def test_classify_commit_plain_commit_is_violation(mod, diverged_repo):
    """普通提交（只有一个父）⇒ `violation` —— 它没有「被合进来」的语义。"""
    commit = mod.parse_commit(_head(mod, diverged_repo, 'main'), str(diverged_repo))
    assert commit is not None
    verdict = mod.classify_commit(commit, 'dev', str(diverged_repo))
    assert verdict['kind'] == 'violation', verdict


def test_classify_commit_release_uses_second_parent(mod, tmp_path):
    """**方向测**：合规发版 merge 的判定必须看**第二父**，不能看第一父。

    造一个「第一父**不是** dev 的祖先、第二父**是**」的发版合并：
    `main` 先自己提交，再从 `dev` 分叉后合并进来 ⇒ `[main-side, dev-tip]`。
    取第二父 ⇒ `release`（正确）；取第一父 ⇒ 会被误判成 `violation`（方向反了）。
    """
    import os

    repo = tmp_path / 'dir'
    repo.mkdir()
    env = {
        'GIT_AUTHOR_NAME': 't',
        'GIT_AUTHOR_EMAIL': 't@e',
        'GIT_COMMITTER_NAME': 't',
        'GIT_COMMITTER_EMAIL': 't@e',
        'PATH': os.environ['PATH'],
    }

    def git(*args):
        subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, env=env)

    git('init', '-q', '-b', 'main')
    git('config', 'commit.gpgsign', 'false')
    (repo / 'base.txt').write_text('base\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '--no-gpg-sign', '-m', 'base')
    # dev 从 base 分出
    git('checkout', '-q', '-b', 'dev')
    (repo / 'd1.txt').write_text('d1\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '--no-gpg-sign', '-m', 'dev work 1')
    # main 在**自己这一侧**提交（不是 dev 的祖先）
    git('checkout', '-q', 'main')
    (repo / 'm1.txt').write_text('m1\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '--no-gpg-sign', '-m', 'main-side work')
    # 发版：把 dev 合进 main ⇒ merge 的父是 [main-side, dev-tip]
    git('merge', '--no-ff', '-q', '--no-gpg-sign', '-m', '合并来自 dev 的合并请求 #1', 'dev')

    commit = mod.parse_commit(_head(mod, repo, 'main'), str(repo))
    assert commit is not None
    assert len(commit['parents']) == 2, commit
    # 前提成立：第一父**不是** dev 的祖先（否则本用例测不到方向）
    first_is_ancestor = (
        subprocess.run(['git', 'merge-base', '--is-ancestor', commit['parents'][0], 'dev'], cwd=repo).returncode == 0
    )
    assert not first_is_ancestor, '用例前提不成立：第一父竟是 dev 的祖先，测不出方向错误'
    verdict = mod.classify_commit(commit, 'dev', str(repo))
    assert verdict['kind'] == 'release', (
        f'合规发版必须判 release（看**第二父**）；取第一父会误判成 violation。实际 {verdict}'
    )
    assert verdict['merged_side'] == commit['parents'][1][:8], verdict


def test_needs_red_reads_both_layers(mod):
    """`needs_red()` 的两层判据各自**单独**就能报红（直接用 dict 钉，不靠仓库形态）。

    为什么用 dict 而不是造仓库：真实仓库里「绕过 dev 的提交」几乎必然**同时**被内容级
    （`git cherry`）抓到 —— 两层冗余。于是「只改一处判据」的变异不会被任何仓库型用例咬住
    （实测 M4 探针 MISSED）。这里把两层**各自**喂给 `needs_red`，让它们分别可被验伪。
    """
    base = {
        'left_only': 0,
        'right_only': 0,
        'left_only_jobs': [],
        'right_only_jobs': [],
        'commits_readable': True,
        'commits': [],
        'violations': [],
        'unknowns': [],
        'content': {'available': True, 'has_only_left': False},
    }
    # ① 全绿基线（防止上面三条断言把判据测成恒红）
    assert mod.needs_red(dict(base)) is False, base

    # ② **只**有提交级违规 ⇒ 红（内容级是绿的）—— 这一条单独钉住 violations 分支
    only_violation = {
        **base,
        'violations': [{'short': 'abc1234', 'subject': 'bypass', 'verdict': {'kind': 'violation'}}],
    }
    assert mod.needs_red(only_violation) is True, '提交级违规单独存在时也必须红'

    # ③ **只**有 `unknown` ⇒ 红（判不出不等于正常）
    only_unknown = {**base, 'unknowns': [{'short': 'abc1234', 'subject': '?', 'verdict': {'kind': 'unknown'}}]}
    assert mod.needs_red(only_unknown) is True, '判不出的提交必须按红灯对待'

    # ④ **只**有内容级独有 ⇒ 红（提交级是绿的）
    only_content = {**base, 'content': {'available': True, 'has_only_left': True, 'files': ['x.py']}}
    assert mod.needs_red(only_content) is True, '内容级独有单独存在时也必须红'

    # ⑤ 提交级**读不出** ⇒ 红（拿不到输入不得降级成正常）
    unreadable = {**base, 'commits_readable': False}
    assert mod.needs_red(unreadable) is True, '提交清单读不出必须红（#171）'

    # ⑥ 内容级判据**不可用** ⇒ 红
    content_broken = {**base, 'content': {'available': False, 'reason': 'git cherry 失败'}}
    assert mod.needs_red(content_broken) is True, '内容级判据不可用必须红（#171）'

    # ⑦ 合规发版（release）**不**红 —— 这是二分口径的核心，别测反了
    release_only = {
        **base,
        'left_only': 2,
        'commits': [
            {'short': 'a1', 'subject': 'release', 'verdict': {'kind': 'release'}},
            {'short': 'a2', 'subject': 'release', 'verdict': {'kind': 'release'}},
        ],
    }
    assert mod.needs_red(release_only) is False, '合规发版滞后不得报红（#179 的核心）'


# ---------------------------------------------------------------------------
# 二、分叉判定与退出码
# ---------------------------------------------------------------------------


def test_compute_counts_both_directions(mod, diverged_repo):
    res = mod.compute('main', 'dev', str(diverged_repo))
    assert res['left_only'] == 1, 'main 独有 1 个提交'
    assert res['right_only'] == 1, 'dev 独有 1 个提交'
    assert res['left_only_jobs'] == ['.cnb.yml']
    assert res['right_only_jobs'] == ['.github/workflows/cnb-github-backfill.yml']


def test_report_marks_new_shape(mod, diverged_repo):
    """`diverged_repo` 的 `main` 独有提交是**普通提交**（绕过 `dev`）⇒ 报「新形态」。

    判据二分之后报告不再用「已分叉」那个词 —— 要报的是「`left` 上有没人经 `right` 中转的东西」。
    """
    res = mod.compute('main', 'dev', str(diverged_repo))
    report = mod.build_report(res)
    assert '新形态' in report, report
    assert '普通提交' in report, report
    assert '.cnb.yml' in report
    assert 'cnb-github-backfill.yml' in report


def test_report_green_when_same_point(mod, diverged_repo):
    """两侧同一个 ref ⇒ 无独有提交、无独有内容，报告给明确绿灯（别把判据测成恒红）。"""
    same = mod.compute('dev', 'dev', str(diverged_repo))
    assert same['left_only'] == 0 and same['right_only'] == 0
    assert mod.needs_red(same) is False, f'同一个 ref 不该报红：{same}'
    report = mod.build_report(same)
    # 判据段落不得报红（页脚会提到「新形态」这个词，故断言的是**报红行**不存在）
    assert '⚠️ **检出' not in report, report
    assert '没有独有提交' in report or '两侧一致' in report, report
    # 顺带确认真正的违规仍被判出（避免上面这条把判据测成恒绿）
    res = mod.compute('main', 'dev', str(diverged_repo))
    assert mod.needs_red(res) is True
    assert '⚠️ **检出' in mod.build_report(res)


def test_merge_whose_side_is_not_dev_is_red(mod, tmp_path):
    """**合并的第二父不是 `dev` 的祖先** ⇒ 报「新形态」（`feature` → `main` 直通车，CNB #179）。

    这正是 `AGENTS.md`「PR 与 Review」禁止的形态：head 是 `feat/*`、base 却填了 `main`。
    判据只看**第二父**：取第一父（= `main` 自己的历史）会把每一笔合规发版都判成违规 —— 方向反了。
    """
    import argparse
    import os

    repo = tmp_path / 'badmerge'
    repo.mkdir()
    env = {
        'GIT_AUTHOR_NAME': 't',
        'GIT_AUTHOR_EMAIL': 't@e',
        'GIT_COMMITTER_NAME': 't',
        'GIT_COMMITTER_EMAIL': 't@e',
        'PATH': os.environ['PATH'],
    }

    def git(*args):
        subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, env=env)

    git('init', '-q', '-b', 'main')
    git('config', 'commit.gpgsign', 'false')
    (repo / 'base.txt').write_text('base\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '--no-gpg-sign', '-m', 'base')
    # dev 往前走
    git('checkout', '-q', '-b', 'dev')
    (repo / 'd.txt').write_text('d\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '--no-gpg-sign', '-m', 'dev work')
    # feature 从 dev 分出
    git('checkout', '-q', '-b', 'feature')
    (repo / 'f.txt').write_text('f\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '--no-gpg-sign', '-m', 'feature work')
    # **违规**：把 feature 直接合进 main（第二父 = feature，不是 dev 的祖先）
    git('checkout', '-q', 'main')
    git('merge', '--no-ff', '-q', '--no-gpg-sign', '-m', '合并来自 feature 的合并请求 #99', 'feature')
    # dev 再往前走一点，制造「两侧都不含对方」的形态
    git('checkout', '-q', 'dev')
    (repo / 'd2.txt').write_text('d2\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '--no-gpg-sign', '-m', 'dev work 2')

    res = mod.compute('main', 'dev', str(repo))
    kinds = {(c['verdict'] or {}).get('kind') for c in res['commits']}
    assert 'violation' in kinds, f'feature→main 的 merge 应判 violation，实际 {res["commits"]}'
    # 报告要点名那条 merge 的来路
    report = mod.build_report(res)
    assert '新形态' in report and '不是' in report, report
    args = argparse.Namespace(left='main', right='dev', cwd=str(repo), out=None, report=True, jobs_only=False)
    assert mod.run(args) == 1, '绕过 dev 的 merge 必须以退出码 1 表达'


def test_release_only_merge_is_green(mod, tmp_path):
    """**发版形态**（`main` 独有 = 一个发版 merge 节点，内容与 `dev` 完全一致）⇒ 绿、退出码 0。

    这就是 CNB `main` 在发版后的**正常长相**（2026-10-14 实测：`main` 独有 2 个发版
    merge commit，`git diff main dev` 为空）：
        旧口径「`main` 独有提交 > 0 ⇒ 分叉」会把它报成假红 —— **每发一次版红一次**，
        红却不指向任何还需动手的事。故本用例是判据从「提交数级」升级为「内容级」的**锚点**：
        它断言「提交数 > 0 **且** 退出码 0」——回退到只数提交，本用例立刻红。
    """
    import argparse
    import os

    repo = tmp_path / 'rel'
    repo.mkdir()
    env = {
        'GIT_AUTHOR_NAME': 't',
        'GIT_AUTHOR_EMAIL': 't@e',
        'GIT_COMMITTER_NAME': 't',
        'GIT_COMMITTER_EMAIL': 't@e',
        'PATH': os.environ['PATH'],
    }

    def git(*args):
        subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, env=env)

    git('init', '-q', '-b', 'dev')
    git('config', 'commit.gpgsign', 'false')
    (repo / 'a.txt').write_text('a\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '--no-gpg-sign', '-m', 'base')
    (repo / 'b.txt').write_text('b\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '--no-gpg-sign', '-m', 'feat b')
    # `main` 从 base 分出，只多一个**发版 merge 节点**（内容与 dev 一致）
    git('branch', 'main', 'HEAD~1')
    git('checkout', '-q', 'main')
    git('merge', '--no-ff', '-q', '--no-gpg-sign', '-m', '合并来自 dev 的合并请求 #177', 'dev')

    res = mod.compute('main', 'dev', str(repo))
    # 结构级：`main` 确实多出提交（旧口径会在此判「分叉」）
    assert res['left_only'] == 1, f'`main` 应有 1 个独有发版节点，实际 {res["left_only"]}'
    assert res['right_only'] == 0
    # 提交级二分：这一个独有提交是 merge、且第二父（dev）是 dev 的祖先 ⇒ release
    kinds = [(c['verdict'] or {}).get('kind') for c in res['commits']]
    assert kinds == ['release'], f'发版 merge 应判 release，实际 {res["commits"]}'
    # 内容级：`git cherry dev main` 无 `+` 行 ⇒ `main` 没有 dev 拿不到的改动
    assert res['content']['available'] is True
    assert res['content']['has_only_left'] is False, f'发版形态不该有独有内容：{res["content"]}'
    # 退出码：必须是 0（旧口径会给 1 —— 那就是假红）
    args = argparse.Namespace(left='main', right='dev', cwd=str(repo), out=None, report=True, jobs_only=False)
    assert mod.run(args) == 0, '发版 merge 节点不得判为分叉 —— 否则每发版一次假红一次'
    assert '无新形态' in mod.build_report(res)


def test_real_content_divergence_is_red(mod, tmp_path):
    """`main` 真有 `dev` 拿不到的代码 ⇒ 红、退出码 1，且报告**点名文件**（规则 1 的另一半）。

    与上一条成对：上一条防「假红」，本用例防「假绿」——判据改口径后必须两边都还咬得住。
    """
    import argparse
    import os

    repo = tmp_path / 'truediv'
    repo.mkdir()
    env = {
        'GIT_AUTHOR_NAME': 't',
        'GIT_AUTHOR_EMAIL': 't@e',
        'GIT_COMMITTER_NAME': 't',
        'GIT_COMMITTER_EMAIL': 't@e',
        'PATH': os.environ['PATH'],
    }

    def git(*args):
        subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, env=env)

    git('init', '-q', '-b', 'dev')
    git('config', 'commit.gpgsign', 'false')
    (repo / 'a.txt').write_text('a\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '--no-gpg-sign', '-m', 'base')
    # `main` 与 `dev` 从同一点各自长出**不同内容**（真双向分叉）
    git('branch', 'main')
    (repo / 'only-dev.txt').write_text('dev\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '--no-gpg-sign', '-m', 'dev adds file')
    git('checkout', '-q', 'main')
    (repo / 'only-main.txt').write_text('main\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '--no-gpg-sign', '-m', 'main adds file')

    res = mod.compute('main', 'dev', str(repo))
    # 内容级：`git cherry dev main` 必须报到 `+`，且内容级段点名文件
    assert res['content']['available'] is True
    assert res['content']['has_only_left'] is True, f'`main` 有独有提交，cherry 应报 `+`：{res["content"]}'
    report = mod.build_report(res)
    assert 'only-main.txt' in report, f'内容级段要点名 `main` 独有的路径，实际：{report}'
    assert '拿不到的改动' in report, report
    args = argparse.Namespace(left='main', right='dev', cwd=str(repo), out=None, report=True, jobs_only=False)
    assert mod.run(args) == 1, '`main` 有 `dev` 拿不到的代码 ⇒ 必须报分叉'


def test_report_flags_unavailable_judgments(mod, monkeypatch, diverged_repo):
    """拿不到 `git cherry` / `git log` ⇒ 报告**明说判据不可用**，且**退出口径不得是「正常」**（#171）。

    两层判据各自「拿不到输入」都必须显式报警：内容级不可用时 `needs_red` 为真（红），
    提交级不可用时同理。**不得**降级成一个看起来正常的结论 —— 那是 #171 的假绿。
    """
    import argparse

    real_git = mod._git

    def flaky(args, cwd=None):
        # 让 cherry（内容级）与 log（提交级清单）都取不到
        if args and args[0] in ('cherry', 'log'):
            return 1, ''
        return real_git(args, cwd)

    monkeypatch.setattr(mod, '_git', flaky)
    args = argparse.Namespace(left='main', right='dev', cwd=str(diverged_repo), out=None, report=True, jobs_only=False)
    assert mod.run(args) == 1, '判据不可用不得当作「未分叉」（#171：拿不到 ≠ 空的）'
    broken = mod.compute('main', 'dev', str(diverged_repo))
    report = mod.build_report(broken)
    assert '判据不可用' in report, report
    assert mod.needs_red(broken) is True


def test_content_only_divergence_is_red(mod, monkeypatch):
    """**交叉合并的假阳性**：内容级必须用 `git cherry`，不能靠 `git diff` + 祖先关系（#179）。

    造出「`main` 合过 `dev`、`dev` 又前进」⇒ 两侧都不是对方的祖先（`--is-ancestor` 双向 false），
    但 `main` **零独有内容**。旧实现（diff 非空 + 非祖先 ⇒ 红）会在这里**假红**；
    新实现（`git cherry` 无 `+`）必须绿。
    """
    import argparse
    import os

    repo = tmp_path = None
    import tempfile

    tmpdir = tempfile.mkdtemp()
    repo = pathlib.Path(tmpdir) / 'x'
    repo.mkdir(parents=True)
    env = {
        'GIT_AUTHOR_NAME': 't',
        'GIT_AUTHOR_EMAIL': 't@e',
        'GIT_COMMITTER_NAME': 't',
        'GIT_COMMITTER_EMAIL': 't@e',
        'PATH': os.environ['PATH'],
    }

    def git(*args):
        subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, env=env)

    git('init', '-q', '-b', 'main')
    git('config', 'commit.gpgsign', 'false')
    (repo / 'base.txt').write_text('base\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '--no-gpg-sign', '-m', 'base')
    # dev 前进
    git('checkout', '-q', '-b', 'dev')
    (repo / 'd1.txt').write_text('d1\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '--no-gpg-sign', '-m', 'dev work 1')
    # main 把 dev 合进来（合规发版）
    git('checkout', '-q', 'main')
    git('merge', '--no-ff', '-q', '--no-gpg-sign', '-m', '合并来自 dev 的合并请求 #1', 'dev')
    # dev 再前进 ⇒ 交叉合并，两侧互不含
    git('checkout', '-q', 'dev')
    (repo / 'd2.txt').write_text('d2\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '--no-gpg-sign', '-m', 'dev work 2')

    res = mod.compute('main', 'dev', str(repo))
    # 前提：确实「互不包含」（否则本用例测不到那个坑）
    assert subprocess.run(['git', 'merge-base', '--is-ancestor', 'main', 'dev'], cwd=repo).returncode == 1
    assert subprocess.run(['git', 'merge-base', '--is-ancestor', 'dev', 'main'], cwd=repo).returncode == 1
    # 且 `git diff main dev` 非空（旧实现的假阳性触发条件）
    assert subprocess.run(['git', 'diff', '--quiet', 'main', 'dev'], cwd=repo).returncode == 1
    # 关键断言：`main` 零独有内容 ⇒ 必须绿
    assert res['content']['available'] is True
    assert res['content']['has_only_left'] is False, (
        f'交叉合并下 `main` 零独有内容，cherry 不该报 `+`：{res["content"]}'
    )
    # 提交级：唯一的独有提交是合规发版 merge
    kinds = [(c['verdict'] or {}).get('kind') for c in res['commits']]
    assert kinds == ['release'], f'应判 release，实际 {res["commits"]}'
    args = argparse.Namespace(left='main', right='dev', cwd=str(repo), out=None, report=True, jobs_only=False)
    assert mod.run(args) == 0, '交叉合并 + 零独有内容 ⇒ 不得假红（#179）'


def test_run_returns_1_on_new_shape(mod, diverged_repo):
    import argparse

    args = argparse.Namespace(left='main', right='dev', cwd=str(diverged_repo), out=None, report=True, jobs_only=False)
    assert mod.run(args) == 1, '新形态必须以退出码 1 表达（供 CI 当信号）'


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
    assert mod.run(args) == 2, '取不到分支要用独立退出码，别混进「有新形态」'


# ---------------------------------------------------------------------------
# 二之二、`--explain`：答「为什么会分叉」+「发版会不会冲突」
# ---------------------------------------------------------------------------


def test_explain_lists_left_only_commits(mod, diverged_repo):
    """`main` 独有的提交要被逐个列出（短号 + 主题），人来判断来路。"""
    exp = mod.explain('main', 'dev', str(diverged_repo))
    subjects = ' '.join(c['subject'] for c in exp['commits'])
    assert 'main-only' in subjects, f'应列出 main 独有提交，实际 {exp["commits"]}'
    assert 'dev-only' not in subjects, 'dev 独有的提交不该出现在 main 的清单里'


def test_explain_clean_merge_when_fast_forward(mod, diverged_repo):
    """两边只各自加文件、不碰同一文件 ⇒ 试算应报「可干净合并」。"""
    exp = mod.explain('main', 'dev', str(diverged_repo))
    assert exp['merge_trial']['status'] == 'clean', exp['merge_trial']


def test_explain_detects_conflict(mod, tmp_path):
    """同一文件两侧都改 ⇒ 试算必须报冲突，且**指名文件**。

    这条钉的是 `merge-tree --write-tree` 的方向：`git merge-tree <A> <B>` 的语义是
    「把 B 合进 A」。发版方向是 `dev`→`main`（right→left），传反了算出来的冲突
    与发布 PR 无关 —— 而冲突文件名的输出形态（首行是 40 位 tree hash）也一并钉住：
    不滤掉那行，报告里会混进一条谁也看不懂的哈希。
    """
    import os

    repo = tmp_path / 'c'
    repo.mkdir()
    env = {
        'GIT_AUTHOR_NAME': 't',
        'GIT_AUTHOR_EMAIL': 't@e',
        'GIT_COMMITTER_NAME': 't',
        'GIT_COMMITTER_EMAIL': 't@e',
        'PATH': os.environ['PATH'],
    }

    def git(*args):
        subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, env=env)

    git('init', '-q', '-b', 'main')
    (repo / 'shared.txt').write_text('base\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '-m', 'base')

    (repo / 'shared.txt').write_text('main side\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '-m', 'main-edit')

    git('checkout', '-q', '-b', 'dev', 'HEAD~1')
    (repo / 'shared.txt').write_text('dev side\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '-m', 'dev-edit')

    exp = mod.explain('main', 'dev', str(repo))
    trial = exp['merge_trial']
    assert trial['status'] == 'conflict', f'同一文件两侧都改，必须报冲突：{trial}'
    assert 'shared.txt' in trial['conflicts'], f'冲突清单里要有文件名：{trial["conflicts"]}'
    assert not any(len(f) == 40 and all(ch in '0123456789abcdef' for ch in f) for f in trial['conflicts']), (
        f'tree hash 不该混进冲突清单：{trial["conflicts"]}'
    )


def test_merge_trial_direction_matters(mod, tmp_path):
    """**方向不对称**的场景：`dev` 侧有未提交到 `main` 的重命名 ⇒ 只有正确方向才报冲突。

    为什么单开一条：上面那条用的是**对称冲突**（同一文件两侧都改），`git merge-tree A B`
    与 `merge-tree B A` 都会报同一个文件——方向传反了也照样绿。实测探针就是这样 MISSED 的。

    本用例造**不对称**：`dev` 上把 `a.txt` 改名成 `b.txt`，`main` 上继续改 `a.txt`。
    合 `dev` 进 `main`（发版方向）⇒ 改名对改内容，**冲突**；
    合 `main` 进 `dev` ⇒ 同样冲突……故这里改用「`main` 独有一个**新增**文件、
    `dev` 把它**改名**」的形态：只有「把 dev 合进 main」才会撞上改名/新增之争。
    """
    import os

    repo = tmp_path / 'd'
    repo.mkdir()
    env = {
        'GIT_AUTHOR_NAME': 't',
        'GIT_AUTHOR_EMAIL': 't@e',
        'GIT_COMMITTER_NAME': 't',
        'GIT_COMMITTER_EMAIL': 't@e',
        'PATH': os.environ['PATH'],
    }

    def git(*args):
        subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, env=env)

    git('init', '-q', '-b', 'main')
    (repo / 'base.txt').write_text('base\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '-m', 'base')

    # main：新增 only-on-main.txt
    (repo / 'only-on-main.txt').write_text('from main\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '-m', 'main-adds-file')

    # dev：从 base 分出，把同一路径改成目录（与 main 的新增文件正面相撞）
    git('checkout', '-q', '-b', 'dev', 'HEAD~1')
    (repo / 'only-on-main.txt').mkdir()
    (repo / 'only-on-main.txt' / 'inner.txt').write_text('inner\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '-m', 'dev-turns-it-into-dir')

    trial = mod._merge_trial('main', 'dev', str(repo))
    assert trial['status'] == 'conflict', f'方向不对称场景应报冲突：{trial}'
    # git 对「改名 / 建目录」这类冲突会写成 `路径~<侧>`（这里是 `only-on-main.txt~main`），
    # 故只断言**文件名前缀存在**，不要求逐字相等。
    assert any('only-on-main.txt' in c for c in trial['conflicts']), trial['conflicts']


def test_merge_trial_call_direction_is_release_direction(mod, diverged_repo, monkeypatch):
    """钉住 `explain()` 传给 `_merge_trial` 的**参数顺序**。

    `git merge-tree <A> <B>` = 「把 B 合进 A」。发版方向是 `dev`→`main`（right→left），
    故必须调 `_merge_trial(left, right)` —— 传反了算出来的是反方向的冲突，
    与发布 PR 无关。上面那条「同一文件两侧都改」的对称场景**测不出这个错**（实测探针 MISSED），
    故这里直接记录调用参数。
    """
    seen = {}
    real = mod._merge_trial

    def spy(left, right, cwd=None):
        seen['args'] = (left, right)
        return real(left, right, cwd)

    monkeypatch.setattr(mod, '_merge_trial', spy)
    mod.explain('main', 'dev', str(diverged_repo))
    assert seen.get('args') == ('main', 'dev'), (
        f'发版方向是 dev→main（right→left），_merge_trial 必须收 (left, right)；实际 {seen.get("args")}'
    )


def test_explain_never_guesses_platform(mod, diverged_repo):
    """`--explain` **不得**猜「提交来自 GitHub 还是 CNB」。

    实测过三条路（提交信息启发式 / `refs/fetched` / `sync/mirror` 分支）都答不了这个问题：
    `feat(detail): …（#2029 卡 B）` 与 `docs(api): …（#2029 卡 B）` 同批同源、
    却没有任何标记能区分。猜错的代价是**报告指向错误的处置**（该发版的被判成纪律违规），
    比不给结论坏得多。故这里钉住「只报可证事实」。
    """
    exp = mod.explain('main', 'dev', str(diverged_repo))
    rendered = mod.build_explanation({'left': 'main', 'right': 'dev'}, exp)
    for banned in ('github-pr', 'cnb-local', 'github-issue'):
        assert banned not in rendered, f'报告不该出现平台归类标签 `{banned}`（那是猜）'


def test_explain_renders_unknown_when_no_base(mod, monkeypatch):
    """取不到 merge-base 时明写「试算不可用」，**不猜**成「无冲突」。"""
    monkeypatch.setattr(mod, '_git', lambda *a, **k: (1, ''))
    trial = mod._merge_trial('main', 'dev', None)
    assert trial['status'] == 'unknown', trial
    assert trial.get('reason')


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


def test_merge_tree_args_are_left_right(mod, monkeypatch):
    """钉住 `_merge_trial` **自己**传给 `git merge-tree` 的参数顺序。

    上一条只钉了 `explain` → `_merge_trial` 的传参；若有人在 `_merge_trial` 内部把
    `_git([... left, right])` 写成 `right, left`，那一条照样绿（实测探针 MISSED）。
    这里直接记录 `_git` 收到的参数，把方向钉死在**真正执行 git 的那一行**。

    `git merge-tree <A> <B>` = 把 B 合进 A。发版是 `dev`→`main`（right→left），
    故必须看到 `merge-tree ... left right`。
    """
    seen = {}
    real = mod._git

    def spy(args, cwd=None):
        if args and args[0] == 'merge-tree':
            seen['args'] = list(args)
        return real(args, cwd)

    monkeypatch.setattr(mod, '_git', spy)
    # CI 检出可能只有 PR ref（或浅克隆），没有 origin/main / origin/dev —— 此时
    # `_merge_trial` 在 merge-base 一步就优雅返回，根本不会调到 merge-tree（实测 CI 红灯）。
    # 与上一条用例同口径：缺 ref 就跳过，不把环境问题算成代码问题。
    code, _ = real(['merge-base', 'origin/main', 'origin/dev'], str(_REPO_ROOT))
    if code != 0:
        pytest.skip('缺 origin/main / origin/dev（CI 检出无完整 ref），无法在真实 ref 上钉参数顺序')
    # 用**本仓真实 ref**：`cwd=None` 在测试进程里不保证能解析出 main/dev。
    mod._merge_trial('origin/main', 'origin/dev', str(_REPO_ROOT))
    got = seen.get('args')
    assert got is not None, '没有调到 merge-tree'
    assert got[-2:] == ['origin/main', 'origin/dev'], f'merge-tree 的参数顺序必须是 (left, right)；实际 {got}'


# ---------------------------------------------------------------------------
# 五、交叉合并下的**删除类违规**：`git cherry` 看得见，逐文件 blob 历史看不见
#     （PR #181 冲突复盘，源 CNB #179）
# ---------------------------------------------------------------------------


def _mk_cross_merge_repo(tmp_path, name):
    """造「交叉合并 + `left` 上纯删除」的仓库——本仓 #179 实测那种形态。

        base ── main: merge dev ── main: 删除 a.txt（违规，绕过 dev）
                 └─ dev: 加 d.txt ── dev: 再加 e.txt

    合并之后 `main` 与 `dev` **互不包含**（都不是对方的祖先），`git diff` 也非空。
    """
    import os

    repo = tmp_path / name
    repo.mkdir()
    env = {
        'GIT_AUTHOR_NAME': 't',
        'GIT_AUTHOR_EMAIL': 't@e',
        'GIT_COMMITTER_NAME': 't',
        'GIT_COMMITTER_EMAIL': 't@e',
        'PATH': os.environ['PATH'],
    }

    def git(*args):
        subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, env=env)

    git('init', '-q', '-b', 'main')
    (repo / 'a.txt').write_text('v1\n', encoding='utf-8')
    (repo / 'keep.txt').write_text('keep\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '-m', 'base')

    git('checkout', '-q', '-b', 'dev')
    (repo / 'd.txt').write_text('dev\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '-m', 'dev-adds-d')

    main_side = subprocess.run(['git', 'rev-parse', 'dev'], cwd=repo, capture_output=True, text=True).stdout.strip()
    git('checkout', '-q', 'main')
    git('merge', '-q', '--no-ff', main_side, '-m', 'release: merge dev')

    # 违规：在 main 上**直接删掉** a.txt（`dev` 里它还在）
    git('rm', '-q', 'a.txt')
    git('commit', '-q', '-m', 'violation: 绕过 dev 在 main 上删文件')

    # dev 再往前走 ⇒ 两侧互不包含
    git('checkout', '-q', 'dev')
    (repo / 'e.txt').write_text('more\n', encoding='utf-8')
    git('add', '.')
    git('commit', '-q', '-m', 'dev-adds-e')
    return repo


def test_cross_merge_deletion_on_left_is_red(mod, tmp_path):
    """交叉合并下 `left` 上的**纯删除**必须报红 —— 这是逐文件 blob 法的盲区。

    实测（PR #181 冲突复盘）：另一版实现遍历 `git diff --name-only` 的路径、再查
    「`left` 侧该 blob 在 `right` 历史里出现过吗」。它只处理 `left` 侧**存在**的路径，
    删除侧（`left:{path}` 解析失败）被 `continue` 跳过 ⇒ 给出「✅ 两侧内容一致」**假绿**。

    本仓的判据是 `git cherry`（补丁等价），以**补丁**为单位，没有这个盲区。
    这条用例把结论钉死在行为上：删一个 `right` 里还在的文件，**必须**是红灯。
    """
    repo = _mk_cross_merge_repo(tmp_path, 'del')
    # 前提校验：确实是「互不包含」，才有意义
    left_is_anc = subprocess.run(['git', 'merge-base', '--is-ancestor', 'main', 'dev'], cwd=repo).returncode == 0
    right_is_anc = subprocess.run(['git', 'merge-base', '--is-ancestor', 'dev', 'main'], cwd=repo).returncode == 0
    assert not left_is_anc and not right_is_anc, '本用例要求互不包含的交叉合并形态'

    res = mod.compute('main', 'dev', str(repo))
    content = res['content']
    assert content['available'], content
    assert content['has_only_left'], f'`main` 上那条删除是 `dev` 拿不到的改动，必须报红：{content}'
    assert 'a.txt' in content['files'], f'要点名被删的路径：{content["files"]}'
    assert mod.needs_red(res) is True, '纯删除是违规，必须判红'


def test_content_ahead_uses_cherry_not_diff(mod, tmp_path, monkeypatch):
    """钉住内容级判据**确实**调的是 `git cherry`，不是 `git diff` / `--find-object`。

    为什么单开一条：上面那条只证明「结论对」，但**换个实现也可能碰巧对**。
    这里直接记录 `_git` 收到的参数，把判据的形态钉在**真正执行 git 的那一行**
    ——「判据必须有失败态」，换成 `diff` 或逐文件 blob 历史即失败。
    """
    seen = []
    real = mod._git

    def spy(args, cwd=None):
        seen.append(list(args))
        return real(args, cwd)

    monkeypatch.setattr(mod, '_git', spy)
    repo = _mk_cross_merge_repo(tmp_path, 'spy')
    mod.content_ahead('main', 'dev', str(repo))

    assert any(a and a[0] == 'cherry' for a in seen), f'内容级判据必须调 `git cherry`，实际调用：{seen}'
    assert not any('--find-object' in ' '.join(a) for a in seen), '不得退回逐文件 blob 历史（交叉合并下漏报删除）'
