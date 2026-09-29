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


def _is_shallow_clone() -> bool:
    """是否为浅克隆（CI 的 backend job 用 actions/checkout 默认 fetch-depth=1）。"""
    r = _git('rev-parse', '--is-shallow-repository')
    return r.returncode == 0 and r.stdout.strip() == 'true'


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
    """每条豁免 sha 必须在真实仓里存在——否则就是匹配不到命中的僵尸条目。

    **浅克隆必须跳过**：CI 的 backend job 用 `actions/checkout` 默认 `fetch-depth=1`，
    看不到历史对象（`git cat-file -e` 返回 128）。这条不变式的价值在**完整克隆**上兑现
    ——本地开发仓与乱码守卫 job（`fetch-depth: 0`）都是完整的，故仍有真实约束力。
    """
    if _is_shallow_clone():
        pytest.skip('浅克隆：历史对象不可见，跳过存在性断言（完整克隆会真跑）')
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


# —— 5. push 事件的范围解析（#1767）——
#
# push 的 `before` 有若干畸形形态（全零 / 对象不可达 / 跨分支非祖先）。最坏情形是
# **静默放行**（范围算错、什么都没扫却 exit 0）。这组用例钉死三件事：
# ① 全零与不可达 → 降级为单提交并给 NOTE；② **非祖先不降级**（发版 PR 的正解是仍全量扫描）；
# ③ 范围不可确定 → 显式报错，绝不静默通过。


def _head_and_parent():
    """返回 (HEAD, HEAD^)；浅克隆等历史不可见的情形返回 (None, None)。"""
    head = _git('rev-parse', 'HEAD').stdout.strip()
    parent = _git('rev-parse', 'HEAD^').stdout.strip()
    if not head or _git('cat-file', '-e', f'{parent}^{{commit}}').returncode != 0:
        return None, None
    return head, parent


def test_resolve_range_zero_before_degrades(guard):
    """before 全零（首次推送 / 新建分支）→ 降级为只校验 head 单提交，并给出 NOTE。"""
    head = _git('rev-parse', 'HEAD').stdout.strip()
    revs, note, ok = guard._resolve_range('0' * 40, head)
    assert ok is True
    assert revs == [head]
    assert '首次推送' in note


def test_resolve_range_empty_head(guard):
    """head 为空 → ok=False（调用方据此报错，绝不静默放行）。"""
    revs, note, ok = guard._resolve_range('0' * 40, '')
    assert ok is False
    assert revs == []
    assert note


def test_resolve_range_missing_head(guard):
    """head 对象不在仓库 → ok=False。"""
    revs, note, ok = guard._resolve_range('0' * 40, 'deadbeef' * 5)
    assert ok is False
    assert revs == []
    assert 'head' in note


def test_resolve_range_normal(guard):
    """正常范围（base 是 head 的祖先）→ 返回区间提交且无 NOTE。"""
    head, parent = _head_and_parent()
    if head is None:
        pytest.skip('浅克隆：历史对象不可见')
    revs, note, ok = guard._resolve_range(parent, head)
    assert ok is True
    assert revs == [head]
    assert note == ''


def test_resolve_range_non_ancestor_is_still_scanned(guard):
    """base 不是 head 的祖先（force push / 发版 PR 跨分支）→ **仍按 rev-list 全量扫描**。

    用 `git commit-tree` 造一个游离提交充当「重写后的新 head」：它可达而 base 不可达，
    正是 force push 的形态；对象只落在本地对象库、不挂任何分支（测试后自然悬空）。

    这条用例守着初版被真实场景证伪的设计错误：曾把「非祖先」当降级信号，
    会让**发版 PR**（base=main，而 main 独有的发版合并提交 dev 并不包含）的扫描
    从 210 个提交退化成 1 个 —— 即「看起来通过、其实没扫」。
    """
    head, _ = _head_and_parent()
    if head is None:
        pytest.skip('浅克隆：历史对象不可见')
    tree = _git('rev-parse', 'HEAD^{tree}').stdout.strip()
    probe = _git('commit-tree', tree, '-m', 'test probe (orphan commit)')
    orphan = probe.stdout.strip()
    if probe.returncode != 0 or not orphan:
        pytest.skip('无法构造游离提交（commit-tree 不可用）')
    revs, note, ok = guard._resolve_range(head, orphan)
    assert ok is True
    assert revs == [orphan]
    assert note == ''


def test_scan_range_ok_on_real_range(guard, monkeypatch):
    """真实范围扫描通过：范围 diff（文件）+ 逐提交信息都干净。"""
    head, parent = _head_and_parent()
    if head is None:
        pytest.skip('浅克隆：历史对象不可见')
    monkeypatch.chdir(_REPO_ROOT)
    assert guard._scan_range(parent, head) == 0


def test_scan_range_unresolvable_head_is_error(guard, monkeypatch):
    """范围无法确定 → 退出码 2（本层的关键不变量：不静默放行）。"""
    monkeypatch.chdir(_REPO_ROOT)
    assert guard._scan_range('', 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef') == 2


def test_cli_scan_range_missing_args():
    """CLI：--scan-range 缺参 → 退出码 2。"""
    r = subprocess.run(
        [sys.executable, str(_GUARD_PATH), '--scan-range'],
        cwd=str(_REPO_ROOT),
        capture_output=True,
    )
    assert r.returncode == 2
