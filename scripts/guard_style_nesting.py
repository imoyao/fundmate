#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守卫：非 SCSS 的样式块里禁止写 ``&__x`` / ``&-x`` 这类拼接式嵌套（#3213）。

WHY
---
``<style scoped>``（**没有** ``lang="scss"``）走的是**原生 CSS**，浏览器按 CSS Nesting
解析。原生 CSS 的 ``&`` 是「父选择器引用」，后面只能接组合符 / ``.class`` / ``#id`` /
``[attr]`` / 伪类伪元素；``&__value``、``&-line`` 是 **SCSS 的字符串拼接**，在原生 CSS 里
是**非法选择器** ⇒ **整条嵌套规则被丢弃**，且三处都不吭声：

- 构建不报错：postcss 原样透传，Vue 只负责在 ``&`` 后补 scope 属性；
- stylelint 不报错：本仓配置不校验 ``&`` 后缀；
- 只有肉眼 + computed style 才能发现——所以它只能靠「事后撞见」，不会自己浮出来。

实测（2026-11-21，#3213，用真实 ``@vue/compiler-sfc`` 编译）产物形如
``.net-range { &[data-v-xxx] { 声明 } &__value[data-v-xxx] { 声明 } }``——
**基类声明因为被包进 ``&[data-v]`` 而幸存**，子类规则整条消失。这正是「样式看起来
写了、实际一条没生效」的成因，也是它容易被误判成「浏览器缓存 / 优先级」的原因。

存量 3 个文件 8 条规则曾全部失效（IntelligentAnalysis 1 / inventory 1 / ImageUploader 6），
其中 ImageUploader 的预览缩略图连 ``72×48`` 尺寸都没有，按原图尺寸渲染。

判据（零容忍，无基线）
----------------------
``frontend/src`` 下的 ``.vue`` ``<style>`` 块与 ``.css`` 文件里，只要**不是**预处理语言
（无 ``lang`` 或 ``lang="css"``），出现 ``&`` 紧跟 ``[A-Za-z0-9_-]`` 即红。

两种正解，按块体量二选一：

1. 加 ``lang="scss"``——块内本来就是 SCSS 写法（BEM 拼接），一整块改编译方式；
2. 拆平选择器——``.x__y { … }`` 独立成条，保持纯 CSS，不必引入预处理。

不覆盖（刻意）
--------------
- ``lang="scss" / "sass" / "less" / "postcss"`` 的块：那里 ``&__`` 由预处理器展开，合法；
- 其余 SCSS-only 语法（``$var`` / ``@include`` / ``#{}``）不在本判据内——只治「静默丢弃」
  这一类，因为它们的失败形态不同（前者编译期即报错，不需要守卫）；
- 注释与字符串字面量已剔除，说明文字里写 ``&__x`` 不会误红。

用法
----
    python scripts/guard_style_nesting.py                 # 扫描 frontend/src 全量
    python scripts/guard_style_nesting.py a.vue b.css      # 只扫指定文件（pre-commit 场景）

退出码：0 = 通过；1 = 命中栅栏；2 = 拿不到输入（结论不可信，**不得**当成通过）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "frontend" / "src"
SCAN_SUFFIXES = {".vue", ".css"}

STYLE_BLOCK_RE = re.compile(r"<style(?P<attrs>[^>]*)>(?P<body>.*?)</style>", re.S)
LANG_RE = re.compile(r"""lang\s*=\s*["']?([\w-]+)""", re.I)
# 注释与字符串一律抹成空格（**保留换行**，否则报出来的行号会整体前移）
NOISE_RE = re.compile(r"""/\*.*?\*/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'""", re.S)
# 命中形态：`&` 紧跟标识符字符。原生 CSS 里 `&` 后接这些字符**没有**合法含义，
# 只可能是 SCSS 拼接（`&__x` / `&--x` / `&-x`）或手滑写错的类名。
BAD_NESTING_RE = re.compile(r"&[A-Za-z0-9_-]")


def _blank_noise(text: str) -> str:
    """把注释 / 字符串替换为等长空白（换行保留），让偏移量与行号保持有效。"""
    return NOISE_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _iter_blocks(suffix: str, text: str):
    """产出 (块内容, 块首之前的换行数, lang)。``lang`` 缺省按原生 CSS 处理。"""
    if suffix == ".css":
        yield text, 0, "css"
        return
    for m in STYLE_BLOCK_RE.finditer(text):
        lang_match = LANG_RE.search(m.group("attrs"))
        lang = (lang_match.group(1) if lang_match else "css").lower()
        yield m.group("body"), text.count("\n", 0, m.start("body")), lang


def scan_text(suffix: str, text: str) -> list[tuple[int, str]]:
    """返回 [(行号, 命中的片段)]；``suffix`` 决定按 ``.vue`` 还是 ``.css`` 解析。"""
    hits: list[tuple[int, str]] = []
    for body, base_lines, lang in _iter_blocks(suffix, text):
        if lang != "css":
            continue
        cleaned = _blank_noise(body)
        for m in BAD_NESTING_RE.finditer(cleaned):
            offset = m.start()
            line = base_lines + body.count("\n", 0, offset) + 1
            # 片段取到本行末：``&__label {`` 这种足够定位，且与 grep 结果对齐
            snippet = body[offset:].split("\n", 1)[0].strip()
            hits.append((line, snippet))
    return hits


def scan_file(path: Path) -> list[tuple[int, str]]:
    return scan_text(path.suffix, path.read_text(encoding="utf-8"))


def iter_targets(root: Path):
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        if path.suffix in SCAN_SUFFIXES and path.is_file():
            yield path


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("-")]
    targets = [Path(a) for a in args] if args else list(iter_targets(DEFAULT_ROOT))
    if not targets:
        print(f"[style-nesting] 拿不到输入：{DEFAULT_ROOT} 下没有可扫的 .vue/.css", file=sys.stderr)
        return 2

    failures = 0
    for path in targets:
        if not path.exists():
            print(f"[style-nesting] 拿不到输入：{path} 不存在", file=sys.stderr)
            return 2
        for line, snippet in scan_file(path):
            failures += 1
            rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
            print(f"{rel}:{line}: 非 SCSS 样式块里的嵌套拼接 `{snippet}`")

    if failures:
        print(
            f"\n[style-nesting] {failures} 处：原生 CSS 里 `&__x` / `&-x` 是非法选择器，"
            "整条规则会被浏览器丢弃（不报错）。\n"
            '  正解① 给该 <style> 加 lang="scss"（块内本就是 SCSS 写法）；\n'
            "  正解② 拆平选择器，把子类写成独立规则。详见 #3213。",
            file=sys.stderr,
        )
        return 1
    print(f"[style-nesting] OK：{len(targets)} 个文件均无非 SCSS 块的嵌套拼接")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
