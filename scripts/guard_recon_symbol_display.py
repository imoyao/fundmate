#!/usr/bin/env python3
"""守卫：对账工作台模板里的产品身份展示必须走 reconDisplay 契约。

WHY
---
「用户在卡片 / 抽屉标题处看到 ``SH515250`` 而不是『智能汽车』」这类回归**已经发生过两次**。
根因从来不是算错，而是每个组件各写各的插值：有人写 ``{{ g.symbol }}``，有人写
``${group?.symbol || '数据缺失'}``——后端 symbol 是编码（``SH515250`` / ``20|001982``），
产品名在另一个字段里，裸插值必然把编码当成标题印给用户。

约定后的唯一口径（``frontend/src/views/asset/investment/reconcile-workbench/utils/reconDisplay.ts``）：

- **标题**必须经 ``reconGroupTitle(symbol, displayName)``；
- **编码**只允许作为次要事实出现，且必须经 ``reconSymbolCode(...)`` 或
  ``specialSymbolLabel(...)``。

散文约定拦不住「新组件又裸插一次」（同 #1798 路由死链守卫的教训），故把判据钉进 CI。

判据（行级，便于定位；扫 ``reconcile-workbench/**/*.vue`` 的**模板段**）
------------------------------------------------------------------------
- 只看模板段：``<script>`` / ``<style>`` 块整段剔除（脚本里的 ``row.symbol`` 是取数，
  不是展示）；HTML 注释（``<!-- -->``）一并剔除——注释里举例反例不该判红。
- 模板段内出现 ``.symbol``（含 ``?.symbol``）的行，若同一行**不含**
  ``reconGroupTitle(`` / ``reconSymbolCode(`` / ``specialSymbolLabel(``，判红，
  逐条打印 ``file:line: 原文``。
- **非展示绑定不判**：``:key`` / ``v-if`` / ``v-else-if`` / ``v-show`` / ``v-for`` /
  ``:loading`` / ``:disabled`` / ``:class`` / ``:style`` 这些属性值**不产生可见文本**
  （定位、条件、状态），匹配前整段剔除。判据只看「会不会印到屏幕上」——把
  ``<template v-if="it.symbol">`` 判成裸编码，只会逼人往真问题旁边贴豁免。
  ``:symbol="x.symbol"`` 这类**组件 prop 传递**不剔除：它可能被子组件直接渲染，
  由调用点用下面的逃生口显式声明理由。
- **逃生口**：``recon-symbol-allow`` 标记放行「**该行 + 紧随其后的整个标签**」
  （直到那一行出现 ``>`` 为止）。为什么不是只放行同一行：``<Tag :symbol="x.symbol" />``
  的标签内部塞不进 ``<!-- -->``（HTML 合法性），实写时只能把备注写在标签正上方。
  **只用于「编码本身就是内容或只作查询键」的场景**（改前 / 改后编码对比、传给流水表的
  代码查询条件）。脚本尾部打印放行计数与清单——豁免必须可见，不许悄悄堆积
  （同 guard_cross_repo_refs 的豁免台账思路）。

失败态（AGENTS.md 三之二）
--------------------------
扫描不到任何 .vue 文件（根目录不存在 / 目录为空 / 文件全部读不了）时**非 0 退出**
并声明「结论不可信」——**不得**退化成「零命中 = 全部通过」：那正是 CNB #171 的
「拉到 0 张 → 打印已对齐」同族假绿。

刻意不覆盖（宁可漏报也不误报，登记于 guard_rule_registry 的 covered）
----------------------------------------------------------------------
- **非 .vue 的 .ts 构造函数**：标题在 TS 里拼好再传进模板（如 composables 里的
  '#${id} ${symbol}' 模板串）——那是构造侧，模板判据看不见；
- **运行时拼接**：变量名换了（``const s = row.symbol`` 后插 ``{{ s }}``）静态判不出；
- script 段的字符串拼接（见上，模板段之外不判）。
这些留给代码审查与 ``reconDisplay.spec.ts``。

用法
----
    python scripts/guard_recon_symbol_display.py           # 判红即退出 1（CI 用）
    python scripts/guard_recon_symbol_display.py --report  # 另打印台账明细

退出码：0 = 通过；1 = 命中裸插值；2 = 拿不到输入（结论不可信，不得当成通过）。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# 正常跑扫仓库内的对账工作台；`GUARD_RECON_SRC` 只服务于回归用例（造临时目录喂样本）。
DEFAULT_SRC = REPO_ROOT / 'frontend' / 'src' / 'views' / 'asset' / 'investment' / 'reconcile-workbench'

# 判据一：行内出现 `.symbol`（含 `?.symbol`——两者都以「点 + symbol」收尾）。
# `\b` 防止 `symbol_identity` / `symbols` 这类更长标识符被截着命中。
RE_SYMBOL = re.compile(r'\.\s*symbol\b')
# 判据二：同一行必须带着契约函数调用。只认「名字 + 左括号」，
# 只写函数名不调用（import 行在模板段不存在，故无需再排除）。
RE_ALLOWED = re.compile(r'reconGroupTitle\(|reconSymbolCode\(|specialSymbolLabel\(')
# 逃生口标记：写在模板注释里，见文件头「逃生口」一节。
ALLOW_MARKER = 'recon-symbol-allow'
# 非展示绑定：这些属性值只用于定位 / 条件 / 状态，不产生可见文本，匹配前整段剔除。
# 只列「确定不渲染」的：`:label` / `:title` / `:placeholder` / `:symbol` 一律不剔。
RE_NON_DISPLAY_ATTR = re.compile(
    r'(?::key|v-if|v-else-if|v-show|v-for|:loading|:disabled|:class|:style)\s*=\s*"[^"]*"'
    r"|(?::key|v-if|v-else-if|v-show|v-for|:loading|:disabled|:class|:style)\s*=\s*'[^']*'"
)


def strip_sfc_blocks(text: str) -> list[str]:
    """剔除 `<script>` / `<style>` 块，返回**行数不变**的模板段行列表。

    WHY 行数不变：判据是行级的，报红要能对回源文件行号——块内行置空而不是删行。
    `<script>` / `<style>` 标签按 Vue SFC 惯例独占一行；标签所在行整行剔除。
    """
    lines: list[str] = []
    in_block = False
    for raw in text.splitlines():
        if in_block:
            if '</script>' in raw or '</style>' in raw:
                in_block = False
            lines.append('')
            continue
        if '<script' in raw or '<style' in raw:
            in_block = True
            lines.append('')
            continue
        lines.append(raw)
    return lines


def strip_html_comments(line: str, state: dict[str, bool]) -> str:
    """剔掉本行的 HTML 注释部分；跨行注释用 state 传递（同 guard_net_assets_source）。"""
    if state['html']:
        if '-->' in line:
            line = line.split('-->', 1)[1]
            state['html'] = False
        else:
            return ''
    if '<!--' in line:
        before, _, after = line.partition('<!--')
        if '-->' in after:
            line = before + after.split('-->', 1)[1]
        else:
            state['html'] = True
            line = before
    return line


def scan_text(text: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """返回 (命中行 [(行号, 原文)], 放行行 [(行号, 原文)])。"""
    template_lines = strip_sfc_blocks(text)
    hits: list[tuple[int, str]] = []
    exempt: list[tuple[int, str]] = []
    state = {'html': False}
    # 逃生口：标记行放行，并延续到紧随其后的那个标签闭合（含 `>` 的行）为止。
    pending_exempt = False
    for lineno, original in enumerate(template_lines, start=1):
        # 先维护 HTML 注释状态机（否则「标记写在注释里」那行会让后面的行全被当成注释）。
        code_line = strip_html_comments(original, state)
        # 逃生口：标记按**原始行**判（标记本来就写在注释里，剔掉注释就看不见了）。
        if ALLOW_MARKER in original:
            exempt.append((lineno, original.strip()))
            # 只有「不含标签闭合」的备注行才延续到下一个标签：写在标签内部的标记
            # 只放行本行，否则一个标记会把后面整段模板都放行（宁可少放，不可多放）。
            pending_exempt = '>' not in code_line
            continue
        if pending_exempt:
            exempt.append((lineno, original.strip()))
            if '>' in code_line:
                pending_exempt = False
            continue
        # 非展示绑定（:key / v-if / 状态类）不产生可见文本，剔除后再判（见文件头）。
        code_line = RE_NON_DISPLAY_ATTR.sub('', code_line)
        if RE_SYMBOL.search(code_line) and not RE_ALLOWED.search(code_line):
            hits.append((lineno, original.strip()))
    return hits, exempt


def collect_vue_files(root: Path) -> list[Path]:
    return sorted(root.rglob('*.vue'))


def run(src_dir: Path) -> int:
    if not src_dir.is_dir():
        print(f'❌ 拿不到输入：扫描根目录不存在：{src_dir} —— 本轮结论不可信，不得当成通过')
        return 2
    files = collect_vue_files(src_dir)
    if not files:
        print(f'❌ 拿不到输入：{src_dir} 下扫不到任何 .vue 文件 —— 本轮结论不可信，不得当成通过')
        return 2

    total_hits: list[tuple[str, int, str]] = []
    total_exempt: list[tuple[str, int, str]] = []
    unreadable: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            unreadable.append(str(path.relative_to(REPO_ROOT) if REPO_ROOT in path.parents else path))
            continue
        hits, exempt = scan_text(text)
        rel = str(path.relative_to(REPO_ROOT) if REPO_ROOT in path.parents else path)
        total_hits.extend((rel, ln, raw) for ln, raw in hits)
        total_exempt.extend((rel, ln, raw) for ln, raw in exempt)

    if unreadable:
        print('❌ 拿不到输入：以下文件读不了，无法判定 —— 本轮结论不可信，不得当成通过：')
        for name in unreadable:
            print(f'  {name}')
        return 2

    for rel, ln, raw in total_hits:
        print(f'❌ {rel}:{ln}: {raw}')
    if total_hits:
        print(
            f'共 {len(total_hits)} 处裸 .symbol 插值 —— 标题请走 '
            f'reconGroupTitle(symbol, displayName)，编码走 reconSymbolCode / specialSymbolLabel'
        )

    # 豁免台账：放行必须可见，不许悄悄堆积（每次都打印计数与清单）。
    if total_exempt:
        print(f'\n🟡 recon-symbol-allow 放行 {len(total_exempt)} 处：')
        for rel, ln, raw in total_exempt:
            print(f'  {rel}:{ln}: {raw}')
    else:
        print('🟡 recon-symbol-allow 放行 0 处')

    if total_hits:
        return 1
    print(f'✅ 对账工作台模板无裸 .symbol 插值（扫了 {len(files)} 个文件）')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='对账工作台产品身份展示契约守卫（模板段 .symbol 必须经 reconDisplay 契约）'
    )
    parser.add_argument('--report', action='store_true', help='额外打印台账明细（退出码语义不变）')
    args = parser.parse_args(argv)
    override = os.environ.get('GUARD_RECON_SRC')
    src = Path(override) if override else DEFAULT_SRC
    rc = run(src)
    if args.report and rc == 0:
        print(f'--report：扫描根 {src}，共 {len(collect_vue_files(src))} 个 .vue，无命中、无放行')
    return rc


if __name__ == '__main__':
    sys.exit(main())
