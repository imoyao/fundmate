#!/usr/bin/env node
/**
 * scripts/guard_ts_any.mjs —— 全仓 TS/Vue 显式 any 类型注解「只减不增」防回潮闸门。
 * 源 issue #2879「全仓 455 处 any，类型护栏泄漏」的第一刀：先把口径钉死、冻结存量。
 *
 * ==================================================================================
 * WHY（为什么散文规范拦不住 / 为什么用 AST）
 * ==================================================================================
 * 为什么散文规范拦不住：「别再写 any」这类约定写进 AGENTS.md / review 清单，失败时
 * **没有任何报错** —— tsc 默认允许显式 any（noImplicitAny 也管不到显式标注）、
 * eslint 规则可临时关、构建照绿。于是每轮重构「顺手 any 一下」都会悄悄沉淀，直到
 * 有人做一次全仓普查才发现几百处。没有机器化闸门，收敛多少都会涨回去（同 #1606 /
 * #2873「拆完必涨」的教训）。第一刀不追求把存量清零（一次性全量收紧会让几百处全红、
 * 谁都动不了），而是**冻结存量、堵住新增**：之后每消掉一处就 --write 收紧一次。
 *
 * 为什么用 AST、不用裸正则：卡面「455 处」与实测「裸 \bany\b 正则 561 token /
 * 156 文件」差一大截，因为裸正则把注释、字符串、英文单词（含变量名 any）、JSDoc、
 * .d.ts 说明里的 "any" 全算了进去 —— 这些根本不是类型注解，拿它当基线只会制造
 * 「改个注释就红灯」的假信号。本守卫用 TypeScript Compiler API 数
 * ts.SyntaxKind.AnyKeyword 节点：只有真正作为类型关键字出现的 any 才计数
 * （: any / as any / Array<any> / 返回类型 / 类型别名 / 泛型实参等）；注释、字符串、
 * 标识符、JSDoc 里的 {any} 天然落到 Trivia / StringLiteral / JSDoc 节点，不进
 * forEachChild 遍历，一律不计。.vue 的 <script> / <script setup> 由
 * @vue/compiler-sfc 的 parse() 取出内容再交给 TS，避免把 <template> 里的英文 any
 * 算进来。
 *
 * ==================================================================================
 * 判定规则
 * ==================================================================================
 * 扫描 frontend/src 目录下所有 .ts / .vue，输出「按文件的 AnyKeyword 计数」，与
 * scripts/ts-any-baseline.json（按路径字典序，收录**所有**被扫文件，含 0 值）比对：
 *   1. 总数不许涨：基线内文件的实测 any 总和 > 基线冻结总和 ⇒ 拦截；
 *   2. 任何已有文件（在基线里）的计数不许涨：实测 > 基线 ⇒ 拦截（回潮）；
 *   3. 新增文件（不在基线里）：其 any 计数 > NEW_FILE_ANY_LIMIT(3) ⇒ 拦截；≤ 3 放行，
 *      但提示用 --write 纳入基线（纳入后即受规则 2 约束，0→1 也会红）；--write 纳入
 *      新增文件时同样校验 ≤ 上限，防「先写 10 个 any 再回写洗掉」；
 *   4. 实测低于基线 ⇒ 打印「请 --report 收紧基线」提示但**不报错**（loose 语义，
 *      同 guard_service_size.py：正常收敛不该红掉校验）；
 *   5. 基线里有、文件已删 ⇒ stale 提示，不报错。
 * 基线收录所有文件（含 0）是刻意的：0 值条目钉住「这个文件本来干净」，否则一个
 * 原本无 any 的存量文件 0→1 会被当成「新增文件」从上限 3 下溜过去 —— 那正是回潮。
 *
 * --report 打印可直接粘贴/写回的基线 JSON；--write 实际回写（只允许收紧：已有条目
 * 实测变大、或新增文件超上限时拒绝写入，防「用 --write 洗掉回潮」）。
 *
 * ==================================================================================
 * 刻意不覆盖的边界（别把闸门读成「类型安全了」）
 * ==================================================================================
 * - 只判「显式 any 类型注解」的**数量**，不判该 any 是否合理、能否换成 unknown、
 *   不判类型是否真的安全（那是 code review / 后续收敛的事）。
 * - 只扫 frontend/src 的 .ts / .vue；不扫 .tsx / .js / .jsx（本仓口径，.js 无类型
 *   注解、JSDoc 里的 {any} 也不计）、不扫 scripts/ / backend/ / node_modules / dist。
 * - .d.ts 声明文件同为 .ts，其中的 any 照计（AnyKeyword 口径不区分声明与实现）——
 *   它同样属于「类型护栏泄漏」，刻意不排除，避免开后门。
 * - <script src="./x.ts"> 外部引用：compiler-sfc 取不到内联内容，不计；被指向的 .ts
 *   本身会被 walk 单独扫到（若它在 src 下）。
 * - 不追 git 历史 / 不判「这个文件是不是本轮新建」：新增文件 = 不在基线里的文件。
 *
 * ==================================================================================
 * 口径限制（如实标注，不粉饰）
 * ==================================================================================
 * 依赖解析顺序：createRequire(frontend/package.json)（CI 里 pnpm install 后天然命中；
 * 本地 worktree 可由 NODE_PATH 或 frontend/node_modules junction 提供）→
 * createRequire(import.meta.url)（认 NODE_PATH）。
 *
 * typescript 与 @vue/compiler-sfc **任一不可用**时，本守卫判 **exit 2、不产出任何结论**：
 * 不比对基线、不打印 OK、不产生「收紧基线」提示。正式判据只在装了前端依赖的环境跑
 * （CI 的 frontend job；本地设 NODE_PATH 或在 frontend 下建 node_modules junction）。
 * --report / --write 在依赖缺失时同样拒绝：否则会拿降级口径的数字回写、洗掉正式基线，
 * 后果不可逆。
 *
 * 为什么**不能**降级出结论（实测证据，2026-11-06 复核）：
 *   - AST 口径（依赖可用）：540 处 any；
 *   - 降级正则（依赖缺失）：539 处 any，少 1 处，且对 composables/usePositionSubmit.ts
 *     数出 2（AST 是 3）——拿口径不同的数字与同一份 AST 基线比对，会误报一条
 *     「已低于基线，请收紧」，同时仍返回 0「只减不增」。这是假绿。
 *   故降级计数函数（countFallback / stripNonCode / extractVueScript / isTypeContext）
 *   仅保留为导出的纯函数，供回归网做解析层测试（验证注释 / 字符串里的 any 不计），
 *   **生产路径绝不调用它出结论**；单个 .vue 解析失败也不局部降级，直接抛错转 exit 2。
 *
 * ==================================================================================
 * 用法
 * ==================================================================================
 *   node scripts/guard_ts_any.mjs                 # 校验（CI / pre-commit）
 *   node scripts/guard_ts_any.mjs --report        # 打印当前实测基线 JSON
 *   node scripts/guard_ts_any.mjs --write         # 回写/收紧 scripts/ts-any-baseline.json
 *   # 回归网造沙箱：GUARD_TS_ANY_SRC=<dir> GUARD_TS_ANY_BASELINE=<file> node scripts/guard_ts_any.mjs
 *
 * 退出码：0 = 通过；1 = 拦截（回潮 / 新增文件超上限 / --write 拒绝上调）；
 *         2 = 拿不到可信输入（依赖缺失 / 源文件解析失败、扫不到任何文件、
 *             基线缺失或格式非法、未知参数）—— 结论不可信，**不得**当成通过
 *             （不许静默绿）。依赖缺失正属于这一类，不降级、不产出结论。
 */

import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, extname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_SRC = join(ROOT, "frontend", "src");
const DEFAULT_BASELINE = join(ROOT, "scripts", "ts-any-baseline.json");

// 回归网造沙箱用；正常跑不必设。两者都按绝对路径解析，避免受 cwd 影响。
const SRC = process.env.GUARD_TS_ANY_SRC
  ? resolve(process.env.GUARD_TS_ANY_SRC)
  : DEFAULT_SRC;
const BASELINE_PATH = process.env.GUARD_TS_ANY_BASELINE
  ? resolve(process.env.GUARD_TS_ANY_BASELINE)
  : DEFAULT_BASELINE;

const EXTS = new Set([".ts", ".vue"]);
const SKIP_DIRS = new Set(["node_modules", "dist", ".git"]);
const ISSUE = 2879;
/** 新增文件（或 --write 纳入新增文件）允许的 any 计数上限，超出即红。 */
const NEW_FILE_ANY_LIMIT = 3;

// ── 依赖加载 ────────────────────────────────────────────────────────────────
// ESM 顶层静态 import 不认 NODE_PATH，故用 createRequire 动态加载：
//   ① 指向 frontend/package.json → 命中 frontend/node_modules（CI / 本地 junction）；
//   ② 指向本脚本 → 命中 NODE_PATH（用户在本机可把主仓 node_modules 喂进来）。
const requireFrontend = createRequire(join(ROOT, "frontend", "package.json"));
const requireSelf = createRequire(import.meta.url);

function loadOptional(name) {
  for (const req of [requireFrontend, requireSelf]) {
    try {
      return req(name);
    } catch (e) {
      if (e.code !== "MODULE_NOT_FOUND") throw e; // 包内部报错不吞，别伪装成「不可用」
    }
  }
  return null;
}

const ts = loadOptional("typescript");
const sfc = loadOptional("@vue/compiler-sfc");
const AST_OK =
  !!ts &&
  !!sfc &&
  typeof ts.createSourceFile === "function" &&
  typeof ts.forEachChild === "function" &&
  typeof sfc.parse === "function";

// ── 扫描 ────────────────────────────────────────────────────────────────────
function walk(dir, acc) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return acc;
  }
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name) || entry.name.startsWith(".")) continue;
      walk(full, acc);
    } else if (entry.isFile() && EXTS.has(extname(entry.name))) {
      acc.push(full);
    }
  }
  return acc;
}

/** 基线 key 一律相对扫描根、POSIX 分隔符（Windows 反斜杠会让 CI 与本地成两条记录）。 */
function keyOf(file) {
  return relative(SRC, file).split(sep).join("/");
}

// ── AST 口径（主路径）──────────────────────────────────────────────────────
function scriptKindOf(lang) {
  switch ((lang || "").toLowerCase()) {
    case "tsx":
      return ts.ScriptKind.TSX;
    case "jsx":
      return ts.ScriptKind.JSX;
    case "js":
      return ts.ScriptKind.JS;
    default:
      // 无 lang 的 <script> 也按 TS 解析：TS 能容错解析 JS 子集，且 JS 里本就无
      // AnyKeyword 类型节点，不会凭空多数。
      return ts.ScriptKind.TS;
  }
}

function countAst(text, file) {
  let n = 0;
  const visit = (node) => {
    if (node.kind === ts.SyntaxKind.AnyKeyword) n += 1;
    ts.forEachChild(node, visit);
  };
  const parse = (content, lang) => {
    const sf = ts.createSourceFile(
      file,
      content,
      ts.ScriptTarget.Latest,
      false,
      scriptKindOf(lang),
    );
    visit(sf);
  };

  if (file.endsWith(".vue")) {
    const { descriptor } = sfc.parse(text, { filename: file });
    for (const block of [descriptor.script, descriptor.scriptSetup]) {
      // <script src="./x.ts"> 时 content 为空，被指向的 .ts 会被 walk 单独扫到。
      if (block && block.content) parse(block.content, block.lang);
    }
  } else {
    parse(text, "ts");
  }
  return n;
}

// ── 降级口径（仅作解析层纯函数测试，生产路径不调用）────────────────────────
const NON_CODE_RE =
  /\/\*[\s\S]*?\*\/|\/\/[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`/g;

function stripNonCode(text) {
  // 用等长空白替换，保留换行与结构，避免把 "foo/*bar*/any" 之类拼成假 token。
  return text.replace(NON_CODE_RE, (m) => m.replace(/[^\n]/g, " "));
}

function extractVueScript(text) {
  const blocks = [];
  const re = /<script\b[^>]*>([\s\S]*?)<\/script\s*>/gi;
  let m;
  while ((m = re.exec(text)) !== null) blocks.push(m[1]);
  return blocks.join("\n");
}

/** 该 any 是否处在「类型位置」：前面是类型引入符 / 关键字，或后面是类型延续符。 */
function isTypeContext(before, after) {
  const b = before.trimEnd();
  const a = after.trimStart();
  const LEFT =
    /(?::|<|\||&|,|\(|\[|=|=>|\bas\b|\bsatisfies\b|\bextends\b|\bkeyof\b|\breadonly\b|\bnew\b|\btypeof\b)\s*$/;
  const RIGHT =
    /^(?:>|\||&|,|\)|\]|;|=>|\[|\{|\bas\b|\bextends\b|\bsatisfies\b)/;
  return LEFT.test(b) || RIGHT.test(a);
}

export function countFallback(text, file) {
  const src = file.endsWith(".vue") ? extractVueScript(text) : text;
  const stripped = stripNonCode(src);
  let n = 0;
  const re = /\bany\b/g;
  let m;
  while ((m = re.exec(stripped)) !== null) {
    const before = stripped.slice(Math.max(0, m.index - 24), m.index);
    const after = stripped.slice(m.index + 3, m.index + 3 + 24);
    if (isTypeContext(before, after)) n += 1;
  }
  return n;
}

/**
 * 生产路径的单文件计数：只走 AST，绝不降级。解析失败直接抛错，由 main() 转成
 * exit 2（拿不到可信输入），不许用近似口径出结论。
 */
function countAny(text, file) {
  return countAst(text, file);
}

/** 返回 { 相对 src 的路径: AnyKeyword 计数 }；扫不到任何文件返回 null，读取 / 解析失败抛错。 */
export function collectCounts() {
  const files = walk(SRC, []);
  if (files.length === 0) return null;
  const counts = {};
  for (const file of files) {
    // 读取失败不静默跳过（少算文件就是假绿），抛给 main() 转 exit 2。
    counts[keyOf(file)] = countAny(readFileSync(file, "utf8"), file);
  }
  return counts;
}

// ── 基线 I/O ────────────────────────────────────────────────────────────────
export function buildBaseline(counts) {
  const keys = Object.keys(counts).sort();
  return {
    $comment:
      "issue #2879 第一刀：TS/Vue 显式 any 类型注解（TS AnyKeyword AST 口径）冻结基线，只减不增。" +
      " 收录所有被扫文件（含 0：0 值条目钉住「本来干净」，0→1 也算回潮）。" +
      " 由 `node scripts/guard_ts_any.mjs --write` 生成；实测低于基线请收紧，不要手工调大。",
    issue: ISSUE,
    newFileAnyLimit: NEW_FILE_ANY_LIMIT,
    generatedAt: new Date().toISOString().slice(0, 10),
    files: Object.fromEntries(keys.map((k) => [k, counts[k]])),
  };
}

/** 返回解析后的基线；失败返回 null（调用方判 exit 2）。allowMissing 仅供 --write 首次生成。 */
export function loadBaseline(path, allowMissing) {
  let raw;
  try {
    raw = readFileSync(path, "utf8");
  } catch (e) {
    // missing 标记供 --write 区分「首次全量冻结」与「在既有基线上收紧」。
    if (allowMissing && e.code === "ENOENT")
      return { files: {}, missing: true };
    console.error(`[TS any 守卫] ❌ 读不到基线文件 ${path}：${e.message}`);
    console.error("  基线缺失 ≠「没有存量」——静默降级就是假绿，故判 exit 2。");
    return null;
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (e) {
    console.error(`[TS any 守卫] ❌ 基线 JSON 解析失败 ${path}：${e.message}`);
    return null;
  }
  if (
    !parsed ||
    typeof parsed !== "object" ||
    typeof parsed.files !== "object" ||
    parsed.files === null ||
    Array.isArray(parsed.files)
  ) {
    console.error(
      '[TS any 守卫] ❌ 基线格式不对：需要 { files: { "<相对 src 的路径>": 非负整数 } }',
    );
    return null;
  }
  for (const [k, v] of Object.entries(parsed.files)) {
    if (!Number.isInteger(v) || v < 0) {
      console.error(
        `[TS any 守卫] ❌ 基线条目非法：${k} = ${JSON.stringify(v)}（须为非负整数）`,
      );
      return null;
    }
  }
  return parsed;
}

const sumValues = (obj) => Object.values(obj).reduce((s, n) => s + n, 0);

// ── 判据 ────────────────────────────────────────────────────────────────────
export function compareToBaseline(counts, base) {
  const violations = [];
  const loose = [];
  const newFiles = [];
  const frozenTotal = sumValues(base);
  let measuredExistingTotal = 0;

  for (const [k, n] of Object.entries(counts)) {
    if (k in base) {
      measuredExistingTotal += n;
      if (n > base[k]) violations.push({ kind: "GROW", key: k, n, b: base[k] });
      else if (n < base[k]) loose.push({ key: k, n, b: base[k] });
    } else if (n > NEW_FILE_ANY_LIMIT) {
      violations.push({ kind: "NEW_OVER", key: k, n });
    } else if (n > 0) {
      newFiles.push({ key: k, n });
    }
    // 0 any 的新文件：静默放行，避免「新增一个纯类型文件」也刷提示。
  }
  const stale = Object.keys(base).filter((k) => !(k in counts));

  // 总数不许涨（冗余于逐文件，但作为显式全局判据把冻结数字摆出来）。
  const totalRose = measuredExistingTotal > frozenTotal;
  const measuredAll = sumValues(counts);

  if (violations.length === 0 && !totalRose) {
    console.log(
      `[TS any 守卫] OK：存量冻结 ${Object.keys(base).length} 个文件 / 冻结 any 总数 ${frozenTotal}；` +
        `本轮实测 ${measuredAll} 处 any（已有文件 ${measuredExistingTotal} 处，共扫 ${Object.keys(counts).length} 个文件）；只减不增`,
    );
    if (loose.length) {
      console.log(
        "提示：以下文件已低于基线，请 --report 收紧基线（只减不增；不收紧该维度会静默失效）：",
      );
      for (const h of loose) console.log(`  - ${h.key}: ${h.n}（基线 ${h.b}）`);
    }
    if (newFiles.length) {
      console.log(
        `提示：以下 ${newFiles.length} 个新文件未在基线内（any ≤ ${NEW_FILE_ANY_LIMIT} 放行），请用 --write 纳入基线：`,
      );
      for (const h of newFiles) console.log(`  - ${h.key}: ${h.n} 处 any`);
    }
    if (stale.length) {
      console.log("提示：以下文件已不在基线中（stale），请用 --write 清理：");
      for (const k of stale) console.log(`  - ${k}`);
    }
    return 0;
  }

  console.error("[TS any 守卫] ❌ 显式 any 类型注解回潮（只减不增）：");
  if (totalRose) {
    console.error(
      `  - 总数回潮：已有文件实测 ${measuredExistingTotal} > 冻结总数 ${frozenTotal}`,
    );
  }
  for (const v of violations) {
    if (v.kind === "GROW") {
      console.error(
        `  - ${v.key}: ${v.n} 处 any（基线 ${v.b}，+${v.n - v.b}）`,
      );
    } else {
      console.error(
        `  - ${v.key}: 新文件 ${v.n} 处 any，超过新增文件上限 ${NEW_FILE_ANY_LIMIT}`,
      );
    }
  }
  console.error(
    "\n  修法：把新增的 any 换成具体类型 / unknown；新文件确需 any 时先压到上限内，\n" +
      "        并在同 PR 用 --write 纳入基线。存量每消掉一处就用 --write 收紧一次。",
  );
  return 1;
}

// ── CLI ─────────────────────────────────────────────────────────────────────
/**
 * @param {string[]} argv CLI 参数
 * @param {{ astOk?: boolean }} [opts] 仅供回归网注入依赖可用性（模拟「无 AST 依赖」）。
 */
export function main(argv = [], opts = {}) {
  const astOk = opts.astOk ?? AST_OK;
  const report = argv.includes("--report");
  const write = argv.includes("--write");
  const unknown = argv.filter(
    (a) => a.startsWith("-") && a !== "--report" && a !== "--write",
  );
  if (unknown.length) {
    console.error(
      `[TS any 守卫] ❌ 未知参数：${unknown.join(" ")}（只认 --report / --write）`,
    );
    return 2;
  }

  if (!astOk) {
    console.error(
      "[TS any 守卫] ❌ 拿不到可信输入：typescript / @vue/compiler-sfc 不可用 → 判 exit 2，不产出结论。\n" +
        "  正式判据只在装了前端依赖的环境跑：CI 的 frontend job；本地请设 NODE_PATH 指向\n" +
        "  frontend/node_modules，或在 worktree 的 frontend 下建 node_modules junction。\n" +
        "  --report / --write 同样拒绝：不得拿降级口径的数字回写、洗掉正式基线。\n" +
        "  实测证据：AST 口径 540 处 any，依赖缺失时的降级正则只有 539 处（少数 1 处，\n" +
        "  且对 composables/usePositionSubmit.ts 数出 2 而非 3），口径不同却与同一份\n" +
        "  AST 基线比对并宣布通过 = 假绿，故此处显式失败。降级计数函数仅作解析层测试。",
    );
    return 2;
  }

  let counts;
  try {
    counts = collectCounts();
  } catch (e) {
    console.error(
      `[TS any 守卫] ❌ 拿不到可信输入：源文件读取 / AST 解析失败（${e.message}）→ 判 exit 2，不用降级口径出结论`,
    );
    return 2;
  }
  if (counts === null) {
    console.error(
      `[TS any 守卫] ❌ 拿不到输入：未在 ${SRC} 扫到任何 .ts / .vue 文件 —— 本轮结论不可信，不得当成通过`,
    );
    return 2;
  }

  if (write) {
    const prev = loadBaseline(BASELINE_PATH, true);
    if (prev === null) return 2;
    // 首次全量冻结（基线本来不存在）：那批全是存量，不套「新增文件上限」——
    // 否则一个 10 处 any 的历史文件就会让基线永远生成不出来。
    const isFirstWrite = prev.missing === true;
    const raised = Object.keys(counts).filter(
      (k) => k in prev.files && counts[k] > prev.files[k],
    );
    const overNew = isFirstWrite
      ? []
      : Object.keys(counts).filter(
          (k) => !(k in prev.files) && counts[k] > NEW_FILE_ANY_LIMIT,
        );
    if (raised.length || overNew.length) {
      console.error(
        "[TS any 守卫] ❌ 拒绝 --write：先修代码，不要用回写洗掉回潮 / 放宽上限。",
      );
      for (const k of raised) {
        console.error(`  - 已有文件回潮 ${k}: ${prev.files[k]} → ${counts[k]}`);
      }
      for (const k of overNew) {
        console.error(
          `  - 新文件超上限 ${k}: ${counts[k]} > ${NEW_FILE_ANY_LIMIT}`,
        );
      }
      return 1;
    }
    const payload = buildBaseline(counts);
    try {
      writeFileSync(
        BASELINE_PATH,
        `${JSON.stringify(payload, null, 2)}\n`,
        "utf8",
      );
    } catch (e) {
      console.error(`[TS any 守卫] ❌ 写基线失败：${e.message}`);
      return 2;
    }
    console.log(
      `[TS any 守卫] 基线已写入 ${BASELINE_PATH}（${Object.keys(counts).length} 个文件 / any 总数 ${sumValues(counts)}；只减不增）`,
    );
    return 0;
  }

  if (report) {
    console.log(JSON.stringify(buildBaseline(counts), null, 2));
    return 0;
  }

  const baseline = loadBaseline(BASELINE_PATH, false);
  if (baseline === null) return 2;
  return compareToBaseline(counts, baseline.files);
}

// Windows 下 import.meta.url 与 process.argv[1] 的斜杠数不一致，必须用 pathToFileURL
// 比较，否则守卫会静默不执行、exit 0（假绿灯）。
if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  process.exit(main(process.argv.slice(2)));
}
