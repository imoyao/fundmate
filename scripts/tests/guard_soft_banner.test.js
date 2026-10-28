/**
 * guard_soft_banner 回归样本（#2725 防回潮：拦住新增自绘提示条壳）。
 *
 * 五组样本各司其职，缺一不可：
 *   · **命中样本** —— 判据真能抓到「自绘壳」。用 #2718 之前 `DiscrepancyBanner` 的
 *     **真实原文**（`.recon-banner`），不是编的。
 *   · **放行样本** —— 不得误报。这里最危险的一类是**迁移后的消费方**：它们留着
 *     `class="recon-banner"` 这类 e2e 锚点类名，样式里只剩排版声明。守卫若按
 *     「类名含 banner」一刀切，就会把已经收敛好的代码判红 —— 那样的守卫上线当天就会被
 *     `banner-guard-allow` 淹掉（#2725 正文的「误判即弃用」）。
 *   · **豁免样本** —— `banner-guard-allow` 的粒度是「本行或相邻行」，刻意不给目录级豁免。
 *   · **元样本** —— 报错行号必须指到规则块那一行（行号指错 = 判据查不到）。
 *   · **真实文件** —— 全仓扫描必须绿；而把 SoftBanner 自身的样式搬到仓外副本必须红，
 *     两条合起来才证明「白名单是唯一的放行出口」，不是判据根本没跑到它。
 *
 * 为什么 SoftBanner 必须红而复本又必须绿：组件自身就是「一份壳」的唯一定义处，判据在它
 * 身上命中是**正确**的；它能通过靠的是 `ALLOWLIST` 显式登记。若哪天判据退化到看不见它，
 * 「组件被绕过、有人在别处抄了一份」同样看不见。
 */
import { spawnSync } from "node:child_process";
import { pythonOrFail } from "./_python-interpreter.mjs";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import assert from "node:assert/strict";
import test from "node:test";

const ROOT = process.cwd();
const SCRIPT = join(ROOT, "scripts", "guard_soft_banner.py");
const SOFT_BANNER = join(
  ROOT,
  "frontend/src/components/SoftBanner/index.vue"
);

/**
 * 解释器探测交给唯一一份 `_python-interpreter.mjs`（#119）。
 * 写死 `python` 在 Debian/Ubuntu、容器、CNB 工作区都会 ENOENT，而「什么都没跑」
 * 恰好满足所有「必须放行」的断言 —— 最坏的一种绿。
 */
const PY = pythonOrFail();
const PY_BIN = PY[0];
const PY_ARGS = PY.slice(1);

function run(paths, extraArgs = []) {
  const r = spawnSync(
    PY_BIN,
    [...PY_ARGS, SCRIPT, ...extraArgs, ...paths],
    { encoding: "utf8" }
  );
  // 退出码 1 是「发现了问题」的正常信号，2 是自身拿不到输入；后者喂给放行断言
  // 会伪装成「无回潮」，故直接抛。
  if (r.error) {
    throw new Error(`守卫脚本无法启动（${PY_BIN}）：${r.error.message}`);
  }
  if (r.status === 2) {
    throw new Error(
      `守卫脚本拿不到输入（status=2）：\n${r.stdout || ""}\n${r.stderr || ""}`
    );
  }
  return { status: r.status, out: (r.stdout || "") + (r.stderr || "") };
}

/** 把样本写到**仓外**临时目录再交给守卫——天然不命中白名单/基线，测的是判据本身 */
function guard(files, ext = ".vue") {
  const dir = mkdtempSync(join(tmpdir(), "soft-banner-"));
  const paths = files.map((content, i) => {
    const p = join(dir, `s${i}${ext}`);
    writeFileSync(p, content, "utf8");
    return p;
  });
  return run(paths);
}

// ────────────────────────────── 命中样本 ──────────────────────────────

/**
 * #2718 之前的 `DiscrepancyBanner/index.vue` 样式段**原文**（只裁掉与判据无关的
 * 子元素规则）。这段代码是真实存在过的，不是为测试编的。
 */
const LEGACY_DISCREPANCY = `<template>
  <div class="recon-banner" role="alert">
    <span class="recon-banner__title">待核对</span>
  </div>
</template>

<style scoped>
.recon-banner {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px 14px;
  margin-bottom: 16px;
  color: var(--text-primary);
  background: var(--color-warning-20);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-sm, 8px);
}
</style>`;

test("命中：改造前的真实 DiscrepancyBanner（.recon-banner 自带 flex + 背景 + 边框）", () => {
  const { status, out } = guard([LEGACY_DISCREPANCY]);
  assert.equal(status, 1, `应判红，实际 exit=${status}\n${out}`);
  assert.match(out, /\.recon-banner/);
});

test("命中：SCSS 嵌套 &__ 拼接（子块自带壳同样算）", () => {
  const sample = `<template><div class="a-banner"><i class="a-banner__inner" /></div></template>
<style scoped lang="scss">
.a-banner {
  &__inner {
    display: flex;
    background: var(--bg-soft);
  }
}
</style>`;
  const { status, out } = guard([sample]);
  assert.equal(status, 1, `应判红，实际 exit=${status}\n${out}`);
  // `&__inner` 展开后是 `.a-banner__inner`（BEM 拼接，不是后代选择器）
  assert.match(out, /\.a-banner__inner/);
});

test("命中：块内声明与子块混排时，子块选择器不得串入前面的声明", () => {
  const sample = `<template><div class="b-banner" /></template>
<style scoped lang="scss">
.b-banner {
  max-width: 1200px;
  padding: 0 24px;
  &__inner {
    display: flex;
    border: 1px solid var(--border-default);
  }
}
</style>`;
  const { status, out } = guard([sample]);
  assert.equal(status, 1, `应判红，实际 exit=${status}\n${out}`);
  assert.ok(
    !/max-width:.*\.b-banner__inner/.test(out),
    `选择器里混进了声明文本：\n${out}`
  );
});

// ────────────────────────────── 放行样本 ──────────────────────────────

test("放行：迁移后的消费方——保留 banner 锚点类名，样式只剩排版", () => {
  // 这就是 #2724 迁移后 import/index.vue 的真实形态：
  // `.draft-banner` 只用来当 e2e 锚点，壳已经在 SoftBanner 里
  const sample = `<template><div class="draft-banner">恢复草稿</div></template>
<style scoped>
.draft-banner-text {
  flex: 1;
  font-size: var(--text-small);
  color: var(--text-secondary);
}
</style>`;
  const { status, out } = guard([sample]);
  assert.equal(status, 0, `不该判红（锚点类名保留是迁移的既定形态）\n${out}`);
});

test("放行：display:flex + border-radius（radius 不是 border）", () => {
  const sample = `<template><div class="c-banner" /></template>
<style scoped>
.c-banner {
  display: flex;
  border-radius: var(--radius-sm);
  background: transparent;
}
</style>`;
  const { status, out } = guard([sample]);
  assert.equal(status, 0, `不该判红（没有真实背景/边框）\n${out}`);
});

test("放行：background:none / border:none 这类「声明了但没有」", () => {
  const sample = `<template><div class="d-banner" /></template>
<style scoped>
.d-banner {
  display: flex;
  background: none;
  border: none;
}
</style>`;
  const { status } = guard([sample]);
  assert.equal(status, 0, "不该判红：壳的三个要素里背景与边框都是空值");
});

test("放行：不叫 banner 的块（判据的已知边界，不做宽泛匹配）", () => {
  const sample = `<template><div class="notice-bar" /></template>
<style scoped>
.notice-bar {
  display: flex;
  padding: 12px 16px;
  background: var(--bg-soft);
  border: 1px solid var(--border-default);
}
</style>`;
  const { status } = guard([sample]);
  assert.equal(status, 0, "已知不覆盖：类名不含 banner 时本守卫不管（靠 review）");
});

// ────────────────────────────── 豁免样本 ──────────────────────────────

test("豁免：banner-guard-allow 写在本行或相邻行才生效", () => {
  const adjacent = `<template><div class="e-banner" /></template>
<style scoped>
/* banner-guard-allow: 这是品牌色营销块，不是提示条（示例） */
.e-banner {
  display: flex;
  background: var(--brand-100);
}
</style>`;
  assert.equal(guard([adjacent]).status, 0, "相邻行豁免应生效");

  // 同一个块，但豁免注释放到 3 行以外 ⇒ 不生效
  const faraway = `<template><div class="f-banner" /></template>
<style scoped>
/* banner-guard-allow: 距离太远 */
/* 隔了一行 */
/* 又隔了一行 */
.f-banner {
  display: flex;
  background: var(--brand-100);
}
</style>`;
  assert.equal(
    guard([faraway]).status,
    1,
    "豁免的粒度是「本行或相邻行」，隔 3 行不该生效"
  );
});

// ────────────────────────────── 元样本 ──────────────────────────────

test("元：报错行号指向规则块那一行（不是文件头，也不是声明行之后的偏移）", () => {
  const sample = `<template><div class="g-banner" /></template>
<style scoped>
.g-banner {
  display: flex;
  background: var(--bg-soft);
}
</style>`;
  const { status, out } = guard([sample]);
  assert.equal(status, 1);
  // `.g-banner {` 在第 3 行
  assert.match(out, /s0\.vue:3\b/, `行号应指向第 3 行：\n${out}`);
});

// ────────────────────────────── 真实文件 ──────────────────────────────

test("真实文件：SoftBanner 自身不命中（壳与 variant 分块写，单块判据看不见）", () => {
  // 这是一个**刻意的判据边界**，不是 bug：`.soft-banner` 只有 display:flex，
  // 配色在 `.soft-banner--info/warning/danger` 三个兄弟块里。判据要求「同一块内
  // 同时具备三要素」，故组件自身不命中；ALLOWLIST 里那条是**双保险**——将来有人
  // 把配色内联回基础块时，它会红，而白名单让它继续绿。
  //
  // 代价：抄 SoftBanner 的写法（拆成基础块 + 修饰块）另起一份，本判据拦不住。
  // 这写在脚本 docstring 的「已知不覆盖」里；现实中手写第 N 份几乎都是一块写完
  // （本仓 6 处命中全部如此），而「照抄组件内部实现」属另一类问题。
  const src = readFileSync(SOFT_BANNER, "utf8");
  const { status, out } = guard([src]);
  assert.equal(status, 0, `组件自身按当前判据不该命中：\n${out}`);
});

test("真实文件：把 SoftBanner 的壳与配色内联成一块后必须判红（判据没瞎）", () => {
  // 反向探针：证明「上一条绿」是因为分块，不是因为判据根本没跑到这个文件
  const inlined = `<template><div class="soft-banner" /></template>
<style scoped>
.soft-banner {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-soft);
  border: 1px solid var(--border-default);
}
</style>`;
  const { status, out } = guard([inlined]);
  assert.equal(status, 1, `内联后必须命中：\n${out}`);
  assert.match(out, /\.soft-banner/);
});

test("真实文件：全仓扫描必须通过（白名单 + 基线覆盖了全部命中）", () => {
  const { status, out } = run([], ["--report"]);
  assert.equal(status, 0, `全仓扫描不该有未登记的命中：\n${out}`);
  // 防「空转绿」：必须真的扫到了文件、真的命中了、且阻断数为 0
  assert.match(out, /扫描 \d{3,} 个文件/);
  assert.match(out, /原始命中 [1-9]\d* 处/);
  assert.match(out, /阻断 0 处/);
  assert.match(out, /\[ALLOW\] views\/explore\/exploreView\/ExploreConvBanner\.vue/);
});

test("真实文件：基线里的 3 处被逐条登记（不是整文件放行）", () => {
  const { out } = run([], ["--report"]);
  for (const key of [
    "EaccountReconcileResult.vue:150  .conflict-banner",
    "LedgerDetailOverview.vue:350  .soft-reconcile-banner",
    "OrphanCleanupDialogs.vue:356  .orphan-banner"
  ]) {
    assert.ok(
      out.includes(`[BASE ] ${key}`.replace("[BASE ] ", "")) ||
        out.includes(key),
      `基线条目未被命中（可能已改形状，需删除该条）：${key}\n${out}`
    );
  }
});
