# -*- coding: utf-8 -*-
"""GitHub → CNB issue 增量镜像脚本的回归网（源 issue `#2` 的「要不要做成常驻同步」）。

## WHY 有这份文件

`scripts/bridge/github_cnb_issues.py` 由 `.cnb.yml` 的每日 cron **无人值守**驱动，且做的是
**有外部副作用**的事：在 CNB 建卡。它一旦「静默半失效」，后果不是少建一张，而是：

  - **幂等键（`GitHub 编号：#N`）写歪** → 每天把全部 107 张卡重贴一遍，看板被淹；
  - **标签名不合法**（含 `&`、`（）`、`#`）→ CNB 400 拒收，卡片裸奔没有里程碑信息；
  - **正文格式漂移** → 同一批卡出现两种长相，与 2026-10-11 那次全量同步的存量卡对不上。

故本文件按四类钉死：

1. **字段映射**：象阵 → priority、里程碑 → `里程碑:` 标签、原标签去重；
2. **标签合法性**：非法字符被等价替换、超长截断到 CNB 的 50 字上限、总数不超 10；
3. **幂等键**：`build_body` 产出的正文能被 `extract_github_number` 原样抠回；
4. **格式冻结**：正文头部与存量镜像卡（CNB `#5`，GitHub `#783`）逐字节一致——
   这条是防止「格式漂移」的硬钉子，改格式必须是有意识的决定。

全程 **零网络、零写入**，只跑纯函数。
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / 'scripts' / 'bridge' / 'github_cnb_issues.py'

_MIRROR = None


def _load_mirror():
    """按路径加载脚本模块（进程内只加载一次，与 test_guard_mojibake.py 同法）。"""
    global _MIRROR
    if _MIRROR is None:
        spec = importlib.util.spec_from_file_location('github_cnb_issues', _SCRIPT_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules['github_cnb_issues'] = module
        spec.loader.exec_module(module)
        _MIRROR = module
    return _MIRROR


@pytest.fixture()
def m():
    return _load_mirror()


def _issue(**over):
    """造一张最小可用的 GitHub issue 载荷，测试按需覆盖字段。"""
    base = {
        'number': 783,
        'state': 'open',
        'title': '记账功能需求检查单',
        'body': '正文 **加粗**',
        'milestone': {'title': 'P0 导入统一入口 Import Unified Entry'},
        'user': {'login': 'imoyao'},
        'created_at': '2026-05-26T01:02:03Z',
        'comments': 5,
        'labels': [
            {'name': 'triage-done'},
            {'name': '导入导出'},
            {'name': 'Q2-YELLOW'},
        ],
    }
    base.update(over)
    return base


# —— 1. 字段映射 ——


def test_xiangzhen_maps_to_priority():
    m = _load_mirror()
    assert m.priority_from_labels(['bug', 'Q1-RED']) == 'P0'
    assert m.priority_from_labels(['Q2-YELLOW']) == 'P1'
    assert m.priority_from_labels(['Q3-GREEN']) == 'P2'
    assert m.priority_from_labels(['Q4-GRAY']) == 'P3'


def test_no_xiangzhen_leaves_priority_unset():
    """没有象阵标签时返回 None —— 建卡时不传 priority，交给 CNB 默认值。"""
    m = _load_mirror()
    assert m.priority_from_labels(['bug', 'enhancement']) is None


def test_xiangzhen_label_is_not_duplicated_as_label():
    """象阵已转 priority，不该再以标签形式挂一遍。"""
    m = _load_mirror()
    labels = m.build_labels(_issue())
    assert 'Q2-YELLOW' not in labels
    assert 'GitHub 同步' in labels


def test_milestone_becomes_prefixed_label():
    m = _load_mirror()
    labels = m.build_labels(_issue())
    assert '里程碑:P0 导入统一入口 Import Unified Entry' in labels


def test_original_labels_kept_and_deduped():
    m = _load_mirror()
    labels = m.build_labels(_issue(labels=[{'name': 'bug'}, {'name': 'bug'}, {'name': '前端'}]))
    assert labels.count('bug') == 1
    assert '前端' in labels


# —— 2. 标签合法性（CNB 硬限制）——


def test_sanitize_replaces_cnb_illegal_chars():
    """`&`、`（）`、`#` 会被 CNB 400 拒收，必须替换成等价可读写法。"""
    m = _load_mirror()
    assert m.sanitize_label('Feedback & Changelog') == 'Feedback 和 Changelog'
    assert m.sanitize_label('Product Detail（#1909）') == 'Product Detail No.1909'


def test_sanitize_truncates_to_50_chars():
    """CNB 标签名长度上限 50，超长必须截断而不是提交后 400。"""
    m = _load_mirror()
    assert len(m.sanitize_label('长' * 80)) == 50


def test_labels_never_exceed_cnb_limit():
    """CNB 单卡标签上限 10；原标签再多也不能越界。"""
    m = _load_mirror()
    many = [{'name': f'label-{i}'} for i in range(30)]
    labels = m.build_labels(_issue(labels=many))
    assert len(labels) <= 10
    assert labels[0] == 'GitHub 同步'


def test_milestone_label_survives_label_overflow():
    """标签溢出时丢原标签、保里程碑 —— 里程碑是看板归类的硬信息。"""
    m = _load_mirror()
    many = [{'name': f'label-{i}'} for i in range(30)]
    labels = m.build_labels(_issue(labels=many))
    assert any(s.startswith('里程碑:') for s in labels)


def test_no_milestone_no_label():
    m = _load_mirror()
    labels = m.build_labels(_issue(milestone=None))
    assert not any(s.startswith('里程碑:') for s in labels)


# —— 3. 幂等键往返 ——


def test_github_number_roundtrip():
    """`build_body` 写进去的编号必须能被 `extract_github_number` 原样抠回。

    幂等全靠这一对函数：抠不回来 = 下一轮把同一张 GitHub 卡再建一遍。
    """
    m = _load_mirror()
    for n in (1, 42, 783, 2051):
        body = m.build_body(_issue(number=n))
        assert m.extract_github_number(body) == n


def test_extract_returns_none_on_foreign_body():
    """非镜像正文（比如 CNB 侧自建的卡）抠不到编号，返回 None。"""
    m = _load_mirror()
    assert m.extract_github_number('这是一张 CNB 侧自建的卡') is None
    assert m.extract_github_number('') is None
    assert m.extract_github_number(None) is None


# —— 4. 格式冻结（防漂移）——


def _fixed_clock(m, monkeypatch, when='2026-10-12'):
    """把 `build_body` 的建卡时刻钉死，让头部可以逐字节断言（否则日期一过就红）。

    供 `test_header_matches_frozen_shape` 等用例复用；存量卡对照口径见其 docstring。
    """

    class _FixedDatetime:
        @staticmethod
        def now(tz=None):
            from datetime import datetime

            return datetime.fromisoformat(f'{when}T00:00:00+00:00')

    monkeypatch.setattr(m, 'datetime', _FixedDatetime)


def test_header_matches_frozen_shape(m, monkeypatch):
    """正文头部形状冻结（源头卡为 CNB #5 ← GitHub imoyao/fundmate#783 的镜像，2026-10-11 全量同步）。  <!-- cross-repo-ref-allow -->

    字段顺序 / 措辞 / 全角空格都钉在这里；改它等于让前后两批镜像卡出现两种长相，
    必须是有意识的决定，而不是顺手重构的副作用。

    #118 与 #120 都想让卡面「自己声明是快照」，合并时统一到一份溯源块：
    保留 #120 的建卡时刻 + 更正台账（`mirror_correction.py`），并并入 #118 的
    可执行核对动作（`git show <ref>:<file>`）。幂等键仍在同一位置。
    """
    m = _load_mirror()
    _fixed_clock(m, monkeypatch)
    body = m.build_body(_issue())
    expected_header = '\n'.join(
        [
            '> 🔁 **本卡由 GitHub Issue 同步而来（CNB 镜像）**',
            '>',
            '> - 来源：https://github.com/imoyao/fundmate/issues/783',
            '> - GitHub 编号：`#783`　状态：`open`',
            '> - 里程碑：`P0 导入统一入口 Import Unified Entry`',
            '> - 原标签：`triage-done` `导入导出` `Q2-YELLOW`',
            '> - 作者：@imoyao　创建：2026-05-26　评论数：5',
            '> - 镜像生成时间：2026-10-12 00:00 UTC',
            '>',
            '> ⚠️ 本卡是**建卡时快照**（截至 2026-10-12），**不覆盖后续变更**；',
            '> 正文引用的文件 / 行号 / 字段 / 结论均为快照时刻的位置，可能与当前代码不一致——',
            '> 按它动手之前，先用 `git show <ref>:<file>` 确认该行仍在当前分支上。',
            '> ⚠️ 正式讨论、更正与状态变更请回到 GitHub 原卡，CNB 侧改动不会自动回流；',
            '> 本卡正文若与 GitHub 原卡不符，**一律以 GitHub 为准**。',
            '>',
            '> 📝 **更正**：在本卡评论区追加一条更正评论（不改正文）——',
            '> 标题写 `## 更正（{日期}）`，正文逐条写「❌ 原文 → ✅ 实际（依据：PR/commit）」。',
            '> 依据 AGENTS.md「失实信息修正纪律」；命令见 `scripts/bridge/mirror_correction.py`。',
            '',
            '---',
            '',
            '正文 **加粗**',
        ]
    )
    assert body == expected_header


def test_snapshot_warning_is_present(m, monkeypatch):
    """#118 的硬要求：卡面必须**自己声明**可能过期，且给出核对动作。

    这条不是措辞问题：镜像卡正文顶上原本写着「状态：`open`」这类看着权威的字段，
    读者没有任何线索知道它是快照——`#106` 就是活例子（引用的行号早已删除，
    卡面读了两个版本前的代码）。
    """
    m = _load_mirror()
    _fixed_clock(m, monkeypatch)
    body = m.build_body(_issue())
    # 必须出现：建卡时刻、快照声明、核对动作、以 GitHub 为准
    assert '镜像生成时间：2026-10-12' in body
    assert '建卡时快照' in body
    assert 'git show <ref>:<file>' in body
    assert '以 GitHub 为准' in body
    # 旧的「只读镜像」措辞不得复活（它与「更正在评论区」自相矛盾）
    assert '本卡为只读镜像' not in body


def test_idempotency_key_position_unchanged(m, monkeypatch):
    """加字段不得动幂等键：`GitHub 编号：#N` 仍是溯源块里的独立一行，抠得回来。"""
    m = _load_mirror()
    _fixed_clock(m, monkeypatch)
    for n in (1, 783, 2051):
        assert m.extract_github_number(m.build_body(_issue(number=n))) == n


def test_body_keeps_origin_content_verbatim():
    """GitHub 原文必须原样拼在后面，不做任何转义 / 截断。"""
    m = _load_mirror()
    origin = '# 标题\n\n| 列 | 值 |\n|---|---|\n| `code` | **粗** |'
    assert m.build_body(_issue(body=origin)).endswith(origin)


def test_empty_body_and_no_labels_do_not_crash():
    """边界：GitHub 卡可能没有正文 / 没有标签，脚本不能因此崩。"""
    m = _load_mirror()
    body = m.build_body(_issue(body=None, labels=[], comments=0))
    assert '原标签：—' in body
    assert 'GitHub 编号：`#783`' in body
    assert m.build_labels(_issue(labels=[], milestone=None)) == ['GitHub 同步']


# —— 5. CNB 本地卡（#117：只对 CNB 有效的卡不该被当成「漏同步的镜像卡」）——


def _cnb_card(**over):
    """造一张最小可用的 CNB 卡载荷（判据只看 labels / body / comment_count）。"""
    base = {'number': 117, 'state': 'open', 'title': '某张卡', 'comment_count': 0, 'labels': [], 'body': ''}
    base.update(over)
    return base


def test_mirror_card_marked_by_label():
    """挂 `GitHub 同步` 标签的卡是镜像卡，不是本地卡。"""
    m = _load_mirror()
    card = _cnb_card(labels=[{'name': m.MIRROR_LABEL}], body='随便写的正文')
    assert m.is_mirror_card(card) is True
    assert m.is_local_card(card) is False
    assert m.local_card_kind(card) == ''


def test_mirror_card_marked_by_idempotency_key():
    """没标签但有幂等键 `GitHub 编号：#N` 的也是镜像卡（判据互补，不是只认标签）。"""
    m = _load_mirror()
    card = _cnb_card(body='> - GitHub 编号：`#2034`　状态：`open`')
    assert m.is_mirror_card(card) is True
    assert m.is_local_card(card) is False


def test_local_card_marked_by_label():
    """挂 `CNB 本地` 标签 = 显式声明，判定来源记为 `label`。"""
    m = _load_mirror()
    card = _cnb_card(labels=[{'name': m.LOCAL_LABEL}], body='正文')
    assert m.is_local_card(card) is True
    assert m.local_card_kind(card) == 'label'


def test_local_card_marked_by_body_declaration():
    """正文顶部写 `> 📍 **CNB 本地卡**` = 显式声明，判定来源记为 `body`。

    这条存在的意义：人工开的本地卡**不一定记得挂标签**，
    但一定写得出这一行；两者都认，声明才不至于因为「忘了挂标签」而失效。
    """
    m = _load_mirror()
    for body in ('> 📍 **CNB 本地卡**\n\n正文', '> **CNB 本地卡**\n\n正文'):
        card = _cnb_card(labels=[{'name': m.MIRROR_LABEL}], body=body)
        assert m.local_card_kind(card) == 'body', body
        assert m.is_local_card(card) is True


def test_local_card_fallback_is_labelled_as_guess():
    """既无标签又无幂等键 ⇒ 判为本地卡，但来源必须是 `fallback`（**猜的**）。

    这是本判据最容易做错的地方：兜底把「格式写歪的镜像卡」也说成本地卡。
    把来源单独记下来，报告里才能把「声明」与「猜测」分开计数 ——
    否则一张少算的报告看上去依然自洽（#117 的静默失效主题）。
    """
    m = _load_mirror()
    card = _cnb_card(labels=[], body='随便写的正文')
    assert m.local_card_kind(card) == 'fallback'
    assert m.is_local_card(card) is True


def test_mentioning_the_concept_is_not_a_declaration():
    """正文里**提到**「**CNB 本地卡**」这个概念，不等于本卡是本地卡。

    这条是判据的证伪用例：没有它，`LOCAL_MARKER_RE` 退化成
    「只要出现过这几个字就算」也能全绿 —— 而那张卡其实只是挂了镜像标签、
    正在讲解这个概念（本卡的正文就是这种）。
    """
    m = _load_mirror()
    card = _cnb_card(labels=[{'name': m.MIRROR_LABEL}], body='本卡讲解 **CNB 本地卡** 与镜像卡的区别')
    assert m.local_card_kind(card) == ''
    assert m.is_local_card(card) is False


def test_conflict_is_reported_not_silently_resolved():
    """两种判据都命中（既挂镜像标签又挂本地标签）⇒ 报 `conflict`，不替人选边。"""
    m = _load_mirror()
    card = _cnb_card(labels=[{'name': m.MIRROR_LABEL}, {'name': m.LOCAL_LABEL}], body='正文')
    report = m.local_card_report([card])
    row = report['cards'][0]
    assert row['conflict'] is True
    assert row['local'] is True and row['mirror'] is True
    assert report['summary']['conflict'] == 1


def test_github_refs_only_counts_github_side():
    """`_github_refs` 只收 GitHub 侧引用。

    一张 CNB 本地卡正文里满是 `duoduobei/fundmate#106`（指向 CNB 自己）——
    把它们也算成「提到了 GitHub」，提示就变成噪音，人就不会再看这一列了。
    """
    m = _load_mirror()
    body = '相关：duoduobei/fundmate#106（GitHub imoyao/fundmate#2034）、CNB #120'  # cross-repo-ref-allow
    assert m._github_refs(body) == ['imoyao/fundmate#2034']
    assert m._github_refs('只有 CNB 自己的卡 duoduobei/fundmate#106') == []
    assert m._github_refs('见 https://github.com/imoyao/fundmate/issues/2034') == [
        'https://github.com/imoyao/fundmate/issues/2034'
    ]


def test_report_summary_counts_local_comments():
    """报告要算出「本地卡上的评论总数」——这是「讨论被静默留在 CNB」的实际规模。

    `#117` 的实测口径：123 张卡 = 111 镜像 + 12 本地，本地卡上 72 条评论。
    本用例只钉**算式**（不钉真实数字，那个数会随看板变化）。
    """
    m = _load_mirror()
    cards = [
        _cnb_card(number=1, labels=[{'name': m.LOCAL_LABEL}], comment_count=3),
        _cnb_card(number=2, labels=[], body='', comment_count=4),
        _cnb_card(number=3, labels=[{'name': m.MIRROR_LABEL}], comment_count=9),
    ]
    report = m.local_card_report(cards)
    assert report['summary']['total'] == 3
    assert report['summary']['mirror'] == 1
    assert report['summary']['local'] == 2
    assert report['summary']['comments_on_local'] == 7
    assert report['summary']['by_kind']['label'] == 1
    assert report['summary']['by_kind']['fallback'] == 1


def test_render_report_shows_local_card_and_flags_guess():
    """渲染出的报告必须能让人看出「这张是猜的」，否则它与「已声明」长得一样。"""
    m = _load_mirror()
    cards = [_cnb_card(number=117, labels=[], body='x', comment_count=3)]
    text = m.render_local_report(m.local_card_report(cards))
    assert 'CNB 本地卡对照报告' in text
    assert '兜底猜测' in text
    assert '#117' in text
    assert '这些讨论不会出现在 GitHub' in text
