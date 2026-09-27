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

**边界（刻意不拦）**：`role="tablist"` 的手写按钮组若不用 `-segmented` 命名
（如 `.import-mode-switch` / `.rank-switch` / `.road-pills`）不会被本守卫命中——本仓另有若干处
这类控件属**其他**设计语言，另立跟进卡收敛；本守卫只覆盖已实际发生的回潮形态，
不做「看见 tablist 就拦」的宽泛匹配（那会制造大量白名单噪音，白名单一多守卫就形同虚设）。

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

# 唯一实现自身：允许出现 `el-segmented` 文字（docstring 就在讲「为什么不用它」）
DEFINITION_FILES = {
    Path("frontend/src/components/SegmentedControl/index.vue"),
}

# 刻意例外：留理由 + 跟进卡，不要为了「让守卫变绿」而加白名单
ALLOWED_FILES = {
    Path(
        "frontend/src/views/asset/investment/eaccount-import/components/EaccountAiPanel.vue"
    ): "eaccount-import 页的实心圆角变体（--brand-600 实底 + 圆角矩形），与同页 import-mode-switch 同构，"
    "属另一套语言；已另立跟进卡 #1731，不在 #1717 收敛范围",
}

# pure-admin 模板命名空间（ReSegmented 等模板自带组件，非本仓设计语言；本仓未使用）
VENDOR_CLASS_PREFIX = "pure-"

SKIP_MARKER = "segmented-allow"

EP_TAG_RE = re.compile(r"<\s*(?:el-segmented|ElSegmented|ReSegmented)\b")
EP_CSS_RE = re.compile(r"\.el-segmented\b")
CUSTOM_CSS_RE = re.compile(r"^\s*\.([A-Za-z][A-Za-z0-9_-]*-segmented)(?![A-Za-z0-9_-])")

HINTS = {
    "ep-tag": "改用 `SegmentedControl`（@/components/SegmentedControl/index.vue）",
    "ep-css": "改用 `SegmentedControl`，不要覆盖 EP 的选中滑块",
    "custom-css": "改用 `SegmentedControl`，不要在页面自写分段控制器样式",
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
        hits = _scan(path)
        if hits:
            violations[rel] = hits

    if not violations:
        print("OK: 无分段控制器回潮（唯一实现：src/components/SegmentedControl/index.vue）")
        return 0

    print("ERROR: 检测到分段控制器回潮（#1717）：", file=sys.stderr)
    for rel in sorted(violations):
        for rule, lineno, line in violations[rel]:
            print("  %s:%d  [%s] %s" % (rel, lineno, rule, line), file=sys.stderr)
            print("        -> %s" % HINTS[rule], file=sys.stderr)
    print(
        "\n      唯一实现：frontend/src/components/SegmentedControl/index.vue\n"
        "      规范：frontend/design.md「Segmented（分段控制器）」\n"
        "      确需例外：在同行加注释 %s 并说明理由（或在 ALLOWED_FILES 登记 + 跟进卡）"
        % SKIP_MARKER,
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
