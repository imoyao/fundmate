#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守门：投顾组合进 positions **必须** balance 模式——这条口径要真的在代码里（D70 / #2740）。

WHY（缺口是真实发生过的，不是假想）
------------------------------------
`core/asset_types.py` 曾写「manager / portfolio **不进 positions**，仅 watchlist 引用」。
那句话**没有任何代码执行它**，于是现状变成「能记进去、但记了是坏的」：

- `asset_type='portfolio'` 落在默认的 `nav` 模式（`domains/positions/models.py` 的默认值），
- 组合没有份额、没有净值 ⇒ `position_price` job 不会给它定价 ⇒ **市值恒为 0**，
- 而 `has_position` 只看 positions 是否命中 ⇒ 详情页照常渲染一张「持仓 0 元」的卡。

失败形态是**静默**的：没有任何报错，用户只是看到一个说不通的数字。所以判据不能靠
「约定没人这么写」，必须钉在写入路径上。

判据（三条，全部静态可判）
--------------------------
1. **写入侧**：`backend/app/services/position_service.py` 的 `process_buy_or_deposit` 内，
   必须有一个 `if` 语句，其条件同时满足——
   a) 出现 `'portfolio'` 字面量；b) 含「非 balance」判定（`not is_balance`，或
   `... != ValuationMode.BALANCE` / `... == ValuationMode.NAV` 这类比较）；
   c) 该分支体内 `raise`。
   缺 a 或 b ⇒ 约束被删；缺 c ⇒ 只剩注释不看结果。任一不满足即红。
2. **规范侧**：`backend/app/core/asset_types.py` 的注释里
   - **不得**再出现「portfolio 不进 positions」这类旧规则（同行同时出现 `portfolio`
     与 `不进 positions` ⇒ 红；旧表述长这样，且正是把后来者带偏的那一句）；
   - 必须有一处注释**同时**说明 portfolio 进 positions 与 balance（同一注释块内 ±3 行
     出现 `portfolio` 与 `balance` ⇒ 满足），否则说明口径只剩代码、文档又会漂回去。
3. **决策侧**：`docs/spec/decisions.md` 必须存在 D70 行，且该行含 `portfolio` 与 `balance`。
   决策条目被删/被改写成不含这两者 ⇒ 红：代码里有一条没出处的约束。

退出码
------
- 0：通过；
- 1：有违规；
- 2：输入不可信（文件缺失 / 语法错误 / 找不到目标函数）——**不得**退化成「通过」
  （「拿不到输入 ≠ 输入为空」，同 CNB #171 那类假绿）。

边界（有意不覆盖）
------------------
- **不判运行时行为**：`portfolio + nav` 真的被拒绝由
  `backend/tests/domains/test_positions.py::TestPortfolioBalanceMode` 管；本守卫只保证
  「那段判据还在原处」，即接线在、位置对。
- **不判前端**：买入表单是否提交 `valuation_mode='balance'` 由
  `frontend/src/components/QuickEntry/__tests__/buyFormPayload.spec.ts` 钉住。
- **不判 `assets` 表**：投顾组合是否也能记成静态资产属另一条口径（D70 只谈 positions）。
- **只认 `process_buy_or_deposit` 这一个写入入口**：本仓手动记账 / 导入 / 编辑三条路径
  都汇到这里。若将来出现第二入口而不经过它，先扩判据再合并。

用法
----
    python scripts/guard_portfolio_balance_mode.py            # 在仓库根执行（CI）
    python scripts/guard_portfolio_balance_mode.py --root .   # 显式指定根目录
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Iterable

POSITION_SERVICE = 'backend/app/services/position_service.py'
ASSET_TYPES = 'backend/app/core/asset_types.py'
DECISIONS = 'docs/spec/decisions.md'

#: 写入路径上的目标函数；D70 的约束必须落在它体内。
WRITE_FUNC = 'process_buy_or_deposit'

#: 违规的旧表述标记：出现在「提到 portfolio 的注释行」上即视为回归。
STALE_PHRASES = ('不进 positions', '不进 positions 表', '一律不进 positions')

#: 决策条目标识（decisions.md 表首列）。
DECISION_ID = 'D70'


class InputError(Exception):
    """输入不可信：调用方必须以退出码 2 收场，而不是当成「没问题」。"""


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except OSError as exc:
        raise InputError(f'读不到 {path}: {exc}') from exc


def _parse(path: Path, source: str) -> ast.Module:
    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise InputError(f'{path} 语法错误：{exc}') from exc


def _string_constants(node: ast.AST) -> list[str]:
    """条件表达式里出现的全部字符串字面量。"""
    return [
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]


def _identifier_names(node: ast.AST) -> set[str]:
    """条件表达式里出现的全部标识符（含属性访问的根名与 attr 名）。"""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def _is_balance_negated(node: ast.AST, names: set[str]) -> bool:
    """条件里是否表达了「不是 balance」。

    认两种写法，都是本仓现存的直白形态：
    - `not is_balance`（写入路径当前写法）；
    - `... != ValuationMode.BALANCE` / `... == ValuationMode.NAV`（等价明确写法）。
    """
    for child in ast.walk(node):
        if isinstance(child, ast.UnaryOp) and isinstance(child.op, ast.Not):
            if 'is_balance' in _identifier_names(child):
                return True
        if isinstance(child, ast.Compare):
            operands = [child.left, *child.comparators]
            texts = [ast.unparse(operand) for operand in operands]
            joined = ' '.join(texts)
            if 'BALANCE' in joined:
                if any(isinstance(op, ast.NotEq) for op in child.ops):
                    return True
                if any(isinstance(op, ast.Eq) for op in child.ops) and 'NAV' in joined:
                    return True
    return False


def _has_raise(node: ast.AST) -> bool:
    """分支体（含嵌套）里是否真的抛错——只写注释/只打日志不算执行约束。"""
    return any(isinstance(child, ast.Raise) for child in ast.walk(node))


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def check_write_guard(source: str, path: Path) -> list[str]:
    """判据 1：`process_buy_or_deposit` 里必须有「portfolio 非 balance ⇒ raise」。"""
    tree = _parse(path, source)
    func = _find_function(tree, WRITE_FUNC)
    if func is None:
        # 找不到目标函数 = 输入不可信，不是「没问题」：写入路径改名/搬迁后必须同步本守卫。
        raise InputError(f'{path} 里找不到 {WRITE_FUNC}（写入路径改名/搬迁后请同步本守卫）')

    for node in ast.walk(func):
        if not isinstance(node, ast.If):
            continue
        strings = _string_constants(node.test)
        if 'portfolio' not in strings:
            continue
        names = _identifier_names(node.test)
        if not _is_balance_negated(node.test, names):
            continue
        if _has_raise(node):
            return []

    return [
        f'{path.name}:{func.lineno} {WRITE_FUNC}：'
        '缺少「portfolio 且非 balance ⇒ raise」的写入约束——'
        '组合落成 nav 模式后市值恒为 0，且没有任何报错（D70 / #2740）'
    ]


def _comment_lines(text: str) -> Iterable[tuple[int, str]]:
    """逐行取出注释行（`#` 开头），带上 1-based 行号。

    刻意不做「字符串里的 `#` 也算注释」这种猜测：本文件没有含 `#` 的字符串字面量，
    宁可漏一点也不要误判（判据宁窄勿宽）。
    """
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith('#'):
            yield index, stripped


def check_asset_types_text(text: str, path: Path) -> list[str]:
    """判据 2：旧表述不许回归，且新口径必须写在注释里。"""
    if "'portfolio'" not in text:
        raise InputError(f'{path} 里找不到 portfolio 条目（标签映射被改名？请同步本守卫）')

    findings: list[str] = []
    comments = list(_comment_lines(text))

    for lineno, line in comments:
        if 'portfolio' not in line:
            continue
        for phrase in STALE_PHRASES:
            if phrase in line:
                findings.append(
                    f'{path.name}:{lineno} 出现旧规则「{phrase}」——'
                    'D70 已改为「portfolio 进 positions，且必须 balance」'
                )

    # 新口径：某条提到 portfolio 的注释，其 ±3 行内必须同时提到 balance。
    portfolio_lines = [lineno for lineno, line in comments if 'portfolio' in line]
    accepts_balance = any(
        any(
            'balance' in line
            for lineno2, line in comments
            if abs(lineno2 - lineno) <= 3
        )
        for lineno in portfolio_lines
    )
    if not accepts_balance:
        findings.append(
            f'{path.name}: portfolio 的注释里没有提到 balance——'
            '代码里强制 balance、文档里不写，下一个人照样会按旧口径写'
        )

    return findings


def check_decisions_text(text: str, path: Path) -> list[str]:
    """判据 3：D70 决策条目必须在，且写明 portfolio + balance。"""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith('|'):
            continue
        if DECISION_ID not in stripped:
            continue
        low = stripped.lower()
        if 'portfolio' in low and 'balance' in low:
            return []
        return [
            f'{path.name}: {DECISION_ID} 行没有同时写明 portfolio 与 balance——'
            '决策条目与代码约束必须一一对应'
        ]
    return [f'{path.name}: 找不到 {DECISION_ID} 决策条目——代码里有一条没出处的约束']


def run(root: Path) -> int:
    """扫一遍并打印结论。返回值即进程退出码。"""
    service_path = root / POSITION_SERVICE
    asset_types_path = root / ASSET_TYPES
    decisions_path = root / DECISIONS

    for path in (service_path, asset_types_path, decisions_path):
        if not path.is_file():
            raise InputError(f'找不到 {path}（不在仓库根执行？）')

    findings: list[str] = []
    service_source = _read(service_path)
    findings += check_write_guard(service_source, service_path)
    findings += check_asset_types_text(_read(asset_types_path), asset_types_path)
    findings += check_decisions_text(_read(decisions_path), decisions_path)

    if findings:
        print(f'❌ 投顾组合 balance 口径不通过（{len(findings)} 处）：', file=sys.stderr)
        for item in findings:
            print(f'  - {item}', file=sys.stderr)
        return 1

    print(
        '✅ 投顾组合 balance 口径通过：'
        f'{POSITION_SERVICE} 的写入约束在、{ASSET_TYPES} 的表述是新的、{DECISIONS} 有 {DECISION_ID}'
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK，直接 print 中文/符号会 UnicodeEncodeError 崩掉——
    # 守门在本地跑崩 = 守门失效（同 guard_pro_endpoint_registry.py）。
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is not None:
            try:
                reconfigure(encoding='utf-8')
            except (AttributeError, ValueError, OSError):
                pass

    parser = argparse.ArgumentParser(description='投顾组合 balance 口径守门（D70 / #2740）')
    parser.add_argument(
        '--root',
        default=None,
        help='仓库根目录，默认为本脚本的上一级（scripts/ 的父目录）',
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    try:
        return run(root)
    except InputError as exc:
        print(f'❌ 输入不可信：{exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
