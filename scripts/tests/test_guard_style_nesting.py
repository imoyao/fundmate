# -*- coding: utf-8 -*-
"""回归网：``scripts/guard_style_nesting.py``（#3213 原生 CSS 里的 `&__x` / `&-x`）。

四组用例，缺一不可（与 ``test_guard_net_assets_source.py`` 同款）：

  · **合成命中样本** —— ``&__value``（BEM 元素）与 ``&-line``（BEM 修饰/后缀）都要抓到。
    第二类是本守卫存在的关键：只认 ``&__`` / ``&--`` 的写法会**放过 ImageUploader**
    （它 6 条死规则全是 ``&-line`` / ``&-img`` 这种形态）。
  · **合成放行样本** —— 原生 CSS 里合法的 ``&:hover`` / ``&.is-active`` / ``& > em`` /
    ``&[data-x]`` / 裸 ``&``、注释与字符串里出现 ``&__x``、``lang="scss"`` 的块。
    误报比漏报更贵：一旦有人被无理由卡住，这条守卫就会被绕过。
  · **真实文件回退探针** —— 拿当前仓库里那个带 ``lang="scss"`` 的真实组件，在内存里把
    ``lang="scss"`` 摘掉（= 回到 #3213 的缺陷形态），守卫必须转红且命中 6 处。
    没有这条，「守卫是绿的」只能证明「它没扫到东西」。
  · **失败态** —— 扫不到输入必须 exit 2，不得读成「无事发生」。

⚠️ 用 ``unittest.TestCase`` 写法：CI 的 ``scripts_test`` job 以
``python -m unittest discover -s scripts/tests`` 收，pytest 风格裸函数不会被收集。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "guard_style_nesting.py"
REAL_FILE = REPO_ROOT / "frontend/src/components/ImageUploader/index.vue"
TMP_ROOT = Path(tempfile.gettempdir()).resolve()

# 命中：BEM 元素写法（IntelligentAnalysis / inventory 的原始形态）
HIT_BEM_ELEMENT = """<template>
  <span class="net-range__value">+1.23%</span>
</template>

<style scoped>
.net-range {
  display: inline-flex;

  &__value {
    font-family: var(--font-mono);
  }
}
</style>
"""

# 命中：后缀拼接（ImageUploader 的原始形态，`&--x` 之外的另一半）
HIT_BEM_SUFFIX = """<template>
  <p class="tip-line">说明</p>
</template>

<style scoped>
.tip {
  margin: 0;

  &-line {
    color: var(--text-label);
  }
}
</style>
"""

# 放行：原生 CSS 合法的 `&` 用法
PASS_NATIVE_NESTING = """<template>
  <div class="box"><em>字</em></div>
</template>

<style scoped>
.box {
  color: red;

  &:hover {
    color: blue;
  }

  &.is-active {
    color: green;
  }

  & > em {
    font-weight: 600;
  }

  &[data-state="open"] {
    display: block;
  }

  & .inner {
    margin: 0;
  }
}
</style>
"""

# 放行：说明文字里出现 `&__x`（注释 / 字符串），不得误红
PASS_COMMENTS_AND_STRINGS = """<template>
  <div class="x" />
</template>

<style scoped>
/* 反例：&__value 在原生 CSS 里非法，会整条丢弃（#3213） */
.x {
  content: "&__value 不是选择器";
  &::after {
    content: '&--mod';
  }
}
</style>
"""

# 放行：SCSS 块里的 `&__x` 由预处理器展开，是合法写法
PASS_SCSS_BLOCK = """<template>
  <span class="net-range__value">+1.23%</span>
</template>

<style lang="scss" scoped>
.net-range {
  &__value {
    font-family: var(--font-mono);
  }
}
</style>
"""


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


class GuardStyleNestingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="style-nesting-", dir=str(TMP_ROOT))).resolve()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, body: str) -> Path:
        path = self.tmp / name
        path.write_text(body, encoding="utf-8")
        return path

    # ── 灵敏度：命中样本 ────────────────────────────────────────────────
    def test_bem_element_is_flagged(self) -> None:
        path = self._write("Element.vue", HIT_BEM_ELEMENT)
        result = _run(str(path))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("&__value", result.stdout)
        # 行号要指得准：`&__value` 在第 9 行（`<style>` 在第 5 行）
        self.assertIn(":9:", result.stdout)

    def test_bem_suffix_is_flagged(self) -> None:
        """`&-line` 这一形态必须命中——否则 ImageUploader 的 6 条死规则会漏。"""
        path = self._write("Suffix.vue", HIT_BEM_SUFFIX)
        result = _run(str(path))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("&-line", result.stdout)

    def test_plain_css_file_is_flagged(self) -> None:
        path = self._write("legacy.css", ".tip {\n  &--holding {\n    color: red;\n  }\n}\n")
        result = _run(str(path))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("&--holding", result.stdout)

    # ── 放行：不得误报 ──────────────────────────────────────────────────
    def test_native_nesting_is_not_flagged(self) -> None:
        path = self._write("Native.vue", PASS_NATIVE_NESTING)
        result = _run(str(path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_comments_and_strings_are_not_flagged(self) -> None:
        path = self._write("Noise.vue", PASS_COMMENTS_AND_STRINGS)
        result = _run(str(path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_scss_block_is_not_flagged(self) -> None:
        path = self._write("Scss.vue", PASS_SCSS_BLOCK)
        result = _run(str(path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    # ── 失败态：拿不到输入不得读成「无事发生」 ──────────────────────────
    def test_missing_input_exits_two(self) -> None:
        result = _run(str(self.tmp / "no-such-dir"))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("拿不到输入", result.stdout + result.stderr)

    # ── 真实文件回退探针 ────────────────────────────────────────────────
    def test_real_file_regression_probe(self) -> None:
        text = REAL_FILE.read_text(encoding="utf-8")
        self.assertIn(
            '<style lang="scss" scoped>',
            text,
            "取样组件已改写法（不再是 lang=scss 的块）——请同步改本用例的探针",
        )
        self.assertEqual(_run(str(REAL_FILE)).returncode, 0, "当前真实文件应当已修好")

        # 探针：摘掉 lang="scss"，回到 #3213 的缺陷形态，守卫必须转红
        reverted = self.tmp / REAL_FILE.name
        reverted.write_text(
            text.replace('<style lang="scss" scoped>', "<style scoped>"),
            encoding="utf-8",
        )
        result = _run(str(reverted))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        # 6 条：&-line / &-hint / &-img / &-meta / &-name / &-size
        self.assertEqual(len(re.findall(r"非 SCSS 样式块", result.stdout)), 6, result.stdout)


if __name__ == "__main__":
    unittest.main()
