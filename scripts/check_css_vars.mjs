#!/usr/bin/env node
/**
 * CSS 自定义属性（令牌）守卫（#1545 T1.4）
 *
 * 拦截「被 var() 引用、却在源码里找不到定义」的幽灵令牌。
 *
 * 为什么需要它：`--bg-subtle` 曾被 6 处引用（探市市场机会卡 + 记账导入页），
 * 但全仓零定义——`var(--bg-subtle)` 求值无效，导致整条 `color-mix(...)` 声明
 * 静默失效（市场机会卡只剩左边框有颜色），而构建 / 类型检查 / lint 全绿，
 * 没有任何机制能发现。本守卫把这类「引用与定义脱节」变成显式红灯。
 *
 * 实现：纯 Node（零依赖）。扫描 frontend/src 下所有
 * .css / .scss / .vue / .ts / .tsx / .js / .jsx / .mjs 文件，
 * 分别收集「定义」（`--x:` 声明、`'--x':` 对象键、`setProperty('--x'`）与
 * 「引用」（`var(--x`），差集即为幽灵令牌。动态拼接（`var(--x-${t})`）不参与判定。
 *
 * 白名单：`--el-*` / `--pure-*` / `--tw-*` 由 element-plus / pure-admin /
 * tailwind 运行时注入，不属于本仓定义范围。
 *
 * 退出码：发现**新增**幽灵令牌 → 1（CI 红灯）。
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, extname, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(ROOT, "frontend", "src");

const EXTS = new Set([
  ".css",
  ".scss",
  ".vue",
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".mjs"
]);

/** 外部库 / 运行时注入的变量前缀，不算本仓定义范围 */
const ALLOW_PREFIX = ["--el-", "--pure-", "--tw-"];

/**
 * 存量基线（#1545 全仓扫描时发现，属独立技术债，已登记 issue #1548 之外的
 * 「幽灵令牌存量清理」卡）：
 * 这些令牌在本 PR 之前就已被引用但未定义，分布在 Aggregation / login /
 * ledgers / 记账导入 / profile 等非探市页面。逐处补定义会**改变这些页面的视觉**
 * （原声明当前完全失效），需单独走查，故此处冻结为基线：**只拦截新增**。
 *
 * 维护：修复某令牌后把它从下方移除即可；脚本会对「已不再是幽灵令牌却仍留在
 * 基线」的项打印提示（不阻断）。
 */
const BASELINE = new Set([
  "--space-4",
  "--space-6",
  "--space-8",
  "--shadow-overlay",
  "--c-success",
  "--border-strong",
  "--bg-secondary",
  "--color-gray-200", // 疑似 tailwind v4 调色板注入，待核实
  "--text-on-brand",
  "--brand-50",
  "--radius-xl",
  "--brand-700-rgb"
]);

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) out.push(...walk(p));
    else if (EXTS.has(extname(p))) out.push(p);
  }
  return out;
}

// 定义：CSS 声明 `--x: v`，或 JS / Vue 对象键 `'--x': v` / `"--x": v`
const DEF_RE = /(--[A-Za-z0-9_-]+)['"]?\s*:/g;
const USE_RE = /var\(\s*(--[A-Za-z0-9_-]+)/g;
const SETPROP_RE = /setProperty\(\s*['"`](--[A-Za-z0-9_-]+)/g;

const files = walk(SRC);
const defined = new Set();
const used = new Map(); // name -> ["rel:line", ...]

for (const f of files) {
  const text = readFileSync(f, "utf8");
  const rel = relative(ROOT, f).replace(/\\/g, "/");

  for (const m of text.matchAll(DEF_RE)) defined.add(m[1]);
  for (const m of text.matchAll(SETPROP_RE)) defined.add(m[1]);

  text.split("\n").forEach((line, i) => {
    for (const m of line.matchAll(USE_RE)) {
      // 动态拼接（如 var(--temp-${tone})）无法静态判定，跳过
      if (line[m.index + m[0].length] === "$") continue;
      const name = m[1];
      if (!used.has(name)) used.set(name, []);
      used.get(name).push(`${rel}:${i + 1}`);
    }
  });
}

const missing = [];
const missingNames = new Set();
for (const [name, locs] of used) {
  if (defined.has(name)) continue;
  if (ALLOW_PREFIX.some(p => name.startsWith(p))) continue;
  missing.push({ name, locs });
  missingNames.add(name);
}

const newMissing = missing.filter(m => !BASELINE.has(m.name));
const resolved = [...BASELINE].filter(n => !missingNames.has(n));

if (resolved.length) {
  console.log(
    `提示：基线中 ${resolved.length} 项已不再是幽灵令牌，可从 BASELINE 移除：${resolved.join(", ")}`
  );
}

if (newMissing.length) {
  console.error(`? 发现 ${newMissing.length} 个「被引用但未定义」的 CSS 变量：\n`);
  for (const { name, locs } of newMissing) {
    console.error(`  ${name}`);
    for (const l of locs.slice(0, 5)) console.error(`      ${l}`);
    if (locs.length > 5) console.error(`      … 另 ${locs.length - 5} 处`);
  }
  console.error(
    "\n请在 frontend/src/style/ 补定义（亮色 colors.css + 暗色 dark.scss 双端），或改用已有令牌。"
  );
  process.exit(1);
}

console.log(
  `? CSS 令牌引用检查通过（定义 ${defined.size} 个 / 引用 ${used.size} 个；` +
    `存量基线 ${BASELINE.size} 个，本次无新增幽灵令牌）。`
);
