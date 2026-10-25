/**
 * guard_col_divider 回归样本（2026-10 #2157 栏间竖向分割线收口）。
 *
 * 四组样本各司其职，缺一不可：
 *   · **命中样本** —— 规则真能抓到问题（改回旧写法要红）；
 *   · **放行样本** —— 不得误报。这里最危险的是**语义强调条**（3px/4px + warning/danger/
 *     info）、**选中指示条**（2px transparent）、**卡片内降权线**（--border-subtle）——
 *     issue #2157 正文特意写「不要一刀切」，误报会把这三类好写法一起逼死；
 *   · **豁免样本** —— `col-divider-allow` 的粒度是「本行或相邻行」（刻意不给文件级豁免）；
 *   · **元样本** —— 报错行号必须指到出问题的那一行（行号指错 = 判据等于查不到，
 *     AGENTS「正则/字符串类判据的两个常见错」记着这个坑）。
 *
 * 最后跑**真实文件**：基线 3 处必须静默、全仓扫描必须零命中；再把裸声明注回真实文件的
 * 副本 —— 只有这条红了，才知道前面那条「零命中」不是空转。
 */
import { spawnSync } from "node:child_process";
import { pythonOrFail } from "./_python-interpreter.mjs";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import assert from "node:assert/strict";
import test from "node:test";

const ROOT = process.cwd();
const SCRIPT = join(ROOT, "scripts", "guard_col_divider.py");
const REAL_WITH_SEMANTIC_BAR = join(
  ROOT,
  "frontend/src/views/product/components/ProductHoldingSection.vue"
);
const STYLE_ENTRY = join(ROOT, "frontend/src/style/index.scss");
const BASELINE_FILES = [
  "frontend/src/components/Watchlist/ColumnSettingsModal.vue",
  "frontend/src/views/asset/watchlist/components/FilterPanelBody.vue",
  // PageToc 2026-10-25 自 views/product/components/ProductPageToc.vue 上提改名
  "frontend/src/components/PageToc/index.vue"
].map((rel) => join(ROOT, rel));

const OVERVIEW_CARD = join(
  ROOT,
  "frontend/src/views/asset/panorama/components/OverviewSummaryCard.vue"
);

/**
 * 解释器探测与「静默绿」（#119，同 guard_control_clip.test.js）。
 *
 * 写死 `python` 在 Debian/Ubuntu、容器、CNB 工作区都会 ENOENT；此时子进程根本没跑，
 * 而放行断言恰好因为「什么都没跑」而全部假通过 —— 最坏的一种绿。故探测交给唯一一份
 * `_python-interpreter.mjs`（本文件原先是 6 份拷贝之一），探测不到就在加载期抛错。
 */
const PY = pythonOrFail();
const PY_BIN = PY[0];
const PY_ARGS = PY.slice(1);

function run(paths) {
  const r = spawnSync(PY_BIN, [...PY_ARGS, SCRIPT, ...paths], { encoding: "utf8" });
  // 退出码 1 是守卫「发现了问题」的正常信号，>1 才是自身崩溃；把崩溃喂给放行断言
  // 会伪装成「无回潮」，所以这里直接抛。
  if (r.error) {
    throw new Error(`守卫脚本无法启动（${PY_BIN}）：${r.error.message}`);
  }
  if (r.status > 1) {
    throw new Error(`守卫脚本异常退出（status=${r.status}）：\n${r.stdout || ""}\n${r.stderr || ""}`);
  }
  return (r.stdout || "") + (r.stderr || "");
}

/** 把样本写成临时 .vue 后交给守卫扫（临时文件在仓外 ⇒ 不命中任何基线预算） */
function guard(files, ext = ".vue") {
  const dir = mkdtempSync(join(tmpdir(), "col-divider-"));
  const paths = files.map((content, i) => {
    const p = join(dir, `s${i}${ext}`);
    writeFileSync(p, content, "utf8");
    return p;
  });
  return run(paths);
}

/** 通过的输出里既不该有命中标记，也不该有 Python 崩溃（崩溃会让放行断言空转） */
const NO_HIT = /ERROR: |Traceback/;

/* ---------- 命中样本 ---------- */

const PRE_FIX = `<template>
  <div class="filter-panel__sidebar">x</div>
</template>

<style scoped>
.filter-panel__sidebar {
  border-right: 1px solid var(--border-light);
}
</style>`;

test("命中：修复前的真实写法（border-right + 1px + --border-light）", () => {
  const out = guard([PRE_FIX]);
  assert.match(out, /ERROR: /);
  assert.match(out, /border-right: 1px solid var\(--border-light\)/);
  // 命中行号本身就是判据：必须指到声明那一行（样本里是第 7 行）
  assert.match(out, /s0\.vue:7\b/, `行号没指向声明行：\n${out}`);
});

test("命中：空白与大小写与 !important 都不能骗过判据（归一化后仍报）", () => {
  const out = guard([
    `<template><div class="cs-nav">x</div></template>
<style scoped>
.cs-nav {
  border-left:1px  SOLID   var( --border-light ) !important;
}
</style>`
  ]);
  assert.match(out, /ERROR: /, `归一化后应命中：\n${out}`);
  assert.match(out, /border-left: 1px solid var\(--border-light\)/);
});

test("命中：同一文件里写两条 → 两条都要报（不是只报一条）", () => {
  const out = guard([
    `<template><div>x</div></template>
<style scoped>
.a { border-left: 1px solid var(--border-light); }
.b { border-right: 1px solid var(--border-light); }
</style>`
  ]);
  assert.match(out, /s0\.vue:3\b/, out);
  assert.match(out, /s0\.vue:4\b/, out);
  assert.match(out, /border-left: 1px solid var\(--border-light\)/);
  assert.match(out, /border-right: 1px solid var\(--border-light\)/);
});

test("命中：@media / 嵌套块里的声明同样被扫到（正则切块会漏这一类）", () => {
  const out = guard([
    `<template><div class="page-toc">x</div></template>
<style scoped>
@include bp.above("lg") {
  .page-toc {
    border-left: 1px solid var(--border-light);
  }
}
</style>`
  ]);
  assert.match(out, /ERROR: /, `嵌套块没被扫到：\n${out}`);
  // 声明落在第 5 行（1 template / 2 <style> / 3 @include / 4 选择器 / 5 声明）
  assert.match(out, /s0\.vue:5\b/, out);
});

test("命中：.scss 文件（无 <style> 段）按全文扫描", () => {
  const out = guard(
    [`.legacy-panel {
  border-right: 1px solid var(--border-light);
}`],
    ".scss"
  );
  assert.match(out, /ERROR: /, `独立样式文件没被扫到：\n${out}`);
  assert.match(out, /s0\.scss:2\b/, out);
});

/* ---------- 放行样本（误报源，issue #2157 点名的三类必须先放行） ---------- */

test("放行：语义强调条（3px warning）——是信息不是分割，issue 明令不要混为一谈", () => {
  const out = guard([
    `<template><div class="holding-row">x</div></template>
<style scoped>
.holding-row {
  border-left: 3px solid var(--color-warning, var(--brand-700));
}
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `语义强调条被误判成栏间分割线：\n${out}`);
});

test("放行：抽屉内 4px 竖条（温度语义色）", () => {
  const out = guard([
    `<template><div class="opportunity-item">x</div></template>
<style scoped>
.opportunity-item { border-left: 4px solid var(--temp-low); }
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `4px 语义条被误判：\n${out}`);
});

test("放行：选中指示条（2px transparent 占位 + 选中态只改 color）", () => {
  const out = guard([
    `<template><a class="page-toc__link">x</a></template>
<style scoped>
.page-toc__link {
  margin-left: -1px;
  border-left: 2px solid transparent;
}
.page-toc__link.is-active { border-left-color: var(--brand-700); }
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `选中指示条被误判成分割线：\n${out}`);
});

test("放行：卡片内降权分割线用 --border-subtle（design.md 的另一档）", () => {
  const out = guard([
    `<template><div class="card-row">x</div></template>
<style scoped>
.card-row + .card-row { border-left: 1px solid var(--border-subtle); }
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `--border-subtle 不该被当成栏间分割线：\n${out}`);
});

test("放行：四边简写与长写（border / border-left-width / border-left-color）", () => {
  const out = guard([
    `<template><div class="boxed">x</div></template>
<style scoped>
.boxed {
  border: 1px solid var(--border-light);
  border-left-width: 1px;
  border-left-color: var(--border-light);
  border-left-style: solid;
}
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `简写 / 长写不该命中：\n${out}`);
});

test("放行：非 1px（2px + --border-light）不属本判据", () => {
  const out = guard([
    `<template><div class="thick">x</div></template>
<style scoped>
.thick { border-right: 2px solid var(--border-light); }
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `2px 不在判据内：\n${out}`);
});

test("放行：只扫 <style>，script 里的 CSS 字符串不参与判定", () => {
  const out = guard([
    `<script setup lang="ts">
const legacyStyle = "border-left: 1px solid var(--border-light)";
const inline = { borderLeft: "1px solid var(--border-light)" };
</script>
<template><div /></template>
<style scoped>
.ok { color: red; }
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `脚本字符串被当成真样式了：\n${out}`);
});

test("放行：注释里写的旧写法不判定（讲解本守卫时会这么写）", () => {
  const out = guard([
    `<template><div class="rail">x</div></template>
<style scoped>
/* 反例：不要再写 border-left: 1px solid var(--border-light)，改用 .soft-col-divider */
.rail { composes: soft-col-divider; }
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `注释被当成代码（先 stripComments 的坑）：\n${out}`);
});

test("放行（已声明的边界）：值跨行书写漏判——宁可漏判不可错判", () => {
  const out = guard([
    `<template><div class="rail">x</div></template>
<style scoped>
.rail {
  border-left:
    1px solid var(--border-light);
}
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `跨行值是已声明的漏判边界，不该硬报：\n${out}`);
});

test("边界：非样式后缀（.ts）不在扫描范围", () => {
  const out = guard([`export const s = "border-left: 1px solid var(--border-light)";`], ".ts");
  assert.match(out, /未发现待扫描的前端样式文件/, `非样式后缀不该被扫：\n${out}`);
});

/* ---------- 豁免（本行或相邻行，刻意不给文件级豁免） ---------- */

const DECL = "  border-left: 1px solid var(--border-light);";

test("豁免：声明本行带 col-divider-allow → 放行", () => {
  const out = guard([
    `<template><div class="rail">x</div></template>
<style scoped>
.rail {
  border-left: 1px solid var(--border-light); /* col-divider-allow: 说明理由 */
}
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `本行标记没生效：\n${out}`);
});

test("豁免：声明上一行/下一行带标记 → 同样放行", () => {
  const above = guard([
    `<template><div class="rail">x</div></template>
<style scoped>
.rail {
  /* col-divider-allow: 说明理由 */
${DECL}
}
</style>`
  ]);
  assert.doesNotMatch(above, NO_HIT, `上一行标记没生效：\n${above}`);

  const below = guard([
    `<template><div class="rail">x</div></template>
<style scoped>
.rail {
${DECL}
  /* col-divider-allow: 说明理由 */
}
</style>`
  ]);
  assert.doesNotMatch(below, NO_HIT, `下一行标记没生效：\n${below}`);
});

test("豁免边界：标记隔了 2 行不生效（粒度就是本行/相邻行）", () => {
  const out = guard([
    `<template><div class="rail">x</div></template>
<style scoped>
/* col-divider-allow: 说明理由 */
.rail {
${DECL}
}
</style>`
  ]);
  assert.match(out, /ERROR: /, `隔 2 行的标记不该豁免（否则等于文件级豁免）：\n${out}`);
});

/* ---------- 元样本：行号 ---------- */

test("元样本：两条命中的行号分别指向各自的声明行", () => {
  // 行 7 = .filter-panel__sidebar，行 11 = .cs-nav
  const src = [
    "<template>",
    '  <div class="filter-panel__sidebar">x</div>',
    "</template>",
    "",
    "<style scoped>",
    ".filter-panel__sidebar {",
    "  border-right: 1px solid var(--border-light);",
    "}",
    "",
    ".cs-nav {",
    "  border-right: 1px solid var(--border-light);",
    "}",
    "</style>"
  ].join("\n");
  const out = guard([src]);
  assert.match(out, /s0\.vue:7\b/, `第一条没指到行 7：\n${out}`);
  assert.match(out, /s0\.vue:11\b/, `第二条没指到行 11：\n${out}`);
});

/* ---------- 真实文件：正反两面 ---------- */

test("真实文件：3 处存量基线文件必须静默（在预算内不算新增）", () => {
  const out = run(BASELINE_FILES);
  assert.doesNotMatch(out, NO_HIT, `基线文件不该报红：\n${out}`);
  assert.match(
    out,
    /存量基线剩余 3 \/ 3 处，已逐处复核为保留原样/,
    `基线计数不对：\n${out}`
  );
});

test("真实文件：OverviewSummaryCard 三列竖线走 --border-subtle（故已从基线移出）", () => {
  // 2026-10-23 基线 4→3 的依据：这道竖线降成「卡片内并列列的降权分割」。
  // 只删基线条目不足以说明理由，故把「为什么删」也钉住：它若被改回 --border-light，
  // 预算已为 0 ⇒ 全仓扫描会红，而这条先给出可读的原因。
  const src = readFileSync(OVERVIEW_CARD, "utf8");
  const block = src.match(
    /\.summary-card__metric \+ \.summary-card__metric \{([\s\S]*?)\}/
  );
  assert.ok(block, "找不到三列竖线选择器，样式可能被改名，请同步本断言。");
  assert.match(
    block[1],
    /border-left:\s*1px solid var\(--border-subtle\)/,
    `三列竖线应走 --border-subtle：\n${block[1]}`
  );
  assert.doesNotMatch(
    src,
    /border-(?:left|right):\s*1px solid var\(--border-light\)/,
    "本文件不该再有裸的 --border-light 竖线（基线预算已移除）"
  );
});

test("真实文件：frontend/src/style 整目录跳过（.soft-col-divider 的定义处就在这里）", () => {
  // 该文件里就有 `border-left: 1px solid var(--border-light)`，跳过生效才不报
  const out = run([STYLE_ENTRY]);
  assert.doesNotMatch(out, NO_HIT, `唯一来源目录没被跳过：\n${out}`);
});

test("真实文件：全仓扫描（含全部基线）必须零命中", () => {
  const out = run([]);
  assert.doesNotMatch(out, NO_HIT, `仓内存在新增的裸栏间分割线：\n${out}`);
  assert.match(out, /存量基线剩余 3 \/ 3 处，已逐处复核为保留原样/, out);
});

test("回退探针：把裸声明注回真实文件副本 → 必须报红", () => {
  const src = readFileSync(REAL_WITH_SEMANTIC_BAR, "utf8");
  // 行尾随 checkout 而变（本机 core.autocrlf=true → CRLF，CI Linux → LF），
  // 锚点必须按检出时的实际行尾拼，否则锚点匹配不上、探针只会空转着失败。
  const eol = src.includes("\r\n") ? "\r\n" : "\n";
  const anchor = "<style scoped>";
  assert.ok(
    src.includes(anchor),
    "探针失效：ProductHoldingSection.vue 里找不到 <style scoped>，写法已变，请更新本探针。"
  );
  // 该文件本来是 3px 语义条（放行）；注入裸栏间分割线后必须红 —— 证明放行不是因为
  // 「整文件被跳过」，而确实是因为判据区分了两种语境。
  const injected = src.replace(
    anchor,
    `${anchor}${eol}.probe-injected { border-left: 1px solid var(--border-light); }`
  );
  assert.notEqual(injected, src, "探针失效：注入替换没有生效。");

  const out = guard([injected]);
  assert.match(out, /ERROR: /, `把裸声明注回去却没报红，守门失效：\n${out}`);
  assert.match(out, /border-left: 1px solid var\(--border-light\)/, out);
  // 同一份内容里的 3px 语义条仍须放行（不该顺带误报）
  assert.doesNotMatch(out, /3px solid/, `语义条被连带误报：\n${out}`);
});
