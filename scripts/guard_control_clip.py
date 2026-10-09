#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：拦截「容器盖子裁切控件」与「用 padding 撑大热区」两类回潮。

WHY
---
2026-10-09 用户反馈：自选页头部四个圆形快捷按钮「又大又被切」。根因是两条独立的
CSS 写法叠在一起，且**每一条单独看都像是在「收紧 / 补偿」**：

1. ``.head-primary { max-height: 40px; overflow: hidden }`` —— 折叠态机制 2026-09-05
   废弃后留下的天花板。行内控件高度各有各的来源，盖子却只进不出；
2. ``.icon-tool-btn { box-sizing: content-box; width/height: 28px; padding: 6px;
   border: 1px }`` —— 注释写着「视觉保持 28、靠 padding 把命中区扩到 40」，但 padding
   与 border 同样绘制在 border-box 上：可见圆其实是 28 + 6×2 + 1×2 = **42px**。

42 > 40 ⇒ 上下各被切 1px ⇒ 正圆渲染成「上下压扁的椭圆」，还比旁边 36px 的主按钮大。
这两条错此前没有任何机制拦得住：散文规范写的是「视觉 28」，跟代码对不上时没人发现。

本守卫把两条不变量钉成 CI 断言：

- ``RULE clip``：同一文件里，若某规则块同时声明 ``max-height: Npx`` 与
  ``overflow: hidden|clip``（＝会裁切子元素的盖子），则同文件内**任何能静态算出
  外框高度**的控件不得高于 N。判断用**外框（border-box）高度**，即按 box-sizing 把
  padding / border 计入 —— 正是 42 vs 40 那一步。
- ``RULE pad``：按钮规则用 ``box-sizing: content-box`` + **非 0 padding** 扩热区。
  这是本 bug 的成因写法，全仓已清零；热区要扩一律用 ``::after`` 伪元素
  （不参与布局、不画背景，视觉尺寸不受影响）。

**判据边界（刻意，写下来免得下一个人以为是漏判）**：
- 只按**文件**配对容器与控件，不解析模板里的真实父子关系——静态 CSS 拿不到 DOM。
  代价是可能在「同文件但互不相干」的两处之间误报，好处是实现简单、判据在真实代码上
  稳定可跑；本仓全量扫描为零命中，精度可信到拿去阻断。新增误报先收紧判据，别加白名单。
- 只认 px 字面量：``max-height: 60vh`` / ``height: var(--x)`` / ``calc()`` / ``em``
  一律跳过（算不出确定值就不猜）。``box-sizing`` 未声明按 border-box 计——本仓有全局
  border-box 重置（frontend/src/style），与浏览器默认 content-box 不同，这条要说清楚。
- ``overflow-y: auto|scroll`` 不算盖子：那是**有意**的滚动容器。
- 行内豁免：在**出问题的规则块内**加一行注释 ``control-clip-allow`` 并写明理由。
  ``clip`` 类命中按控件那一侧报行号，但**控件块或容器块任一侧**打标记都能豁免
  （写在哪一侧取决于「哪边是有意的」）。

用法
----
    python scripts/guard_control_clip.py                 # 扫描 frontend/src 全量
    python scripts/guard_control_clip.py a.vue b.css     # 只扫指定文件（合成样例 / 局部验证）

退出码：0 = 通过；1 = 命中栅栏。
"""

from __future__ import annotations

import bisect
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "frontend" / "src"
SCAN_SUFFIXES = {".vue", ".css", ".scss", ".sass"}

SKIP_MARKER = "control-clip-allow"

PX_RE = re.compile(r"(-?\d+(?:\.\d+)?)px\b")
MAX_HEIGHT_RE = re.compile(r"^max-height$")
OVERFLOW_RE = re.compile(r"^overflow(?:-x|-y)?$")
HEIGHT_RE = re.compile(r"^height$")
PADDING_RE = re.compile(r"^padding(?:-(?:top|bottom))?$")
BORDER_SHORTHAND_RE = re.compile(r"^border(?:-(?:top|bottom))?$")
BORDER_WIDTH_RE = re.compile(r"^border(?:-(?:top|bottom))?-width$")
BOX_SIZING_RE = re.compile(r"^box-sizing$")
STYLE_OPEN_RE = re.compile(r"<style[^>]*>")
# 「盖住」子元素的 overflow 取值；auto/scroll 是有意滚动，不算裁切
CLIP_TOKENS = ("hidden", "clip")
# 命中 RULE pad 的选择器特征：只管按钮，避免误伤输入框等合法 content-box 用法
BUTTON_SELECTOR_RE = re.compile(r"btn|button", re.IGNORECASE)

HINTS = {
    "clip": "容器声明了 max-height + overflow:hidden，同文件里有控件比它高——子元素"
    "会被切边。请收敛控件尺寸，或去掉容器上的盖子（改由外层布局控制高度）",
    "pad": "不要用 padding 扩热区：padding 会一起画进可见尺寸，把 28px 的圆撑成 42px。"
    "热区改用 ::after { position:absolute; inset:-6px } 伪元素，视觉尺寸不变",
}


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for idx, ch in enumerate(text):
        if ch == "\n":
            starts.append(idx + 1)
    return starts


def _extract_style_text(raw: str) -> str:
    """取出 CSS 文本，且**保证行号与原文件逐行对齐**（非 style 行填成空行）。

    按行处理而不是正则切片：正则切出的片段拼接后行号会漂移，
    违规行号一旦指错，报错就查不到东西（判据类脚本的老坑）。
    """
    if not raw.lstrip().startswith("<") and "<style" not in raw:
        return raw
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
    """剥掉 CSS 注释但**保留换行**（行号不漂移）。"""
    return re.sub(
        r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S
    )


def iter_css_blocks(text: str, starts: list[int], base: int = 0):
    """按花括号配对扫描，产出 (selector, body, start_line, end_line)。

    不用正则切块：``@media`` 里有嵌套花括号，``[^{}]+\\{[^{}]*\\}`` 会把内层规则的
    selector 拿错。这里用配对扫描，``@media/@supports`` 的内容向内递归。
    ``base`` 是本段 text 在原文件中的字节偏移（.vue 只取 style 段时用于折算行号）。
    """

    def line_at(pos: int) -> int:
        return bisect.bisect_right(starts, pos + base)

    i = 0
    n = len(text)
    block_start = 0
    sel_start = None  # selector 的第一个非空白字符位置（用于行号，见下）
    while i < n:
        ch = text[i]
        if sel_start is None and not ch.isspace():
            sel_start = i
        if ch == "{":
            # 行号取 selector **真正起始**字符，而不是块起点：块起点是上一个 `}` 的
            # 下一位，落点常在上一块的收尾行甚至文件首行，报出来的行号会指错地方
            # —— 判据类脚本报错行号一旦指错，等于查不到（本仓踩过，见 AGENTS §四）。
            selector_start = sel_start if sel_start is not None else block_start
            selector = text[block_start:i].strip()
            depth = 1
            j = i + 1
            body_start = j
            while j < n and depth:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                j += 1
            body = text[body_start : j - 1] if depth == 0 else text[body_start:]
            start_line = line_at(selector_start)
            end_line = line_at(body_start + len(body))
            if selector.startswith("@"):
                yield from iter_css_blocks(body, starts, base + body_start)
            elif selector:
                yield selector, body, start_line, end_line
            i = j
            block_start = i
            sel_start = None
            continue
        i += 1


def _decls(body: str) -> list[tuple[str, str]]:
    """规则体 → [(property, value)]；跳过内嵌块（scss 的 & 嵌套等）。"""
    out: list[tuple[str, str]] = []
    depth = 0
    seg_start = 0
    for idx, ch in enumerate(body):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ";" and depth == 0:
            parsed = _parse_decl(body[seg_start:idx])
            if parsed:
                out.append(parsed)
            seg_start = idx + 1
    parsed = _parse_decl(body[seg_start:])
    if parsed:
        out.append(parsed)
    return out


def _parse_decl(segment: str) -> tuple[str, str] | None:
    segment = segment.strip()
    if not segment or ":" not in segment or "{" in segment:
        return None
    prop, _, value = segment.partition(":")
    prop = prop.strip().lower()
    value = value.strip()
    if not prop or prop.startswith("@") or prop.startswith("&"):
        return None
    if "!" in value:
        value = value.split("!", 1)[0].strip()
    if not value:
        return None
    return prop, value


def _px(value: str) -> float | None:
    m = PX_RE.fullmatch(value.strip())
    return float(m.group(1)) if m else None


def _length_token(value: str) -> float | None:
    """取字符串里第一个 px 长度（``1px solid var(--x)`` → 1.0）。"""
    m = PX_RE.search(value)
    return float(m.group(1)) if m else None


def _vertical_pair(value: str) -> tuple[float, float] | None:
    """padding 简写的纵向值：`a` → (a,a)；`a b` → (a,a)；`a b c d` → (a,c)。

    非 px（var()/em/%）或无长度语义（``none`` / ``0`` 无单位）按语义处理，
    取不到确定值返回 None —— 算不出就不猜（宁可漏判，不可错判）。
    """
    stripped = value.strip()
    if stripped in ("none", "0", "initial", "revert", "unset"):
        return (0.0, 0.0)
    parts = stripped.split()
    nums = [_px(p) for p in parts]
    if any(n is None for n in nums):
        return None
    vals = [n for n in nums if n is not None]
    if len(vals) == 1:
        return (vals[0], vals[0])
    if len(vals) == 2:
        return (vals[0], vals[0])
    if len(vals) >= 4:
        return (vals[0], vals[2])
    return None


def _border_vertical(value: str) -> tuple[float, float] | None:
    """border 简写的纵向宽度：``1px solid var(--x)`` → (1,1)；``none``/``0`` → (0,0)。"""
    stripped = value.strip()
    if stripped in ("none", "0", "initial", "revert", "unset"):
        return (0.0, 0.0)
    length = _length_token(stripped)
    if length is None:
        return None
    return (length, length)


def _outer_height(decls: list[tuple[str, str]]) -> float | None:
    """按 box-sizing 算外框（border-box）高度；缺 height 或取不到 px 时返回 None。"""
    height: float | None = None
    pad_top = pad_bottom = 0.0
    brd_top = brd_bottom = 0.0
    content_box = False
    for prop, value in decls:
        if HEIGHT_RE.match(prop):
            h = _px(value)
            if h is not None:
                height = h
        elif BOX_SIZING_RE.match(prop):
            content_box = value.strip() == "content-box"
        elif PADDING_RE.match(prop):
            pair = _vertical_pair(value)
            if pair is None:
                continue
            if prop == "padding":
                pad_top, pad_bottom = pair
            elif prop == "padding-top":
                pad_top = pair[0]
            else:
                pad_bottom = pair[1]
        elif BORDER_SHORTHAND_RE.match(prop):
            pair = _border_vertical(value)
            if pair is None:
                continue
            if prop == "border":
                brd_top, brd_bottom = pair
            elif prop.endswith("top"):
                brd_top = pair[0]
            else:
                brd_bottom = pair[1]
        elif BORDER_WIDTH_RE.match(prop):
            w = _px(value)
            if w is None:
                continue
            if prop.endswith("top"):
                brd_top = w
            elif prop.endswith("bottom"):
                brd_bottom = w
            else:
                brd_top = brd_bottom = w
    if height is None:
        return None
    if not content_box:
        # border-box：height 已含 padding / border（本仓全局 border-box 重置）
        return height
    return height + pad_top + pad_bottom + brd_top + brd_bottom


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _scan(path: Path) -> list[tuple[str, int, str]]:
    """返回 [(rule, lineno, detail)]；rule 取值见 HINTS。"""
    raw = _read(path)
    if raw is None:
        return []

    # 豁免行（注释里带 SKIP_MARKER）：按**原文件行号**记，落在某个规则块的行区间内
    # 才生效。刻意不提供「文件级豁免」——整文件放行会让规则在真实代码上失去意义。
    marked = {
        idx
        for idx, line in enumerate(raw.splitlines(), start=1)
        if SKIP_MARKER in line
    }

    text = _strip_comments(_extract_style_text(raw))
    if not text.strip():
        return []
    starts = _line_starts(text)

    blocks = list(iter_css_blocks(text, starts))
    containers: list[tuple[str, float, int]] = []
    controls: list[tuple[str, float, int]] = []
    button_blocks: list[tuple[str, list[tuple[str, str]], int, int]] = []

    for selector, body, start_line, end_line in blocks:
        if any(start_line <= m <= end_line for m in marked):
            continue  # 块内显式豁免
        decls = _decls(body)
        if not decls:
            continue
        max_h: float | None = None
        clipped = False
        for prop, value in decls:
            if MAX_HEIGHT_RE.match(prop):
                max_h = _px(value)
            elif OVERFLOW_RE.match(prop) and any(t in value for t in CLIP_TOKENS):
                clipped = True
        if max_h is not None and clipped:
            containers.append((selector, max_h, start_line))
        outer = _outer_height(decls)
        if outer is not None:
            controls.append((selector, outer, start_line))
        if BUTTON_SELECTOR_RE.search(selector):
            button_blocks.append((selector, decls, start_line, end_line))

    hits: list[tuple[str, int, str]] = []
    for sel_c, limit, _c_line in containers:
        for sel_h, outer, h_line in controls:
            if outer > limit:
                hits.append(
                    (
                        "clip",
                        h_line,
                        f"{sel_h} 外框高 {outer:g}px > 同文件容器 {sel_c} 的 "
                        f"max-height {limit:g}px，子元素会被切掉 {outer - limit:g}px",
                    )
                )

    for sel, decls, d_line, _d_end in button_blocks:
        content_box = False
        pad = 0.0
        for prop, value in decls:
            if BOX_SIZING_RE.match(prop) and value.strip() == "content-box":
                content_box = True
            if PADDING_RE.match(prop):
                pair = _vertical_pair(value)
                if pair is not None:
                    pad = max(pad, pair[0], pair[1])
        if content_box and pad > 0:
            hits.append(
                (
                    "pad",
                    d_line,
                    f"{sel} 用 content-box + padding {pad:g}px 扩尺寸：padding 会画进"
                    "可见框，把视觉尺寸一起撑大",
                )
            )
    return hits


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

    violations: dict[str, list[tuple[str, int, str]]] = {}
    for path in files:
        try:
            rel = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            rel = str(path)
        hits = _scan(path)
        if hits:
            violations[rel] = hits

    if not violations:
        print(
            "OK: 无「容器裁切控件 / padding 撑热区」回潮（扫 %d 个样式文件）" % len(files)
        )
        return 0

    print("ERROR: 检测到控件被裁切或热区写法回潮：", file=sys.stderr)
    for rel in sorted(violations):
        for rule, lineno, detail in violations[rel]:
            print("  %s:%d  [%s] %s" % (rel, lineno, rule, detail), file=sys.stderr)
            print("        -> %s" % HINTS[rule], file=sys.stderr)
    print(
        "\n      背景：2026-10-09 自选页圆按钮「又大又被切」——max-height 盖子 + "
        "content-box 撑 padding 叠加所致。\n"
        "      确需例外：在控件块或容器块内加一行注释 %s 并写明理由。" % SKIP_MARKER,
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
