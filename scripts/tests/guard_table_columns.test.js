/**
 * guard_table_columns 回归样本（#3210：单弹性列独吃容器余量）。
 *
 * 六组样本，缺一不可：
 *   · **命中样本** —— #3208 修复前的真实写法必须红，且行号指到 `<el-table` 那行
 *     （行号指错 = 判据查不到，AGENTS「正则/字符串类判据的常见错」）；
 *   · **放行样本** —— ≥2 弹性列 / 全固定 / 只有结构列与操作列，都不能误报。
 *     误报会逼后来者把合法写法也删掉，比没有守卫更糟；
 *   · **动态列样本** —— 分两类：#3210 收尾后，**字面量 `width` 的 `v-for` 是可判的**
 *     （重复一个定宽列不改变弹性列个数，CrowdingTable 形态），必须照判；
 *     只有 `:width="expr"` 这种真动态才判不了——判不了也**不许静默跳过**，
 *     必须登记进 `CONFIG_TABLE_JUDGE` 并由 vitest 判据承接（换路径的新表照样红）；
 *   · **注释样本** —— 注释里写 `<el-table-column width="120">` 不构成结构事实，
 *     不能因为它把「1 弹性 + 0 固定」翻成命中（#3200 那个坑的镜像）；
 *   · **豁免样本** —— `table-col-allow` 必带 6 字以上理由；裸标记不放行；
 *     且粒度只到「这一张表」——相邻的第二张表**不得**蹭用第一张的标记；
 *   · **真实文件 + 反向探针** —— 全仓零命中本身可能是空转（判据没生效也是零命中），
 *     所以拿真实文件的两种状态各验一次：摘掉标记必须红、把 min-width 改回 width 必须红。
 */
import { spawnSync } from "node:child_process";
import { pythonOrFail } from "./_python-interpreter.mjs";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import assert from "node:assert/strict";
import test from "node:test";

const ROOT = process.cwd();
const SCRIPT = join(ROOT, "scripts", "guard_table_columns.py");
const PY = pythonOrFail();

/** 真实文件：修好的 5 列持仓表（全 min-width） */
const REAL_FIXED = join(
  ROOT,
  "frontend/src/views/asset/inventory/components/InvestmentPositionTable.vue"
);
/** 真实文件：9 列已横滚表，靠 table-col-allow 放行 */
const REAL_MARKED = join(
  ROOT,
  "frontend/src/views/asset/ledgers/components/LedgerDetailHoldingsPane.vue"
);
/** 真实文件：列宽由配置驱动（`:min-width="col.minWidth"`），登记在 CONFIG_TABLE_JUDGE */
const REAL_CONFIG_DRIVEN = join(
  ROOT,
  "frontend/src/views/asset/fund-ranking/components/FundRankingTable.vue"
);
/** 真实文件：v-for 重复定宽列（乖离 6/20/60 日，width=76），靠 table-col-allow 放行 */
const REAL_VFOR_LITERAL = join(
  ROOT,
  "frontend/src/views/explore/components/detail/CrowdingTable.vue"
);

function run(paths) {
  const r = spawnSync(PY[0], [...PY.slice(1), SCRIPT, ...paths], {
    encoding: "utf8"
  });
  // 退出码 1 = 守卫发现问题的正常信号；0 = 通过；2 = 拿不到输入（判据没跑）。
  // 崩溃喂给放行断言会伪装成「无回潮」，所以 >1 直接抛。
  if (r.error) {
    throw new Error(`守卫脚本无法启动（${PY[0]}）：${r.error.message}`);
  }
  if (r.status > 1) {
    throw new Error(
      `守卫脚本异常退出（status=${r.status}）：\n${r.stdout || ""}\n${r.stderr || ""}`
    );
  }
  return { status: r.status, out: (r.stdout || "") + (r.stderr || "") };
}

/** 把样本写成临时文件后交给守卫扫（临时目录在仓外 ⇒ 不污染真实扫描） */
function guard(samples) {
  const dir = mkdtempSync(join(tmpdir(), "table-col-"));
  const paths = samples.map(({ name, body }) => {
    const p = join(dir, name);
    writeFileSync(p, body, "utf8");
    return p;
  });
  return run(paths);
}

const NO_HIT = /OK: /;

/** #3208 修复前的真实写法：首列 min-width，其余全 width（1440 视口首列 376/1036） */
const PRE_FIX = `<template>
  <el-table :data="rows" stripe>
    <el-table-column label="产品信息" min-width="150" show-overflow-tooltip>
      <template #default="{ row }">{{ row.name }}</template>
    </el-table-column>
    <el-table-column prop="account_name" label="归属账户" width="120" />
    <el-table-column label="市值" width="130" align="right" />
    <el-table-column label="盈亏" width="170" align="right" />
  </el-table>
</template>`;

test("命中：#3208 修复前的真实写法（行号指到 <el-table 那行）", () => {
  const { status, out } = guard([{ name: "pre-fix.vue", body: PRE_FIX }]);
  assert.equal(status, 1, `修复前的写法应判红：\n${out}`);
  assert.match(out, /ERROR: 1 张表/, `命中数不对：\n${out}`);
  assert.match(out, /pre-fix\.vue:2\b/, `行号没指向 <el-table：\n${out}`);
  assert.match(out, /产品信息/, `没报出唯一弹性列的 label：\n${out}`);
});

test("命中：只有 2 列（1 弹性 + 1 固定）也要拦——余量照样全给它", () => {
  const { status, out } = guard([
    {
      name: "two-col.vue",
      body: `<template>
  <el-table :data="rows">
    <el-table-column prop="name" label="账户名称" min-width="150" />
    <el-table-column prop="type" label="账户类型" width="120" />
  </el-table>
</template>`
    }
  ]);
  assert.equal(status, 1, `两列表同样会灌余量：\n${out}`);
});

test("命中：裸标记（没写理由）不放行", () => {
  const { status, out } = guard([
    {
      name: "bare-marker.vue",
      body: `<template>
  <!-- table-col-allow -->
  <el-table :data="rows">
    <el-table-column prop="a" label="名称" min-width="150" />
    <el-table-column prop="b" label="金额" width="120" />
  </el-table>
</template>`
    }
  ]);
  assert.equal(status, 1, `裸标记应判红：\n${out}`);
  assert.match(out, /没写理由/, `没说明「为什么红」：\n${out}`);
});

test("放行：≥2 个弹性列（#3208 的修法）", () => {
  const { status, out } = guard([
    {
      name: "fixed.vue",
      body: `<template>
  <el-table :data="rows">
    <el-table-column prop="name" label="产品信息" min-width="150" />
    <el-table-column prop="account" label="归属账户" min-width="120" />
    <el-table-column prop="value" label="市值" min-width="130" />
  </el-table>
</template>`
    }
  ]);
  assert.equal(status, 0, `两列以上弹性不该红：\n${out}`);
  assert.match(out, NO_HIT, out);
});

test("放行：全固定宽（0 个弹性列）不归本判据管", () => {
  const { status, out } = guard([
    {
      name: "all-fixed.vue",
      body: `<template>
  <el-table :data="rows">
    <el-table-column prop="name" label="产品" width="160" />
    <el-table-column prop="value" label="市值" width="130" />
  </el-table>
</template>`
    }
  ]);
  assert.equal(status, 0, `全固定宽是另一种形态（右侧整片空白），不属本条：\n${out}`);
});

test("放行：结构列与操作列不参与分配（不构成「固定数据列」）", () => {
  const { status, out } = guard([
    {
      name: "struct-action.vue",
      body: `<template>
  <el-table :data="rows">
    <el-table-column type="selection" width="55" />
    <el-table-column type="index" label="#" width="48" />
    <el-table-column prop="name" label="产品信息" min-width="150" />
    <el-table-column label="操作" width="120">
      <template #default="{ row }"><el-button>详情</el-button></template>
    </el-table-column>
  </el-table>
</template>`
    }
  ]);
  assert.equal(status, 0, `选中列 / 序号列 / 操作列都是固定宽的常态：\n${out}`);
});

test("放行：带理由的 table-col-allow（本行或上一非空行）", () => {
  const body = (marker) => `<template>
  ${marker}
  <el-table :data="rows">
    <el-table-column prop="name" label="产品" min-width="160" />
    <el-table-column prop="a" label="首买日" width="120" />
  </el-table>
</template>`;
  const above = guard([
    {
      name: "allowed.vue",
      body: body("<!-- table-col-allow: 8 列合计 932 > 实测表宽 856，已横滚 -->")
    }
  ]);
  assert.equal(above.status, 0, `有理由的标记应放行：\n${above.out}`);

  const blank_line = guard([
    {
      name: "allowed-gap.vue",
      body: `<template>

  <!-- table-col-allow: 640px 弹窗内小表，余量给名称列 -->
  <el-table :data="rows">
    <el-table-column prop="name" label="名称" min-width="140" />
    <el-table-column prop="a" label="金额" width="120" />
  </el-table>
</template>`
    }
  ]);
  assert.equal(blank_line.status, 0, `空行隔开也应认（上一个非空行）：\n${blank_line.out}`);
});

test("命中：字面量 width 的 v-for 是「重复定宽列」，照判（CrowdingTable 形态）", () => {
  // 收尾前这类表被「含 v-for ⇒ 跳过」整块放过，于是 CrowdingTable 一直隐形。
  // 重复一个**定宽**列不改变弹性列个数（0 个还是 0 个）⇒ 判据照样成立。
  const { status, out } = guard([
    {
      name: "vfor-literal-width.vue",
      body: `<template>
  <el-table :data="rows">
    <el-table-column type="index" label="#" width="48" />
    <el-table-column prop="item_name" label="行业" min-width="110" />
    <el-table-column prop="a" label="拥挤度" width="140" />
    <el-table-column
      v-for="n in WINDOWS"
      :key="n"
      :label="'乖离' + n + '日'"
      width="76"
    />
  </el-table>
</template>`
    }
  ]);
  assert.equal(status, 1, `重复定宽列不该让整表免判：\n${out}`);
});

test("放行：字面量 width 的 v-for + 2 个弹性列", () => {
  const { status, out } = guard([
    {
      name: "vfor-literal-two-flex.vue",
      body: `<template>
  <el-table :data="rows">
    <el-table-column prop="item_name" label="行业" min-width="110" />
    <el-table-column prop="note" label="备注" min-width="120" />
    <el-table-column
      v-for="n in WINDOWS"
      :key="n"
      :label="'乖离' + n + '日'"
      width="76"
    />
  </el-table>
</template>`
    }
  ]);
  assert.equal(status, 0, `≥2 弹性列应放行：\n${out}`);
});

test("命中：真动态列（:width 绑表达式）未登记 ⇒ 不许静默跳过", () => {
  const { status, out } = guard([
    {
      name: "dynamic-bound.vue",
      body: `<template>
  <el-table :data="rows">
    <el-table-column prop="name" label="名称" min-width="200" />
    <el-table-column prop="value" label="数值" :width="colWidth" />
  </el-table>
</template>`
    }
  ]);
  assert.equal(status, 1, `判不了的列不许无声跳过：\n${out}`);
  assert.match(out, /CONFIG_TABLE_JUDGE/, `红的时候要给出正解（登记 + vitest）：\n${out}`);
});

test("放行：已登记的配置驱动表（真实文件）由 vitest 承接", () => {
  const { status, out } = run([REAL_CONFIG_DRIVEN]);
  assert.equal(status, 0, `登记过的动态列表应放行：\n${out}`);
});

test("命中：把已登记的表换个路径（= 新加一张同形表）⇒ 仍需登记", () => {
  // 登记是按**文件**认的：新表复制同名写法到新文件，必须重新登记 + 补判据，
  // 否则「新加的配置驱动表」会回到「静默无判据」——这正是收尾要堵的洞。
  const src = readFileSync(REAL_CONFIG_DRIVEN, "utf8");
  const { status, out } = guard([{ name: "new-dynamic-table.vue", body: src }]);
  assert.equal(status, 1, `新路径的动态列表必须登记：\n${out}`);
});

test("注释里的 <el-table-column width> 不算结构事实（1 弹性 + 0 固定 ⇒ 放行）", () => {
  const { status, out } = guard([
    {
      name: "commented.vue",
      body: `<template>
  <el-table :data="rows">
    <el-table-column prop="name" label="名称" min-width="200" />
    <!-- <el-table-column prop="value" label="数值" width="120" /> -->
  </el-table>
</template>`
    }
  ]);
  assert.equal(status, 0, `注释不能把表格翻成命中：\n${out}`);
});

test("注释里的整张 <el-table> 不该被当成表来判", () => {
  const { status, out } = guard([
    {
      name: "commented-table.vue",
      body: `<template>
  <div>
    <!-- 旧写法：<el-table :data="old"><el-table-column label="产品信息" width="150" /></el-table> -->
    <el-table :data="rows">
      <el-table-column prop="name" label="名称" min-width="200" />
      <el-table-column prop="type" label="类型" min-width="120" />
    </el-table>
  </div>
</template>`
    }
  ]);
  assert.equal(status, 0, `注释里的表不是结构事实：\n${out}`);
});

test("豁免不外溢：相邻两张表，标记只覆盖第一张", () => {
  const { status, out } = guard([
    {
      name: "leak.vue",
      body: `<template>
  <div>
    <!-- table-col-allow: 第一张表已横滚（8 列合计 932 > 856） -->
    <el-table :data="a"><el-table-column label="A" min-width="120" /><el-table-column label="B" width="100" /></el-table>
    <el-table :data="b"><el-table-column label="C" min-width="120" /><el-table-column label="D" width="100" /></el-table>
  </div>
</template>`
    }
  ]);
  assert.equal(status, 1, `第二张表蹭不到第一张的标记：\n${out}`);
  assert.match(out, /leak\.vue:5\b/, `红的应是第二张表（第 5 行）：\n${out}`);
});

test("输入不可信（路径不存在）返回 2，不得当成通过", () => {
  // 这条不能用 run()：它把 status>1 当崩溃抛掉，而这里要断言的正是「拿不到输入」。
  const r = spawnSync(
    PY[0],
    [...PY.slice(1), SCRIPT, join(ROOT, "frontend/src/__nope__.vue")],
    { encoding: "utf8" }
  );
  assert.equal(r.status, 2, `不存在的路径不能静默绿：\n${r.stdout || ""}${r.stderr || ""}`);
});

test("真实文件：修好的表零命中（且确实扫到了 500+ 文件，防空转）", () => {
  const { status, out } = run([]);
  assert.equal(status, 0, `全仓应零命中：\n${out}`);
  const scanned = Number((out.match(/扫描 (\d+) 个 \.vue/) || [])[1]);
  assert.ok(scanned > 400, `扫描文件数异常（疑空转）：${scanned}`);
});

test("反向探针 1：摘掉真实文件的 table-col-allow ⇒ 必须转红", () => {
  const src = readFileSync(REAL_MARKED, "utf8");
  const stripped = src.replace(/^.*table-col-allow.*\n/gm, "");
  assert.notEqual(stripped, src, "样本里没找到 table-col-allow，探针失效");
  const { status, out } = guard([{ name: "stripped.vue", body: stripped }]);
  assert.equal(status, 1, `摘掉标记后应判红：\n${out}`);
});

test("反向探针 2：把修好表的 min-width 改回 width ⇒ 必须转红", () => {
  const src = readFileSync(REAL_FIXED, "utf8");
  // 首列保持弹性、其余 min-width → width（复现 #3208 修复前的表达方式）
  let seen = 0;
  const reverted = src.replace(/min-width="(\d+)"/g, (all, n) => {
    seen += 1;
    return seen === 1 ? all : `width="${n}"`;
  });
  assert.ok(seen >= 3, `样本列的 min-width 数量不对（${seen}），探针失vacuous`);
  const { status, out } = guard([{ name: "reverted.vue", body: reverted }]);
  assert.equal(status, 1, `改回固定宽应判红：\n${out}`);
});

test("反向探针 3：CrowdingTable 摘掉放行标记 ⇒ 必须转红（字面量 v-for 已可判）", () => {
  // 这条同时钉住「v-for 不再免判」：收尾前该文件整表被跳过，摘标记也不会红。
  const src = readFileSync(REAL_VFOR_LITERAL, "utf8");
  const stripped = src.replace(/^.*table-col-allow.*\n/gm, "");
  assert.notEqual(stripped, src, "样本里没找到 table-col-allow，探针失效");
  const { status, out } = guard([{ name: "crowding-stripped.vue", body: stripped }]);
  assert.equal(status, 1, `摘掉标记后应判红：\n${out}`);
});
