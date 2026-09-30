#!/usr/bin/env node
/**
 * 守卫：路由死链 —— `to="/xxx"`、`router.push("/xxx")`、`{ name: "Xxx" }` 指向不存在的路由。
 *
 * WHY
 * ---
 * `docs/design/welcome-greeting-spec.md` 自 v1.2 起把首页空状态 CTA 写成
 * `to="/asset/entry"`，而全仓**从来没有**这条路由（`router/modules/*.ts` 里查无此项）。
 * 后果非常安静：点击**毫无反应、控制台不报错、构建照绿、typecheck 照绿**——
 * 因为 `vue-router` 收到一个「没匹配上任何记录」的字符串 path 时只是导航失败，
 * 不会抛异常；`tsc` 更无从知道这个字符串是不是路由。
 * 于是这个死链从 v1.2（2026-08-10）一直活到 #936（2026-09-29），近 7 周无人发现，
 * 还是靠人肉点页面才暴露。
 *
 * 散文规范拦不住这类问题（`welcome-greeting-spec.md` 甚至**明确写了**跳转目标），
 * 唯一可靠的办法是把「路由表」当成事实来源做静态比对 —— 本守卫就做这件事。
 *
 * 判定规则
 * --------
 * 1. `RULE path` 字面量跳转（`to="/x"` / `to: "/x"` / `router.push("/x")`）是否命中路由表；
 * 2. `RULE name` 命名跳转（同行出现 `to:` 或 `router.push(`/`replace(` 的 `{ name: "X" }`）
 *    是否是路由表里登记过的 name。
 *
 * 路由表来源 = `frontend/src/router/modules/*.ts` 的 `path:` / `name:` 字面量。
 * 路由全部用字面量声明（无动态拼装），故静态提取即等价于真实路由表。
 * `path: "investment"` 这类**相对**子路径靠「缩进栈」补全成绝对路径
 * （父级 = 缩进更浅的最近一条），`/asset/investment` 因此也在表内。
 *
 * 刻意不覆盖（避免误报，需要时再扩边）
 * --------------------------------
 * - 模板字符串 / 变量拼接的跳转（`` router.push(`/x/${y}`) ``）—— 动态，无法静态判定；
 * - 跨行写法（`{` 与 `name:` 不在同一行）—— 只会漏报，不会误报；
 * - `redirect: "/x"`（路由模块内部）—— 属路由表自身一致性，另作他论；
 * - `.vue` 的 HTML 注释**已剔除**（注释里举例的 `to="/x"` 不参与判定）。
 *
 * 用法
 * ----
 *     node scripts/check_router_links.mjs
 *
 * 退出码：0 = 通过；1 = 命中死链。
 * 确需例外：在该行加 `router-link-allow` 注释说明理由（与 `guard_segmented.py`
 * 的 `segmented-allow` 同惯例）——不要为了变绿而放宽本脚本的匹配面。
 */

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

/** 仓库根 = 本脚本所在目录（scripts/）的上一级；单测会把脚本复制进临时仓以复用该约定。 */
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ROUTE_DIR = join(ROOT, "frontend", "src", "router", "modules");
const SCAN_DIR = join(ROOT, "frontend", "src");

const ROUTE_SUFFIXES = new Set([".ts"]);
const SCAN_SUFFIXES = new Set([".vue", ".ts", ".tsx", ".js", ".jsx"]);
const SKIP_DIRS = new Set(["node_modules", "dist", ".git"]);

/** 同行豁免标记。 */
const SKIP_MARKER = "router-link-allow";

/* 路由声明必须独占一行且形如 `path: "/x"` —— 本仓 `router/modules/*.ts` 全部如此。 */
const PATH_DECL_RE = /^\s*path:\s*["']([^"']+)["']/;
const NAME_DECL_RE = /^\s*name:\s*["']([^"']+)["']/;

/* 跳转字面量：`to="/x"` / `to: "/x"` / `router.push("/x")` / `router.replace("/x")`。
   刻意要求 `router.` 前缀，避免把数组的 `arr.push("...")` 之类误当路由跳转。 */
const ROUTER_CALL = String.raw`\brouter\s*\.\s*(?:push|replace)\s*\(`;
const PATH_LITERAL_RE = new RegExp(
  String.raw`(?:to\s*[:=]\s*|${ROUTER_CALL}\s*)["'](\/[^"'\s]*)["']`,
  "g"
);
/** 只有当同一行出现跳转上下文时，`name: "X"` 才被当作路由名。 */
const NAME_CTX_RE = new RegExp(String.raw`(?:\bto\s*[:=]|${ROUTER_CALL})`);
const NAME_LITERAL_RE = /\bname\s*:\s*["']([^"'\s]+)["']/g;

function walk(dir, suffixes) {
  const out = [];
  if (!existsSync(dir)) return out;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      out.push(...walk(join(dir, entry.name), suffixes));
      continue;
    }
    const dot = entry.name.lastIndexOf(".");
    if (dot > 0 && suffixes.has(entry.name.slice(dot))) out.push(join(dir, entry.name));
  }
  return out;
}

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * 把路由路径编译成匹配器。
 * 参数段（`:id`）与通配段（`:path(.*)`）分别放宽为「一段」与「任意段」，
 * 这样 `router.push("/asset/ledgers/abc")` 不会因为路由写的是 `/asset/ledgers/:id` 而误报。
 */
function toMatcher(routePath) {
  const src = routePath
    .split("/")
    .map(seg => {
      if (!seg.startsWith(":")) return escapeRegExp(seg);
      return seg.endsWith("(.*)") ? ".*" : "[^/]+";
    })
    .join("/");
  return new RegExp(`^${src}/?$`);
}

function joinRoutePath(parent, child) {
  if (!parent || parent === "/") return `/${child}`;
  return `${parent.replace(/\/+$/, "")}/${child.replace(/^\/+/, "")}`;
}

/** 提取路由表：绝对 path 集合 + name 集合 + 参数化匹配器。 */
function collectRoutes(routeDir = ROUTE_DIR) {
  const paths = new Set(["/"]);
  const names = new Set();

  for (const file of walk(routeDir, ROUTE_SUFFIXES)) {
    let lines;
    try {
      lines = readFileSync(file, "utf8").split(/\r?\n/);
    } catch {
      continue;
    }
    /* 缩进栈：相对子路径要拼上父级，父级 = 缩进更浅的最近一条已声明路由。 */
    const stack = [];
    for (const line of lines) {
      const pathMatch = PATH_DECL_RE.exec(line);
      if (pathMatch) {
        const indent = line.length - line.trimStart().length;
        while (stack.length > 0 && stack[stack.length - 1].indent >= indent) stack.pop();
        const raw = pathMatch[1];
        const full = raw.startsWith("/")
          ? raw
          : joinRoutePath(stack.length > 0 ? stack.at(-1).full : "", raw);
        stack.push({ indent, full });
        paths.add(full);
      }
      const nameMatch = NAME_DECL_RE.exec(line);
      if (nameMatch) names.add(nameMatch[1]);
    }
  }

  return { paths, names, matchers: [...paths].map(toMatcher) };
}

/** 去掉查询串 / hash / 末尾斜杠后比对（路由表里存的是不含查询串的路径）。 */
function isKnownPath(routes, raw) {
  const stripped = raw.split("?")[0].split("#")[0];
  const normalized = stripped.replace(/\/+$/, "") || "/";
  if (routes.paths.has(normalized)) return true;
  return routes.matchers.some(re => re.test(normalized));
}

/** `.vue` 的 HTML 注释按同长度空白剔除，保留行号 —— 注释里举例的跳转不参与判定。 */
function stripHtmlComments(text) {
  return text.replace(/<!--[\s\S]*?-->/g, m => m.replace(/[^\n]/g, " "));
}

/** 扫描单个文件，返回违规项数组。 */
function scanFile(file, routes) {
  let text;
  try {
    text = readFileSync(file, "utf8");
  } catch {
    return [];
  }
  if (file.endsWith(".vue")) text = stripHtmlComments(text);

  const rel = relative(ROOT, file).split(sep).join("/");
  const violations = [];

  text.split(/\r?\n/).forEach((line, index) => {
    if (line.includes(SKIP_MARKER)) return;
    for (const match of line.matchAll(PATH_LITERAL_RE)) {
      if (!isKnownPath(routes, match[1])) {
        violations.push({
          rel,
          line: index + 1,
          rule: "path",
          value: match[1],
          source: line.trim()
        });
      }
    }
    if (NAME_CTX_RE.test(line)) {
      for (const match of line.matchAll(NAME_LITERAL_RE)) {
        if (!routes.names.has(match[1])) {
          violations.push({
            rel,
            line: index + 1,
            rule: "name",
            value: match[1],
            source: line.trim()
          });
        }
      }
    }
  });

  return violations;
}

function main() {
  const routes = collectRoutes();
  if (routes.paths.size <= 1) {
    console.log("OK: 未找到路由表（frontend/src/router/modules 为空），跳过");
    return 0;
  }

  const files = walk(SCAN_DIR, SCAN_SUFFIXES);
  if (files.length === 0) {
    console.log("OK: 未发现待扫描的前端源文件");
    return 0;
  }

  const violations = files.flatMap(file => scanFile(file, routes));

  if (violations.length === 0) {
    console.log(
      `OK: 无路由死链（路由表 ${routes.paths.size} 条 path / ${routes.names.size} 个 name，` +
        `扫描 ${files.length} 个文件）`
    );
    return 0;
  }

  console.error("ERROR: 检测到路由死链（点击无反应，且不会有任何报错）：");
  for (const v of violations.sort((a, b) => a.rel.localeCompare(b.rel) || a.line - b.line)) {
    const label = v.rule === "name" ? `name: "${v.value}"` : `to="${v.value}"`;
    console.error(`  ${v.rel}:${v.line}  [${v.rule}] ${label}`);
    console.error(`        ${v.source}`);
  }
  console.error(
    "\n      路由清单：frontend/src/router/modules/*.ts（`path:` / `name:` 字面量）\n" +
      "      跳转优先用**命名路由** `{ name: \"Xxx\" }`：name 写错时 vue-router 会告警，\n" +
      "      而字符串 path 写错是静默失败（本守卫就是为它准备的）。\n" +
      `      确需例外（如外部链接）：该行加注释 ${SKIP_MARKER} 说明理由。`
  );
  return 1;
}

/* 仅在被直接执行时跑 main；被单测 import 时只导出纯函数。 */
if (process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  process.exit(main());
}
