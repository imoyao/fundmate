/**
 * `scripts/check_router_links.mjs` 的回归网（#936）
 *
 * 为什么需要：这个守卫决定 CI 红/绿，而它要抓的恰恰是**最安静的一类缺陷**——
 * `to="/asset/entry"` 这种死链点击无反应、控制台不报错、构建与类型检查全绿
 * （`welcome-greeting-spec.md` 从 v1.2 到 #936 靠人肉点页面才暴露）。
 * 若守卫自己漏报（正则写窄了）或误报（把参数化路由 / 注释里的示例当成死链），
 * 后果是「真死链继续潜伏」或「无辜 PR 被卡红」，两者都没有第二道网兜住。
 *
 * 做法：临时目录造 `scripts/` + `frontend/src/**`（路由表 + 待扫源码），把真脚本
 * 复制进去（脚本以自身位置的上一级为 ROOT），子进程跑真入口，断言退出码与输出。
 * 零新依赖（只用 node:test / node:assert）。
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { mkdtempSync, mkdirSync, writeFileSync, copyFileSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join, dirname } = require("node:path");

const REAL_SCRIPT = join(__dirname, "..", "check_router_links.mjs");

/**
 * 造一个隔离仓：
 *   <tmp>/scripts/check_router_links.mjs
 *   <tmp>/frontend/src/router/modules/<name>.ts    （路由表，键为文件名）
 *   <tmp>/frontend/src/<rel>                       （待扫描的源码，键为相对路径）
 */
function makeRepo({ routes = {}, files = {} } = {}) {
  const root = mkdtempSync(join(tmpdir(), "rlinks-"));
  mkdirSync(join(root, "scripts"), { recursive: true });
  copyFileSync(REAL_SCRIPT, join(root, "scripts", "check_router_links.mjs"));

  const routeDir = join(root, "frontend", "src", "router", "modules");
  mkdirSync(routeDir, { recursive: true });
  for (const [name, content] of Object.entries(routes)) {
    writeFileSync(join(routeDir, name), content);
  }

  for (const [rel, content] of Object.entries(files)) {
    const abs = join(root, "frontend", "src", rel);
    mkdirSync(dirname(abs), { recursive: true });
    writeFileSync(abs, content);
  }
  return root;
}

/** 跑真脚本，返回 { code, out }（不抛异常）。 */
function run(root) {
  try {
    const out = execFileSync(process.execPath, [join(root, "scripts", "check_router_links.mjs")], {
      cwd: root,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"]
    });
    return { code: 0, out };
  } catch (e) {
    return { code: e.status ?? 1, out: `${e.stdout ?? ""}${e.stderr ?? ""}` };
  }
}

/**
 * 一份含「绝对父路径 + 相对子路径 + 参数化子路径」的路由表夹具。
 * 相对子路径 `inventory` 必须靠缩进栈补全成 `/asset/inventory`，
 * 参数化 `ledgers/:id` 必须放宽成「一段」，两者都是易漏报/易误报的边界。
 */
const ROUTE_FIXTURE = {
  "asset.ts": [
    "const assetRoutes = {",
    '  path: "/asset",',
    '  name: "AssetParent",',
    "  children: [",
    "    {",
    '      path: "inventory",',
    '      name: "Inventory",',
    "    },",
    "    {",
    '      path: "ledgers/:id",',
    '      name: "LedgerDetail",',
    "    },",
    "    {",
    '      path: "/investment/manual",',
    '      name: "InvestmentManual",',
    "    },",
    "  ],",
    "};",
    ""
  ].join("\n")
};

/* ── 正向：合法 path / name 不得报错 ─────────────────────────── */
test("正向：绝对 path、相对子路径补全、命名路由全部通过", () => {
  const root = makeRepo({
    routes: ROUTE_FIXTURE,
    files: {
      "views/page.vue": [
        "<template>",
        '  <router-link to="/asset/inventory">全面盘点</router-link>',
        '  <router-link :to="{ name: \'InvestmentManual\' }">手动记账</router-link>',
        "</template>",
        "<script setup lang=\"ts\">",
        "function go() {",
        '  router.push("/investment/manual");',
        "}",
        "</script>",
        ""
      ].join("\n")
    }
  });
  const { code, out } = run(root);
  assert.equal(code, 0, `应通过，实际输出：\n${out}`);
  assert.match(out, /OK: 无路由死链/);
});

/* ── 反向①：字符串 path 死链（#936 的真实形态）────────────────── */
test("反向①：`to=\"/asset/entry\"` 死链必须红灯并给出行号", () => {
  const root = makeRepo({
    routes: ROUTE_FIXTURE,
    files: {
      "views/welcome/components/WelcomeGreeting.vue": [
        "<template>",
        '  <router-link to="/asset/entry">开始记账</router-link>',
        "</template>",
        ""
      ].join("\n")
    }
  });
  const { code, out } = run(root);
  assert.equal(code, 1, `应红灯，实际 exit=${code}\n${out}`);
  assert.match(out, /检测到路由死链/);
  assert.match(out, /\[path\] to="\/asset\/entry"/);
  assert.match(out, /WelcomeGreeting\.vue:2/, "应给出准确行号");
});

/* ── 反向②：命名路由写错 ─────────────────────────────────────── */
test("反向②：`{ name: \"GhostRoute\" }` 未登记必须红灯", () => {
  const root = makeRepo({
    routes: ROUTE_FIXTURE,
    files: {
      "views/a.vue": [
        "<script setup lang=\"ts\">",
        'router.push({ name: "GhostRoute" });',
        "</script>",
        ""
      ].join("\n")
    }
  });
  const { code, out } = run(root);
  assert.equal(code, 1, `应红灯，实际 exit=${code}\n${out}`);
  assert.match(out, /\[name\] name: "GhostRoute"/);
});

/* ── 防误报①：参数化路由带实参跳转 ───────────────────────────── */
test("防误报①：`/asset/ledgers/abc` 命中 `ledgers/:id`，不得误报", () => {
  const root = makeRepo({
    routes: ROUTE_FIXTURE,
    files: {
      "views/b.ts": 'export const go = () => router.push("/asset/ledgers/abc");\n'
    }
  });
  const { code, out } = run(root);
  assert.equal(code, 0, `参数段应放宽匹配，实际 exit=${code}\n${out}`);
  // 注意断言用「检测到路由死链」而非「死链」：通过时的正常输出也含「无路由死链」字样
  assert.ok(!/检测到路由死链/.test(out), `不应出现死链告警：\n${out}`);
});

/* ── 防误报②：查询串 / hash / 尾斜杠归一化 ───────────────────── */
test("防误报②：查询串、hash、尾斜杠归一化后视为同一条路由", () => {
  const root = makeRepo({
    routes: ROUTE_FIXTURE,
    files: {
      "views/c.ts": [
        'router.push("/asset/inventory?tab=all");',
        'router.push("/asset/inventory#top");',
        'router.push("/asset/inventory/");',
        ""
      ].join("\n")
    }
  });
  const { code, out } = run(root);
  assert.equal(code, 0, `归一化后应通过，实际 exit=${code}\n${out}`);
});

/* ── 防误报③：`arr.push("...")` 不是路由跳转 ──────────────────── */
test("防误报③：数组 `arr.push(\"/nope\")` 不得被当作路由跳转", () => {
  const root = makeRepo({
    routes: ROUTE_FIXTURE,
    files: { "views/d.ts": 'const t = [];\nt.push("/totally/not/a/route");\n' }
  });
  const { code, out } = run(root);
  assert.equal(code, 0, `无 router. 前缀不应命中，实际 exit=${code}\n${out}`);
});

/* ── 防误报④：`.vue` 注释里的示例跳转不参与判定 ───────────────── */
test("防误报④：HTML 注释里举例的 `to=\"/dead\"` 不算死链", () => {
  const root = makeRepo({
    routes: ROUTE_FIXTURE,
    files: {
      "views/e.vue": [
        "<template>",
        '  <!-- 历史写法：<router-link to="/asset/entry">，已废弃 -->',
        '  <router-link to="/asset/inventory">OK</router-link>',
        "</template>",
        ""
      ].join("\n")
    }
  });
  const { code, out } = run(root);
  assert.equal(code, 0, `注释应被剔除，实际 exit=${code}\n${out}`);
});

/* ── 防过度抑制：豁免标记必须有效，且只作用于本行 ─────────────── */
test("豁免：`router-link-allow` 只放行本行，其他行照报", () => {
  const root = makeRepo({
    routes: ROUTE_FIXTURE,
    files: {
      "views/f.vue": [
        "<template>",
        '  <!-- router-link-allow: 外部站点，不走 vue-router -->',
        '  <a href="/asset/entry">外部</a>',
        '  <router-link to="/asset/entry">漏网</router-link>',
        "</template>",
        ""
      ].join("\n")
    }
  });
  const { code, out } = run(root);
  // 第三行没有标记，必须仍被报出——证明豁免不是「文件级」开关
  assert.equal(code, 1, `无标记行应被报出，实际 exit=${code}\n${out}`);
  assert.match(out, /e\.vue|f\.vue|:4/, "应报出第 4 行");
});

/* ── 兜底：仓库内不存在路由表时不算失败（避免空仓误红）────────── */
test("兜底：无路由表时不判失败", () => {
  const root = makeRepo({ files: { "views/g.vue": "<template><div/></template>\n" } });
  const { code, out } = run(root);
  assert.equal(code, 0, `空路由表应跳过，实际 exit=${code}\n${out}`);
  assert.match(out, /skip|跳过/);
});
