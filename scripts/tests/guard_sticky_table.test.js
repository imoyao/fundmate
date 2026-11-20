/**
 * guard_sticky_table 回归样本（#3200 表头吸顶：自建 table 的结构性死冲突）。
 *
 * 五组样本，缺一不可：
 *   · **命中样本** —— 迁移前的真实写法必须红，且行号指到 `position: sticky` 那行
 *     （行号指错 = 判据查不到，AGENTS「正则/字符串类判据的常见错」）；
 *   · **放行样本** —— 两种正解（迁 el-table / 内部滚动容器）与「div 布局的 sticky」
 *     都不能误报。误报会逼着后来者把合法写法也删掉，比没有守卫更糟；
 *   · **注释样本** —— 注释里写 `<table>` 不构成结构事实：#3200 自己的迁移注释就写了
 *     `<table>`，若守卫按全文 includes 判，迁移完的当天就红（记忆里那把坑：注释喂假绿；
 *     这里是它的镜像——注释喂假红）；
 *   · **豁免样本** —— `sticky-table-allow` 的粒度是「本行或上一行」，刻意不给文件级豁免；
 *   · **真实文件 + 反向探针** —— 全仓零命中本身可能空转（判据没生效也是零命中），
 *     所以把真实合法文件的内部滚动容器拆掉，必须转红才算数。
 */
import { spawnSync } from "node:child_process";
import { pythonOrFail } from "./_python-interpreter.mjs";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import assert from "node:assert/strict";
import test from "node:test";

const ROOT = process.cwd();
const SCRIPT = join(ROOT, "scripts", "guard_sticky_table.py");

/** 方案 B 的合法先例：max-height + overflow-y:auto，表头相对内部容器吸顶 */
const LEGAL_INNER_SCROLL = join(
  ROOT,
  "frontend/src/views/product/components/ProductHoldingSection.vue"
);
/** #3200 迁移后的实现：el-table + 注释里保留了 `<table>` 这个词 */
const MIGRATED_TABLE = join(
  ROOT,
  "frontend/src/views/asset/fund-ranking/components/FundRankingTable.vue"
);

/**
 * 解释器探测与「静默绿」（#119）：写死 `python` 在 Ubuntu / 容器里会 ENOENT，
 * 子进程根本没跑，放行断言却因「什么都没跑」而全部假通过。
 */
const PY = pythonOrFail();
const PY_BIN = PY[0];
const PY_ARGS = PY.slice(1);

function run(paths) {
  const r = spawnSync(PY_BIN, [...PY_ARGS, SCRIPT, ...paths], {
    encoding: "utf8"
  });
  // 退出码 1 = 守卫发现问题的正常信号；>1 才是自身崩溃。
  // 崩溃喂给放行断言会伪装成「无回潮」，所以这里直接抛。
  if (r.error) {
    throw new Error(`守卫脚本无法启动（${PY_BIN}）：${r.error.message}`);
  }
  if (r.status > 1) {
    throw new Error(
      `守卫脚本异常退出（status=${r.status}）：\n${r.stdout || ""}\n${r.stderr || ""}`
    );
  }
  return (r.stdout || "") + (r.stderr || "");
}

/** 把样本写成临时文件后交给守卫扫（临时目录在仓外 ⇒ 不污染真实扫描） */
function guard(samples) {
  const dir = mkdtempSync(join(tmpdir(), "sticky-table-"));
  const paths = samples.map(({ name, body }) => {
    const p = join(dir, name);
    writeFileSync(p, body, "utf8");
    return p;
  });
  return run(paths);
}

/** 通过时既不该有命中标记，也不该有 Python 崩溃（崩溃会让放行断言空转） */
const NO_HIT = /ERROR: |Traceback/;

/* ---------- 命中样本 ---------- */

const PRE_FIX = `<template>
  <div class="table-scroll">
    <table class="ranking-table">
      <thead><tr><th>夏普</th></tr></thead>
      <tbody><tr><td>2.00</td></tr></tbody>
    </table>
  </div>
</template>

<style scoped>
.table-scroll {
  overflow-x: auto;
}

.ranking-table th {
  position: sticky;
  top: 0;
}
</style>`;

test("命中：迁移前的真实写法（自建 table + th sticky + 裸 overflow-x:auto）", () => {
  const out = guard([{ name: "old.vue", body: PRE_FIX }]);
  assert.match(out, /ERROR: /, `迁移前的写法应判红：\n${out}`);
  // 行号必须是 position:sticky 那行（样本第 16 行），不是规则首行、不是文件头
  assert.match(out, /old\.vue:16\b/, `行号没指向 sticky 声明：\n${out}`);
});

test("命中：大小写 / 空白变体不能骗过判据（POSITION : STICKY）", () => {
  const out = guard([
    {
      name: "case.vue",
      body: `<template><table><thead><tr><th>x</th></tr></thead></table></template>
<style scoped>
.grid th { POSITION : STICKY ; }
</style>`
    }
  ]);
  assert.match(out, /ERROR: /, `归一化后应命中：\n${out}`);
});

test("命中：SCSS 嵌套块里的 sticky 同样被扫到（扁平正则漏内层就白干）", () => {
  const out = guard([
    {
      name: "nested.vue",
      body: `<template><table><thead><tr><th>x</th></tr></thead></table></template>
<style lang="scss" scoped>
.grid {
  thead th {
    position: sticky;
    top: 0;
  }
}
</style>`
    }
  ]);
  assert.match(out, /ERROR: /, `嵌套块没被扫到：\n${out}`);
  assert.match(out, /nested\.vue:5\b/, out);
});

test("边界：独立 .scss 里只有样式、没有表格结构标记 → 放行（跨文件形态判不出）", () => {
  // 如实记录一条**已知不覆盖**：表格在 .vue、样式在全局 .scss 的拆分布局，
  // 两边各自都不满足三件套，静态判不出来。本仓表格样式一律与组件同文件，
  // 故暂不追；哪天出现跨文件写法，这条测试会先提醒「以为守住了」。
  const out = guard([
    {
      name: "legacy.scss",
      body: `.legacy-table th {
  position: sticky;
}`
    }
  ]);
  assert.doesNotMatch(out, NO_HIT, `跨文件形态的变化需要重新评估判据：\n${out}`);
});

test("命中：同一文件两条 sticky 规则 → 两条都报（不是只报第一条）", () => {
  const out = guard([
    {
      name: "two.vue",
      body: `<template><table><thead><tr><th>x</th></tr></thead></table></template>
<style scoped>
.a th { position: sticky; }
.b thead { position: sticky; }
</style>`
    }
  ]);
  assert.match(out, /two\.vue:3\b/, out);
  assert.match(out, /two\.vue:4\b/, out);
});

/* ---------- 放行样本 ---------- */

test("放行：方案 B（max-height + overflow-y:auto，表头相对内部容器吸顶）", () => {
  const out = guard([
    {
      name: "inner-scroll.vue",
      body: `<template><div class="wrap"><table><thead><tr><th>x</th></tr></thead></table></div></template>
<style scoped>
.wrap {
  max-height: 420px;
  overflow-y: auto;
}
.wrap th { position: sticky; top: 0; }
</style>`
    }
  ]);
  assert.doesNotMatch(out, NO_HIT, `方案 B 被误判：\n${out}`);
});

test("放行：方案 B 用 overflow 简写（auto）同样算内部滚动容器", () => {
  const out = guard([
    {
      name: "shorthand.vue",
      body: `<template><table><thead><tr><th>x</th></tr></thead></table></template>
<style scoped>
.wrap { max-height: 300px; overflow: auto; }
.wrap th { position: sticky; top: 0; }
</style>`
    }
  ]);
  assert.doesNotMatch(out, NO_HIT, `overflow 简写被误判：\n${out}`);
});

test("放行：迁 el-table（模板里没有自建 <table>）", () => {
  const out = guard([
    {
      name: "ep.vue",
      body: `<template>
  <el-table :data="rows">
    <el-table-column prop="sharpe" label="夏普" sortable="custom" />
  </el-table>
</template>

<style scoped>
.el-table__header-wrapper { position: sticky; top: 0; }
</style>`
    }
  ]);
  assert.doesNotMatch(out, NO_HIT, `el-table 被误判成自建表：\n${out}`);
});

test("放行：注释里的 <table> 不是结构事实（#3200 迁移注释就写了它）", () => {
  const out = guard([
    {
      name: "commented.vue",
      body: `<template>
  <!-- 旧实现是自建 <table> + .table-scroll{overflow-x:auto}，已迁 el-table -->
  <el-table :data="rows" />
</template>

<style scoped>
/* 别再写 <table> + th { position: sticky } 这套 */
.el-table__header-wrapper { position: sticky; top: 0; }
</style>`
    }
  ]);
  assert.doesNotMatch(out, NO_HIT, `注释里的标签被当成结构事实：\n${out}`);
});

test("放行：div 布局的 sticky 表头（没有 table，天然不产生滚动祖先）", () => {
  const out = guard([
    {
      name: "div-grid.vue",
      body: `<template><div class="grid"><div class="grid__head">夏普</div></div></template>
<style scoped>
.grid__head { position: sticky; top: 0; }
</style>`
    }
  ]);
  assert.doesNotMatch(out, NO_HIT, `div 布局被误判：\n${out}`);
});

test("放行：同行标 sticky-table-allow 的存量例外", () => {
  const out = guard([
    {
      name: "allowed.vue",
      body: `<template><table><thead><tr><th>x</th></tr></thead></table></template>
<style scoped>
/* 历史形态，待 #3200 第二阶段迁移 */
.grid th {
  position: sticky; /* sticky-table-allow */
  top: 0;
}
</style>`
    }
  ]);
  assert.doesNotMatch(out, NO_HIT, `豁免标记没生效：\n${out}`);
});

/* ---------- 真实文件 ---------- */

test("真实文件：方案 B 先例（ProductHoldingSection）通过", () => {
  const out = run([LEGAL_INNER_SCROLL]);
  assert.doesNotMatch(out, NO_HIT, `合法的内部滚动容器被误判：\n${out}`);
});

test("真实文件：#3200 迁移后的 FundRankingTable（注释含 <table>）通过", () => {
  const out = run([MIGRATED_TABLE]);
  assert.doesNotMatch(out, NO_HIT, `迁移后的实现被误判：\n${out}`);
});

test("真实仓全量扫描零命中", () => {
  const out = run([]);
  assert.doesNotMatch(out, NO_HIT, `存量出现死冲突：\n${out}`);
});

/* ---------- 反向探针：证明「零命中」不是空转 ---------- */

test("反向探针：拆掉真实文件的内部滚动容器 → 必须转红", () => {
  const source = readFileSync(LEGAL_INNER_SCROLL, "utf8");
  const stripped = source
    .split("\n")
    .filter(line => !/^\s*(max-height|overflow-y)\s*:/.test(line))
    .join("\n");
  assert.notEqual(stripped, source, "探针没改动真实文件（正则可能没匹配上）");

  const dir = mkdtempSync(join(tmpdir(), "sticky-table-probe-"));
  const probe = join(dir, "ProductHoldingSection.vue");
  writeFileSync(probe, stripped, "utf8");

  const out = run([probe]);
  assert.match(out, /ERROR: /, `拆掉内滚容器后应转红（判据可能是空转）：\n${out}`);
  assert.match(out, /ProductHoldingSection\.vue:\d+/, out);
});
