# -*- coding: utf-8 -*-
"""#2136 大类取值守卫：major_category 只能用权威词表里的值。

背景：#2136 的裁决过程里挖出一个**活的错值**——`ledger_service` 的三处账户现金
查询按 `Asset.major_category == 'current'` 过滤，而 `'current'`：

- 不在权威词表 `ASSET_CATEGORY_LABELS` 里（词表只有 `cash`）；
- 也不是任何写入路径会产出的值（前端录入表单写的是 `cash`）。

⇒ 账户现金恒读成 0，活期余额与类现金合计静默漏算。这类 bug 的特点是
**没有任何报错**：值合法地传进了 SQL，只是永远匹配不到行。

本文件是**词表守卫**，把「取值必须出自词表」这条规矩钉死，覆盖三个方向：

1. 词表本身不得混入词表外的历史错值（`'current'`）；
2. 后端源码里凡是拿 `major_category` 与字面量比较的地方，取值必须 ∈ 词表；
3. 前端标签表的键必须 ∈ 词表（防「前后端各维护一份、慢慢漂」）。

方向 2 是本卡的根因防线：以后谁再写 `== 'current'`（或任何词表外的值），
这里直接红，而不是等用户发现账户页的活期余额是 0。
"""

import re
from pathlib import Path

from app.core.asset_types import (
    ASSET_CATEGORY_LABELS,
    MAJOR_CATEGORY_CASH,
    MAJOR_CATEGORY_VALUES,
    is_valid_major_category,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_CONSTANTS = BACKEND_ROOT.parent / 'frontend' / 'src' / 'constants' / 'index.ts'

# 迁移文件按定义就是要提到历史错值（它负责把那个值归一掉），故豁免。
_EXEMPT_FILES = {'app/core/migrations.py'}

# `major_category` 与字面量比较（== / != / = / in / not_in）——只看比较语境，
# 避免把 `normalize_major_category()`、列名、字典键等误当成取值。
_COMPARISON_RE = re.compile(
    r"""major_category\s*(?:==|!=|=|in|not_in)\s*[\(\[]?\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]""",
)


def test_vocabulary_has_no_legacy_wrong_value():
    """词表里不得再有 'current'——它就是 #2136 那个错值的来源。"""
    assert 'current' not in ASSET_CATEGORY_LABELS, "词表混入了历史错值 'current'（应统一为 'cash'）"
    assert MAJOR_CATEGORY_CASH == 'cash'
    assert MAJOR_CATEGORY_CASH in ASSET_CATEGORY_LABELS
    assert MAJOR_CATEGORY_VALUES == frozenset(ASSET_CATEGORY_LABELS.keys())


def test_is_valid_major_category():
    assert is_valid_major_category('cash') is True
    assert is_valid_major_category('liability') is True
    assert is_valid_major_category('current') is False
    assert is_valid_major_category('not_a_category') is False
    assert is_valid_major_category('') is False
    assert is_valid_major_category(None) is False


def test_backend_major_category_literals_are_in_vocabulary():
    """后端所有 `major_category` 比较用的字面量必须 ∈ 权威词表。"""
    offenders = []
    for path in sorted((BACKEND_ROOT / 'app').rglob('*.py')):
        rel = path.relative_to(BACKEND_ROOT).as_posix()
        if rel in _EXEMPT_FILES:
            continue
        text = path.read_text(encoding='utf-8')
        for value in _COMPARISON_RE.findall(text):
            if value not in MAJOR_CATEGORY_VALUES:
                offenders.append(f'{path.relative_to(BACKEND_ROOT)}: {value!r}')
    assert not offenders, '以下 major_category 取值不在权威词表内（读侧会永远匹配不到行）：\n' + '\n'.join(offenders)


def test_frontend_major_category_labels_subset_of_vocabulary():
    """前端大类标签表的键必须 ⊆ 后端词表（防两处各维护一份慢慢漂）。"""
    text = FRONTEND_CONSTANTS.read_text(encoding='utf-8')
    block = text.split('MAJOR_CATEGORY_LABELS', 1)[1]
    block = block.split('}', 1)[0]
    keys = set(re.findall(r'^\s{2}([A-Za-z_][A-Za-z0-9_]*):', block, re.MULTILINE))
    assert keys, '没解析到前端 MAJOR_CATEGORY_LABELS 的键，解析逻辑该更新了'
    unknown = sorted(k for k in keys if k not in MAJOR_CATEGORY_VALUES)
    assert not unknown, f'前端用了后端词表里没有的大类：{unknown}'
