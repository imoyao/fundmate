#!/usr/bin/env node
/**
 * CSS 自定义属性（令牌）守卫（#1545 T1.4）
 *
 * 拦截两类问题：
 *
 * ① 「幽灵令牌」——被 var() 引用、却在源码里找不到定义。
 *    `--bg-subtle` 曾被 6 处引用（探市市场机会卡 + 记账导入页）但全仓零定义，
 *    `var(--bg-subtle)` 求值无效导致整条 `color-mix(...)` 声明静默失效，
 *    而构建 / 类型检查 / lint 全绿。
 *
 * ② 「自引用令牌」——`--x: var(--x)`（#1602）。按 CSS 规范这是循环引用，
 *    该变量在计算期 guaranteed-invalid，**反而会覆盖掉**同元素上更早定义的真实值。
 *    `design-tokens.css` 曾因此有 14 个令牌（--bg-* / --text-* / --border-light /
 *    --border-subtle / --shadow-modal / --radius-pill）把 colors.css 的真实定义
 *    覆盖成无效值，仅仅因为 main.ts 在 index.scss 之后又导入了一次 colors.css
 *    才侥幸生效。① 的检测完全抓不到这类：`--x: var(--x)` 在 ① 眼里既是「定义」
 *    又是「使用」，天然自洽。
 *
 * 两类分别可用行内指令豁免（须带理由），指令形如 css-vars-ok: ...，
 * 写在声明所在行或上一行即可（详见脚本内的 OK_RE）。
 *
 * 实现：纯 Node（零依赖）。扫描 frontend/src 下所有
 * .css / .scss / .vue / .ts / .tsx / .js / .jsx / .mjs 文件，
 * 分别收集「定义」（`--x:` 声明、`'--x':` 对象键、`setProperty('--x'`）与
 * 「引用」（`var(--x`），差集即为幽灵令牌。动态拼接（`var(--x-${t})`）不参与判定。
 *
 * 白名单：`--el-*` / `--pure-*` / `--tw-*` 由 element-plus / pure-admin /
 * tailwind 运行时注入，不属于本仓定义范围。
 *
 * 退出码：发现**新增**幽灵令牌或**任何**自引用令牌 → 1（CI 红灯）。
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
  // 2026-09-17 #1558：12 个存量幽灵令牌已全部清零（引用改既有令牌 / src 零引用直接移除），见 PR。
  // 见 docs/working-notes 或 issue #1558。清空后守卫会拦截任何「新增」未定义令牌。
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

// ── 自引用检测（#1602）──────────────────────────────────────────────
// `--x: <值里含 var(--x)>` 是 CSS 循环引用：该变量 guaranteed-invalid，
// 且会**覆盖**同元素上更早/更低特异性的真实定义。跨行声明（rgba( 换行）也要能匹配。
const OK_RE = /css-vars-ok:\s*([^\n*]*)/;
const hasOk = (lines, idx) => {
  // 向上最多 8 行找豁免指令（覆盖多行注释块）；越过「本行之前的已结束声明」即停，
  // 避免命中更早、不相干的豁免。
  for (let j = idx; j >= Math.max(0, idx - 8); j--) {
    if (OK_RE.test(lines[j])) return true;
    if (j < idx && /;\s*$/.test(lines[j]) && !/^\s*(\/\*|\*|\/\/)/.test(lines[j])) return false;
  }
  return false;
};
const DECL_RE = /^\s*(--[A-Za-z0-9_-]+)\s*:\s*([^;]*);/gm;

const selfRefs = [];
for (const f of files) {
  const text = readFileSync(f, "utf8");
  const rel = relative(ROOT, f).replace(/\\/g, "/");
  const lines = text.split("\n");
  for (const m of text.matchAll(DECL_RE)) {
    const name = m[1];
    // 值里出现对自身的 var() 引用即构成循环（带 fallback 的写法同样成立）
    const selfUse = new RegExp("var\\(\\s*" + name.replace(/[-]/g, "\\-") + "\\s*[,)]");
    if (!selfUse.test(m[2])) continue;
    const lineNo = text.slice(0, m.index).split("\n").length;
    if (hasOk(lines, lineNo - 1)) continue;
    selfRefs.push({ name, loc: `${rel}:${lineNo}` });
  }
}

if (selfRefs.length) {
  console.error(
    `✗ 发现 ${selfRefs.length} 个「自引用」CSS 变量（值是 var(自身) → 循环引用，变量失效并覆盖真实定义）：\n`
  );
  const byName = new Map();
  for (const r of selfRefs) {
    if (!byName.has(r.name)) byName.set(r.name, []);
    byName.get(r.name).push(r.loc);
  }
  for (const [name, locs] of byName) console.error(`  ${name}  ${locs.join(", ")}`);
  console.error(
    "\n自引用没有任何正面作用：直接删掉该声明即可，值会由同元素/更低特异性的真实定义提供。" +
      "\n（若确属有意为之，在声明行或其上一行写 css-vars-ok: <理由> 并说明后果。）"
  );
  process.exit(1);
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
