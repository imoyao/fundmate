# -*- coding: utf-8 -*-
"""GitHub → CNB issue 增量镜像脚本的回归网（源 issue #2 的「要不要做成常驻同步」）。

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
4. **格式冻结**：正文头部与存量镜像卡（CNB #5，GitHub #783）逐字节一致——
   这条是防止「格式漂移」的硬钉子，改格式必须是有意识的决定。

全程 **零网络、零写入**，只跑纯函数。
"""

import importlib.util
import sys
from pathlib import Path

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


def test_header_matches_legacy_mirror_card():
    """正文头部必须与 2026-10-11 全量同步的存量镜像卡（CNB #5 ← GitHub #783）一致。

    存量卡的字段顺序 / 措辞 / 全角空格都钉在这里；改这里的格式等于让两侧镜像卡
    出现两种长相，必须是有意识的决定，而不是顺手重构的副作用。
    """
    m = _load_mirror()
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
            '>',
            '> ⚠️ 本卡为只读镜像，正式讨论与状态变更请回到 GitHub 原卡；CNB 侧改动不会自动回流。',
            '',
            '---',
            '',
            '正文 **加粗**',
        ]
    )
    assert body == expected_header


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
