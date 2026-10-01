#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：输入类控件的焦点**不得**使用 `--focus-ring`（#1815）。

WHY
---
`--focus-ring`（`frontend/src/style/colors.css`）是**无障碍用的双环**指示器：
`0 0 0 2px 间隙 + 0 0 0 4px 品牌实环`。它曾被拼进输入框基线的焦点表达式
（`element-plus.scss` 的 `--input-focus-shadow`），于是**一个聚焦的输入框叠出三层描边**：
1px 品牌内描边 + 2px 间隙 + 4px 实环 —— 正是用户反复反馈的「输入框一聚焦，描边好几层」。

当年登录页 / 找回密码 / OCR 弹窗各自把令牌覆盖成「1px + 12% 柔光」绕开了它，所以问题只在
**局部**被治好（"应该已经解决过，但没全局解决"），而默认路径一直带病：`EditAccountDialog`
等所有没覆盖令牌的页面都在吃三层环。

#1815 起的约定（见 `frontend/design.md`「输入框基线契约」）：

- 输入类控件（`el-input` / `el-textarea` / `el-select`）焦点走 `--input-focus-shadow`
  的**柔光单环**（`1px 品牌内描边 + 3px 12% 品牌柔光`）；
- `--focus-ring` 只用于**非输入类**的键盘焦点（按钮 / 链接 / 自定义控件 / 容器 `:focus-within`）。

本守卫把这条边界钉死：基线或页面覆盖里，只要 `--input-focus-shadow` 的值引用了
`--focus-ring` 即变红。另校验基线自身仍是「可见焦点」（含 `inset` 内描边）。

用法
----
    python scripts/guard_input_focus.py

退出码：0 = 通过；1 = 命中栅栏。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOT = REPO_ROOT / 'frontend' / 'src'
SCAN_SUFFIXES = {'.vue', '.css', '.scss'}

# 输入基线单一来源：默认值与「必须可见」的校验点
BASELINE_REL = 'frontend/src/style/element-plus.scss'
BASELINE_FILE = REPO_ROOT / BASELINE_REL

FORBIDDEN_TOKEN = '--focus-ring'
REQUIRED_IN_BASELINE = 'inset'

DECL_RE = re.compile(r'--input-focus-shadow\s*:\s*([^;]+);')

# 注释里的举例不算违规：扫描前把块注释与行注释抹成等长空白（保留行号）
BLOCK_COMMENT_RE = re.compile(r'/\*.*?\*/', re.S)
LINE_COMMENT_RE = re.compile(r'//[^\n]*')


def _strip_comments(text: str) -> str:
    text = BLOCK_COMMENT_RE.sub(lambda m: re.sub(r'[^\n]', ' ', m.group(0)), text)
    return LINE_COMMENT_RE.sub(lambda m: ' ' * len(m.group(0)), text)


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """返回 [(行号, 违规的声明值)]。"""
    try:
        raw = path.read_text(encoding='utf-8')
    except OSError:
        return []
    text = _strip_comments(raw)
    hits: list[tuple[int, str]] = []
    for match in DECL_RE.finditer(text):
        value = ' '.join(match.group(1).split())
        if FORBIDDEN_TOKEN in value:
            line = text.count('\n', 0, match.start()) + 1
            hits.append((line, value))
    return hits


def main() -> int:
    violations: list[str] = []

    for path in sorted(SCAN_ROOT.rglob('*')):
        if path.suffix not in SCAN_SUFFIXES or not path.is_file():
            continue
        for line, value in _scan_file(path):
            rel = path.relative_to(REPO_ROOT).as_posix()
            violations.append(f'  {rel}:{line}  --input-focus-shadow: {value}')

    # 基线自身必须还能看见焦点（含 inset 内描边），否则「环没了」是另一种回归
    baseline_raw = BASELINE_FILE.read_text(encoding='utf-8') if BASELINE_FILE.exists() else ''
    baseline_values = [
        ' '.join(m.group(1).split()) for m in DECL_RE.finditer(_strip_comments(baseline_raw))
    ]
    if not baseline_values:
        violations.append(f'  {BASELINE_REL}  缺少 --input-focus-shadow 基线声明')
    elif REQUIRED_IN_BASELINE not in baseline_values[0]:
        violations.append(
            f'  {BASELINE_REL}  基线焦点表达式缺少 `{REQUIRED_IN_BASELINE}`（焦点将不可见）：'
            f'{baseline_values[0]}'
        )

    if not violations:
        print('OK: 输入类焦点未使用 --focus-ring（单环基线完好）')
        return 0

    print('ERROR: 输入类控件的焦点不得使用 --focus-ring（会与内描边叠成三层描边）：')
    print('\n'.join(violations))
    print(
        '\n  约定见 frontend/design.md「输入框基线契约」：\n'
        '    · 输入类控件：--input-focus-shadow 用「1px 内描边 + 3px 12% 品牌柔光」单环；\n'
        f'    · {FORBIDDEN_TOKEN}：只用于非输入类的键盘焦点（按钮 / 链接 / 自定义控件 / 容器 :focus-within）。'
    )
    return 1


if __name__ == '__main__':
    sys.exit(main())
