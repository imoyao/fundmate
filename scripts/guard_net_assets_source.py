#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：净资产一律取 ``/api/summary/`` 的 ``net_assets_cny`` 直出，页面层不得现算（#119 / #2883）。

WHY
---
#119 把「净资产 / 总负债取 ``/api/summary/`` 直出、前端不做二次计算」立为判据，
首页卡 ``WelcomeAssetBoard.vue`` 已按此实现（``props.summary?.net_assets_cny``）。
但资产全景页左卡 ``OverviewAssetsCard.vue`` 漏了这一处：页面自己写
``totalAssets - totalLiabilities``，而 ``panorama/index.vue`` 只从 ``getSummary()``
取了 ``total_assets_cny`` / ``total_liabilities_cny``，``net_assets_cny`` 从未读出。

**当前不会显示错**——后端 ``net_worth`` 就等于 ``total_assets - total_liabilities``。
真正的问题是口径漂移无人告警：一旦净资产纳入不可估值资产调整、汇率折算或取整策略，
这一处会与首页卡、与 ``/api/summary/`` 三处不一致，且页面层的减法**不经过任何契约测试**。
更贵的是它成了一个可以照抄的坏样例：同一指标两条来源，后人改口径必然只改一处。

散文规范拦不住「顺手再减一次」（#1798 路由死链守卫同款教训），故把判据钉进 CI。

判据（逐行正则，纯标准库，扫 ``frontend/src`` 全量）
----------------------------------------------------
- R1 **命名族精确命中**：``totalAssets - totalLiabilities`` 及其下划线 / ``props.`` 前缀
  变体（``total_assets_cny - total_liabilities_cny`` 等）；
- R2 **词根命中（防换个变量名绕过）**：减法两侧分别含 ``asset`` / ``liabilit`` 词根，
  如 ``foo_assets - bar_liabilities``。
- **注释不算**：行注释（``//``）、块注释（``/* */``）、Vue 模板注释（``<!-- -->``）
  与 HTML 注释里举例说明这个表达式，都不构成违规（本守卫自己的说明文字即属此类）。

刻意不覆盖（宁可漏报也不误报，与 ``check_router_links.mjs`` 同一取舍）
--------------------------------------------------------------------
- 把两值先赋给无词根别名再相减（``const a = ...; const b = ...; a - b``）——静态看不出语义；
- 反向的 ``totalLiabilities - totalAssets``（那是净负债，不是净资产）；
- **合法的各自使用**：``CategoryBalanceTable.vue`` 把 ``totalAssets`` / ``totalLiabilities``
  分别当占比分母，两值不出现在同一个减法里，不命中；
- 不判数值是否真的相等、不判后端口径对不对（那是契约测试与代码审查的事）。

用法
----
    python scripts/guard_net_assets_source.py                  # 扫 frontend/src 全量
    python scripts/guard_net_assets_source.py a.vue b.ts       # 只扫指定文件

退出码：0 = 通过；1 = 命中现算；2 = 拿不到输入（结论不可信，不得当成通过）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "frontend" / "src"
SCAN_SUFFIXES = {".vue", ".ts", ".tsx", ".js", ".jsx"}

# R1：命名族精确命中。左侧总资产族、右侧总负债族，中间允许任意空白的减号。
# 允许 `props.` / `sum.xxx.` 等成员前缀；词尾用 \b 防止 `totalAssetsExtra` 之类误命中。
_ASSET_NAMES = r"(?:totalAssets|total_assets_cny|total_assets|totalAsset)"
_LIAB_NAMES = r"(?:totalLiabilities|total_liabilities_cny|total_liabilities|totalLiab)"
_MEMBER_PREFIX = r"(?:[A-Za-z_$][\w$]*\.)*"
R1_NAMED = re.compile(
    rf"\b{_MEMBER_PREFIX}{_ASSET_NAMES}\b\s*-\s*{_MEMBER_PREFIX}{_LIAB_NAMES}\b"
)

# R2：词根命中（防改名绕过）。两侧各自是一个含 asset / liabilit 词根的标识符链。
R2_ROOTS = re.compile(
    r"\b[A-Za-z_$][\w$.]*asset[\w$.]*\s*-\s*[A-Za-z_$][\w$.]*liabilit[\w$.]*",
    re.IGNORECASE,
)


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def iter_files(roots: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in roots:
        p = Path(raw)
        if p.is_file():
            out.append(p)
            continue
        for f in sorted(p.rglob("*")):
            if f.is_file() and f.suffix in SCAN_SUFFIXES:
                out.append(f)
    return out


def _strip_comments(line: str, state: dict[str, bool]) -> str:
    """剔掉本行里的注释部分，返回仍可能含代码的部分；跨行块注释用 state 传递。

    保守处理：命中不确定时宁可保留（会漏报，不会误报）。URL 里的 `//` 靠
    「前面是 :」排除，避免把 `https://...` 之后的代码整段吃掉。
    """
    # Vue / HTML 注释块
    if state["html"]:
        if "-->" in line:
            line = line.split("-->", 1)[1]
            state["html"] = False
        else:
            return ""
    if "<!--" in line:
        before, _, after = line.partition("<!--")
        if "-->" in after:
            line = before + after.split("-->", 1)[1]
        else:
            state["html"] = True
            line = before

    # JS / CSS 块注释
    if state["block"]:
        if "*/" in line:
            line = line.split("*/", 1)[1]
            state["block"] = False
        else:
            return ""
    if "/*" in line:
        before, _, after = line.partition("/*")
        if "*/" in after:
            line = before + after.split("*/", 1)[1]
        else:
            state["block"] = True
            line = before

    # 行注释：只认前面不是 ':' 的 //（避开 URL）
    m = re.search(r"(?<!:)//", line)
    if m:
        line = line[: m.start()]
    return line


def scan_line(line: str, state: dict[str, bool]) -> re.Match[str] | None:
    """本行（剔注释后）是否命中 R1 / R2；返回命中对象供报错回显。

    注意：``state`` 会被就地更新（跨行块注释），所以每行**只能调用一次**。
    """
    code = _strip_comments(line, state)
    return R1_NAMED.search(code) or R2_ROOTS.search(code)


def main(argv: list[str]) -> int:
    roots = argv[1:] or [str(DEFAULT_ROOT)]
    files = iter_files(roots)
    if not files:
        print("❌ 拿不到输入：未扫描到任何前端源码文件 —— 本轮结论不可信，不得当成通过")
        return 2

    violations: list[tuple[str, int, str, str]] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        state = {"block": False, "html": False}
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = scan_line(line, state)
            if match:
                violations.append((_rel(f), lineno, match.group(0).strip(), line.strip()))

    if not violations:
        print(f"OK: 页面层未发现净资产现算（扫描 {len(files)} 个前端源码文件，净资产一律走 net_assets_cny 直出）")
        return 0

    print(
        "ERROR: 发现 %d 处页面层现算净资产，违反 #119「净资产取 /api/summary/ 直出、前端不做二次计算」："
        % len(violations),
        file=sys.stderr,
    )
    for rel, lineno, expr, snippet in violations:
        print(f"  {rel}:{lineno}  命中 {expr}\n         源码：{snippet[:120]}", file=sys.stderr)
    print(
        "\n  正解：由 /api/summary/ 的 net_assets_cny 直出并用 prop 透传"
        "（对照 frontend/src/views/welcome/components/WelcomeAssetBoard.vue）；\n"
        "        不要在页面层写「总资产 − 总负债」——两条路径当前数值相同，口径一变就分叉。\n"
        "  确属不相干的减法（如两值分别作占比分母）→ 让它们不出现在同一个减法表达式里即可。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
