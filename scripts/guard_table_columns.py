#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：`el-table` 非固定列一律 `min-width`，禁止「单弹性列独吃容器余量」（#3210）。

WHY（源 PR #3208 实测：首列占 36%~76%）
--------------------------------------
Element Plus 的 `updateColumnsWidth()` **只把「不带数字 `width`」的列纳入容器余量分配**。
一张表里如果只有一个弹性列（写了 `min-width`、或两者都不写），其余全是固定 `width`，
宽屏下**整条余量都灌给那一个弹性列**，其它列一动不动。1440 视口实测（#3208）：

| 表 | 容器 | 首列改前 | 改后 |
|---|---|---|---|
| 全面盘点·持仓明细 | 1036 | 376 (36%) | 275 (27%) |
| 全面盘点·类现金 | 1036 | 416 (40%) | 298 (29%) |
| 组合详情·持仓明细 | 904 | 420 (46%) | 234 (26%) |
| 组合详情·关联账户 | 904 | 684 (76%) | 460 |
| 策略视图 | 1134 | 444 (39%) | 289 (25%) |
| 探市详情·温度指标 | 1302 | 936 (72%) | 489 (38%) |

首列右侧大片空白还是次要的——同一个机制反手把窄列挤坏：`width="120"` 的「归属账户」
被挤成两行（#3208 的截图）。**这不是样式写错，而是列宽「表达方式」错了**：只留一个
弹性列，等于把「余量怎么分」这个决定权整个交给它。

判据（只判机制，不猜容器）
------------------------
一张 `<el-table>` 内的列先分类：

- **结构列**：`type="selection|index|expand"`，不参与分配，忽略；
- **操作列**：`label` 为「操作 / 操作列 / 行为 / Actions」，固定宽是常态，忽略；
- **动态列**：带 `v-for`，或 `:width` / `:min-width` 绑非数字表达式——判不了，
  整表跳过（宁可漏判，不误杀）；
- **弹性列**：有数字 `min-width`，或两者都没写（EP 视作 flex）；
- **固定列**：有数字 `width`。

**命中 = 弹性列恰好 1 个，且固定列 ≥ 1 个。** 两个及以上弹性列时，余量按 `min-width`
比例分摊，任何一列都吃不掉整条余量——这正是 #3208 采用的修法。

为什么不判「首列占比」：占比要**容器宽度**，静态拿不到。按 `--layout-content-width`
（1400）减 padding 去估会**虚警一大片**——页面内容区实测只有 856~1302px。
故判据落在「分配机制」上：机制错了占比一定错；机制对了，占比交给 `min-width` 比例。

放行（`table-col-allow`）
------------------------
已横滚的表与弹窗内的小表，弹性列并没有吃余量，但静态判不出容器宽度。这类按行放行：
在 `<el-table` 同一行或**紧邻的上一个非空行**写 `<!-- table-col-allow: 理由 -->`，
**理由必填**（6 字以上；裸标记不放行）。粒度刻意只到「这一张表」——文件级豁免会让
同文件里新增的第二张表自动通过（同 `sticky-table-allow` 的取舍）。

配置驱动的表（本守卫判不了，但**不许无声跳过**）
----------------------------------------------
列宽写在 `*.ts`（`:width="def.width"` / `:min-width="col.minWidth"`）的表，本守卫静态解析
不到。这类**必须**登记进 `CONFIG_TABLE_JUDGE`，由
`frontend/src/__tests__/tableColumnFlexInvariant.spec.ts` 直接 import 那份配置做断言——
比正则猜精确（能拿到 spread / 常量 / 计算属性之后的真值），且配置一改就跟着回归。
未登记即红；登记了但判据本体不存在也红（跳过不许写成通过）。

字面量 `width` 的 `v-for` **不**属于这一类：重复一个定宽列不改变弹性列个数，守卫自己判
（`CrowdingTable` 的「乖离 6/20/60 日」三列）。

其余不覆盖
----------
- 不判「已横滚」：`Σ列宽 ≥ 容器` 的表靠放行标记说明，不靠判据猜（要运行时）。
- 不校验 `min-width` 的取值是否合理（240 还是 320）：只判「有几个弹性列」。
- 只扫 `frontend/src/**/*.vue`；`<style>` 里的列宽样式与 `columns` 数组不在范围内。

用法
----
    python scripts/guard_table_columns.py            # 扫描 frontend/src（CI）
    python scripts/guard_table_columns.py a.vue      # 只扫指定文件（合成样例 / 局部验证）
    python scripts/guard_table_columns.py --report   # 打印每张表的分类结果（不改判定）

退出码：0 = 通过；1 = 命中栅栏；2 = 拿不到输入（路径不存在 / 扫不到任何文件——
结论不可信，**不得**当成通过）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "frontend" / "src"

STRUCT_TYPES = {"selection", "index", "expand"}
ACTION_LABELS = {"操作", "操作列", "行为", "actions", "action"}

SKIP_MARKER = "table-col-allow"
MIN_REASON_CHARS = 6

# 列宽由配置驱动（`:width="def.width"` / `:min-width="col.minWidth"`）的表：静态判不了，
# **必须在这里登记**，并到 vitest 判据里真正 import 那份配置做断言。
#
# 登记不是走过场——它挡的是「新加一张配置驱动的表，静默回到无判据状态」：
# 2026-11-21（#3210 收尾）之前，全仓 4 张 `v-for` 表都是「跳过」，其中 3 张的列宽
# 完全在 *.ts 里，守卫连看都看不见。现在：
#   · 字面量 `width` 的 `v-for` 已可判（重复定宽列不改弹性列个数），由守卫直接判；
#   · 其余动态列 ⇒ 未登记即红，登记后由 SPEC_FILE 里的用例承接。
CONFIG_TABLE_JUDGE: dict[str, str] = {
    "frontend/src/views/asset/watchlist/components/WatchlistTableSection.vue": (
        "columnDefs.getDefaultVisibleColumns()（冻结列 width / 其余 minWidth）"
    ),
    "frontend/src/views/asset/fund-ranking/components/FundRankingTable.vue": (
        "rankingColumns.tableColumns（接口里根本没有 width，只有 minWidth）"
    ),
    "frontend/src/views/asset/investment/import/components/PreviewTable.vue": (
        "importWizardData.columnsForMode()（基金 / 股票两套列全 minWidth）"
    ),
}
# 登记项指向的判据本体。**内容不在这里校验**（全文 includes 会被注释喂假绿，见 #2453），
# 只钉「文件存在」；用例侧用 `CASES.length` 钉住覆盖张数，删掉一条就红。
SPEC_FILE = REPO_ROOT / "frontend/src/__tests__/tableColumnFlexInvariant.spec.ts"

TABLE_OPEN_RE = re.compile(r"<el-table(?![\w-])")
COLUMN_OPEN_RE = re.compile(r"<el-table-column(?![\w-])")
TABLE_CLOSE = "</el-table>"
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def _blank_comments(text: str) -> str:
    """把 HTML 注释抹成等长空白（保留换行）——注释里的 `<el-table>` 不是结构事实。

    注释喂假红是 #3200 的镜像坑：迁移后的注释里写着旧写法，按全文判就会当天红。
    """

    def repl(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    return COMMENT_RE.sub(repl, text)


def _read_tag(text: str, start: int):
    """从 `text[start]` 起读一个开始标签，返回 (属性串, 结束下标)；读不到返回 None。"""
    m = re.match(r"<\s*[A-Za-z0-9_-]+", text[start:])
    if not m:
        return None
    i = start + m.end()
    quote = None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == ">":
            return text[start + m.end():i], i + 1
        i += 1
    return None


def _attr(attrs: str, key: str):
    """取属性原文，返回 (值, 是否 v-bind 绑定)；没有该属性返回 None。"""
    m = re.search(r"(?:^|\s)(:|v-bind:)%s\s*=\s*\"([^\"]*)\"" % re.escape(key), attrs)
    if m:
        return m.group(2), True
    m = re.search(r"(?:^|\s)%s\s*=\s*\"([^\"]*)\"" % re.escape(key), attrs)
    if m:
        return m.group(1), False
    return None


def _num(raw):
    """数值宽度；动态 / 非整数返回 None。"""
    if raw is None:
        return None
    value = raw[0].strip()
    if not re.fullmatch(r"\d+", value):
        return None
    return int(value)


def _columns(block: str):
    """返回 ([(kind, label)], 是否含动态列)。kind ∈ struct/action/dynamic/flex/fixed。"""
    kinds: list[tuple[str, str]] = []
    dynamic = False
    i = 0
    while True:
        m = COLUMN_OPEN_RE.search(block, i)
        if not m:
            break
        tag = _read_tag(block, m.start())
        if not tag:
            break
        attrs, i = tag

        ctype = _attr(attrs, "type")
        if ctype and ctype[0] in STRUCT_TYPES:
            kinds.append(("struct", ""))
            continue

        label = _attr(attrs, "label")
        label_text = label[0] if label else ""
        if label_text.lower() in ACTION_LABELS:
            kinds.append(("action", label_text))
            continue

        raw_width = _attr(attrs, "width")
        raw_min = _attr(attrs, "min-width")
        width = _num(raw_width)
        min_width = _num(raw_min)

        if (raw_width is not None and width is None) or (
            raw_min is not None and min_width is None
        ):
            dynamic = True
            kinds.append(("dynamic", label_text))
        elif re.search(r"(?:^|\s)v-for\s*=", attrs):
            # `v-for` 只是**重复同一个列**：重复一个「定宽」列不改变弹性列个数（0 个还是 0 个），
            # 故字面量 width 的 `v-for` 可判——`CrowdingTable` 的「乖离 6/20/60 日」三列正是此形。
            # 重复一个「弹性」列则会改变个数（N 要读运行时常量，静态未知）⇒ 仍判不了。
            if width is not None:
                kinds.append(("fixed", label_text))
            else:
                dynamic = True
                kinds.append(("dynamic", label_text))
        elif raw_min is not None:
            kinds.append(("flex", label_text))
        elif width is not None:
            kinds.append(("fixed", label_text))
        else:
            # 两者都没写：EP 把无 width 的列当 flex
            kinds.append(("flex", label_text))
    return kinds, dynamic


def _tables(text: str):
    """产出 (起始行号, 表格块文本)。块尾按 `<el-table` / `</el-table>` 平衡。"""
    pos = 0
    while True:
        m = TABLE_OPEN_RE.search(text, pos)
        if not m:
            return
        start = m.start()
        depth = 0
        i = start
        while True:
            nxt = TABLE_OPEN_RE.search(text, i)
            open_at = nxt.start() if nxt else -1
            close_at = text.find(TABLE_CLOSE, i)
            if close_at == -1:
                # 未闭合：交给 Vue 编译器报错，这里按到文件尾处理，避免静默漏判
                yield text[:start].count("\n") + 1, text[start:]
                return
            if open_at != -1 and open_at < close_at:
                depth += 1
                i = open_at + 1
                continue
            depth -= 1
            i = close_at + len(TABLE_CLOSE)
            if depth == 0:
                break
        yield text[:start].count("\n") + 1, text[start:i]
        pos = i


def _marker_in(line: str):
    """该行是否带放行标记。返回 None = 没有标记；(True, 理由) / (False, 说明)。"""
    at = line.find(SKIP_MARKER)
    if at == -1:
        return None
    # 必须在 HTML 注释里（防止模板字符串 / 文案里出现这个词就放行）
    if "<!--" not in line[:at] or "-->" not in line[at:]:
        return None
    reason = line[at + len(SKIP_MARKER): line.rfind("-->")]
    reason = reason.strip(" \t:：-—")
    if len(reason) >= MIN_REASON_CHARS:
        return True, reason
    return False, "（标记后没写理由）"


def _exempt(lines: list[str], lineno: int):
    """同行，或紧邻的上一个非空行。返回 (是否放行, 说明)。"""
    found = _marker_in(lines[lineno - 1]) if lineno - 1 < len(lines) else None
    if found:
        return found
    idx = lineno - 2
    while idx >= 0 and not lines[idx].strip():
        idx -= 1
    if idx >= 0:
        found = _marker_in(lines[idx])
        if found:
            return found
    return False, ""


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _scan(path: Path, report: bool):
    """返回 (命中 [(行号, 说明)], 报表行)。"""
    try:
        raw = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return [], []
    code = _blank_comments(raw)
    if TABLE_OPEN_RE.search(code) is None:
        return [], []

    rel = _rel(path)
    lines = raw.splitlines()
    hits: list[tuple[int, str]] = []
    rows: list[str] = []
    for lineno, block in _tables(code):
        kinds, dynamic = _columns(block)
        flex = [lb for kind, lb in kinds if kind == "flex"]
        fixed = [lb for kind, lb in kinds if kind == "fixed"]

        if dynamic:
            judged_by = CONFIG_TABLE_JUDGE.get(rel)
            if judged_by:
                rows.append("%d: 跳过（列宽由配置驱动，判据见 vitest：%s）" % (lineno, judged_by))
                continue
            detail = (
                "列宽由配置驱动（动态列），守卫静态判不了，且**未登记** CONFIG_TABLE_JUDGE"
            )
            rows.append("%d: 命中（%s）" % (lineno, detail))
            hits.append((lineno, detail))
            continue
        if len(flex) != 1 or not fixed:
            rows.append(
                "%d: 通过（弹性列 %d / 固定列 %d）" % (lineno, len(flex), len(fixed))
            )
            continue

        ok, reason = _exempt(lines, lineno)
        if ok:
            rows.append("%d: 放行（%s）" % (lineno, reason))
            continue
        detail = "唯一弹性列 = 「%s」，其余 %d 列全固定宽（%s）%s" % (
            flex[0] or "无 label",
            len(fixed),
            " / ".join(lb or "无 label" for lb in fixed),
            "" if reason == "" else "；" + reason,
        )
        rows.append("%d: 命中（%s）" % (lineno, detail))
        hits.append((lineno, detail))

    if report and rows:
        for row in rows:
            print("  %s:%s" % (rel, row))
    return hits, rows


def _iter_files(targets: list[str]):
    """返回 (待扫文件, 输入是否可信)。"""
    if targets:
        files = []
        missing = []
        for raw in targets:
            p = Path(raw)
            if not p.is_absolute():
                p = REPO_ROOT / p
            if p.is_file() and p.suffix == ".vue":
                files.append(p)
            else:
                missing.append(raw)
        if missing:
            print(
                "ERROR: 指定的路径不是可扫描的 .vue 文件：%s" % "、".join(missing),
                file=sys.stderr,
            )
            return [], False
        return files, True

    if not DEFAULT_ROOT.is_dir():
        print("ERROR: 找不到 %s" % DEFAULT_ROOT, file=sys.stderr)
        return [], False
    return [
        p
        for p in DEFAULT_ROOT.rglob("*.vue")
        if p.is_file() and "node_modules" not in p.parts
    ], True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="el-table 列宽表达守卫（#3210）")
    parser.add_argument("paths", nargs="*", help="只扫指定 .vue 文件")
    parser.add_argument("--report", action="store_true", help="打印每张表分类结果")
    args = parser.parse_args(argv)

    files, trustworthy = _iter_files(args.paths)
    if not trustworthy:
        return 2
    if not files:
        print(
            "ERROR: 没有扫到任何 .vue 文件——判据等于没跑，不得视为通过", file=sys.stderr
        )
        return 2
    if CONFIG_TABLE_JUDGE and not SPEC_FILE.exists():
        print(
            "ERROR: 登记了 %d 张「配置驱动」的表，但判据本体不存在：%s\n"
            "      登记项必须有承接的用例，否则等于把跳过写成了通过。"
            % (len(CONFIG_TABLE_JUDGE), _rel(SPEC_FILE)),
            file=sys.stderr,
        )
        return 1

    violations: dict[str, list[tuple[int, str]]] = {}
    for path in files:
        hits, _ = _scan(path, args.report)
        if hits:
            try:
                rel = path.relative_to(REPO_ROOT).as_posix()
            except ValueError:
                rel = str(path)
            violations[rel] = hits

    if not violations:
        print("OK: 无「单弹性列独吃余量」的表格（扫描 %d 个 .vue）" % len(files))
        return 0

    total = sum(len(v) for v in violations.values())
    print(
        "ERROR: %d 张表只有 1 个弹性列，其余全固定宽——"
        "容器余量会全部灌给这一列（EP 只给「无数字 width」的列分余量）：" % total,
        file=sys.stderr,
    )
    for rel in sorted(violations):
        for lineno, detail in violations[rel]:
            print("  %s:%d  %s" % (rel, lineno, detail), file=sys.stderr)
    print(
        "\n      正解①（普通表）：非固定列一律 `min-width`（≥2 个弹性列即通过）；"
        "只有冻结列 / 选择列 / 操作列才用 `width`。\n"
        "      正解②（列宽由配置驱动、守卫判不了）：把该文件登记进 CONFIG_TABLE_JUDGE，\n"
        "        并在 %s 里 import 那份配置做断言。\n"
        "      已横滚或弹窗内小表确需例外：在 `<el-table` 上方一行写\n"
        "        <!-- %s: 理由（8 列合计 932 > 表宽 856，已横滚） -->\n"
        "      规范：frontend/design.md「表格 · 列宽用 minWidth 表达」"
        % (_rel(SPEC_FILE), SKIP_MARKER),
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
