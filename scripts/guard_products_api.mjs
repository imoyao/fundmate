#!/usr/bin/env node
/**
 * 守卫：产品域 API 的 barrel 纯度与子模块规模（#2878）。
 *
 * `api/products.ts` 曾是 1364 行 / 21 个端点 / 77 个顶层声明的巨型客户端。
 * 拆成 `api/products/*.ts` 后，最容易发生的回潮是「新端点图省事又写回公共入口」——
 * 它不会让任何测试变红（调用点照样编译、URL 照样通），只会让文件重新长回去。
 * 本守卫把「回潮」变成红灯，四条判据：
 *
 *   R1 `products.ts` 除注释/空行外只允许 `export * from "./products/<子域>";`；
 *   R2 每条转发的目标文件必须存在，且目录里的每个子模块都必须被转发（双向）；
 *   R3 barrel 行数 ≤ 30，单个子模块行数 ≤ 500（防止桶里堆注释 / 子模块长成新巨石）；
 *   R4 子模块不得 import 公共入口（会形成循环依赖）。
 *
 * 用法：
 *   node scripts/guard_products_api.mjs                 # CI / 本地校验，退出码 0/1
 *   node scripts/guard_products_api.mjs --report        # 额外打印每个文件行数
 *   node scripts/guard_products_api.mjs --root <dir>    # 合成样例 / 回归网用
 *
 * 退出码：0 = 干净；1 = 违规；2 = 参数错误。
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, "..");

const MAX_BARREL_LINES = 30;
const MAX_MODULE_LINES = 500;
const REEXPORT = /^export \* from "\.\/products\/([A-Za-z0-9_-]+)";$/;

function parseArgs(argv) {
  const out = { root: REPO_ROOT, report: false };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--root") {
      if (!argv[i + 1]) return { error: "--root 缺少参数" };
      out.root = path.resolve(argv[i + 1]);
      i += 1;
    } else if (argv[i] === "--report") {
      out.report = true;
    } else {
      return { error: `未知参数 ${argv[i]}` };
    }
  }
  return out;
}

/** 返回「非注释、非空」的真实代码行：[行号, 文本]。 */
function codeLines(text) {
  const out = [];
  let inBlock = false;
  text.split(/\r?\n/).forEach((line, idx) => {
    const t = line.trim();
    if (inBlock) {
      if (t.includes("*/")) inBlock = false;
      return;
    }
    if (t === "" || t.startsWith("//")) return;
    if (t.startsWith("/*")) {
      if (!t.includes("*/")) inBlock = true;
      return;
    }
    out.push([idx + 1, t]);
  });
  return out;
}

function check(root) {
  const apiDir = path.join(root, "frontend", "src", "api");
  const barrelPath = path.join(apiDir, "products.ts");
  const subDir = path.join(apiDir, "products");
  const problems = [];

  if (!fs.existsSync(barrelPath)) {
    return { problems: ["缺少 frontend/src/api/products.ts"], stats: [] };
  }
  const barrelText = fs.readFileSync(barrelPath, "utf8");
  const barrelLines = barrelText.split(/\r?\n/).length - 1;

  const forwarded = new Set();
  const real = codeLines(barrelText);
  for (const [lineNo, text] of real) {
    const m = REEXPORT.exec(text);
    if (!m) {
      problems.push(
        `R1 products.ts:${lineNo} 不是合法的子域转发（barrel 里出现实现代码）：${text.slice(0, 90)}`
      );
      continue;
    }
    if (forwarded.has(m[1])) {
      problems.push(`R1 products.ts:${lineNo} 重复转发子域 ${m[1]}`);
    }
    forwarded.add(m[1]);
  }
  if (real.length === 0) {
    problems.push("R1 products.ts 没有任何 re-export（公共入口不能是空壳）");
  }
  if (barrelLines > MAX_BARREL_LINES) {
    problems.push(
      `R3 products.ts ${barrelLines} 行 > ${MAX_BARREL_LINES}，注释/转发也不该堆厚`
    );
  }

  const files = fs.existsSync(subDir)
    ? fs.readdirSync(subDir).filter(f => f.endsWith(".ts")).sort()
    : [];
  const stats = [];

  for (const name of forwarded) {
    if (!fs.existsSync(path.join(subDir, `${name}.ts`))) {
      problems.push(`R2 products.ts 转发了不存在的子域模块 products/${name}.ts`);
    }
  }

  for (const file of files) {
    const moduleName = file.slice(0, -3);
    const full = path.join(subDir, file);
    const text = fs.readFileSync(full, "utf8");
    const lines = text.split(/\r?\n/).length - 1;
    stats.push([file, lines]);

    if (!forwarded.has(moduleName)) {
      problems.push(
        `R2 products/${file} 未被 products.ts 转发（搬走了但没接回公共入口）`
      );
    }
    if (lines > MAX_MODULE_LINES) {
      problems.push(
        `R3 products/${file} ${lines} 行 > ${MAX_MODULE_LINES}，请按子域再拆一个模块`
      );
    }
    if (/from\s+["']@\/api\/products["']/.test(text)) {
      problems.push(
        `R4 products/${file} 反向 import 公共入口 @/api/products，会形成循环依赖`
      );
    }
  }

  return { problems, stats, barrelLines, moduleCount: files.length };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.error) {
    console.error(`ERROR: ${args.error}`);
    return 2;
  }
  const { problems, stats, barrelLines, moduleCount } = check(args.root);
  if (args.report) {
    console.log(`products.ts ${barrelLines} 行（barrel）；子域模块 ${moduleCount} 个：`);
    for (const [file, lines] of stats) {
      console.log(`  products/${file.padEnd(18)} ${String(lines).padStart(4)} 行`);
    }
  }
  if (problems.length) {
    console.error("FAIL: 产品域 API 分层被破坏（#2878）：");
    for (const p of problems) console.error(`  - ${p}`);
    console.error(
      "\n修复：把实现写进 frontend/src/api/products/<子域>.ts，products.ts 只保留 export * 转发。"
    );
    return 1;
  }
  console.log(
    `OK: 产品域 API 分层干净（barrel ${barrelLines} 行 / ${moduleCount} 个子域模块，均 ≤ ${MAX_MODULE_LINES} 行）`
  );
  return 0;
}

process.exitCode = main();
