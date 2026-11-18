# -*- coding: utf-8 -*-
"""回归网：``scripts/guard_net_assets_source.py``（#119 / #2883 净资产单一出口守卫）。

四组用例，缺一不可（与 ``test_detail_tables_guard.py`` 同款）：
  · **合成命中样本** —— R1 命名族 / R2 词根族各自能抓到现算；
  · **合成放行样本** —— 不得误报。最危险的是两值分别作占比分母
    （``CategoryBalanceTable.vue`` 的真实形态）、注释里的举例说明、反向净负债；
  · **真实文件回退探针** —— 把修复摘掉（注回 ``totalAssets - totalLiabilities``），
    守卫必须转红。没有这条，「守卫是绿的」只能证明「它没扫到东西」；
  · **失败态** —— 扫不到输入必须 exit 2，不得读成「无事发生」。

⚠️ 用 ``unittest.TestCase`` 写法：CI 的 ``scripts_test`` job 以
``python -m unittest scripts.tests.test_guard_net_assets_source -v`` 显式收，
pytest 风格裸函数不会被收集。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "guard_net_assets_source.py"
REAL_FILE = (
    REPO_ROOT
    / "frontend/src/views/asset/panorama/components/OverviewAssetsCard.vue"
)
TMP_ROOT = Path(tempfile.gettempdir()).resolve()

# R1：命名族精确命中（原始缺陷形态）
HIT_NAMED = """<template>
  <MoneyDisplay :value="totalAssets - totalLiabilities" />
</template>
"""

# R2：换个变量名也躲不掉（含 asset / liabilit 词根）
HIT_ROOTS = """<script setup lang="ts">
const result = foo_assets - bar_liabilities;
</script>
"""

# 放行：两值分别当占比分母，不出现在同一个减法里（CategoryBalanceTable.vue 真实形态）
PASS_SEPARATE = """<script setup lang="ts">
const assetPct = item.value / props.totalAssets * 100;
const liabPct = item.value / props.totalLiabilities * 100;
</script>
"""

# 放行：注释里举例说明这个表达式（守卫 docstring / 修复注释里都会写）
PASS_COMMENTS = """<template>
  <!-- 不要在页面层写 totalAssets - totalLiabilities，净资产一律直出 -->
  <MoneyDisplay :value="netAssets" />
</template>
<script setup lang="ts">
// 反例：totalAssets - totalLiabilities 会绕过 #119 单一出口
/* 再举一例：total_assets_cny - total_liabilities_cny */
const url = "https://example.com/a-b";
</script>
"""

# 放行：反向是净负债，不是净资产
PASS_REVERSE = """<script setup lang="ts">
const netDebt = totalLiabilities - totalAssets;
</script>
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


class GuardNetAssetsSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="net-assets-", dir=str(TMP_ROOT))).resolve()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, body: str) -> Path:
        path = self.tmp / name
        path.write_text(body, encoding="utf-8")
        return path

    # ── 灵敏度：命中样本 ────────────────────────────────────────────────
    def test_named_subtraction_is_flagged(self) -> None:
        path = self._write("Hit.vue", HIT_NAMED)
        result = _run(str(path))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("totalAssets - totalLiabilities", result.stderr)

    def test_renamed_subtraction_is_flagged(self) -> None:
        path = self._write("Hit.vue", HIT_ROOTS)
        result = _run(str(path))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("foo_assets - bar_liabilities", result.stderr)

    def test_underscore_backend_field_names_are_flagged(self) -> None:
        path = self._write("Hit.vue", 'const n = data.total_assets_cny - data.total_liabilities_cny;\n')
        result = _run(str(path))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    # ── 放行：不得误报 ──────────────────────────────────────────────────
    def test_separate_ratio_denominators_are_not_flagged(self) -> None:
        path = self._write("Ratios.vue", PASS_SEPARATE)
        result = _run(str(path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_comment_examples_are_not_flagged(self) -> None:
        path = self._write("Commented.vue", PASS_COMMENTS)
        result = _run(str(path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_reverse_subtraction_is_not_flagged(self) -> None:
        path = self._write("Reverse.vue", PASS_REVERSE)
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
        self.assertIn(':value="netAssets"', text, "取样文件已搬家，探针会恒真——请同步改本用例")
        fake = self.tmp / REAL_FILE.name
        # 探针：把修复摘掉，注回页面层减法
        fake.write_text(
            text.replace(':value="netAssets"', ':value="totalAssets - totalLiabilities"'),
            encoding="utf-8",
        )
        result = _run(str(fake))
        self.assertEqual(result.returncode, 1, "注回减法后守卫必须转红")
        self.assertIn("totalAssets - totalLiabilities", result.stderr)

        # 还原后必须恢复为绿（否则前面的红是别的原因造成的）
        fake.write_text(text, encoding="utf-8")
        result = _run(str(fake))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_current_repo_is_clean(self) -> None:
        """仓库当前状态必须通过（防「永远绿」也防「永远红」）。"""
        result = _run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
