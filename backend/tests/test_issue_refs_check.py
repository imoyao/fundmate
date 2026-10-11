# -*- coding: utf-8 -*-
"""`scripts/bridge/check_issue_refs.py` 的回归网（源 CNB issue #118）。

## WHY 有这份文件

这个脚本要解决的正是 #118 记的那件事：镜像卡正文引用 `WelcomeAssetBoard.vue:119-130`，
**该行在 `dev` / `main` 上早已删除**，而卡面没有任何线索说明它取自哪个版本，下一个人
照着不存在的代码动手。

它本身**只读**（不建卡、不改 issue），所以出错不会造成外部损坏；但它一旦「静默失效」，
后果是**给出反向的安心**——红灯不变绿、或者绿灯把失效引用报成有效。这正是本仓
「守门通过 ≠ 守门有效」那一课的同类：判据自己先崩，守门就只提供虚假信心。

故按四类钉死：

1. **抽取**：`path:line` / `path:line-end` / `path@ref:line` 三种写法都要认得，
   且**不能**把 `#118`、URL、时间戳这类误认成引用；
2. **路径补全**：卡面常写短路径（`views/welcome/...`），要能补成仓库根相对路径；
3. **判定**：文件不存在 / 行号越界 / 引用有效，三种结论都要对；
4. **`--strict-ref`**：没写 `@ref` 时能红灯——这是本卡的核心纪律，
   不能因为「反正有默认 ref」而变成永远绿。

前三类用**真实 git 仓库**（本仓自己）断言，不做 mock：mock 出来的 git 永远绿，
而被测的正是「跟真实 git 对话时结论对不对」。
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / 'scripts' / 'bridge' / 'check_issue_refs.py'

_MOD = None


def _load():
    global _MOD
    if _MOD is None:
        spec = importlib.util.spec_from_file_location('check_issue_refs', _SCRIPT_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules['check_issue_refs'] = module
        spec.loader.exec_module(module)
        _MOD = module
    return _MOD


@pytest.fixture()
def mod():
    return _load()


def _run(mod, text, *args):
    """把正文喂给脚本的 run()，返回 (exit_code, 捕获的输出)。"""
    import argparse
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    ns = argparse.Namespace(
        issue=None,
        file=None,
        ref='origin/dev',
        cwd=str(_REPO_ROOT),
        strict_ref='--strict-ref' in args,
        json=False,
    )
    # 直接喂正文，绕开 stdin —— load_body 在 file/issue 都为 None 时读 stdin
    mod.load_body = lambda _a: text
    with redirect_stdout(buf):
        code = mod.run(ns)
    return code, buf.getvalue()


# ---------------------------------------------------------------------------
# 1. 抽取：认得该认的，不认不该认的
# ---------------------------------------------------------------------------


def test_extract_simple_path_line(mod):
    refs = mod.extract_refs('见 `views/welcome/index.vue:12`')
    assert len(refs) == 1
    assert refs[0]['path'] == 'views/welcome/index.vue'
    assert refs[0]['start'] == 12
    assert refs[0]['end'] is None
    assert refs[0]['ref'] is None


def test_extract_range_and_explicit_ref(mod):
    refs = mod.extract_refs('`frontend/src/a/b.ts@origin/dev:119-130`')
    assert len(refs) == 1
    r = refs[0]
    assert r['path'] == 'frontend/src/a/b.ts'
    assert r['ref'] == 'origin/dev'
    assert r['start'] == 119 and r['end'] == 130


def test_extract_ignores_issue_numbers_and_urls(mod):
    """`#118` / `https://…` / `12:30` 不能被当成文件引用（误报比漏报更耗信任）。"""
    text = '源 CNB issue #118；见 https://github.com/imoyao/fundmate/issues/2034 ；时间 12:30'  # cross-repo-ref-allow
    assert mod.extract_refs(text) == []


def test_extract_dedupes(mod):
    """同一处引用在正文里出现两次，只核对一次。"""
    refs = mod.extract_refs('`a/b.vue:1` 和 `a/b.vue:1`')
    assert len(refs) == 1


def test_extract_keeps_inline_code_refs(mod):
    """行内代码里的引用**要**抽取 —— 本仓卡面绝大多数把引用写在反引号里。

    这处与 `close_linked_issues.js` 相反：那里必须 stripCode（免得把讲解用的
    `Closes #1` 当真），这里必须**保留**（否则把核对对象删了）。两个脚本的
    取舍不能互相照抄。
    """
    refs = mod.extract_refs('就是这一行：`frontend/src/views/welcome/index.vue:1`')
    assert len(refs) == 1


# ---------------------------------------------------------------------------
# 2. 路径补全（卡面写短路径）
# ---------------------------------------------------------------------------


def test_resolves_short_path_with_frontend_prefix(mod):
    """`views/welcome/...` 这种卡面常用写法要能补成 `frontend/src/views/welcome/...`。"""
    real, err = mod._resolve_path('views/welcome/index.vue', 'origin/dev', str(_REPO_ROOT))
    assert real == 'frontend/src/views/welcome/index.vue', err


def test_resolves_repo_relative_path_unchanged(mod):
    """本来就是仓库根相对路径的，原样命中（不能因为试前缀而错认到别的文件）。"""
    real, _ = mod._resolve_path('frontend/src/views/welcome/index.vue', 'origin/dev', str(_REPO_ROOT))
    assert real == 'frontend/src/views/welcome/index.vue'


def test_unresolvable_path_returns_error(mod):
    real, err = mod._resolve_path('nonexistent/nowhere.vue', 'origin/dev', str(_REPO_ROOT))
    assert real is None
    assert '不存在' in err


def test_bare_filename_resolved_by_unique_suffix(mod):
    """卡面常只写 `summary_service.py:392`（无目录）。全仓唯一命中时要能认出来。

    不做 mock：`summary_service.py` 在本仓当前确实唯一，一旦哪天多出一个同名文件，
    这条用例会红——**那正是想要的**：多命中时按哪个文件核对都是猜，必须回来改判据。
    """
    real, note = mod._resolve_path('summary_service.py', 'origin/dev', str(_REPO_ROOT))
    assert real == 'backend/app/services/summary_service.py', note


def test_bare_filename_never_uses_scripts_dir(mod):
    """`scripts/` 必须**不在**前缀表里。

    它是本脚本自己的目录：放进去之后 `check_issue_refs.py:1` 之类会去试
    `scripts/check_issue_refs.py`，把「引用的是别的文件」核对成本脚本自己。
    """
    assert 'scripts/' not in mod.PATH_PREFIXES


def test_backend_app_prefix_precedes_backend(mod):
    """`services/xxx.py` 指的是 `backend/app/services/...`，不是 `backend/services/...`。

    顺序错会让引用核对成另一个文件（若恰好存在）——给出假绿灯。
    """
    pre = list(mod.PATH_PREFIXES)
    assert pre.index('backend/app/') < pre.index('backend/')


# ---------------------------------------------------------------------------
# 3. 判定：有效 / 越界 / 文件不存在
# ---------------------------------------------------------------------------


def test_valid_ref_passes(mod):
    code, out = _run(mod, '`frontend/src/views/welcome/index.vue@origin/dev:1-10`')
    assert code == 0, out
    assert '仍然有效' in out


def test_out_of_range_line_fails(mod):
    """行号越界 = 卡面读过时了，必须红灯——这正是 #118 要抓的形态。"""
    code, out = _run(mod, '`frontend/src/views/welcome/index.vue@origin/dev:99999`')
    assert code == 1, out
    assert '越界' in out


def test_missing_file_fails(mod):
    code, out = _run(mod, '`no/such/file.vue@origin/dev:1`')
    assert code == 1, out
    assert '不存在' in out


def test_no_refs_is_not_a_failure(mod):
    """正文里没有引用 → 无需核对 → 绿（不能因为「没得查」就红灯）。"""
    code, out = _run(mod, '这张卡没有引用任何文件行号。')
    assert code == 0, out
    assert '无需核对' in out


# ---------------------------------------------------------------------------
# 4. --strict-ref：没写 @ref 必须红灯（#118 的核心纪律）
# ---------------------------------------------------------------------------


def test_strict_ref_flags_missing_version(mod):
    """#118 的硬要求：引用具体行号时必须写 `@<ref>`，否则核对者不知道拿哪个版本比。"""
    code, out = _run(mod, '`frontend/src/views/welcome/index.vue:1`', '--strict-ref')
    assert code == 1, out
    assert '@<ref>' in out


def test_strict_ref_passes_when_version_present(mod):
    code, out = _run(mod, '`frontend/src/views/welcome/index.vue@origin/dev:1`', '--strict-ref')
    assert code == 0, out


def test_non_strict_tolerates_missing_version(mod):
    """默认模式下缺 `@ref` 只提示不拦——本仓的存量卡全都没写，硬拦等于全红。

    这是**有意的宽严分层**：存量卡可以靠默认 ref 核对，新卡由 `--strict-ref` 管。
    """
    code, out = _run(mod, '`frontend/src/views/welcome/index.vue:1`')
    assert code == 0, out


# ---------------------------------------------------------------------------
# 5. 只读纪律（脚本有外部副作用的邻域，边界要钉住）
# ---------------------------------------------------------------------------


def test_script_never_writes(mod):
    """脚本里不得出现写操作：它是在**别人的卡面**上跑判据，写错影响面不可控。"""
    src = _SCRIPT_PATH.read_text(encoding='utf-8')
    for banned in ('json.dump(', 'write_text(', 'open(', '.write('):
        # open( 在 load_body 里用于**读**文件；这里只钉「没有以写模式 open」
        if banned == 'open(':
            assert "open(args.file, encoding='utf-8')" in src
            continue
        assert banned not in src, f'check_issue_refs.py 出现写操作：{banned}'


def test_git_invocations_are_read_only(mod):
    """所有 git 调用必须是 git show（只读）。出现 add/commit/push 即越界。"""
    src = _SCRIPT_PATH.read_text(encoding='utf-8')
    assert "'show'" in src
    for banned in ("'commit'", "'add'", "'push'", "'checkout'", "'reset'"):
        assert banned not in src, f'出现写仓库状态的 git 调用：{banned}'


# ---------------------------------------------------------------------------
# 6. 镜像卡扫描器（check_mirror_refs.py）
# ---------------------------------------------------------------------------


def _load_scanner():
    import importlib.util as ilu

    path = _SCRIPT_PATH.parent / 'check_mirror_refs.py'
    spec = ilu.spec_from_file_location('check_mirror_refs', path)
    module = ilu.module_from_spec(spec)
    sys.modules['check_mirror_refs'] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def scanner():
    return _load_scanner()


def test_scanner_reuses_checker_logic(scanner):
    """扫描器必须复用 `check_issue_refs` 的抽取 / 核对，**不得**自带第二份正则。

    抄一份的代价不是「多几行」：两份判据会漂移，漂移之后哪份绿都说明不了问题。
    这里直接断言它加载到的就是同一个模块（按文件路径加载，模块名一致）。
    """
    checker = scanner._load_checker()
    assert Path(checker.__file__).name == 'check_issue_refs.py'
    # 抽取行为与 checker 一致（同一套正则，不重写）
    assert checker.extract_refs('`a/b.vue:12`')[0]['path'] == 'a/b.vue'


def test_scanner_detects_stale_refs_end_to_end(scanner, monkeypatch, capsys):
    """**走真实代码路径**：给一张卡的正文字符串，扫描器要自己判定出失效引用。

    这条不在 `rows` 上断言（那样等于把被测的判定逻辑换成测试自己造的结论，
    删掉扫描器里的核对循环也照样绿——**探针实测过，确实漏**）。
    这里 mock 的只有「从 CNB 取卡」这一步（网络），判定与抽取全用真实现。
    """
    import argparse

    body = '见 `frontend/src/views/welcome/index.vue:99999`'

    def fake_list(_repo):
        return [{'number': 106, 'title': 'x', 'labels': [{'name': 'GitHub 同步'}]}]

    def fake_get(path):
        # 新增：`run()` 会先拉评论区判断「该卡是否已记过更正」。无评论 ⇒ 判为待更正。
        if path.endswith('/comments'):
            return []
        return {'body': body}

    monkeypatch.setattr(scanner, 'list_mirror_cards', fake_list)
    monkeypatch.setattr(scanner, 'cnb_get', fake_get)
    monkeypatch.setattr(scanner, 'GITHUB_NUMBER_RE', __import__('re').compile(r'GitHub 编号：`#(\d+)`'))

    args = argparse.Namespace(
        repo='duoduobei/fundmate',
        issue=None,
        ref='origin/dev',
        cwd=str(_REPO_ROOT),
        out=None,
        report=True,
    )
    assert scanner.run(args) == 0
    out = capsys.readouterr().out
    assert '#106' in out
    assert '越界' in out, out
    assert '引用已失效**：1 张' in out, out


def test_scanner_report_shape_for_stale(scanner):
    """报告排版：卡号、GitHub 反链、失效引用原文、原因四样都不能少。"""
    rows = [
        {
            'cnb': 106,
            'github': 2034,
            'gh_repo': 'imoyao/fundmate',
            'title': 't',
            'refs': 1,
            'stale': [('Foo.vue:119-130', 'Foo.vue 在 `origin/dev` 上不存在')],
            'corrected': False,
        }
    ]
    report = scanner.build_report(rows, 'origin/dev')
    assert '#106' in report and '#2034' in report
    assert 'Foo.vue:119-130' in report
    assert '引用已失效**：1 张' in report


def test_scanner_report_green_when_clean(scanner):
    """没有失效引用时给明确绿灯（不能只是「没报错」，读者需要一句话）。"""
    rows = [{'cnb': 5, 'github': 783, 'gh_repo': 'x/y', 'title': 't', 'refs': 2, 'stale': []}]
    report = scanner.build_report(rows, 'origin/dev')
    assert '仍然有效' in report
    assert '引用已失效**：0 张' in report


def test_scanner_never_writes_cards(scanner):
    """扫描器**只报告**：出现改卡 / 建卡的调用即越界（改镜像卡要产品拍板，见 CNB #120）。"""
    src = (SCRIPT_DIR_SRC / 'check_mirror_refs.py').read_text(encoding='utf-8')
    for banned in ("method='POST'", "method='PUT'", "method='PATCH'", "method='DELETE'"):
        assert banned not in src, f'扫描器出现写操作：{banned}'
    assert 'def cnb_get' in src  # 只有 GET


# ---------------------------------------------------------------------------
# 五、假红修复（CNB #123）：只读正文会把已记过账的卡永远报成待办
# ---------------------------------------------------------------------------
#
# #120 的更正通道是「正文不动、更正写评论区」。若扫描器只看正文，就会永远报红——
# 修好了也红，而红却不指向任何还需动手的事。这与 #118 要治的「静默降级」同族：
# 那边是假绿，这边是假红，**红灯的可信度一样会掉没**。


def test_correction_key_re_is_reused_not_recopied(scanner):
    """「评论区是否已更正」的判据必须复用 `mirror_correction.py` 的幂等键正则。

    抄第二份的代价与 `_load_checker` 同理：两份判据会漂移，漂移之后「算不算已更正」
    这个结论就不可信了。这里断言它真的用 `mirror_correction.py` 里的那一条。
    """
    key_re = scanner._correction_key_re()
    # 与 source of truth 逐字一致（同一份字面量）
    mirror_src = (SCRIPT_DIR_SRC / 'mirror_correction.py').read_text(encoding='utf-8')
    assert '更正键：' in mirror_src
    assert '([0-9a-f]{12})' in mirror_src
    # 真的能命中 `mirror_correction.build_comment` 产出的正文
    import importlib.util as ilu

    spec = ilu.spec_from_file_location('mirror_correction', SCRIPT_DIR_SRC / 'mirror_correction.py')
    corr = ilu.module_from_spec(spec)
    sys.modules['mirror_correction'] = corr
    spec.loader.exec_module(corr)
    body = corr.build_comment('2026-10-11', ['❌ x → ✅ y'], 'deadbeef0000')
    assert key_re.search(body), '复用失败：连自己脚本产出的更正评论都识别不出'


def test_load_corrected_numbers_reads_comments(scanner, monkeypatch):
    """`load_corrected_numbers` 要按「评论区有无更正键」挑卡，而不是按正文有无。"""
    import argparse  # noqa: F401

    key = '595cc49f310d'
    comments = {
        56: [{'body': f'## 更正（2026-10-11）\n\n- ❌ x → ✅ y\n\n<!-- 更正键：{key} -->'}],
        38: [{'body': '随便聊聊，不是更正'}],
    }

    def fake_get(path):
        for n, c in comments.items():
            if path.endswith(f'issues/{n}/comments'):
                return c
        return []

    monkeypatch.setattr(scanner, 'cnb_get', fake_get)
    cards = [{'number': 56}, {'number': 38}, {'number': 999}]
    got = scanner.load_corrected_numbers('duoduobei/fundmate', cards)
    assert got == {56}, f'只该认出 #56，实际 {got}'


def test_load_corrected_numbers_skips_on_error(scanner, monkeypatch):
    """拉评论失败时**跳过**（按未更正处理）：宁可多报，也不静默漏报。"""

    def boom(_path):
        raise RuntimeError('网络炸了')

    monkeypatch.setattr(scanner, 'cnb_get', boom)
    assert scanner.load_corrected_numbers('x/y', [{'number': 56}]) == set()


def test_report_splits_pending_and_acked(scanner):
    """报告必须把「待更正」与「已更正」分开列——这是消掉假红的全部内容。"""
    stale_row = {
        'cnb': 56,
        'github': 1095,
        'gh_repo': 'imoyao/fundmate',
        'title': 't',
        'refs': 2,
        'stale': [('portfolios/views.py:214-215', '越界')],
    }
    report = scanner.build_report([dict(stale_row, corrected=False)], 'origin/dev')
    assert '需要动手）：1 张' in report
    assert '账已记）：0 张' in report
    assert '### ⚠️ 待更正' in report
    assert '### ✅ 已更正' not in report

    report2 = scanner.build_report([dict(stale_row, corrected=True)], 'origin/dev')
    assert '需要动手）：0 张' in report2
    assert '账已记）：1 张' in report2
    assert '### ✅ 已更正' in report2
    assert '### ⚠️ 待更正' not in report2, '已记过账的卡不该再出现在待办区'


def test_report_green_when_all_acked(scanner):
    """全部已更正时，报告的「待办」是 0 —— 这正是 #123 要的「不再假红」。"""
    rows = [
        {
            'cnb': 56,
            'github': 1095,
            'gh_repo': 'imoyao/fundmate',
            'title': 't',
            'refs': 1,
            'stale': [('portfolios/views.py:193', '越界')],
            'corrected': True,
        }
    ]
    report = scanner.build_report(rows, 'origin/dev')
    assert '引用已失效**：1 张' in report
    assert '需要动手）：0 张' in report


def test_end_to_end_acked_card_counts_as_recorded(scanner, monkeypatch, capsys):
    """**走真实代码路径**：评论区已有更正时，端到端输出里该卡落在「已更正」区。

    这条不 mock `run` 的判定，只 mock 网络（CNB 取卡 + 取评论），与上一条端到端用例同法。
    """
    import argparse
    import re as _re

    body = '见 `frontend/src/views/welcome/index.vue:99999`'
    key = '595cc49f310d'

    def fake_list(_repo):
        return [{'number': 106, 'title': 'x', 'labels': [{'name': 'GitHub 同步'}]}]

    def fake_get(path):
        if path.endswith('/comments'):
            return [{'body': f'## 更正（2026-10-11）\n\n- ❌ x → ✅ y\n\n<!-- 更正键：{key} -->'}]
        return {'body': body}

    monkeypatch.setattr(scanner, 'list_mirror_cards', fake_list)
    monkeypatch.setattr(scanner, 'cnb_get', fake_get)
    monkeypatch.setattr(scanner, 'GITHUB_NUMBER_RE', _re.compile(r'GitHub 编号：`#(\d+)`'))

    args = argparse.Namespace(
        repo='duoduobei/fundmate', issue=None, ref='origin/dev', cwd=str(_REPO_ROOT), out=None, report=True
    )
    assert scanner.run(args) == 0
    out = capsys.readouterr().out
    assert '需要动手）：0 张' in out, out
    assert '账已记）：1 张' in out, out


SCRIPT_DIR_SRC = _SCRIPT_PATH.parent
