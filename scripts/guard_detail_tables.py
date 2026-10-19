#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：详情页 dense 表格必须走 `.detail-table` 共享约定（源 CNB #553）。

WHY
---
产品详情页 5 处手写 `<table>`（多账户持仓 / 行业配置 / 持仓明细 / ETF 对比 / 十大权重）
曾经各写各的：padding 有 `6px var(--space-2)` / `space-2 space-1` / `space-2 space-2` 三种，
分隔线有「首行不加」与「每行都加」两种，表头字重与颜色三套，
数字列有「整表 tabular-nums」「`.xx__num`」「`.ratio`」「默认 right」四套。
每一处单看都合理，五处放在一起就「看起来不像一家人」。

`frontend/src/style/_detail-table.scss` 把这些收成单一来源。本守卫负责让**第六处**长不出来：

1. `RULE 1` 详情页（`frontend/src/views/product/**`）里的 `<table>` 必须带 `detail-table` 类。
2. `RULE 2` 自有样式里不得再手抄一份「表格基线」——即 **同时**出现
   `width: 100%` + `border-collapse: collapse` + 非零 `padding` 三件套。
   存量按**文件级基线**冻结，收编一个少一个。
3. `RULE 3` 详情页里不得自写数字列对齐（`.xx__num { text-align: right }` 之类）——
   数字列对齐只能来自 `.detail-table__num`。同 `guard_segmented.py` 的教训：
   第五处会长出来，所以要在第四处就堵死。

**刻意不做**：起初想过「全仓 `<table>` 必须带 `detail-table` 或 `el-table`」，但它会把
11 处与详情页无关的资产 / 探市 / 自选表格一起判成待治理。那 11 处是另一种密度语义
（`TransactionTable` 是 44px 行高的 el-table，`CategoryBalanceTable` 是分类余额表），
**先判定合法性再收编，不能反过来**。故 RULE 1 只作用于详情页，全仓那层用 RULE 2
（问「有没有第二份基线」）而不是「有没有类名」。

用法
----
    python scripts/guard_detail_tables.py            # 扫描（CI）
    python scripts/guard_detail_tables.py a.vue      # 只扫指定文件（合成样例 / 局部验证）
    python scripts/guard_detail_tables.py --freeze   # 重写存量基线（人工确认后）

退出码：0 = 通过；1 = 命中栅栏；2 = 拿不到输入（结论不可信，**不得**当成通过）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "frontend" / "src"
DETAIL_ROOT = SRC_ROOT / "views" / "product"
BASELINE = REPO_ROOT / "scripts" / "guard_detail_tables.baseline.json"

SCAN_SUFFIXES = {".vue"}
SKIP_MARKER = "detail-table-allow"

TABLE_TAG_RE = re.compile(r"<table\b([^>]*)>", re.IGNORECASE)
CLASS_ATTR_RE = re.compile(r"""\bclass\s*=\s*"([^"]*)\"""")
DYNAMIC_CLASS_RE = re.compile(r""":class\s*=""")
STYLE_BLOCK_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL)

# RULE 2：「手抄表格基线」的三件套。三件同时出现才算——只写 width、只写 padding 的是
# 这张表自己的布局，不是基线，判进来就是误报（同 guard_col_divider「不要一刀切」）。
BASE_WIDTH_RE = re.compile(r"^\s*width\s*:\s*100%", re.MULTILINE)
BASE_COLLAPSE_RE = re.compile(r"^\s*border-collapse\s*:\s*collapse", re.MULTILINE)
BASE_PADDING_RE = re.compile(r"^\s*padding\s*:\s*[^;]+;", re.MULTILINE)

# RULE 3：详情页自写的「数字列右对齐」——选择器带数字语义类名 + 块内有 text-align: right。
NUM_SELECTOR_RE = re.compile(
    r"\.([A-Za-z][\w-]*(?:num|ratio|weight|rank|mono)[\w-]*)\s*\{[^}]*text-align\s*:\s*right",
)

HINTS = {
    "missing-class": (
        "详情页的 <table> 加 `detail-table`（数字列加 `detail-table__num`），"
        "见 frontend/src/style/_detail-table.scss"
    ),
    "second-baseline": (
        "别在组件里再手抄一份表格基线（width/border-collapse/padding 三件套）；"
        "详情页用 `.detail-table`，其余表格先判定合法性再收编"
    ),
    "num-align": "数字列对齐只能来自 `.detail-table__num`，不要在组件里自写 text-align: right",
}


def _rel(p: Path) -> str:
    """仓库内文件给相对路径，仓库外（回归网的临时样例目录）保留原样。

    不在这里 `relative_to` 硬崩：那会把「样例文件不在仓库里」变成一次
    `ValueError` 崩溃，而崩溃的退出码是 1 —— 与「命中栅栏」撞车，
    测试会把它读成「守卫真的拦住了」（假绿）。
    """
    try:
        return p.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(p)


def _iter_files(targets: list[str]) -> list[Path]:
    if targets:
        files: list[Path] = []
        for raw in targets:
            p = Path(raw)
            if not p.is_absolute():
                p = REPO_ROOT / p
            if p.suffix in SCAN_SUFFIXES and p.is_file():
                files.append(p)
        return files
    if not SRC_ROOT.is_dir():
        return []
    return [p for p in SRC_ROOT.rglob("*.vue") if "node_modules" not in p.parts and p.is_file()]


def _is_detail_page(path: Path) -> bool:
    """是不是详情页的组件。

    两种命中形态，**必须都判**：
    - 仓库内的真实路径（CI / 手动扫描走这条）；
    - 路径里带 `views/product/` 的样例文件（回归网在临时目录里造样例走这条）。

    只判第一种时，临时目录里的样例永远判不进详情页 ⇒ 那条用例**恒绿且毫无意义**，
    而它看起来只是在「确认守卫放行正常」。这类假绿比漏判更贵（见文件头 WHY）。
    """
    if DETAIL_ROOT.resolve() in path.resolve().parents:
        return True
    parts = path.parts
    return any(
        parts[i] == "views" and parts[i + 1] == "product"
        for i in range(len(parts) - 1)
    )


def _has_detail_table(attrs: str) -> bool:
    """`<table>` 的 class 里有没有 `detail-table`。

    两种放行：字面量 class 含 `detail-table`（含变体 `--fixed`，前缀匹配）；
    或动态绑定 `:class`（类名运行时算出来，静态判据看不见，猜它会误报）。
    """
    if DYNAMIC_CLASS_RE.search(attrs):
        return True
    for m in CLASS_ATTR_RE.finditer(attrs):
        if any(tok.startswith("detail-table") for tok in m.group(1).split()):
            return True
    return False


def _first_lineno(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def scan_file(path: Path) -> list[tuple[str, int, str]]:
    """返回 [(rule, lineno, line)]。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    hits: list[tuple[str, int, str]] = []
    # 目录身份走**同一处定义**（`_is_detail_page`）：只为 `rel` 的展示不做路径解析，
    # 但「是不是详情页」必须按真实路径判，否则回归网的临时样例目录永远判不进来
    # ——那时守卫会「绿得毫无道理」，而这正是 #171 那类假绿的温床。
    is_detail = _is_detail_page(path)
    lines = text.splitlines()

    # RULE 1：详情页的 <table> 必须带共享类
    if is_detail:
        for m in TABLE_TAG_RE.finditer(text):
            lineno = _first_lineno(text, m.start())
            line = lines[lineno - 1] if lineno - 1 < len(lines) else ""
            if SKIP_MARKER in line:
                continue
            if not _has_detail_table(m.group(1)):
                hits.append(("missing-class", lineno, line.strip()))

    styles = "\n".join(m.group(1) for m in STYLE_BLOCK_RE.finditer(text))
    if not styles.strip():
        return hits

    # RULE 2：自有样式里再手抄一份表格基线（三件套齐全）
    if (
        BASE_WIDTH_RE.search(styles)
        and BASE_COLLAPSE_RE.search(styles)
        and BASE_PADDING_RE.search(styles)
    ):
        lineno = _first_lineno(text, BASE_COLLAPSE_RE.search(styles).start())
        hits.append(
            ("second-baseline", lineno, "样式块里出现 width/border-collapse/padding 三件套")
        )

    # RULE 3：详情页自写数字列右对齐
    if is_detail:
        for m in NUM_SELECTOR_RE.finditer(styles):
            lineno = _first_lineno(text, text.find("." + m.group(1), text.find("<style")))
            hits.append(("num-align", lineno, "." + m.group(1)))

    return hits


def load_baseline() -> dict[str, str]:
    if not BASELINE.is_file():
        return {}
    try:
        data = json.loads(BASELINE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    files = data.get("files") if isinstance(data, dict) else None
    return dict(files) if isinstance(files, dict) else {}


def build_baseline(files: list[Path]) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in files:
        if any(rule == "second-baseline" for rule, _, _ in scan_file(path)):
            out[_rel(path)] = "存量：自有样式里手抄了一份表格基线（收编前先判定该表语义）"
    return dict(sorted(out.items()))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("targets", nargs="*")
    parser.add_argument("--freeze", action="store_true", help="重写存量基线")
    args = parser.parse_args(argv)

    files = _iter_files(args.targets)
    if not files:
        # 「没扫描到文件」不等于「没有问题」——结论不可信，必须显式区分（源 CNB #171）。
        print(
            "NO-INPUT: 未发现待扫描的 .vue 文件（结论不可信，不得当成通过）",
            file=sys.stderr,
        )
        return 2

    if args.freeze:
        frozen = build_baseline(files)
        BASELINE.write_text(
            json.dumps(
                {
                    "_comment": (
                        "存量手抄表格基线（file → 理由）。键是文件；只要该文件里仍有"
                        "「width + border-collapse + padding」三件套就算命中，收编后自动消失。"
                    ),
                    "files": frozen,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print("OK: 基线已写入 %s（%d 个文件）" % (_rel(BASELINE), len(frozen)))
        return 0

    baseline = load_baseline()

    violations: dict[str, list[tuple[str, int, str]]] = {}
    for path in files:
        rel = _rel(path)
        hits = [
            h for h in scan_file(path) if not (h[0] == "second-baseline" and rel in baseline)
        ]
        if hits:
            violations[rel] = hits

    if not violations:
        print(
            "OK: 详情页表格均走 `.detail-table` 约定；存量手抄基线 %d 个文件（只减不增）"
            % len(baseline)
        )
        return 0

    print("ERROR: 详情页表格约定被绕过（源 CNB #553）：", file=sys.stderr)
    for rel in sorted(violations):
        for rule, lineno, line in violations[rel]:
            print("  %s:%d  [%s] %s" % (rel, lineno, rule, line), file=sys.stderr)
            print("        -> %s" % HINTS[rule], file=sys.stderr)
    print(
        "\n      共享约定：frontend/src/style/_detail-table.scss\n"
        "      确需例外：同行加注释 %s 说明理由（不要整文件放行）" % SKIP_MARKER,
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
