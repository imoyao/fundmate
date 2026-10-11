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
 *    是否是路由表里登记过的 name；
 * 3. `RULE orphan` **孤儿路由** —— 反向的那半：路由表里有、但 `frontend/src` 全仓
 *    找不到任何指向它的引用，且 `showLink: false`（侧边栏也不出现）。这种路由
 *    **用户永远到不了**，只能手敲 URL 才打得开，是死代码的温床。
 *
 *      为什么补这一条（#1787）：`/inventory/investment/batch`「批量导入」占位页
 *      自 2026-05-23（`b5b0c830d`）创建后**零引用、零改动、零 spec**，12 行「敬请期待」
 *      潜伏了 5 个月。上面两条规则对它**结构性无能为力**——它们只管「指向不存在的路由」，
 *      不管「存在却没人指的路由」。没有这一条，同一个坑随时能再挖一个。
 *
 *      孤儿的判定刻意保守（宁可漏报也不误报，CI 红灯必须可信）：
 *      - 必须**显式** `showLink: false`（缺省或 `true` = 侧边栏可达，直接放行）；
 *      - 带 `children:` 的**结构父路由**放行 —— 它靠子路由被访问，自身无需被直接引用；
 *      - `redirect: "/x"` / `redirect: { name }` 算入链（那是真实可达路径）；
 *      - 只认静态字面量，动态拼接的跳转无法静态判定（与上面两条同一取舍）。
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
 * - `redirect: "/x"` 只作**入链**证据参与孤儿判定，不参与死链判定（另作他论）；
 * - `.vue` 的 HTML 注释**已剔除**（注释里举例的 `to="/x"` 不参与判定）。
 *
 * 用法
 * ----
 *     node scripts/check_router_links.mjs
 *
 * 退出码：0 = 通过；1 = 命中死链或孤儿路由。
 * 确需例外：死链在该行加 `router-link-allow`、孤儿在**该路由块内**任意行加
 * `router-orphan-allow` 并说明理由（与 `guard_segmented.py` 的 `segmented-allow`
 * 同惯例）——不要为了变绿而放宽本脚本的匹配面。
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
/** 孤儿路由豁免标记：写在**该路由块内**任意行，须附保留理由。 */
const ORPHAN_MARKER = "router-orphan-allow";

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
/** 路由模块内部的重定向 —— 算**入链**（那是一条真实可达路径）。 */
const REDIRECT_PATH_RE = /\bredirect\s*:\s*["'](\/[^"'\s]*)["']/g;
const REDIRECT_NAME_RE =
  /\bredirect\s*:\s*\{[^}\n]*\bname\s*:\s*["']([^"'\s]+)["']/g;
/**
 * 对象式导航的 path 字段（`next({ path: "/x" })` / `router.push({ path: "/x" })`）。
 * 只在**非路由模块**里当入链证据 —— 路由模块里的 `path:` 是声明本身，
 * 混进来会让每条路由都「自证被引用」，孤儿判定随之失效。
 * 同样只作入链、不作死链判定（`router/index.ts` 的守卫跳转另作他论）。
 */
const LOOSE_PATH_RE = /\bpath\s*:\s*["'](\/[^"'\s]*)["']/g;
/**
 * 隐藏路由：`showLink: false`。**不加行首锚点** —— 仓库里
 * `meta: { title: "房产", rank: 4, showLink: false }` 这种单行写法真实存在
 * （`asset.ts` 的 `/realestate`），带 `^` 会把它当「侧边栏可见」漏报。
 * 只认显式 false：缺省在 pure-admin 里等于侧边栏可见，不可能是孤儿。
 */
const SHOW_LINK_FALSE_RE = /\bshowLink:\s*false\b/;
/** 结构父路由：靠 `children` 挂子路由，自身无需被直接引用。 */
const CHILDREN_RE = /\bchildren\s*:/;

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

/**
 * 提取路由表：绝对 path 集合 + name 集合 + 参数化匹配器，
 * 外加供孤儿判定用的 `records`（每条路由的块范围元数据）。
 */
function collectRoutes(routeDir = ROUTE_DIR) {
  const paths = new Set(["/"]);
  const names = new Set();
  const records = [];

  for (const file of walk(routeDir, ROUTE_SUFFIXES)) {
    let lines;
    try {
      lines = readFileSync(file, "utf8").split(/\r?\n/);
    } catch {
      continue;
    }
    const rel = relative(ROOT, file).split(sep).join("/");
    /* 缩进栈：相对子路径要拼上父级，父级 = 缩进更浅的最近一条已声明路由。 */
    const stack = [];
    const decls = [];
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
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
        decls.push({ index: i, full, source: line.trim() });
      }
      const nameMatch = NAME_DECL_RE.exec(line);
      if (nameMatch) names.add(nameMatch[1]);
    }

    /* 第二遍：路由块 = 本条 path 声明到下一条 path 声明之间。
       `showLink` / `children` / 豁免标记 / `redirect` 都写在这个块内。 */
    for (let k = 0; k < decls.length; k++) {
      const start = decls[k].index;
      const end = k + 1 < decls.length ? decls[k + 1].index : lines.length;
      const block = lines.slice(start, end);
      const nameDecl = block.find(l => NAME_DECL_RE.test(l));
      records.push({
        rel,
        line: start + 1,
        full: decls[k].full,
        source: decls[k].source,
        name: nameDecl ? NAME_DECL_RE.exec(nameDecl)[1] : null,
        /* 只认显式 showLink:false —— 缺省在 pure-admin 里等于侧边栏可见。 */
        hidden: block.some(l => SHOW_LINK_FALSE_RE.test(l)),
        structural: block.some(l => CHILDREN_RE.test(l)),
        exempt: block.some(l => l.includes(ORPHAN_MARKER))
      });
    }
  }

  return { paths, names, matchers: [...paths].map(toMatcher), records };
}

/** 去掉查询串 / hash / 末尾斜杠后归一（路由表里存的是不含查询串的路径）。 */
function normalizePath(raw) {
  const stripped = raw.split("?")[0].split("#")[0];
  return stripped.replace(/\/+$/, "") || "/";
}

/** 归一后的引用是否命中路由表（精确 path 或参数化匹配器）。 */
function isKnownPath(routes, raw) {
  const value = normalizePath(raw);
  if (routes.paths.has(value)) return true;
  return routes.matchers.some(re => re.test(value));
}

/** `.vue` 的 HTML 注释按同长度空白剔除，保留行号 —— 注释里举例的跳转不参与判定。 */
function stripHtmlComments(text) {
  return text.replace(/<!--[\s\S]*?-->/g, m => m.replace(/[^\n]/g, " "));
}

/** 扫描单个文件，返回违规项数组；同时把**入链证据**累加进 `refs`（供孤儿判定）。 */
function scanFile(file, routes, refs) {
  let text;
  try {
    text = readFileSync(file, "utf8");
  } catch {
    return [];
  }
  if (file.endsWith(".vue")) text = stripHtmlComments(text);

  const rel = relative(ROOT, file).split(sep).join("/");
  /* 路由模块里的 `name:` 是**声明**，不能当入链；其它文件里的 `name:` 一律算入链
     （含跨行 `router.push({\n name: ...\n})` 与 `defineOptions({ name })`）——
     宁可因此漏报几个孤儿，也不让守卫误红。 */
  const isRouteModule = rel.startsWith("frontend/src/router/modules/");
  const violations = [];

  text.split(/\r?\n/).forEach((line, index) => {
    if (line.includes(SKIP_MARKER)) return;
    for (const match of line.matchAll(PATH_LITERAL_RE)) {
      refs.paths.add(normalizePath(match[1]));
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
    /* `name:` 字面量：入链证据 + 死链判定。
       路由模块里的 `name:` 是**声明**（只有同行走跳转上下文时才算引用），
       其它文件里的一律算入链 —— 这样跨行 `router.push({\n name: ...\n})`
       与 `defineOptions({ name })` 都不会造成误红；宁可漏报几个孤儿。 */
    for (const match of line.matchAll(NAME_LITERAL_RE)) {
      const hasCtx = NAME_CTX_RE.test(line);
      if (hasCtx || !isRouteModule) refs.names.add(match[1]);
      if (hasCtx && !routes.names.has(match[1])) {
        violations.push({
          rel,
          line: index + 1,
          rule: "name",
          value: match[1],
          source: line.trim()
        });
      }
    }
    if (!isRouteModule) {
      /* 对象式导航 + 白名单/配置里的 path —— 只作入链证据，不参与死链判定。 */
      for (const match of line.matchAll(LOOSE_PATH_RE))
        refs.paths.add(normalizePath(match[1]));
    }
    /* `redirect:` 只作入链证据，不参与死链判定（见文首「刻意不覆盖」）。 */
    for (const match of line.matchAll(REDIRECT_PATH_RE))
      refs.paths.add(normalizePath(match[1]));
    for (const match of line.matchAll(REDIRECT_NAME_RE)) refs.names.add(match[1]);
  });

  return violations;
}

/**
 * 孤儿路由：显式 `showLink: false` + 全仓零入链 + 非结构父路由 + 无豁免标记。
 * 判定保守（见文首「孤儿的判定刻意保守」），四条缺一不可。
 */
function findOrphans(routes, refs) {
  return routes.records.filter(r => {
    if (r.exempt || !r.hidden || r.structural) return false;
    if (r.name && refs.names.has(r.name)) return false;
    const re = toMatcher(r.full);
    return ![...refs.paths].some(p => re.test(p));
  });
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

  /* 入链证据与死链违规一次扫描拿全 —— 孤儿判定要用前者，别再扫第二遍。 */
  const refs = { paths: new Set(), names: new Set() };
  const violations = files.flatMap(file => scanFile(file, routes, refs));
  const orphans = findOrphans(routes, refs);

  if (violations.length === 0 && orphans.length === 0) {
    console.log(
      `OK: 无路由死链，亦无孤儿路由（路由表 ${routes.paths.size} 条 path / ` +
        `${routes.names.size} 个 name，扫描 ${files.length} 个文件）`
    );
    return 0;
  }

  if (violations.length > 0) {
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
  }

  if (orphans.length > 0) {
    if (violations.length > 0) console.error("");
    console.error("ERROR: 检测到孤儿路由（路由表里有，但用户永远到不了）：");
    for (const r of orphans.sort(
      (a, b) => a.rel.localeCompare(b.rel) || a.line - b.line
    )) {
      const who = r.name ? `（name: ${r.name}）` : "";
      console.error(`  ${r.rel}:${r.line}  [orphan] ${r.source}`);
      console.error(
        `        ${r.full}${who} 在 frontend/src 内零入链，且 showLink:false 不进侧边栏 —— 只能手敲 URL 才打得开。`
      );
    }
    console.error(
      "\n      两条路选一条：删掉它（死代码 / 从未交付的占位页），\n" +
        `      或在该路由块内任意行加注释 ${ORPHAN_MARKER}: 保留理由（如动态跳转、外部深链）。\n` +
        "      侧边栏可见（`showLink` 缺省或为 true）、带 children 的结构父路由不会被判孤儿。"
    );
  }

  return 1;
}

/* 仅在被直接执行时跑 main；被单测 import 时只导出纯函数。 */
if (process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  process.exit(main());
}
