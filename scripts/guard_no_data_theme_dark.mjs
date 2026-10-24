#!/usr/bin/env node
/**
 * 暗色模式死选择器守卫：拦截「把 data-theme 属性等于 dark 当暗色开关」的选择器。
 *
 * WHY（本条来自一次真实的死代码清理）：
 *   本仓的暗色由 **`<html>` 上的 `.dark` 类**驱动（`useDataThemeChange.ts` 的
 *   `classList.add("dark")`），暗色变量由 `dark.scss` 的 `:root.dark` 块覆盖同名
 *   CSS 变量。而 `data-theme` 属性承载的是**配色主题名**
 *   （light / default / saucePurple / pink / dusk / volcano / mingQing / auroraGreen
 *   / showbuy），**永远不会是 `dark`**。
 *
 *   于是 `[data-theme="dark"]` 这类选择器**一次都不会命中**：不报错、构建绿、
 *   类型检查绿、走查时也看不出问题（因为暗色本来就由变量覆盖生效），唯一后果是
 *   让下一个读代码的人以为「暗色有独立分支」，照着它继续写。
 *   `MoneyDisplay` / `RiseFallText` 就各躺了两块这样的死选择器（已删）。
 *
 * 判据（机械，不看写法只看事实）：
 *   扫描 `frontend/src/**` 下的 .vue / .ts / .scss / .css，命中属性选择器
 *   `[data-theme="dark"]`（双引号 / 单引号 / 不加引号三种写法，属性名与取值
 *   之间的空白随意，取值大小写不敏感）即判红，逐条打印 `file:line`。
 *
 * 本判据**不**覆盖的形态（刻意，避免误伤）：
 *   - 正经的配色主题选择器（如 `html[data-theme="showbuy"]`、`:root.dark[data-theme="showbuy"]`）；
 *   - 文档（`frontend/design*.md`）里的历史沿革叙述——那里需要讲清「为什么不能这么写」，
 *     判据只扫源码；文档口径由 `design.dark.md` 的「机制说明」一节承载。
 *
 * 白名单：只允许**单值精确路径**（相对仓库根、正斜杠）。禁止通配符与目录——
 *   按目录开口子等于把判据作废，而这类死选择器的成因正是「局部照抄」。
 *   当前为空：四处存量已在本轮删除，没有需要豁免的。
 *
 * 失败态（AGENTS.md「判据必须有失败态」）：
 *   扫不到任何文件（路径写错 / glob 失效 / 目录不存在 / 文件读不了）一律 **exit 2**
 *   并明说「拿不到输入，结论不可信」，**绝不**退化成「零命中 = 通过」——
 *   那一半是假绿，比红灯贵。
 *
 * 退出码：0 干净 / 1 命中死选择器 / 2 拿不到输入（结论不可信）。
 * 回归网：scripts/tests/guard_no_data_theme_dark.test.js（真实扫描 + 注入探针 + 失败态探针）。
 */
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_SCAN_ROOT = join(ROOT, "frontend", "src");

/** 扫描范围：只扫源码。文档（design.dark.md）要讲历史，不在判据内。 */
const EXTS = new Set([".vue", ".ts", ".scss", ".css"]);
const SKIP_DIRS = new Set(["node_modules", "dist", ".git", "coverage"]);

/**
 * 白名单：**单值精确路径**（相对仓库根、正斜杠），不接受通配符、不接受目录。
 * 加条目前先问一句：这条路径里真的必须写死那个选择器吗？
 */
const ALLOW_FILES = new Set([]);

/**
 * 默认扫描根下必须存在的哨兵文件。它同时是「路径没写错」的自证：
 * 目录还在、扩展名集合没被改坏，就一定扫得到它；扫不到说明判据的输入坏了。
 */
const SENTINEL = join("frontend", "src", "style", "colors.css");

// 属性选择器 `[data-theme="dark"]`：双引号 / 单引号 / 无引号三种写法都收，
// `=` 两侧与 `]` 前的空白随意，取值大小写不敏感（`Dark` 同样是错的）。
const DEAD_RE = /\[\s*data-theme\s*=\s*(?:"dark"|'dark'|dark)\s*\]/gi;

/** 参数解析：只认 `--root <dir>`（供回归网喂临时副本）与 `--help`。 */
function parseArgs(argv) {
  const opts = { root: null, help: false };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--help" || a === "-h") opts.help = true;
    else if (a === "--root") {
      const v = argv[i + 1];
      if (!v) throw new Error("--root 后面必须跟目录");
      opts.root = v;
      i += 1;
    } else throw new Error(`未知参数：${a}`);
  }
  return opts;
}

/** 递归收集待扫文件；读目录失败即抛出（失败态由 main 统一处理）。 */
function walk(dir, out) {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, out);
    else if (EXTS.has(extname(p))) out.push(p);
  }
  return out;
}

/** 扫描结果里命中的行号（1-based）与其原文，供报告定位。 */
function scanFile(file) {
  const text = readFileSync(file, "utf8");
  const hits = [];
  text.split(/\r?\n/).forEach((line, idx) => {
    DEAD_RE.lastIndex = 0;
    if (DEAD_RE.test(line)) hits.push({ line: idx + 1, text: line.trim() });
  });
  return hits;
}

function displayPath(file, scanRoot) {
  const fromRoot = relative(ROOT, file).replace(/\\/g, "/");
  // 临时目录（回归网喂的副本）落在仓库外，按扫描根给相对路径更好读
  return fromRoot.startsWith("..") ? relative(scanRoot, file).replace(/\\/g, "/") : fromRoot;
}

function main() {
  let opts;
  try {
    opts = parseArgs(process.argv.slice(2));
  } catch (err) {
    console.error(`✗ 参数错误：${err.message}`);
    console.error("  拿不到输入，结论不可信。");
    return 2;
  }

  if (opts.help) {
    console.log("用法：node scripts/guard_no_data_theme_dark.mjs [--root <目录>]");
    return 0;
  }

  const scanRoot = opts.root ? resolve(opts.root) : DEFAULT_SCAN_ROOT;

  // ── 失败态一：目录不存在 / 不是目录 ──────────────────────────────
  if (!existsSync(scanRoot) || !statSync(scanRoot).isDirectory()) {
    console.error(`✗ 扫描根不存在或不是目录：${scanRoot}`);
    console.error("  拿不到输入，结论不可信（这不是「零命中」）。");
    return 2;
  }
  // ── 失败态二：默认扫描根下哨兵文件缺失（路径/扩展名被改坏的信号）──
  if (!opts.root && !existsSync(join(ROOT, SENTINEL))) {
    console.error(`✗ 哨兵文件缺失：${SENTINEL}`);
    console.error("  扫描范围疑似写错（frontend/src 被移动 / 扩展名集合被改坏），拿不到输入，结论不可信。");
    return 2;
  }

  // ── 白名单自检：只允许单值精确路径 ──────────────────────────────
  for (const entry of ALLOW_FILES) {
    const normalized = entry.replace(/\\/g, "/");
    if (/[*?[\]]/.test(normalized) || normalized.endsWith("/")) {
      console.error(`✗ 白名单条目不得是通配符或目录：${entry}`);
      console.error("  白名单只允许单值精确路径（相对仓库根）——按目录开口子等于把判据作废。");
      return 2;
    }
  }

  let files;
  try {
    files = walk(scanRoot, []);
  } catch (err) {
    console.error(`✗ 遍历扫描根失败：${err.message}`);
    console.error("  拿不到输入，结论不可信。");
    return 2;
  }

  // ── 失败态三：一个文件都没扫到（glob 失效最常见的长相）───────────
  if (files.length === 0) {
    console.error(`✗ 在 ${scanRoot} 下没有扫到任何 .vue/.ts/.scss/.css 文件`);
    console.error("  拿不到输入，结论不可信（这不是「零命中 = 通过」）。");
    return 2;
  }

  const hits = [];
  const unreadable = [];
  for (const file of files) {
    const display = displayPath(file, scanRoot);
    if (ALLOW_FILES.has(relative(ROOT, file).replace(/\\/g, "/"))) continue;
    try {
      for (const h of scanFile(file)) hits.push({ file: display, ...h });
    } catch (err) {
      unreadable.push(`${display}（${err.message}）`);
    }
  }

  // ── 失败态四：有文件读不了 ⇒ 结论不完整，照样不许报绿 ─────────────
  if (unreadable.length > 0) {
    console.error(`✗ 有 ${unreadable.length} 个文件读不了，结论不完整：`);
    for (const u of unreadable.slice(0, 10)) console.error(`    ${u}`);
    console.error("  拿不到输入，结论不可信。");
    return 2;
  }

  if (hits.length > 0) {
    console.error(
      `✗ 发现 ${hits.length} 处「data-theme 等于 dark」死选择器（data-theme 只承载配色主题名，永远不会是 dark）：\n`
    );
    for (const h of hits) console.error(`  ${h.file}:${h.line}  ${h.text}`);
    console.error(
      "\n改法：暗色走 `<html>` 上的 .dark 类——暗色变量由 dark.scss 的 `:root.dark` 覆盖同名令牌，" +
        "\n组件只引用语义变量（如 --color-rise-ink / --color-fall-ink），不写任何主题判断。" +
        "\n若确属有意为之，先把它加进本脚本的 ALLOW_FILES（只允许单值精确路径）并说明理由。"
    );
    return 1;
  }

  console.log(
    `✓ 未发现 data-theme=dark 死选择器（扫描 ${files.length} 个文件：` +
      `${relative(ROOT, scanRoot).replace(/\\/g, "/")}）。`
  );
  return 0;
}

process.exit(main());
