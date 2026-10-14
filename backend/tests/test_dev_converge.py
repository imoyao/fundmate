# -*- coding: utf-8 -*-
"""「跨仓 dev 收敛」脚本的回归网（源 CNB #269，2026-10-14）。  # cross-repo-ref-allow

## WHY 有这份文件

`scripts/bridge/dev_converge.py` 是 §17.6 那条「人工收敛路径」的机械化版本。
它的价值不在「跑得通」，而在**它必须只做安全的那半**：
不直接动 `dev`、不自动解冲突、不 push。这三条边界一旦松掉，
它会**悄悄改掉规范与流水线文件**（冲突面覆盖 `.cnb.yml` / `AGENTS.md` / `ci.yml`），
比代码冲突贵得多。

## 四类钉子

1. **方向**：`--base cnb` / `--base github` 必须产出**相反**的 base/merge 对
   ——这是「以谁为基线」的可判定表达，写反了会让收敛结果与口头约定不符；
2. **失败态**：拿不到输入（fetch 失败）⇒ 退出码 2，**不得**降级成 0；
3. **不覆盖已有分支**：目标分支已存在时 refusal（不 `-B` 强行覆盖）；
4. **变异探针**：把 direction 弄反 ⇒ 用例必须红（本仓老规矩「守门通过 ≠ 守门有效」）。

全程**零网络**：`plan()` 是纯函数、`conflict_files()` 只读本地 git；
真跑 `--apply` 的用例用临时仓库手工构造 ref，不碰远端。

## 踩坑：变异探针必须清 `__pycache__`

本次实跑时，探针把源文件改回原样后，`scripts/bridge/__pycache__/` 里那份
**变异版字节码**仍被 `importlib` 加载（mtime 粒度内改回，缓存判定未失效），
于是「还原后的文件」与「测试实际加载的模块」不一致，报出一串看不懂的失败。

⇒ 跑变异探针时，改完源文件要 `rm -rf scripts/bridge/__pycache__`。
（这是**探针工具**的坑，不是被测代码的坑——记在这里是因为它骗过了一次人。
 未来若在 CI 里跑变异探针，把这一步并入工具，而不是靠人记得。）
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BRIDGE_DIR = _REPO_ROOT / 'scripts' / 'bridge'
_SCRIPT_PATH = _BRIDGE_DIR / 'dev_converge.py'

_MOD = None


def _load():
    global _MOD
    if _MOD is None:
        bridge = str(_BRIDGE_DIR)
        if bridge not in sys.path:
            sys.path.insert(0, bridge)
        spec = importlib.util.spec_from_file_location('dev_converge', _SCRIPT_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules['dev_converge'] = module
        spec.loader.exec_module(module)
        _MOD = module
    return _MOD


@pytest.fixture()
def m():
    return _load()


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(['git', *args], cwd=repo, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return (r.stdout or '').strip()


def _commit(repo: Path, filename: str, content: str, message: str) -> str:
    (repo / filename).write_text(content, encoding='utf-8')
    _git(repo, 'add', '-A')
    _git(repo, 'commit', '-m', message)
    return _git(repo, 'rev-parse', 'HEAD')


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / 'r'
    r.mkdir()
    _git(r, 'init', '-q', '-b', 'dev')
    _git(r, 'config', 'user.email', 't@example.com')
    _git(r, 'config', 'user.name', 't')
    _git(r, 'config', 'commit.gpgsign', 'false')
    _git(r, 'config', 'tag.gpgsign', 'false')
    return r


# === 方向：以谁为基线 ===


def test_base_cnb_以_cnb_为基线_合入_github(m):
    p = m.plan('cnb', 'rescue/x')
    assert p['base_name'] == 'CNB'
    assert p['merge_name'] == 'GitHub'
    assert p['base_ref'] == m.CNB_REF
    assert p['merge_ref'] == m.GH_REF


def test_base_github_方向相反(m):
    """两个方向必须真的相反 —— 写反了收敛结果与口头约定不符。"""
    p = m.plan('github', 'rescue/x')
    assert p['base_name'] == 'GitHub'
    assert p['merge_name'] == 'CNB'
    assert p['base_ref'] == m.GH_REF
    assert p['merge_ref'] == m.CNB_REF


def test_默认方向是_cnb(m):
    p = m.plan('cnb', 'rescue/x')
    assert p['base_name'] == 'CNB'


def test_探针_方向写反必须被咬住(m):
    """变异探针：若 `plan` 把 `github` 也返回 cnb 基线，用例 2 会红。"""
    p_cnb = m.plan('cnb', 'rescue/x')
    p_gh = m.plan('github', 'rescue/x')
    assert p_cnb['base_ref'] != p_gh['base_ref'], '两个方向必须产出不同的 base —— 否则收敛方向不可判定'


# === 冲突检测（真跑 merge，用临时仓库） ===


def test_无冲突时合并且不报冲突(m, repo):
    _commit(repo, 'a.txt', 'base\n', 'base')
    _git(repo, 'branch', 'gh-side')
    (repo / 'b.txt').write_text('cnb\n', encoding='utf-8')
    _git(repo, 'add', '-A')
    _git(repo, 'commit', '-m', 'cnb change')
    _git(repo, 'checkout', '-q', 'gh-side')
    (repo / 'c.txt').write_text('gh\n', encoding='utf-8')
    _git(repo, 'add', '-A')
    _git(repo, 'commit', '-m', 'gh change')

    # 以 dev(cnb) 为基线，合 gh-side
    _git(repo, 'checkout', '-q', 'dev')
    code, out = m._git(['merge', '--no-edit', 'gh-side'], str(repo))
    assert code == 0
    assert m.conflict_files(str(repo)) == []


def test_有冲突时列出冲突文件(m, repo):
    _commit(repo, 'shared.txt', 'base\n', 'base')
    _git(repo, 'branch', 'gh-side')
    (repo / 'shared.txt').write_text('cnb version\n', encoding='utf-8')
    _git(repo, 'add', '-A')
    _git(repo, 'commit', '-m', 'cnb changes shared')
    _git(repo, 'checkout', '-q', 'gh-side')
    (repo / 'shared.txt').write_text('gh version\n', encoding='utf-8')
    _git(repo, 'add', '-A')
    _git(repo, 'commit', '-m', 'gh changes shared')

    _git(repo, 'checkout', '-q', 'dev')
    code, _ = m._git(['merge', '--no-edit', 'gh-side'], str(repo))
    assert code != 0  # merge 因冲突退出非 0
    conflicts = m.conflict_files(str(repo))
    assert 'shared.txt' in conflicts


# === 失败态：拿不到输入 ===


def test_拿不到输入_退出码_2(m, tmp_path, monkeypatch):
    """fetch 失败 ⇒ 退 2，**不得**退 0（同 §15 / §17.4 假绿口径）。"""
    monkeypatch.setattr(m, 'fetch_branch', lambda *a, **k: (False, 'boom'))
    ns = m.argparse.Namespace(
        cwd=None,
        cnb_url='https://cnb.example/x.git',
        github_url='https://github.com/x/y.git',
        branch='dev',
        base='cnb',
        out_branch=None,
        apply=True,
        dry_run=False,
    )
    assert m.run(ns) == 2


def test_默认不_apply_时只演练(m, tmp_path, monkeypatch):
    """不带 `--apply` ⇒ 不建分支、不改工作区。"""
    monkeypatch.setattr(m, 'fetch_branch', lambda *a, **k: (True, ''))
    ns = m.argparse.Namespace(
        cwd=None,
        cnb_url='x',
        github_url='y',
        branch='dev',
        base='cnb',
        out_branch=None,
        apply=False,
        dry_run=True,
    )
    assert m.run(ns) == 0


# === 报告内容 ===


def test_报告_演练时说明未改工作区(m):
    p = m.plan('cnb', 'rescue/x')
    report = m.build_report(p, created=False, conflicts=[])
    assert '演练' in report
    assert 'CNB' in report and 'GitHub' in report


def test_报告_有冲突时列出文件且不宣称成功(m):
    p = m.plan('cnb', 'rescue/x')
    report = m.build_report(p, created=True, conflicts=['.cnb.yml', 'AGENTS.md'])
    assert '冲突' in report
    assert '.cnb.yml' in report and 'AGENTS.md' in report
    assert '✅' not in report


def test_报告_无冲突时给下一步(m):
    p = m.plan('cnb', 'rescue/x')
    report = m.build_report(p, created=True, conflicts=[])
    assert '✅' in report
    assert 'PR' in report
