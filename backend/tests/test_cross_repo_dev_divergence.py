# -*- coding: utf-8 -*-
"""「CNB dev ↔ GitHub dev 双向分叉」自检的回归网（源 CNB #269，2026-10-14）。  # cross-repo-ref-allow

## WHY 有这份文件

`scripts/bridge/check_cross_repo_dev_divergence.py` 判的是**跨仓**一件事：
CNB 的 `dev` 与 GitHub 的 `dev` 是不是**各自握有对方没有的改动**。

这个判据的价值不在「它算得对」，而在**它必须真的会红**。2026-10-11 ~ 10-14 三天里
两侧 `dev` 分叉到 30 vs 89，**一个信号都没有**——因为当时的自检（`#123` 的
`check_branch_divergence.py`）只比**同一个仓库内部**的 `main ← dev`，
「另一半在另一个仓库」这件事**根本问不出来**。补上网的同时若不钉住它，
下一个人把 `diverged = cnb_ahead and gh_ahead` 改成 `or`（看起来更"严格"），
就会把「正常的一侧领先」也报成红 —— 红灯随即失去可信度。

## 四类钉子

1. **正向**：两侧都有 `+` ⇒ `diverged=True`、退出码 1；
2. **反向（最要紧）**：只有一侧有 `+`（正常落后）⇒ `diverged=False`、退出码 0
   ——**这是判据的失败态，写错方向会变成「每天都喊狼来了」**；
3. **拿不到输入**：fetch 失败 / ref 缺失 ⇒ `available=False` 且**不得**判成未分叉；
4. **变异探针**：把 `and` 改成 `or`、把 `available` 检查删掉 ⇒ 必须有对应用例转红
   （本仓老规矩「守门通过 ≠ 守门有效」）。

全程**零网络**：用临时 git 仓库手工构造 ref 来喂 `divergence()` 的纯函数部分；
`build_report()` 只吃 dict，不碰 git。
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BRIDGE_DIR = _REPO_ROOT / 'scripts' / 'bridge'
_SCRIPT_PATH = _BRIDGE_DIR / 'check_cross_repo_dev_divergence.py'

_MOD = None


def _load():
    """按路径加载脚本模块（须把 bridge 目录加进 sys.path，它 import 同目录的 check_branch_divergence）。"""
    global _MOD
    if _MOD is None:
        bridge = str(_BRIDGE_DIR)
        if bridge not in sys.path:
            sys.path.insert(0, bridge)
        spec = importlib.util.spec_from_file_location('check_cross_repo_dev_divergence', _SCRIPT_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules['check_cross_repo_dev_divergence'] = module
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
    _git(r, 'config', 'commit.gpgsign', 'false')  # 本机可能全局开着签名，测试仓库必须关掉
    _git(r, 'config', 'tag.gpgsign', 'false')
    return r


def test_两侧各握对方没有的改动_判双向分叉(m, repo):
    """正向：真双向分叉 ⇒ diverged=True（这是要报的形态）。"""
    base = _commit(repo, 'a.txt', 'base\n', 'base')
    _git(repo, 'branch', 'side-a')
    # 两侧从同一点各自前进，且不再有共同后续
    _git(repo, 'checkout', '-q', 'side-a')
    _commit(repo, 'a.txt', 'cnb change\n', 'cnb only')
    _commit(repo, 'b.txt', 'cnb 2\n', 'cnb only 2')
    _git(repo, 'checkout', '-q', 'dev')
    _git(repo, 'checkout', '-q', '-b', 'side-b', base)
    _commit(repo, 'c.txt', 'gh change\n', 'gh only')

    res = m.divergence('side-a', 'side-b', 'side-a', 'side-b', str(repo))
    assert res['available'] is True
    assert res['cnb_ahead'] is True and res['gh_ahead'] is True
    assert res['diverged'] is True
    assert len(res['cnb_only']) == 2  # 两笔补丁 GitHub 都没有
    assert len(res['gh_only']) == 1


def test_只有一侧领先_不算分叉(m, repo):
    """反向（判据的失败态）：GitHub 先走了、CNB 只是落后 ⇒ **不红**。

    写错方向（`and` → `or`）会把这种正常态天天报红，红灯随即失去可信度。
    """
    base = _commit(repo, 'a.txt', 'base\n', 'base')
    _git(repo, 'branch', 'behind')
    _commit(repo, 'a.txt', 'ahead\n', 'gh only')
    _commit(repo, 'b.txt', 'ahead 2\n', 'gh only 2')

    # CNB 侧停在 base（落后），GitHub 侧领先 2 笔
    res = m.divergence('behind', 'dev', 'behind', 'dev', str(repo))
    assert res['available'] is True
    assert res['cnb_ahead'] is False
    assert res['gh_ahead'] is True
    assert res['diverged'] is False  # ← 正常落后，不红


def test_内容一致_不算分叉(m, repo):
    _commit(repo, 'a.txt', 'base\n', 'base')
    _git(repo, 'branch', 'same')
    res = m.divergence('same', 'dev', 'same', 'dev', str(repo))
    assert res['available'] is True
    assert res['diverged'] is False


def test_拿不到输入_不得判成未分叉(m, repo):
    """`#171` / `#269` 的假绿形态：ref 不存在时 `git cherry` 失败 ⇒ available=False。

    **不得**返回「未分叉」——「空」与「没拿到」必须分开。
    """
    _commit(repo, 'a.txt', 'base\n', 'base')
    res = m.divergence('dev', 'dev', 'dev', 'no-such-ref', str(repo))
    assert res['available'] is False
    assert res['diverged'] is False  # 由 available 区分，调用方据 available 返回 2


def test_报告_真分叉时给出两侧笔数(m):
    report = m.build_report(
        {
            'available': True,
            'cnb_sha': 'af8750e0deadbeef',
            'gh_sha': 'eb9c9bbacafebabe',
            'cnb_only': ['a'] * 30,
            'gh_only': ['b'] * 89,
            'cnb_ahead': True,
            'gh_ahead': True,
            'diverged': True,
        }
    )
    assert '双向分叉' in report
    assert '30' in report and '89' in report


def test_报告_单侧领先时明确说不分叉(m):
    report = m.build_report(
        {
            'available': True,
            'cnb_sha': 'x' * 12,
            'gh_sha': 'y' * 12,
            'cnb_only': [],
            'gh_only': ['b'] * 3,
            'cnb_ahead': False,
            'gh_ahead': True,
            'diverged': False,
        }
    )
    assert '未分叉' in report
    assert '双向分叉' not in report


def test_报告_拿不到输入时结论不可信(m):
    report = m.build_report({'available': False})
    assert '不可信' in report
    # 不得给出「一切正常」的结论（✅ 是正常态的标记）
    assert '✅' not in report


# === 变异探针：确认守门真的会红（不是写好看而已） ===


def test_探针_and_改_or_必须被这条用例咬住(m, repo):
    """把 `diverged = cnb_ahead and gh_ahead` 改成 `or` ⇒ 「单侧领先」被误报成红。

    探针方式：不真的改文件，而是直接复算同一组输入下 `or` 的结论，断言它与用例 2 相反。
    """
    base = _commit(repo, 'a.txt', 'base\n', 'base')
    _git(repo, 'branch', 'behind')
    _commit(repo, 'a.txt', 'ahead\n', 'gh only')

    res = m.divergence('behind', 'dev', 'behind', 'dev', str(repo))
    # 正确判据（and）
    assert res['diverged'] is False
    # 变异判据（or）会得出 True —— 证明「单侧领先」这个输入确实能区分两种实现
    assert (res['cnb_ahead'] or res['gh_ahead']) is True, '探针失效：该输入无法区分 and/or'


def test_探针_删掉_available_检查必须被这条用例咬住(m, repo):
    """删掉 `if not available: return available=False` ⇒ 拿不到输入时会被算成未分叉（假绿）。"""
    _commit(repo, 'a.txt', 'base\n', 'base')
    res = m.divergence('dev', 'dev', 'dev', 'no-such-ref', str(repo))
    # 正确实现：available 为假 ⇒ 调用方返回 2
    assert res['available'] is False
    # 变异实现（不看 available，只看 diverged）会把它当「未分叉」放行
    assert res['diverged'] is False, '探针失效'
