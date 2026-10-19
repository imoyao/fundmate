# -*- coding: utf-8 -*-
"""`scripts/bridge/ffback_cnb_dev.py` 的回归网（源 CNB #601）。

被测的是**回向快进**那一步：GitHub `dev` → CNB `dev`，只 FF、永不 force。
这里用**真的 git 仓**（两个 bare + 两个工作仓）跑端到端，因为被测逻辑的绝大部分
就是 git 本身（fetch / merge-base --is-ancestor / push 的快进判定）——
用 mock 替掉 git，等于把最该验的东西替掉。

覆盖：
  ① 两侧一致 ⇒ rc 0；② GitHub 单侧领先 + dry-run ⇒ rc 0 且**没推**；
  ③ `--apply` ⇒ CNB `dev` 真的前进到 GitHub sha；④ 真双向分叉 ⇒ rc 1 且**没推**；
  ⑤ 拿不到输入 ⇒ rc 2（**不是** 0）；⑥ CNB 单侧领先 ⇒ rc 0 且没推；
  ⑦ 推送被拒 ⇒ rc 3（**不是** 1——两者处置不同：分叉要人来合，推不上去要人去开权限）。

变异探针（本文件末尾有实测记录）：
  把 `plan()` 里 `diverged` 那一支改成返回 `'ff'`，则 `test_真分叉_*` 必须转红
  —— 若不红，说明这组用例没有真的咬住「互不包含 ≠ 可快进」这条判据。
"""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BRIDGE_DIR = _REPO_ROOT / 'scripts' / 'bridge'
_SCRIPT_PATH = _BRIDGE_DIR / 'ffback_cnb_dev.py'

_MOD = None


def _load():
    global _MOD
    if _MOD is None:
        bridge = str(_BRIDGE_DIR)
        if bridge not in sys.path:
            sys.path.insert(0, bridge)
        spec = importlib.util.spec_from_file_location('ffback_cnb_dev', _SCRIPT_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules['ffback_cnb_dev'] = module
        spec.loader.exec_module(module)
        _MOD = module
    return _MOD


@pytest.fixture()
def m():
    return _load()


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(['git', *args], cwd=repo, capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert r.returncode == 0, f'git {args} 失败：{r.stderr}'
    return (r.stdout or '').strip()


def _try_git(repo: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(['git', *args], cwd=repo, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, ((r.stdout or '') + (r.stderr or '')).strip()


def _init_work(path: Path) -> Path:
    path.mkdir()
    _git(path, 'init', '-q', '-b', 'dev')
    _git(path, 'config', 'user.email', 't@example.com')
    _git(path, 'config', 'user.name', 't')
    _git(path, 'config', 'commit.gpgsign', 'false')
    _git(path, 'config', 'tag.gpgsign', 'false')
    return path


def _commit(repo: Path, filename: str, content: str, message: str) -> str:
    (repo / filename).write_text(content, encoding='utf-8')
    _git(repo, 'add', '-A')
    _git(repo, 'commit', '-m', message)
    return _git(repo, 'rev-parse', 'HEAD')


def _remote_sha(bare: Path) -> str:
    return _git(bare, 'rev-parse', 'refs/heads/dev')


@pytest.fixture()
def world(tmp_path: Path) -> SimpleNamespace:
    """两个 bare 仓（`cnb` / `github`）+ 一个本地工作仓，三者的 `dev` 起初指向同一提交。"""
    cnb = tmp_path / 'cnb.git'
    gh = tmp_path / 'github.git'
    for bare in (cnb, gh):
        bare.mkdir()
        _git(bare, 'init', '-q', '--bare', '-b', 'dev')

    work = _init_work(tmp_path / 'work')
    base = _commit(work, 'a.txt', 'base\n', 'chore: base')
    _git(work, 'remote', 'add', 'cnb', str(cnb))
    _git(work, 'remote', 'add', 'gh', str(gh))
    _git(work, 'push', '-q', 'cnb', 'dev')
    _git(work, 'push', '-q', 'gh', 'dev')
    assert _remote_sha(cnb) == _remote_sha(gh) == base

    return SimpleNamespace(cnb=cnb, gh=gh, work=work, base=base, tmp=tmp_path)


def _args(world: SimpleNamespace, apply: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        apply=apply,
        cnb_url=str(world.cnb),
        github_url=str(world.gh),
        branch='dev',
        cwd=str(world.work),
    )


def _gh_ahead(world: SimpleNamespace) -> str:
    """在 GitHub 侧加一笔（只有 GitHub 有）—— 这是最常见的「该回向」形态。"""
    clone = world.tmp / 'ghwork'
    _git(world.tmp, 'clone', '-q', str(world.gh), str(clone))
    _git(clone, 'config', 'user.email', 't@example.com')
    _git(clone, 'config', 'user.name', 't')
    sha = _commit(clone, 'gh.txt', 'gh\n', 'feat: GitHub 侧新一笔')
    _git(clone, 'push', '-q', 'origin', 'dev')
    return sha


def _cnb_ahead(world: SimpleNamespace) -> str:
    sha = _commit(world.work, 'cnb.txt', 'cnb\n', 'feat: CNB 侧新一笔')
    _git(world.work, 'push', '-q', 'cnb', 'dev')
    return sha


def test_两侧一致_rc0_且不推送(m, world, capsys):
    assert m.run(_args(world, apply=True)) == 0
    out = capsys.readouterr().out
    assert 'FFBACK_DECISION=same' in out
    assert _remote_sha(world.cnb) == world.base


def test_github_单侧领先_dry_run_rc0_且不推送(m, world, capsys):
    gh_sha = _gh_ahead(world)
    assert m.run(_args(world, apply=False)) == 0
    out = capsys.readouterr().out
    assert 'FFBACK_DECISION=ff' in out
    assert '未推送' in out
    # 关键：dry-run 不能改远端
    assert _remote_sha(world.cnb) == world.base != gh_sha


def test_apply_把_CNB_dev_快进到_GitHub_sha(m, world, capsys):
    gh_sha = _gh_ahead(world)
    assert m.run(_args(world, apply=True)) == 0
    assert '已把 CNB' in capsys.readouterr().out
    assert _remote_sha(world.cnb) == gh_sha


def test_真分叉_rc1_且不推送(m, world, capsys):
    _gh_ahead(world)
    cnb_sha = _cnb_ahead(world)
    gh_sha = _remote_sha(world.gh)
    assert m.run(_args(world, apply=True)) == 1
    out = capsys.readouterr().out
    assert 'FFBACK_DECISION=diverged' in out
    assert 'dev_converge.py' in out
    # 真分叉时两侧都不许动
    assert _remote_sha(world.cnb) == cnb_sha
    assert _remote_sha(world.gh) == gh_sha


def test_cnb_单侧领先_rc0_且不推送(m, world, capsys):
    cnb_sha = _cnb_ahead(world)
    assert m.run(_args(world, apply=True)) == 0
    out = capsys.readouterr().out
    assert 'FFBACK_DECISION=cnb_ahead' in out
    assert _remote_sha(world.cnb) == cnb_sha


def test_拿不到输入_rc2_而不是_rc0(m, world, capsys):
    """#171 的失败态纪律：拉不到 ≠ 已对齐。"""
    args = _args(world, apply=True)
    args.github_url = str(world.tmp / '不存在.git')
    assert m.run(args) == 2
    err = capsys.readouterr().err
    assert '结论不可信' in err


def test_两侧输入源同仓_rc2_且不推送(m, world, capsys):
    """#269 §附 那条假绿：`--cnb-url` 默认取 origin，而本地克隆的 origin 常指 GitHub。  # cross-repo-ref-allow

    两侧都从 GitHub 拉 ⇒ sha 必然一致 ⇒ 打印「无需回向」。**结论是反的且看不出错**，
    所以必须在比 sha 之前就挡掉（rc 2 = 结论不可信）。
    """
    args = _args(world, apply=True)
    args.cnb_url = args.github_url = str(world.gh)
    assert m.run(args) == 2
    err = capsys.readouterr().err
    assert '同一个仓库' in err
    assert '结论不可信' in err
    assert _remote_sha(world.gh) == world.base


def test_normalize_remote_同仓不同写法归一到一起(m):
    same = [
        'https://cnb.cool/duoduobei/fundmate.git',
        'https://cnb.cool/duoduobei/fundmate',
        'https://user:token@cnb.cool/duoduobei/fundmate.git',
        'git@cnb.cool:duoduobei/fundmate.git',
    ]
    assert len({m.normalize_remote(u) for u in same}) == 1
    assert m.normalize_remote('https://github.com/imoyao/fundmate.git') == 'github.com/imoyao/fundmate'


def test_推送被拒_rc3_且不改远端(m, world, capsys, monkeypatch):
    """目标仓只读（模拟「构建身份无写权限」）时，rc 必须是 3，且不能声称成功。"""
    gh_sha = _gh_ahead(world)
    monkeypatch.setattr(m, 'push_fast_forward', lambda *a, **k: (1, '', 'remote: Permission denied'))
    assert m.run(_args(world, apply=True)) == 3
    err = capsys.readouterr().err
    assert '回向推送被拒' in err
    assert _remote_sha(world.cnb) == world.base
    assert _remote_sha(world.gh) == gh_sha


def test_plan_四种形态_需要两侧对象都在本地(m, world):
    """判据本身：`same` / `ff` / `cnb_ahead` / `diverged`。

    ⚠️ 前提是**两侧 sha 的对象都在本地**（`run()` 的正常路径先 fetch 再判）。
    对象不在本地时判出来的是 `unknown`（见 `test_plan_互不包含判_diverged` 的第一条断言）——
    那是有意的：「读不到」不等于「不是祖先」。
    """
    gh_sha = _gh_ahead(world)
    assert m.fetch_branch(str(world.gh), 'dev', m.GH_REF, str(world.work))[0]
    assert m.plan(world.base, world.base, str(world.work)) == 'same'
    assert m.plan(world.base, gh_sha, str(world.work)) == 'ff'
    assert m.plan(gh_sha, world.base, str(world.work)) == 'cnb_ahead'
    cnb_sha = _cnb_ahead(world)  # 在 work 上加一笔 ⇒ 对象本地就有
    assert m.plan(cnb_sha, gh_sha, str(world.work)) == 'diverged'


def test_plan_互不包含判_diverged(m, world):
    gh_sha = _gh_ahead(world)
    cnb_sha = _cnb_ahead(world)
    assert m.plan(cnb_sha, gh_sha, str(world.work)) == 'unknown'  # gh_sha 还没 fetch 进 work
    # fetch 两侧后（run() 的正常路径）才判得出「真分叉」
    args = _args(world, apply=False)
    assert m.fetch_branch(args.cnb_url, 'dev', m.CNB_REF, str(world.work))[0]
    assert m.fetch_branch(args.github_url, 'dev', m.GH_REF, str(world.work))[0]
    assert m.plan(cnb_sha, gh_sha, str(world.work)) == 'diverged'


def _real_git(args, cwd=None):
    r = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, (r.stdout or '').strip(), (r.stderr or '').strip()


def test_读不到对象时走_unknown_而不是当成不是祖先(m, world, capsys):
    """#171 的失败态纪律：对象缺失（`git` 退 128）必须走 `unknown` ⇒ rc 2，而不是 rc 0。"""
    assert m.plan('0' * 40, world.base, str(world.work)) == 'unknown'
    args = _args(world, apply=True)
    # 把 rev-parse 的结果打空，模拟「fetch 成功但解不出 sha」
    monkey = pytest.MonkeyPatch()
    monkey.setattr(m, '_git', lambda a, c=None: (0, '', '') if a[:1] == ['rev-parse'] else _real_git(a, c))
    try:
        assert m.run(args) == 2
    finally:
        monkey.undo()
    assert '结论不可信' in capsys.readouterr().err


def test_不带任何_force_参数(m):
    """判据硬化：回向**永不 force**（这是本脚本存在的全部意义）。

    只看**函数体的代码**（`ast` 解析后剔掉 docstring）——docstring 里解释「为什么不要 force」
    的文字是说明，不是命令。
    """
    import ast
    import inspect

    src = inspect.getsource(m.push_fast_forward)
    fn = ast.parse(src).body[0]
    code_nodes = [
        n
        for n in fn.body
        if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))
    ]
    code = '\n'.join(ast.unparse(n) for n in code_nodes)
    assert '--force' not in code
    assert "'-f'" not in code
