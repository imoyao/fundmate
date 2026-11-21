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
 * ③ 「孤立样式表」——文件存在、却没有任何入口加载它。
 *    这类文件里的规则**一条都不会生效**，而且没人能发现：`login.css` 在仓库里
 *    躺了数月（92 行），期间断点守卫还替它维护着 2 条 `breakpoint-allow` 豁免。
 *    静默程度与 ①② 同级：不报错、不报红、只在浏览器里「什么都没发生」。
 *    判据：从全部非样式源文件出发，按 `import` / `@use` / `@forward` / `@import`
 *    （含 `url()`）/ `<style src="...">` 解析依赖边做可达性闭包，闭包外的
 *    `.css` / `.scss` 即可疑。SCSS 裸名按「当前文件目录 + `_` 前缀」解析。
 *
 * 白名单：`--el-*` / `--pure-*` / `--tw-*` 由 element-plus / pure-admin /
 * tailwind 运行时注入，不属于本仓定义范围。
 *
 * 注释不参与判定：收集定义/引用前先剥掉 `/* *\/` 与 `//`，否则文档里写的
 * `--x: ...` 示例会被当成真实定义，把真幽灵令牌藏起来。实测（同树新旧对照）
 * 定义 429→428、引用 311→308：当前只影响 1 个定义与 3 处引用，属**潜在**漏洞
 * ——但注释里的示例会越来越多，一旦某个令牌只在注释里被「定义」，幽灵检测就永久失明。
 * 行号靠「用空格顶替注释字符」保留，报错位置不受影响。
 *
 * 退出码：发现**新增**幽灵令牌、**任何**自引用令牌、**任何**孤立样式表 → 1（CI 红灯）。
 */
import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { join, relative, extname, dirname, basename } from "node:path";
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

/**
 * 把注释整段替换成空格（**保留换行与列位置**，行号才指得准）。
 *
 * 为什么必须剥：文档/注释里大量写着 `--bg-foo: ...` 这类示例，裸正则会把它
 * 当成真实定义 —— 一个只被引用、从未真正定义的令牌，只要有人在注释里提过一句
 * 「--bg-foo 是 xx 色」，幽灵检测就会放行。反向同理：注释里的 `var(--x)`
 * 会被算成一次引用，让「零引用可删」的判断失真。
 *
 * `//` 只在「行首 / 空白 / ; { } 之后」才算注释，避免把 `url(//cdn...)`
 * 与 `https://` 这类值当成注释吃掉。
 */
function stripComments(text) {
  const blank = (s) => s.replace(/[^\n]/g, " ");
  let out = "";
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    const d = text[i + 1];
    if (c === "/" && d === "*") {
      const end = text.indexOf("*/", i + 2);
      const stop = end === -1 ? text.length : end + 2;
      out += blank(text.slice(i, stop));
      i = stop;
      continue;
    }
    if (c === "/" && d === "/") {
      const prev = out[out.length - 1];
      const atLineStart = out === "" || /[\s;{}]/.test(prev);
      if (atLineStart) {
        const end = text.indexOf("\n", i);
        const stop = end === -1 ? text.length : end;
        out += blank(text.slice(i, stop));
        i = stop;
        continue;
      }
    }
    out += c;
    i++;
  }
  return out;
}

const files = walk(SRC);
const defined = new Set();
const used = new Map(); // name -> ["rel:line", ...]

for (const f of files) {
  const rel = relative(ROOT, f).replace(/\\/g, "/");
  const code = stripComments(readFileSync(f, "utf8"));

  for (const m of code.matchAll(DEF_RE)) defined.add(m[1]);
  for (const m of code.matchAll(SETPROP_RE)) defined.add(m[1]);

  code.split("\n").forEach((line, i) => {
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
  const raw = readFileSync(f, "utf8");
  // 扫描用剥注释版（注释里的 `--x: var(--x)` 属举例，不该判红），
  // 但豁免指令 `css-vars-ok` 本身就写在注释里，必须查原文。
  const code = stripComments(raw);
  const rel = relative(ROOT, f).replace(/\\/g, "/");
  const lines = raw.split("\n");
  for (const m of code.matchAll(DECL_RE)) {
    const name = m[1];
    // 值里出现对自身的 var() 引用即构成循环（带 fallback 的写法同样成立）
    const selfUse = new RegExp("var\\(\\s*" + name.replace(/[-]/g, "\\-") + "\\s*[,)]");
    if (!selfUse.test(m[2])) continue;
    const lineNo = code.slice(0, m.index).split("\n").length;
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

// ── ③ 孤立样式表：文件存在，却没有任何入口加载它（#3213 同族）───────────
// 一个从不被加载的样式表，其规则**一条都不会生效**，而这与 ①② 一样不报错。
// 判据是纯静态的可达性闭包：非样式源文件为根，按解析出的依赖边扩散，
// 闭包外的 .css / .scss 即可疑。所有非样式文件都算根（不建模路由懒加载），
// 所以只会漏报不会误报。
const STYLE_EXTS = new Set([".css", ".scss"]);

/** import 说明符 → 真实文件；解析不出来（外部包 / 别名未命中）返回 null。 */
function resolveSpec(spec, fromFile) {
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(spec)) return null; // http: / data: 等
  const base = spec.startsWith("@/")
    ? join(SRC, spec.slice(2))
    : join(dirname(fromFile), spec); // SCSS 裸名 / 相对路径都按当前文件目录解析
  const cands = [];
  if (STYLE_EXTS.has(extname(base).toLowerCase())) {
    cands.push(base, join(dirname(base), `_${basename(base)}`)); // partial：_x.scss
  } else {
    for (const ext of STYLE_EXTS) {
      cands.push(base + ext, join(dirname(base), `_${basename(base)}${ext}`));
      cands.push(join(base, `index${ext}`));
    }
  }
  for (const c of cands) if (existsSync(c) && statSync(c).isFile()) return c;
  return null;
}

// 五种加载写法：SCSS 指令 / @import url(...) / JS 静态与动态 import / SFC <style src>
const SPEC_RES = [
  /@(?:use|forward|import)\s+(?:url\(\s*)?["']([^"']+)["']/g,
  /@import\s+url\(\s*([^)"'\s]+)\s*\)/g,
  /(?:^|[\s;{(])import\s*\(\s*["']([^"']+)["']/gm,
  /(?:^|[\s;{(])import\s+["']([^"']+)["']/gm,
  /<style[^>]*\ssrc\s*=\s*["']([^"']+)["']/gi
];

const edges = new Map();
for (const f of files) {
  // 用剥注释版：注释里提到的 `<style src="...">` 不是真的加载，会掩盖孤立文件。
  const code = stripComments(readFileSync(f, "utf8"));
  const outs = new Set();
  for (const re of SPEC_RES) {
    for (const m of code.matchAll(re)) {
      const target = resolveSpec(m[1].trim(), f);
      if (target) outs.add(target);
    }
  }
  edges.set(f, outs);
}

const reached = new Set();
const queue = files.filter((f) => !STYLE_EXTS.has(extname(f).toLowerCase()));
while (queue.length) {
  for (const next of edges.get(queue.pop()) || []) {
    if (reached.has(next)) continue;
    reached.add(next);
    queue.push(next);
  }
}
const orphans = files
  .filter((f) => STYLE_EXTS.has(extname(f).toLowerCase()))
  .filter((f) => !reached.has(f));

if (orphans.length) {
  console.error(`? 发现 ${orphans.length} 个「从未被加载」的样式表：\n`);
  for (const f of orphans) {
    const rel = relative(ROOT, f).replace(/\\/g, "/");
    console.error(`  ${rel}  （${readFileSync(f, "utf8").split("\n").length} 行）`);
  }
  console.error(
    "\n这些文件里的规则在浏览器里一条都不会生效（不报错、不报红）。" +
      "\n若样式已迁移到别处（Tailwind 工具类 / 组件内 scoped 块），直接删除该文件；" +
      "\n若确实需要，就把它接进入口：main.ts 的 import、index.scss 的 @use，" +
      '\n或组件里的 <style src="...">。'
  );
  process.exit(1);
}

console.log(
  `? CSS 令牌引用检查通过（定义 ${defined.size} 个 / 引用 ${used.size} 个；` +
    `存量基线 ${BASELINE.size} 个，本次无新增幽灵令牌；孤立样式表 0 个）。`
);
