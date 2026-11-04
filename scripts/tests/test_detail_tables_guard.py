# -*- coding: utf-8 -*-
"""回归网：``scripts/guard_detail_tables.py``（源 CNB #553）。

四组用例，缺一不可：
  · **合成命中样本** —— 三条规则各自能抓到问题；
  · **合成放行样本** —— 不得误报。最危险的是「只写 width / 只写 padding」的表格布局
    （判进来就是逼人删布局）、`:class` 动态类名、以及非详情页的存量表格；
  · **真实文件回退探针** —— 把 `PositionChannelTable.vue` 的共享类摘掉，守卫必须转红。
    没有这条，「守卫是绿的」只能证明「它没扫到东西」；
    ⚠️ 取样文件是**会搬家的**：#980 拆分把这张表从 `ProductPositionSection.vue`
    搬进了 `positionSection/PositionChannelTable.vue`，探针当时因此静默失效
    （突变字符串在旧文件里已不存在 ⇒ 替换是空操作 ⇒ 守卫保持绿 ⇒ 断言报红）。
    再搬表时，这里必须跟着改，否则探针变成恒真。
  · **基线语义** —— 基线里的文件放行、基线外的文件必须红（否则基线会悄悄变成垃圾桶）。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# 真实路径（`resolve()`）：macOS 的 `/tmp` → `/private/tmp`，守卫内部按 resolve 后的
# 路径判「是不是详情页」，临时目录用未解析的 `/tmp` 会与它错开（实测踩过）。
REPO_ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = Path(tempfile.gettempdir()).resolve()
SCRIPT = REPO_ROOT / "scripts" / "guard_detail_tables.py"
DETAIL_SAMPLE = (
    REPO_ROOT
    / "frontend/src/views/product/components/positionSection/PositionChannelTable.vue"
)

ORPHAN_TABLE = """<template>
  <table class="my-table">
    <tbody><tr><td>1</td></tr></tbody>
  </table>
</template>

<style scoped>
.my-table {
  width: 100%;
  border-collapse: collapse;
}
</style>
"""

CONFORMING_TABLE = """<template>
  <table class="detail-table detail-table--fixed my-table">
    <thead><tr><th class="detail-table__num">占比</th></tr></thead>
    <tbody><tr><td class="detail-table__num">1</td></tr></tbody>
  </table>
</template>

<style scoped>
.my-table {
  min-width: 400px;
}
</style>
"""

SECOND_BASELINE = """<template>
  <table class="detail-table my-table">
    <tbody><tr><td>1</td></tr></tbody>
  </table>
</template>

<style scoped>
.my-table {
  width: 100%;
  border-collapse: collapse;
}

.my-table td {
  padding: 6px var(--space-2);
}
</style>
"""

NUM_ALIGN = """<template>
  <table class="detail-table my-table">
    <tbody><tr><td class="my-table__num">1</td></tr></tbody>
  </table>
</template>

<style scoped>
.my-table__num {
  font-variant-numeric: tabular-nums;
  text-align: right;
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


class GuardDetailTablesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="detail-table-", dir=str(TMP_ROOT))).resolve()
        self.detail_dir = self.tmp / "frontend" / "src" / "views" / "product"
        self.other_dir = self.tmp / "frontend" / "src" / "views" / "asset"
        self.detail_dir.mkdir(parents=True)
        self.other_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, where: Path, name: str, body: str) -> Path:
        path = where / name
        path.write_text(body, encoding="utf-8")
        return path

    # ── RULE 1：详情页 <table> 必须带共享类 ──────────────────────────────
    def test_detail_table_without_shared_class_is_flagged(self) -> None:
        path = self._write(self.detail_dir, "Orphan.vue", ORPHAN_TABLE)
        result = _run(str(path))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("missing-class", result.stderr)

    def test_detail_table_with_shared_class_passes(self) -> None:
        path = self._write(self.detail_dir, "Ok.vue", CONFORMING_TABLE)
        result = _run(str(path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dynamic_class_binding_is_not_flagged(self) -> None:
        # 类名运行时算出来的，静态判据看不见；猜它会误报（宁可漏，不可错）。
        body = ORPHAN_TABLE.replace(
            'class="my-table"', ':class="[\'detail-table\', cls]"'
        )
        path = self._write(self.detail_dir, "Dyn.vue", body)
        result = _run(str(path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    # ── RULE 2：第二份表格基线 ─────────────────────────────────────────
    def test_second_table_baseline_is_flagged(self) -> None:
        path = self._write(self.other_dir, "Dup.vue", SECOND_BASELINE)
        result = _run(str(path))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("second-baseline", result.stderr)

    def test_partial_layout_rules_are_not_a_baseline(self) -> None:
        # 只写 min-width / 只写某列 padding 的是布局，不是基线——判进来就是误报。
        body = CONFORMING_TABLE.replace(
            ".my-table {\n  min-width: 400px;\n}",
            ".my-table {\n  width: 100%;\n}",
        )
        path = self._write(self.other_dir, "Layout.vue", body)
        result = _run(str(path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    # ── RULE 3：详情页自写数字列对齐 ───────────────────────────────────
    def test_custom_num_alignment_is_flagged(self) -> None:
        path = self._write(self.detail_dir, "Num.vue", NUM_ALIGN)
        result = _run(str(path))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("num-align", result.stderr)

    def test_default_left_alignment_is_not_flagged(self) -> None:
        # 非数字列的右对齐（如操作列）不是约定要管的东西。
        body = NUM_ALIGN.replace("text-align: right;", "text-align: left;")
        body = body.replace("my-table__num", "my-table__action")
        path = self._write(self.detail_dir, "Action.vue", body)
        result = _run(str(path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    # ── 失败态：拿不到输入不得读成「无事发生」 ──────────────────────────
    def test_missing_input_exits_two(self) -> None:
        result = _run(str(self.tmp / "no-such-file.vue"))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("NO-INPUT", result.stderr)

    # ── 真实文件回退探针：把修复摘掉，守卫必须转红 ───────────────────────
    def test_real_table_regression_probe(self) -> None:
        text = DETAIL_SAMPLE.read_text(encoding="utf-8")
        fake = self.detail_dir / DETAIL_SAMPLE.name
        # 探针一：摘掉共享类（模拟「第六处又手写一张表」）
        fake.write_text(
            text.replace(
                "detail-table detail-table--fixed product-position__table",
                "product-position__table",
            ),
            encoding="utf-8",
        )
        result = _run(str(fake))
        self.assertEqual(result.returncode, 1, "摘掉共享类后守卫必须转红")
        self.assertIn("missing-class", result.stderr)

        # 探针二：把「整表 tabular-nums + 右对齐」的旧实现注回去
        fake.write_text(
            text
            + "\n<style scoped>\n.product-position__table td {\n  width: 100%;\n"
            "  border-collapse: collapse;\n  padding: 6px var(--space-2);\n}\n</style>\n",
            encoding="utf-8",
        )
        result = _run(str(fake))
        self.assertEqual(result.returncode, 1, "注回手抄基线后守卫必须转红")
        self.assertIn("second-baseline", result.stderr)

        # 还原后必须恢复为绿（否则前面的红是别的原因造成的）
        fake.write_text(text, encoding="utf-8")
        result = _run(str(fake))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class GuardBaselineSemanticsTest(unittest.TestCase):
    """基线只冻结「已经在那里的」，不得变成「这个文件以后怎么改都行」。"""

    def test_baseline_files_are_real_and_contain_the_baseline(self) -> None:
        import json

        data = json.loads(
            (REPO_ROOT / "scripts/guard_detail_tables.baseline.json").read_text(
                encoding="utf-8"
            )
        )
        files = data["files"]
        self.assertTrue(files, "基线为空：说明存量已被收编，应删除本基线文件")
        for rel in files:
            path = REPO_ROOT / rel
            self.assertTrue(path.is_file(), f"基线里的文件已不存在：{rel}")


if __name__ == "__main__":
    unittest.main()
