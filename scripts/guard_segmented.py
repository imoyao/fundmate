#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：禁止分段控制器回潮（`el-segmented` / 页面级 `.xxx-segmented` 样式块）。

WHY
---
「多选一、选项少」的切换控件在本仓被反复重造：#1717 落地前共有 10 处各写各的
（5 处直接挂 `el-segmented` 实例 + 5 处手写分段分组，分布在 8 个文件），语言漂移出 6 种形态。
`frontend/design.md` 早有一条「禁止各页面自行手写分段控制器样式」的红线，但它是**散文**，
拦不住任何人——#1717 就是这么漏进来的（资产总览页只覆盖了轨道 / 选项项的圆角，
漏掉 EP 那个 JS 绝对定位的选中滑块 `.el-segmented__item-selected`，于是「选中方块 + hover 胶囊」）。

#1717 已把全部 10 处收敛到唯一实现 `frontend/src/components/SegmentedControl/index.vue`，
本守卫负责把**同一形态**的第五处堵死：

1. `RULE 1` 模板里出现 `<el-segmented>` / `<ElSegmented>`（EP 的选中滑块是 JS 绝对定位的
   独立子元素，几何与轨道各算各的，且带 `transition: all .3s`，每次点击都滑动 / 缩放一次）。
2. `RULE 2` 样式里出现 `.el-segmented` 选择器（含 `:deep(.el-segmented…)`——
   这正是 #1717 的翻车写法：覆盖不全会让选中态与 hover 态几何不一致）。
3. `RULE 3` 定义了一个以 `-segmented` 结尾的自定义 class（`.refresh-segmented` /
   `.type-segmented` / `.ocr-segmented` / `.status-segmented` 都是这么长出来的）。
4. `RULE 4` 出现 `role="tablist"`（#1731 起）。

**边界（#1731 起收紧）**：#1717 时本守卫**刻意不拦**「不用 `-segmented` 命名的手写按钮组」
（`.import-mode-switch` / `.rank-switch` / `.road-pills` …），因为当时这类控件里混着合法的
筛选胶囊语言，宽泛匹配会制造大量白名单噪音。**#1731 已把那一批全部判定并收敛**，于是
`role="tablist"` 本身成了可用的栅栏——现在只剩**两类登记在案**的合法 tablist：

- 分组胶囊 Tab（`design.md` 专节，`views/explore/index.vue` 的 `.panel-switch__inner`）
- 二级筛选水平滑动胶囊栏（`design.md`「Filter & Selection」，`RoadFilterBar.vue` 的 `.road-pills--scroll`）

`ALLOWED_TABLIST_FILES` 因此只有两条，且**精确到类名**（不是整文件放行）——
同文件里再长出第二个 tablist 照样会被拦下。

**仍未覆盖（刻意，另立卡）**：**不带 `role` 的手写切换控件**（#1731 的 C 项
`CategoryBalanceTable.vue` `.balance-switch` 就是这种：无 role、用 `::after` 画 2px 下划线），
以及「品牌中间阶（`--brand-500/600/700`）作实底填充」的漂移形态。两类都需要先判定既有用法
是否合法，与守卫一起在跟进卡里做。

用法
----
    python scripts/guard_segmented.py                 # 扫描 frontend/src 全量
    python scripts/guard_segmented.py a.vue b.css     # 只扫指定文件（合成样例 / 局部验证）

退出码：0 = 通过；1 = 命中栅栏。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "frontend" / "src"
SCAN_SUFFIXES = {".vue", ".ts", ".tsx", ".js", ".jsx", ".css", ".scss", ".sass"}

# 唯一实现自身：允许出现 `el-segmented` 文字（docstring 就在讲「为什么不用它」）与 role="tablist"
DEFINITION_FILES = {
    Path("frontend/src/components/SegmentedControl/index.vue"),
}

# 刻意例外（整文件放行）：留理由 + 跟进卡，不要为了「让守卫变绿」而加白名单。
# #1731 已把 eaccount-import 的实心圆角变体收敛，原先挂在这里的那条白名单随之作废
# ——白名单能删就删，留着只会掩盖下一次回潮。
ALLOWED_FILES: dict[Path, str] = {}

# 保留为**独立登记语言**的 `role="tablist"`（#1731 裁决，边界见 docs/design/components.md）。
# 键 = 文件；值 = (该 tablist 所在元素**必须命中**的类名, 理由)。
# 精确到类名而非整文件放行：同一文件里再长出第二个 tablist 照样会被 RULE 4 拦下。
ALLOWED_TABLIST_FILES: dict[Path, tuple[str, str]] = {
    Path("frontend/src/views/explore/index.vue"): (
        "panel-switch__inner",
        "分组胶囊 Tab（design.md 专节）：带数量徽章 + 横向滚动的分组导航，选中态多一道 "
        "--brand-400 边框、hover 加深到 --brand-200；不是「多选一、选项少」的分段控制器",
    ),
    Path("frontend/src/views/asset/favorites/components/RoadFilterBar.vue"): (
        "road-pills--scroll",
        "二级筛选水平滑动胶囊栏（design.md「Filter & Selection」）：overflow-x: auto 严禁换行；"
        "其一级筛选已迁到 SegmentedControl（#1731）",
    ),
}

# pure-admin 模板命名空间（ReSegmented 等模板自带组件，非本仓设计语言；本仓未使用）
VENDOR_CLASS_PREFIX = "pure-"

SKIP_MARKER = "segmented-allow"

EP_TAG_RE = re.compile(r"<\s*(?:el-segmented|ElSegmented|ReSegmented)\b")
# ⚠️ 这里**不能**用 `\b` 收尾：`_` 是 word 字符，`.el-segmented__item-selected` 里
# `el-segmented` 与 `_` 之间**没有**词边界，`\.el-segmented\b` 会漏拦——而那正是 #1717
# 的翻车写法（只覆盖轨道 / 选项项、漏掉 JS 绝对定位的选中滑块）。
# 2026-09-27 #1731 用合成样例验证时实测到该假阴性，改用「后面不接字母/数字」收尾。
EP_CSS_RE = re.compile(r"\.el-segmented(?![A-Za-z0-9])")
CUSTOM_CSS_RE = re.compile(r"^\s*\.([A-Za-z][A-Za-z0-9_-]*-segmented)(?![A-Za-z0-9_-])")
TABLIST_RE = re.compile(r"""role\s*=\s*["']tablist["']""")

HINTS = {
    "ep-tag": "改用 `SegmentedControl`（@/components/SegmentedControl/index.vue）",
    "ep-css": "改用 `SegmentedControl`，不要覆盖 EP 的选中滑块",
    "custom-css": "改用 `SegmentedControl`，不要在页面自写分段控制器样式",
    "tablist": "「多选一、选项少」一律改用 `SegmentedControl`；确属分组胶囊 Tab / "
    "二级筛选胶囊栏的，在 ALLOWED_TABLIST_FILES 登记（类名 + 理由）",
}


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


def _scan(path: Path) -> list[tuple[str, int, str]]:
    """返回 [(rule, lineno, line)]；rule 取值见 HINTS。"""
    hits: list[tuple[str, int, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return hits

    for lineno, line in enumerate(text.splitlines(), start=1):
        if SKIP_MARKER in line:
            continue
        if EP_TAG_RE.search(line):
            hits.append(("ep-tag", lineno, line.strip()))
            continue
        if EP_CSS_RE.search(line):
            hits.append(("ep-css", lineno, line.strip()))
            continue
        m = CUSTOM_CSS_RE.match(line)
        if m and not m.group(1).startswith(VENDOR_CLASS_PREFIX):
            hits.append(("custom-css", lineno, line.strip()))
        # RULE 4：模板里的 role="tablist"（#1731 起）。例外由调用方按
        # ALLOWED_TABLIST_FILES 的「类名」逐行放行，不在这里整文件跳过。
        if TABLIST_RE.search(line):
            hits.append(("tablist", lineno, line.strip()))
    return hits


def main(argv: list[str]) -> int:
    targets = [a for a in argv if not a.startswith("-")]
    files = _iter_files(targets)

    if not files:
        print("OK: 未发现待扫描的前端源文件")
        return 0

    violations: dict[str, list[tuple[str, int, str]]] = {}
    for path in files:
        try:
            rel = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = str(path)
        if Path(rel) in DEFINITION_FILES or Path(rel) in ALLOWED_FILES:
            continue
        allowed_tablist = ALLOWED_TABLIST_FILES.get(Path(rel))
        hits = [
            hit
            for hit in _scan(path)
            # RULE 4 的例外：该行确实落在登记的那个类名上才放行
            if not (hit[0] == "tablist" and allowed_tablist and allowed_tablist[0] in hit[2])
        ]
        if hits:
            violations[rel] = hits

    if not violations:
        print(
            "OK: 无分段控制器回潮（唯一实现：src/components/SegmentedControl/index.vue；"
            'role="tablist" 登记例外 %d 条）' % len(ALLOWED_TABLIST_FILES)
        )
        return 0

    print("ERROR: 检测到分段控制器回潮（#1717 / #1731）：", file=sys.stderr)
    for rel in sorted(violations):
        for rule, lineno, line in violations[rel]:
            print("  %s:%d  [%s] %s" % (rel, lineno, rule, line), file=sys.stderr)
            print("        -> %s" % HINTS[rule], file=sys.stderr)
    print(
        "\n      唯一实现：frontend/src/components/SegmentedControl/index.vue\n"
        "      规范：frontend/design.md「Segmented（分段控制器）」\n"
        "      确需例外：同行加注释 %s 说明理由；若是 `role=\"tablist\"`，改在\n"
        "      ALLOWED_TABLIST_FILES 登记（类名 + 理由）——别整文件放行" % SKIP_MARKER,
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
