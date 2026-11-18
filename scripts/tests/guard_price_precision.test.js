/**
 * `scripts/guard_price_precision.mjs` 的回归用例。
 *
 * ## WHY 有这份文件
 *
 * 价格 / 净值位数的约定早就写在文档和 `pricePrecision` 里，仍然漂——用户实测
 * 发现走势图 y 轴只剩 1 位（净值 4.8124 显示成 4.8），原因是那个出口压根没走
 * 契约。按项目治理经验（AGENTS.md 的软约束会被绕开），这次把判据做成 CI 守卫，
 * 而守卫自己必须有网：**新增硬编码要真转红**，否则就是「看起来有闸门、实际不设防」。
 *
 * 钉两条：
 * 1. 真实仓库跑下来**绿**（存量已冻结为基线，不许把存量直接判死导致无人看它）；
 * 2. 临时目录里喂一处**新增**硬编码 —— 必须转红，且提示里要点名改用什么契约函数。
 *
 * 另钉两条防「假绿」：
 * 3. 运算 / 金额 / 份额 / 百分比形态**不误伤**（误伤天天发生就没人看它了）；
 * 4. 契约自身文件豁免（否则契约一存在就自己判自己红）。
 *
 * 2026-11-15（#3120）补**录入侧**：展示侧基线只冻结 `.toFixed`，`el-input-number`
 * 的 `:precision` 一直没人看，三处单价写死 2 位因此活到用户手上（可转债 116.036
 * 一进框就变 116.04）。新增三条钉同一套语义：真实回退片段必须转红、金额 / 份额
 * 不误伤、走 `priceInputMeta` 放行。
 */

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { mkdtempSync, mkdirSync, writeFileSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join } = require("node:path");

const root = join(__dirname, "..", "..");
const script = join(root, "scripts", "guard_price_precision.mjs");

/** 跑守卫；返回 { code, out }（失败时不抛，交给断言判断） */
function run(srcDir) {
  const env = { ...process.env };
  if (srcDir) env.GUARD_PRICE_SRC = srcDir;
  else delete env.GUARD_PRICE_SRC;
  try {
    const out = execFileSync(process.execPath, [script], {
      cwd: root,
      env,
      encoding: "utf8",
      // shell 必须为 false：Windows 下交给 cmd 解析会静默吃掉参数（历史坑）
      shell: false
    });
    return { code: 0, out };
  } catch (e) {
    return { code: e.status ?? 1, out: String(e.stdout || "") };
  }
}

/** 造一个临时 src 目录，写入给定文件 */
function tmpSrc(files) {
  const dir = mkdtempSync(join(tmpdir(), "px-guard-"));
  for (const [rel, content] of Object.entries(files)) {
    const p = join(dir, rel);
    mkdirSync(join(p, ".."), { recursive: true });
    writeFileSync(p, content, "utf8");
  }
  return dir;
}

test("真实仓库：存量已冻结为基线，守卫应通过", () => {
  const r = run();
  assert.equal(r.code, 0, `守卫不该红，输出：${r.out}`);
  assert.match(r.out, /本次无新增硬编码/);
});

test("新增硬编码 toFixed 必须转红（反向验证：断言真咬合）", () => {
  const dir = tmpSrc({
    "views/demo/NewCard.vue": "<template>{{ nav.toFixed(4) }}</template>\n"
  });
  const r = run(dir);
  assert.equal(r.code, 1, "新增硬编码应当判红");
  assert.match(r.out, /新增/);
  // 提示要指到契约函数，否则报错等于没说怎么改
  assert.match(r.out, /pricePrecision|formatPrice/);
});

test("运算 / 金额 / 份额 / 百分比形态不误伤", () => {
  const dir = tmpSrc({
    "views/demo/Calc.vue": [
      "form.shares = parseFloat(((v - fee) / form.price).toFixed(4));",
      "const amt = (q * price).toFixed(2);",
      "const x = ((p - c) / c * 100).toFixed(2);",
      "const q2 = row.quantity.toFixed(2);"
    ].join("\n")
  });
  const r = run(dir);
  assert.equal(r.code, 0, `不该误伤运算/金额/份额/百分比，输出：${r.out}`);
  assert.match(r.out, /本次无新增硬编码/);
});

test("契约自身文件豁免（否则契约一落地就自判红）", () => {
  const dir = tmpSrc({
    "utils/pricePrecision.ts":
      "export const f = (v: number) => v.toFixed(pricePrecision(t));\n"
  });
  const r = run(dir);
  assert.equal(r.code, 0, `契约自身应豁免，输出：${r.out}`);
});

// ── 录入侧（issue #3120）──
// 展示侧的基线只管 `.toFixed`，看不见 `:precision=`；三处单价写死 2 位就是这么
// 活到用户手上的。下面这条拿**修复前的真实片段**当样本（`:precision` 与 `v-model`
// 分居两行），确认判据是按元素判、不是按行判。

test("录入：价格语义的 el-input-number 写死 precision 必须转红（真实回退探针）", () => {
  const dir = tmpSrc({
    "views/asset/ledgers/components/TransactionEditDialog.vue": [
      "<template>",
      '  <el-form-item label="单价(元)">',
      "    <el-input-number",
      '      v-model="form.price"',
      '      style="width: 100%"',
      "      :controls=\"false\"",
      '      :min="0"',
      '      :precision="2"',
      '      :step="0.01"',
      '      placeholder="0.00"',
      "    />",
      "  </el-form-item>",
      "</template>"
    ].join("\n")
  });
  const r = run(dir);
  assert.equal(r.code, 1, "写死录入精度应当判红");
  assert.match(r.out, /新增/);
  // 提示要指到录入契约，否则报错等于没说怎么改
  assert.match(r.out, /priceInputMeta/);
  // 行号要指到元素起始行，便于定位
  assert.match(r.out, /TransactionEditDialog\.vue:3/);
});

test("录入：金额 / 份额 / 百分比的写死 precision 不误伤", () => {
  const dir = tmpSrc({
    "views/demo/Money.vue": [
      "<template>",
      '  <el-form-item label="金额(元)">',
      '    <el-input-number v-model="form.amount" :precision="2" />',
      "  </el-form-item>",
      '  <el-form-item label="份额">',
      '    <el-input-number v-model="form.quantity" :precision="4" />',
      "  </el-form-item>",
      '  <el-form-item label="比例">',
      '    <el-input-number v-model="form.ratioPct" :precision="2" />',
      "  </el-form-item>",
      "</template>"
    ].join("\n")
  });
  const r = run(dir);
  assert.equal(r.code, 0, `金额/份额/百分比不该命中，输出：${r.out}`);
});

test("录入：走 priceInputMeta 契约的价格输入框放行", () => {
  const dir = tmpSrc({
    "views/demo/PriceOk.vue": [
      "<template>",
      '  <el-input-number',
      '    v-model="form.price"',
      '    :precision="priceInput.precision"',
      '    :step="priceInput.step"',
      "  />",
      "</template>"
    ].join("\n")
  });
  const r = run(dir);
  assert.equal(r.code, 0, `走契约不该判红，输出：${r.out}`);
});
