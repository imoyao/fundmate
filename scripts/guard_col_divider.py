#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：禁止在业务样式里手写裸的「栏间竖向分割线」（1px + --border-light）。

WHY
---
用户反馈「这个竖向的分割线和文字贴在一起了，我看其他页面也有这个问题」。
根因是两条独立的错叠在一起，而**每一条单独看都像在「收紧布局」**：

1. 分割线紧贴邻栏文字：分割线是**装饰**，不是内容边界。贴上去等于让文字顶着线读，
   视觉上就是「线和字糊在一起」；
2. border 写在**不带断点的类名上**，而两栏布局本身是 ``lg:grid-cols-12``——在 lg 以下
   两栏已纵向堆叠，那条 1px 竖线却还在，变成一根孤零零贴在块左边的怪线。

2026-10 已把这两条钉进全局工具类 ``.soft-col-divider``
（``frontend/src/style/index.scss``：lg 以上才 ``padding-left: 24px`` + 画线，
lg 以下不画）——#2157。

本守卫防的是**第 5 份手写拷贝**：业务样式里再裸写
``border-left|border-right: 1px solid var(--border-light)`` 即 CI 变红。
没有它，「这次收口完下次还会散开」——散文规范拦不住抄粘贴。

判据边界（刻意，写下来免得下一个人以为是漏判）
------------------------------------------------
- **只认这一种字面量**：``1px`` + ``solid`` + ``var(--border-light)``，且必须落在
  ``border-left`` / ``border-right`` 上。于是以下都**有意放行**：
  - **语义强调条**（``3px``/``4px`` + ``--color-warning|danger|info`` + ``temp-low/high/mid``）：
    颜色本身就是信息（如 ``ExploreDetailPanel`` 的机会卡温度条），与「栏间分割线」是
    两回事，不要混为一谈（#2157 正文已明确）；
  - **选中指示条**（``border-left: 2px solid transparent``，选中态改
    ``border-left-color``）：那是占位/指示，不是分割；
  - ``--border-subtle``（卡片内部降权分割线，design.md §边框与分割线）、``--pure-border-color``、
    ``border:`` 四边简写、``border-left-width/color/style`` 长写。
- **只扫 ``<style>`` 段**：``<script>`` 里的 CSS 字符串（``:style="{ borderLeft: ... }"``）
  不参与判定——判据一旦把「讲解用的字符串」当成代码，就会自己先崩（见
  ``guard_control_clip.py`` 的同类教训）。
- **单行匹配**：``border-left`` 的值必须在同一行写完。跨行的值（极罕见）会漏判；
  宁可漏判，不可错判。
- **豁免**：在声明**本行或相邻行**加注释 ``col-divider-allow`` 并写明理由。
  刻意不提供「文件级豁免」——整文件放行会让判据在真实代码上失去意义。

存量冻结（BASELINE）与逐处理由
-------------------------------
``BASELINE`` 是**存量冻结、只减不增**（同 ``guard_breakpoints.py`` / ``check_css_vars.mjs``
手法），按 ``相对路径::归一化声明`` 记**数量预算**——所以「同一个文件里再加一条」同样会红。
基线**不是**「这些是 bug」，而是 #2157「逐处确认」的机器可查档案：

===================  ==========================================================
处（origin/dev）      为什么保留
===================  ==========================================================
``ProductPageToc``    该 1px 线**同时是选中指示条（2px）的轨道**——
  ``.vue``            同文件 ``.page-toc__link`` 的 ``margin-left: -1px`` 注释写着
                      「让选中指示条压在 1px 轨道上，不留双线」。换成
                      ``.soft-col-divider``（给 24px padding）会让指示条脱离轨道。
                      且该线本就在 ``bp.above("xl")`` 内（lg 以下 rail 整体
                      ``display: none``），不存在孤线；文字距线 12px。
``OverviewSummaryCard``  ``.summary-card__metric`` 已有 ``padding: 0 12px``（两侧各
  ``.vue``              12px，不贴字），且固定 3 列**任何视口都不堆叠**，
                      断点语义对它不适用。
``ColumnSettingsModal``  ``.cs-nav`` 是模态框内**恒并排**的左导航轨（宽 168px、
  ``.vue``              ``padding-right: 8px`` + item ``padding: 8px 10px`` ⇒
                      角标距线 18px、不贴字）。``.soft-col-divider`` 只在 lg 以上
                      画线，套上去会让线在窄视口**凭空消失**（错误行为）。
``FilterPanelBody``     同上一类：popover 弹层内固定宽度导航轨，**任何视口都并排**，
  ``.vue``              导航项 ``padding: 10px 12px`` ⇒ 距线 12px。
===================  ==========================================================

⇒ 结论：这 4 处都**不同时具备**「贴字」与「孤线」两条症状，故保留原样并登记；
本守卫防的是**新增第 5 份**。

用法
----
    python scripts/guard_col_divider.py                    # 扫描 frontend/src 全量
    python scripts/guard_col_divider.py a.vue b.scss       # 只扫指定文件（pre-commit / 局部验证）

退出码：0 = 通过；1 = 命中栅栏。
"""

from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "frontend" / "src"
SCAN_SUFFIXES = {".vue", ".css", ".scss", ".sass"}

# 单一来源 + 框架样式目录：``.soft-col-divider`` 的定义处就在这里，
# 排除整目录（业务代码不该往 style/ 里写页面级分割线）。
SKIP_DIRS = (Path("frontend/src/style"),)

# 本行（或相邻行）加此注释可显式豁免（须在 PR 里说明理由）
SKIP_MARKER = "col-divider-allow"

STYLE_OPEN_RE = re.compile(r"<style[^>]*>")
# 竖向外边声明：``border-left: <value>`` / ``border-right: <value>``
DECL_RE = re.compile(r"\bborder-(?P<side>left|right)\s*:\s*(?P<value>[^;{}]*)")
# 判定目标：1px 实线 + --border-light（容忍多余空白，归一化后精确匹配）
DIVIDER_VALUE_RE = re.compile(r"^1px\s+solid\s+var\(\s*--border-light\s*\)$")

BASELINE: dict[str, int] = {
    "frontend/src/components/Watchlist/ColumnSettingsModal.vue::"
    "border-right: 1px solid var(--border-light)": 1,
    "frontend/src/views/asset/panorama/components/OverviewSummaryCard.vue::"
    "border-left: 1px solid var(--border-light)": 1,
    "frontend/src/views/asset/watchlist/components/FilterPanelBody.vue::"
    "border-right: 1px solid var(--border-light)": 1,
    "frontend/src/views/product/components/ProductPageToc.vue::"
    "border-left: 1px solid var(--border-light)": 1,
}

HINT = (
    "栏间竖向分割线唯一走全局工具类 .soft-col-divider"
    "（frontend/src/style/index.scss：lg 以上才画线 + padding-left: 24px）。"
    "手写裸 border 会同时踩两个坑——线贴住邻栏文字、且窄屏两栏堆叠后留下孤线。"
)


def _extract_style_text(raw: str) -> str:
    """取出 CSS 文本，且**保证行号与原文件逐行对齐**（非 style 行填成空行）。

    按行处理而不是正则切片：正则切出的片段拼接后行号会漂移，
    违规行号一旦指错，报错就查不到东西（判据类脚本的老坑）。
    """
    if "<style" not in raw:
        return raw

    out: list[str] = []
    in_style = False
    for line in raw.splitlines():
        if not in_style:
            m = STYLE_OPEN_RE.search(line)
            if m:
                rest = line[m.end() :]
                if "</style>" in rest:
                    out.append(rest.split("</style>", 1)[0])
                else:
                    out.append(rest)
                    in_style = True
            else:
                out.append("")
            continue
        if "</style>" in line:
            out.append(line.split("</style>", 1)[0])
            in_style = False
        else:
            out.append(line)
    return "\n".join(out)


def _strip_comments(text: str) -> str:
    """剥掉 CSS 注释但**保留换行**（行号不漂移）。

    先剥注释再匹配：否则文档/注释里写的「旧写法是 border-left: 1px solid
    var(--border-light)」会被当成代码（讲解本守卫时就会这样自伤）。
    """
    return re.sub(
        r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.DOTALL
    )


def _normalize_value(value: str) -> str:
    """归一化声明值：去 ``!important``、折叠空白、转小写。"""
    value = value.split("!", 1)[0]
    return " ".join(value.split()).lower()


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _is_skipped(rel: str) -> bool:
    rel_path = Path(rel)
    return any(rel_path == d or d in rel_path.parents for d in SKIP_DIRS) or any(
        part == "node_modules" for part in rel_path.parts
    )


def _scan(path: Path) -> list[tuple[str, int]]:
    """返回 [(归一化声明, 行号)]，键形如 ``border-left: 1px solid var(--border-light)``。"""
    raw = _read(path)
    if raw is None:
        return []

    # 豁免标记按**原文件行号**记；声明本行或其上下相邻行带标记即放行
    marked = {
        idx for idx, line in enumerate(raw.splitlines(), start=1) if SKIP_MARKER in line
    }

    style_text = _strip_comments(_extract_style_text(raw))

    found: list[tuple[str, int]] = []
    for idx, line in enumerate(style_text.splitlines(), start=1):
        if any(abs(idx - m) <= 1 for m in marked):
            continue
        for match in DECL_RE.finditer(line):
            if DIVIDER_VALUE_RE.match(_normalize_value(match.group("value"))):
                key = f"border-{match.group('side')}: 1px solid var(--border-light)"
                found.append((key, idx))
    return found


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

    if not DEFAULT_ROOT.is_dir():
        return []
    return [
        p
        for p in DEFAULT_ROOT.rglob("*")
        if p.is_file() and p.suffix in SCAN_SUFFIXES and "node_modules" not in p.parts
    ]


def main(argv: list[str]) -> int:
    targets = [a for a in argv if not a.startswith("-")]
    files = _iter_files(targets)

    if not files:
        print("OK: 未发现待扫描的前端样式文件")
        return 0

    violations: list[tuple[str, int, str, int, int]] = []
    seen: collections.Counter[str] = collections.Counter()

    for path in files:
        try:
            rel = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = path.as_posix()
        if _is_skipped(rel):
            continue

        per_file: collections.Counter[str] = collections.Counter()
        lines_by_key: dict[str, list[int]] = collections.defaultdict(list)
        for key, lineno in _scan(path):
            per_file[key] += 1
            lines_by_key[key].append(lineno)

        for key, count in per_file.items():
            seen[f"{rel}::{key}"] += count
            budget = BASELINE.get(f"{rel}::{key}", 0)
            if count > budget:
                # 只报「超预算」的那几条，避免存量条目淹没新增
                for lineno in lines_by_key[key][budget:]:
                    violations.append((rel, lineno, key, count, budget))

    if not violations:
        if not targets and not any(seen.get(k, 0) for k in BASELINE):
            print("OK: 栏间分割线基线已清零，可把本守卫改为零容忍模式")
        else:
            remain = sum(min(seen.get(k, 0), v) for k, v in BASELINE.items())
            # 措辞刻意写「已逐处复核为保留原样」而非「待收口」：这 4 处是 #2157
            # 「逐处确认」的**结论**（不同时具备「贴字」「孤线」两条症状），不是欠账。
            # 写成「待收口」会误导下一个人去「统一」掉它们——那恰恰是本判据要防的事。
            print(
                "OK: 无新增裸栏间分割线"
                f"（存量基线剩余 {remain} / {sum(BASELINE.values())} 处，"
                "已逐处复核为保留原样）"
            )
        return 0

    print("ERROR: 检测到新写死的裸栏间竖向分割线：", file=sys.stderr)
    for rel, lineno, key, count, budget in violations:
        extra = f"（基线 {budget} 处，现 {count} 处）" if budget else ""
        print(f"  {rel}:{lineno}  {key} {extra}", file=sys.stderr)
    print(
        f"\n      -> {HINT}\n"
        "      规范：frontend/design.md §边框与分割线\n"
        f"      确需例外：在声明本行或相邻行加注释 {SKIP_MARKER} 并写明理由",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
