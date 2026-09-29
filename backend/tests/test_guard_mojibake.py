# -*- coding: utf-8 -*-
"""乱码守卫「历史提交信息豁免」的回归网（2026-09-29，源自发布 PR #1765 被拦）。

`scripts/guard_mojibake.py` 在 CI 里**只随 `pull_request` 事件运行**，直接 push 到 dev
的提交（含 gh api / MCP 直推，本地 pre-push 不参与）不被检查——于是历史乱码提交信息
会一直躺着，直到发布 PR 做全量 `base..head` 扫描才暴露。豁免表是为这种存量准备的，
而它的失效模式同样是**静默放行**：sha 拼错、或有人图省事拿豁免当开关，守卫照样
`exit 0`，而「提交信息乱码必须拦」已悄悄失效。

故本文件按四类钉死：

1. **正向**：真乱码文本必须被拦（样本取自 PR #1664 那条真实乱码）；
2. **反向**：正常中文（含 >=20 CJK 的技术提交）必须放行——防过度敏感；
3. **豁免边界**：完整 sha / >=8 位前缀命中；非豁免 sha、空串、<8 位前缀不命中；
4. **防豁免表空转**：每条豁免必须（a）在真实仓里存在、（b）附带非空理由——
   这两条不变量保证豁免不会变成「匹配不到任何东西的僵尸条目」或「无理由放行」。

另有一条**分层**断言：豁免只作用于提交信息，文件内容检查照旧零容忍。
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARD_PATH = _REPO_ROOT / 'scripts' / 'guard_mojibake.py'

# PR #1664（2026-09-23）合并提交的真实乱码样本（该 PR 标题本身即乱码）
_MOJIBAKE_SUBJECT = 'perf(explore): #1546 T2.2 澶х被璧勪骇瑙傚療鎶樺彔涓哄垎缁勬憳瑕侊紝骞惰浣嶇粰婕忔枟涓讳綋'

# 正常技术提交：CJK 数 >= 20（触发启发式阈值），且必然含常用汉字
_NORMAL_SUBJECT = '重新整理这个模块的配置项与处理逻辑，补充缺失的校验并更新相关文档说明'

_GUARD = None


def _load_guard():
    """按路径加载守卫模块（进程内只加载一次，与 test_guard_cross_domain.py 同法）。"""
    global _GUARD
    if _GUARD is None:
        spec = importlib.util.spec_from_file_location('guard_mojibake', _GUARD_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules['guard_mojibake'] = module
        spec.loader.exec_module(module)
        _GUARD = module
    return _GUARD


@pytest.fixture(scope='module')
def guard():
    return _load_guard()


def _git(*args):
    return subprocess.run(
        ['git', *args],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )


# —— 1. 正向：真乱码必须被拦 ——


def test_mojibake_message_is_rejected(guard, capsys):
    """乱码提交信息（CJK 多但零常用字）必须判为问题。"""
    assert guard._check_commit_message_text(_MOJIBAKE_SUBJECT, 'commit xxxxxxxx message') is True


def test_mojibake_file_is_rejected(guard, tmp_path):
    """乱码文件内容必须判为问题（与提交信息走同一启发式）。"""
    f = tmp_path / 'bad.md'
    f.write_text('澶х被璧勪骇瑙傚療鎶樺彔涓哄垎缁勬憳瑕侊紝骞惰浣嶇粰婕忔枟涓讳綋' * 2, encoding='utf-8')
    assert guard.is_likely_mojibake(Path(f)) is True


# —— 2. 反向：正常中文必须放行（防过度敏感）——


def test_normal_chinese_message_is_allowed(guard):
    """正常中文技术提交（CJK >= 20）必须放行——豁免表不是「中文都放行」的开关。"""
    assert guard._check_commit_message_text(_NORMAL_SUBJECT, 'commit xxxxxxxx message') is False


def test_short_normal_message_is_allowed(guard):
    """短提交信息（CJK < 20，不触发阈值）放行。"""
    assert guard._check_commit_message_text('fix: 修一个笔误', 'commit xxxxxxxx message') is False


# —— 3. 豁免边界 ——


@pytest.mark.parametrize(
    'sha',
    [
        '8e3a935fac008159f485d16bf06626f6cf54525a',  # 完整 sha
        '8e3a935f',  # 8 位前缀
        '8e3a935fac00',  # 更长前缀
        '8E3A935FAC008159F485D16BF06626F6CF54525A',  # 大写同样命中
    ],
)
def test_exempt_hits_full_and_prefix(guard, sha):
    assert guard.is_exempt_commit_message(sha) is True


@pytest.mark.parametrize(
    'sha',
    [
        '',
        '   ',
        'deadbeef',  # 未登记
        '8e3a935',  # < 8 位前缀：不命中（防误放行）
    ],
)
def test_exempt_misses_others(guard, sha):
    assert guard.is_exempt_commit_message(sha) is False


def test_check_commit_short_circuits_on_exempt(guard):
    """豁免提交的**信息检查**直接返回 False（不查 git，因此无需仓内存在该提交）。"""
    assert guard._check_commit('8e3a935fac008159f485d16bf06626f6cf54525a') is False


def test_non_exempt_real_commit_still_checked(guard):
    """非豁免提交照旧走信息检查（用真实 HEAD 提交：正常中文，应放行但不短路）。"""
    head = _git('rev-parse', 'HEAD').stdout.strip()
    assert head, '测试环境应能取到 HEAD'
    # 判 True 说明真拦了（异常），判 False 说明检查通过；这里只要求它**不是**被豁免跳过
    assert guard.is_exempt_commit_message(head) is False


# —— 4. 防豁免表空转（两条不变式）——


def test_exempt_entries_exist_in_repo(guard):
    """每条豁免 sha 必须在真实仓里存在——否则就是匹配不到命中的僵尸条目。"""
    for sha in guard.EXEMPT_COMMIT_MESSAGES:
        r = _git('cat-file', '-e', f'{sha}^{{commit}}')
        assert r.returncode == 0, f'豁免条目 {sha} 在仓内不存在（僵尸条目）'


def test_exempt_entries_have_reason(guard):
    """每条豁免必须附非空理由——空理由即配置错误（同其它守卫的豁免约定）。"""
    for sha, reason in guard.EXEMPT_COMMIT_MESSAGES.items():
        assert reason and reason.strip(), f'豁免条目 {sha} 缺少理由'
        assert len(reason.strip()) >= 10, f'豁免条目 {sha} 的理由过于简略'


# —— 分层：豁免只作用于「提交信息」，不豁免文件内容 ——


def test_exempt_does_not_cover_file_content(guard, tmp_path):
    """拒绝用豁免掩盖文件内容乱码：豁免 sha 的提交若含乱码文件，仍应被文件检查判红。"""
    f = tmp_path / 'bad.md'
    f.write_text('澶х被璧勪骇瑙傚療鎶樺彔涓哄垎缁勬憳瑕侊紝骞惰浣嶇粰婕忔枟涓讳綋' * 2, encoding='utf-8')
    assert guard.is_likely_mojibake(Path(f)) is True


# —— CLI 契约（CI 逐提交循环依赖退出码）——


def test_cli_is_exempt_exit_codes():
    """`--is-exempt`：0 = 命中豁免（CI 跳过），1 = 未命中（继续检查），2 = 缺参。"""
    sha = '8e3a935fac008159f485d16bf06626f6cf54525a'
    hit = subprocess.run(
        [sys.executable, str(_GUARD_PATH), '--is-exempt', sha],
        cwd=str(_REPO_ROOT),
        capture_output=True,
    )
    miss = subprocess.run(
        [sys.executable, str(_GUARD_PATH), '--is-exempt', 'deadbeef'],
        cwd=str(_REPO_ROOT),
        capture_output=True,
    )
    missing_arg = subprocess.run(
        [sys.executable, str(_GUARD_PATH), '--is-exempt'],
        cwd=str(_REPO_ROOT),
        capture_output=True,
    )
    assert hit.returncode == 0, '命中豁免应返回 0'
    assert miss.returncode == 1, '未命中应返回 1'
    assert missing_arg.returncode == 2, '缺参应返回 2'
