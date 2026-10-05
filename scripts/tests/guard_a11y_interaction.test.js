/**
 * guard_a11y_interaction 回归样本（#1842）。
 *
 * 三组样本各司其职，缺一不可：
 *   · **命中样本** —— 规则真能抓到问题（改宽了要红）；
 *   · **放行样本** —— 不得误报（尤其是 @keyframes 的 from、.is-folded 折叠态、
 *     `opacity: 0.5` 的常驻半透明、PascalCase 业务组件，这四类早期版本都误报过）；
 *   · **名单样本** —— element-plus 图标名单不许被清空（清空后规则 1 对裸写图标静默失效）。
 *
 * 样本取自实际代码里出现过的形态，不是构造的理想化片段。
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import assert from "node:assert/strict";
import test from "node:test";

const SCRIPT = join(process.cwd(), "scripts", "guard_a11y_interaction.py");
const PY = process.env.PYTHON || "python";

function guard(files) {
  const dir = mkdtempSync(join(tmpdir(), "a11y-guard-"));
  const paths = files.map((content, i) => {
    const p = join(dir, `s${i}.vue`);
    writeFileSync(p, content, "utf8");
    return p;
  });
  try {
    return execFileSync(PY, [SCRIPT, ...paths], { encoding: "utf8" });
  } catch (e) {
    return (e.stdout || "") + (e.stderr || "");
  }
}

function load() {
  return execFileSync(PY, ["-c", `import importlib.util,sys
spec = importlib.util.spec_from_file_location("g", r"${SCRIPT}")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print(len(m.EP_ICON_NAMES))`], { encoding: "utf8" }).trim();
}

/* ---------- 规则 1：纯图标按钮无可访问名称 ---------- */

test("纯图标按钮缺 aria-label → 命中", () => {
  const out = guard([
    `<template><el-button class="x"><IconifyIconOffline icon="ep:refresh" /></el-button></template>`
  ]);
  assert.match(out, /aria-label\/title/);
});

test("纯图标按钮加了 aria-label → 放行", () => {
  const out = guard([
    `<template><el-button aria-label="刷新"><IconifyIconOffline icon="ep:refresh" /></el-button></template>`
  ]);
  assert.doesNotMatch(out, /发现 \d+ 处/);
});

test("图标 + 文字的按钮有可访问名称 → 放行（不得误报）", () => {
  const out = guard([
    `<template><el-button><IconifyIconOffline icon="ep:lightning" />{{ text }}</el-button></template>`
  ]);
  assert.doesNotMatch(out, /发现 \d+ 处/);
});

test("element-plus 图标直用（裸 <Plus />）→ 命中", () => {
  const out = guard([`<template><el-button class="x"><Plus /></el-button></template>`]);
  assert.match(out, /aria-label\/title/);
});

test("el-icon 容器包裹 element-plus 图标 → 命中", () => {
  const out = guard([`<template><el-button class="x"><el-icon><Refresh /></el-icon></el-button></template>`]);
  assert.match(out, /aria-label\/title/);
});

test("图标 + 紧跟标签的可见文字 → 放行（早期误报源，报了会加多余 aria-label 覆盖可见文字）", () => {
  const out = guard([
    `<template><el-button size="small" text bg @click="openEdit(tag)"><el-icon class="mr-1"><Edit /></el-icon>编辑</el-button></template>`
  ]);
  assert.doesNotMatch(out, /发现 \d+ 处/);
});

test("按钮内文字被 HTML 注释分隔，仍算有可见文字 → 放行", () => {
  const out = guard([
    `<template><el-button><el-icon><Delete /></el-icon><!-- 分隔 -->删除</el-button></template>`
  ]);
  assert.doesNotMatch(out, /发现 \d+ 处/);
});

test("PascalCase 业务组件不是图标 → 放行（不得误报）", () => {
  const out = guard([`<template><el-button class="x"><TransactionTable /></el-button></template>`]);
  assert.doesNotMatch(out, /发现 \d+ 处/);
});

test("element-plus 图标名单非空且含常用图标（防名单被清空后静默失效）", () => {
  const n = Number(load());
  assert.ok(n > 250, `图标名单只剩 ${n} 个，规则 1 会静默失效`);
});

/* ---------- 规则 2：@click 落在非交互元素 ---------- */

test("div @click 缺 role/tabindex/@keydown → 命中", () => {
  const out = guard([`<template><div class="card" @click="go">x</div></template>`]);
  assert.match(out, /role \/ tabindex \/ @keydown/);
});

test("div @click 三件套齐全 → 放行", () => {
  const out = guard([
    `<template><div role="button" tabindex="0" @click="go" @keydown.enter="go">x</div></template>`
  ]);
  assert.doesNotMatch(out, /发现 \d+ 处/);
});

test("有 role+tabindex 但无键盘激活 → 仍命中（半吊子状态）", () => {
  const out = guard([
    `<template><div role="button" tabindex="0" @click="go">x</div></template>`
  ]);
  assert.match(out, /role \/ tabindex \/ @keydown/);
});

test("@click.stop 无表达式的空防护（只 stopPropagation）→ 放行（早期误报源）", () => {
  // 标签必须是 div/span/li —— 守卫只覆盖这三类，用 <footer> 会绕开判据、样本反证不了任何东西
  const out = guard([`<template><div class="road-form" @click.stop>操作区</div></template>`]);
  assert.doesNotMatch(out, /发现 \d+ 处/);
});

test("@click 带表达式仍是可点击 → 命中（防「空防护修复」顺手把真命中也放过）", () => {
  const out = guard([`<template><div class="row" @click="pick(row)">行</div></template>`]);
  assert.match(out, /role \/ tabindex \/ @keydown/);
});

test("a11y-allow 写在标签**上方**（自然写法）→ 豁免（早期只向后看窗口，3 处豁免全落空）", () => {
  const out = guard([
    `<template>\n  <!-- a11y-allow 容器内含 el-checkbox -->\n  <div class="row" @click="pick(row)">行</div>\n</template>`
  ]);
  assert.doesNotMatch(out, /发现 \d+ 处/);
});

test("@keyup.enter 也是键盘激活 → 放行（补 @keydown 会造成回车双触发）", () => {
  const out = guard([
    `<template><div role="button" tabindex="0" @click="go" @keyup.enter="go">触发</div></template>`
  ]);
  assert.doesNotMatch(out, /发现 \d+ 处/);
});

test("同行 a11y-allow 豁免 → 放行", () => {
  const out = guard([
    `<template><div class="c" @click="go" a11y-allow><!-- 装饰性容器，交互在子按钮上 --></div></template>`
  ]);
  assert.doesNotMatch(out, /发现 \d+ 处/);
});

/* ---------- 规则 3：hover 显隐缺兜底（判据最容易被改宽的一类） ---------- */

const HOVER_ONLY = `<template><div class="row"><span class="act">操作</span></div></template>
<style scoped>
.row:hover .act { opacity: 1; }
.act { opacity: 0; }
</style>`;

test("基态隐藏 + 只靠 :hover 显现 + 无兜底 → 命中", () => {
  const out = guard([HOVER_ONLY]);
  assert.match(out, /靠 :hover 才显现/);
});

test("hover 显隐 + :focus-within 兜底 → 放行", () => {
  const out = guard([
    `<template><div class="row"><span class="act">操作</span></div></template>
     <style scoped>
     .row:hover .act, .row:focus-within .act { opacity: 1; }
     .act { opacity: 0; }
     </style>`
  ]);
  assert.doesNotMatch(out, /发现 \d+ 处/);
});

test("hover 显隐 + @media (hover: none) 静态可见兜底 → 放行", () => {
  const out = guard([
    `<template><div class="row"><span class="act">操作</span></div></template>
     <style scoped>
     .row:hover .act { opacity: 1; }
     .act { opacity: 0; }
     @media (hover: none) { .act { opacity: 1; } }
     </style>`
  ]);
  assert.doesNotMatch(out, /发现 \d+ 处/);
});

test("@keyframes 的 from { opacity: 0 } 是动画起点 → 放行（早期误报源）", () => {
  const out = guard([
    `<template><div class="c">x</div></template>
     <style scoped>
     @keyframes fade-up { from { opacity: 0; transform: translateY(24px); } to { opacity: 1; } }
     </style>`
  ]);
  assert.doesNotMatch(out, /发现 \d+ 处/);
});

test(".is-folded 折叠态 opacity:0 不是 hover 显隐 → 放行（早期误报源）", () => {
  const out = guard([
    `<template><div class="panel is-folded">x</div></template>
     <style scoped>
     .panel.is-folded { opacity: 0; grid-template-rows: 0fr; }
     </style>`
  ]);
  assert.doesNotMatch(out, /发现 \d+ 处/);
});

test("基态 opacity:0.5 常驻半透明 + hover 提亮 → 放行（本来就看得见，早期误报源）", () => {
  const out = guard([
    `<template><button class="grab" tabindex="0">抓</button></template>
     <style scoped>
     .grab { opacity: 0.5; }
     .row:hover .grab, .grab:hover { opacity: 1; }
     </style>`
  ]);
  assert.doesNotMatch(out, /发现 \d+ 处/);
});

test("同类两个元素只有一个补了兜底 → 只报没兜底的那个（类级粒度，非文件级）", () => {
  const out = guard([
    `<template><div class="row"><span class="a">A</span><span class="b">B</span></div></template>
     <style scoped>
     .row:hover .a, .row:focus-within .a { opacity: 1; }
     .row:hover .b { opacity: 1; }
     .a, .b { opacity: 0; }
     </style>`
  ]);
  assert.match(out, /\.row:hover \.b/);
  assert.doesNotMatch(out, /\.row:hover \.a/);
});
