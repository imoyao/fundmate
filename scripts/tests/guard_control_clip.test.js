/**
 * guard_control_clip 回归样本（2026-10-09 自选页圆按钮「又大又被切」）。
 *
 * 三组样本各司其职，缺一不可：
 *   · **命中样本** —— 规则真能抓到问题（改回旧写法要红），其中第一条就是修复前的
 *     真实代码，缺了它整个守卫可能只是「永远绿」的装饰；
 *   · **放行样本** —— 不得误报（border-box 无 padding、overflow:auto 滚动容器、
 *     非 px 的 max-height、非按钮的 content-box，这几类最容易被误伤）；
 *   · **元样本** —— 报错行号必须指到出问题的那一块：行号指错 = 判据等于查不到
 *     （AGENTS「正则/字符串类判据的两个常见错」记着这个坑）。
 *
 * 最后两条跑**真实文件**：一条断言当前代码零命中，一条把 bug 注回去断言必须报红
 * —— 只有后者绿了，才知道前者不是空转。
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import assert from "node:assert/strict";
import test from "node:test";

const ROOT = process.cwd();
const SCRIPT = join(ROOT, "scripts", "guard_control_clip.py");
const REAL_FILE = join(
  ROOT,
  "frontend/src/views/asset/watchlist/components/WatchlistHeadPrimary.vue"
);
const PY = process.env.PYTHON || "python";

function run(paths) {
  try {
    return execFileSync(PY, [SCRIPT, ...paths], { encoding: "utf8" });
  } catch (e) {
    return (e.stdout || "") + (e.stderr || "");
  }
}

function guard(files) {
  const dir = mkdtempSync(join(tmpdir(), "control-clip-"));
  const paths = files.map((content, i) => {
    const p = join(dir, `s${i}.vue`);
    writeFileSync(p, content, "utf8");
    return p;
  });
  return run(paths);
}

/** 通过的输出里既不该有命中标记，也不该有 Python 崩溃（崩溃会让放行断言空转） */
const NO_HIT = /\[clip\]|\[pad\]|Traceback/;

/* ---------- 命中样本 ---------- */

const PRE_FIX = `<template>
  <div class="head-primary"><button class="icon-tool-btn">x</button></div>
</template>

<style scoped>
.head-primary {
  display: flex;
  justify-content: space-between;
  max-height: 40px;
  margin-bottom: var(--space-3);
  overflow: hidden;
}

.icon-tool-btn {
  box-sizing: content-box;
  width: 28px;
  height: 28px;
  padding: 6px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
}
</style>`;

test("命中：修复前的真实写法 → clip（42px>40px）与 pad 双双报红", () => {
  const out = guard([PRE_FIX]);
  assert.match(out, /\[clip\]/);
  assert.match(out, /\[pad\]/);
  // 42 这个数字本身就是判据：28 内容 + 6×2 padding + 1×2 border
  assert.match(out, /42px/, `没算出外框 42px，box-model 判据失效了：\n${out}`);
});

test("border 必须计入外框：三段式 border 取不到宽度就会把 42 判成 40 而漏报", () => {
  // 只靠 border 越线（无 padding）——早期版本按 `border:` 第一段取值会取到 `solid`
  // 而放弃，结果 40 > 40 不成立、clip 静默漏判
  const out = guard([
    `<template><div class="head-primary">x</div></template>
<style scoped>
.head-primary { max-height: 40px; overflow: hidden; }
.icon-tool-btn { box-sizing: content-box; height: 40px; border: 1px solid var(--border-default); }
</style>`
  ]);
  assert.match(out, /\[clip\]/, `border 没被计入外框：\n${out}`);
  assert.match(out, /42px/);
  assert.doesNotMatch(out, /\[pad\]/);
});

test("命中：与 padding 无关的超高控件同样要报（规则不只盯这一个按钮）", () => {
  const out = guard([
    `<template><div class="head-primary">x</div></template>
<style scoped>
.head-primary { max-height: 40px; overflow: hidden; }
.heavy-cta { box-sizing: border-box; height: 44px; }
</style>`
  ]);
  assert.match(out, /\[clip\]/);
  assert.doesNotMatch(out, /\[pad\]/);
});

test("命中：@media 内嵌套的规则同样被检查（正则切块会漏掉这一类）", () => {
  const out = guard([
    `<template><div class="head-primary">x</div></template>
<style scoped>
@media (min-width: 768px) {
  .head-primary { max-height: 40px; overflow: hidden; }
  .icon-tool-btn { box-sizing: border-box; height: 44px; }
}
</style>`
  ]);
  assert.match(out, /\[clip\]/, `@media 内层没被扫到：\n${out}`);
});

/* ---------- 放行样本（误报源） ---------- */

test("放行：修复后的写法（border-box 28×28 + padding 0 + ::after 热区）", () => {
  const out = guard([
    `<template>
  <div class="head-primary"><button class="icon-tool-btn">x</button></div>
</template>

<style scoped>
.head-primary {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}

.icon-tool-btn {
  position: relative;
  box-sizing: border-box;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--border-default);
}

.icon-tool-btn::after {
  position: absolute;
  inset: -6px;
  content: "";
}
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `修复后的写法不该报红：\n${out}`);
});

test("放行：content-box 但 padding:0（修复后刻意保留 content-box 的写法）", () => {
  const out = guard([
    `<template><div class="head-primary">x</div></template>
<style scoped>
.head-primary { max-height: 40px; overflow: hidden; }
.icon-tool-btn { box-sizing: content-box; height: 28px; padding: 0; }
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `padding 为 0 不算撑大：\n${out}`);
});

test("放行：外框恰好等于 max-height（正好不切，判据用严格大于）", () => {
  const out = guard([
    `<template><div class="head-primary">x</div></template>
<style scoped>
.head-primary { max-height: 40px; overflow: hidden; }
.tight-ctl { box-sizing: border-box; height: 40px; }
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `恰好相等不该报红：\n${out}`);
});

test("放行：overflow-y:auto 是有意的滚动容器，不算盖子", () => {
  const out = guard([
    `<template><div class="panel">x</div></template>
<style scoped>
.panel { max-height: 40px; overflow-y: auto; }
.tall-ctl { box-sizing: border-box; height: 60px; }
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `滚动容器被误判成裁切：\n${out}`);
});

test("放行：max-height 用非 px（60vh）→ 算不出确定值就跳过，不猜", () => {
  const out = guard([
    `<template><div class="panel">x</div></template>
<style scoped>
.panel { max-height: 60vh; overflow: hidden; }
.tall-ctl { box-sizing: border-box; height: 60px; }
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `非 px 上限不该硬算：\n${out}`);
});

test("放行：非按钮选择器的 content-box + padding（不误伤输入框）", () => {
  const out = guard([
    `<template><input class="search-field" /></template>
<style scoped>
.search-field { box-sizing: content-box; height: 32px; padding: 4px 8px; }
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `输入框被误判成按钮：\n${out}`);
});

test("放行：只扫 <style>，script 里的 CSS 字符串不参与判定", () => {
  const out = guard([
    `<script setup>
const S = ".head-primary { max-height: 40px; overflow: hidden; } .x { height: 60px; }";
</script>
<template><div /></template>
<style scoped>
.ok { color: red; }
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `脚本字符串被当成真样式了：\n${out}`);
});

/* ---------- 豁免（按块，不是按文件） ---------- */

const CAP = `  max-height: 40px;
  overflow: hidden;`;
const BIG_BTN = `.icon-tool-btn {
  box-sizing: content-box;
  height: 28px;
  padding: 6px;
  border: 1px solid var(--border-default);
}`;

test("容器侧 control-clip-allow → 只消掉 clip，pad 仍在（豁免是按块的）", () => {
  const out = guard([
    `<template><div class="head-primary">x</div></template>
<style scoped>
.head-primary {
  /* control-clip-allow: 有意限高，内部控件实测最高 40px */
${CAP}
}
${BIG_BTN}
</style>`
  ]);
  assert.doesNotMatch(out, /\[clip\]/, `容器已豁免不该再报 clip：\n${out}`);
  assert.match(out, /\[pad\]/, `pad 与容器豁免无关，必须仍在：\n${out}`);
});

test("控件侧 control-clip-allow → clip 与 pad 一起消掉（整块跳过）", () => {
  const out = guard([
    `<template><div class="head-primary">x</div></template>
<style scoped>
.head-primary {
${CAP}
}
.icon-tool-btn {
  /* control-clip-allow: 热区补偿有意撑大，已人工核对不与容器冲突 */
  box-sizing: content-box;
  height: 28px;
  padding: 6px;
  border: 1px solid var(--border-default);
}
</style>`
  ]);
  assert.doesNotMatch(out, NO_HIT, `控件已豁免不该报红：\n${out}`);
});

/* ---------- 元样本：行号 ---------- */

test("元样本：报错行号必须指向出问题的那一块", () => {
  // 行 6 = .head-primary（容器），行 11 = .icon-tool-btn（控件）
  const src = [
    "<template>",
    "  <div class='head-primary'>x</div>",
    "</template>",
    "",
    "<style scoped>",
    ".head-primary {",
    "  max-height: 36px;",
    "  overflow: hidden;",
    "}",
    "",
    ".icon-tool-btn {",
    "  box-sizing: content-box;",
    "  height: 28px;",
    "  padding: 6px;",
    "}",
    "</style>"
  ].join("\n");
  const out = guard([src]);
  assert.match(out, /\[clip\]/, out);
  assert.match(out, /s0\.vue:11\b/, `clip 行号没指向 .icon-tool-btn（行 11）：\n${out}`);
  assert.match(out, /\[pad\]/, out);
  assert.match(out, /s0\.vue:11\b/, `pad 行号没指向 .icon-tool-btn（行 11）：\n${out}`);
});

/* ---------- 真实文件：正反两面 ---------- */

test("真实文件：WatchlistHeadPrimary.vue 当前必须零命中", () => {
  const out = run([REAL_FILE]);
  assert.doesNotMatch(out, NO_HIT, `修复后的代码不该报红：\n${out}`);
});

test("回退探针：把盖子 + content-box 写法注回真实文件 → 必须报红", () => {
  const src = readFileSync(REAL_FILE, "utf8");
  // 行尾随 checkout 而变（本机 core.autocrlf=true → CRLF，CI Linux → LF），
  // 锚点必须按检出时的实际行尾拼，否则锚点匹配不上、探针只会空转着失败。
  const eol = src.includes("\r\n") ? "\r\n" : "\n";

  // 两处替换即修复前的原样。若源文件结构变了、替换点找不到，下面的断言会以
  // 「探针失效」失败——那是**期望的失败**，提示按新写法更新本探针，而不是放过回退。
  const capAnchor = [
    "  justify-content: space-between;",
    "  margin-bottom: var(--space-3);",
    "}"
  ].join(eol);
  const capWith = [
    "  justify-content: space-between;",
    "  max-height: 40px;",
    "  margin-bottom: var(--space-3);",
    "  overflow: hidden;",
    "}"
  ].join(eol);
  const btnAnchor = [
    "  box-sizing: border-box;",
    "  width: 28px;",
    "  height: 28px;",
    "  padding: 0;"
  ].join(eol);
  const btnWith = [
    "  box-sizing: content-box;",
    "  width: 28px;",
    "  height: 28px;",
    "  padding: 6px;"
  ].join(eol);

  assert.ok(
    src.includes(capAnchor),
    `探针失效：源文件里找不到 .head-primary 的锚点，说明写法已变，请更新本探针。`
  );
  assert.ok(
    src.includes(btnAnchor),
    `探针失效：源文件里找不到 .icon-tool-btn 的锚点，说明写法已变，请更新本探针。`
  );

  const reverted = src.split(capAnchor).join(capWith).split(btnAnchor).join(btnWith);
  assert.notEqual(reverted, src, "探针失效：回退替换没有生效。");

  const out = guard([reverted]);
  assert.match(out, /\[clip\]/, `把 bug 注回去却没报红，守门失效：\n${out}`);
  assert.match(out, /\[pad\]/, `把 bug 注回去却没报红，守门失效：\n${out}`);
});
