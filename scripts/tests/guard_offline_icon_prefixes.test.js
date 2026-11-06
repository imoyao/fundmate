/**
 * `scripts/guard_offline_icon_prefixes.mjs` 的回归网（#2937）。
 *
 * ## WHY 有这份文件
 *
 * 这条守卫要拦的缺陷**本来就不会报错**：离线图标集里没有的名字，渲染成一个空注释
 * 节点 `<!---->`——不抛异常、不警告、类型检查全绿。所以「写完之后真能拦住吗」
 * 只能靠变异探针回答，靠看代码看不出来。
 *
 * 本文件钉五类证据：
 *
 * 1. **真实仓库跑绿**：存量 100+ 处 `ep:*` 不被误伤（误伤一次，守卫就会被绕过）；
 * 2. **零误报的关键形态**：`import { Icon as IconifyIconOffline } from "@iconify/vue"`
 *    这种「在线组件套离线名字」的别名，仓里有 4 处（ImageUploader / profile ×3 /
 *    watchlist columnRenderers）。按名字判会全部报红，故必须有一条用例钉住它**不报**。
 * 3. **变异探针真红**：静态属性、`:icon` 绑定字面量、三元里的分支、`h()` 渲染函数
 *    四种写法各一条，全部 exit 1；
 * 4. **注释不是注册**：`// addCollection(riIcons)` 躺在真实文件第 8 行，`ri` 必须仍算未注册；
 * 5. **失败态**：注册文件缺失 / 注册集合为空 / 全仓扫不到任何离线图标 ⇒ exit 2，
 *    **不得**退化成「0 违规」（仓内纪律：空 ≠ 没拿到）。
 */

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const { mkdtempSync, mkdirSync, writeFileSync, rmSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join } = require("node:path");

const repoRoot = join(__dirname, "..", "..");
const script = join(repoRoot, "scripts", "guard_offline_icon_prefixes.mjs");

const REGISTRY_OK = `import { addCollection } from "@iconify/vue/dist/offline";
import { icons as epIcons } from "@iconify-json/ep";

addCollection(epIcons);

// import { icons as riIcons } from "@iconify-json/ri";
// addCollection(riIcons);
`;

/** 在临时目录里造一棵最小的 frontend/src 树 */
function makeRoot(files) {
  const dir = mkdtempSync(join(tmpdir(), "offline-icon-guard-"));
  const regDir = join(dir, "frontend", "src", "components", "ReIcon", "src");
  mkdirSync(regDir, { recursive: true });
  // 注意用 `in` 而不是 `??`：本文件用 null 表示「刻意不建注册文件」，
  // 而 `null ?? X` 会回落成默认值，把「缺失」这条失败态探针变成假绿。
  const hasRegistry = "offlineIcon.ts" in files;
  const registry = hasRegistry ? files["offlineIcon.ts"] : REGISTRY_OK;
  if (registry !== null) writeFileSync(join(regDir, "offlineIcon.ts"), registry, "utf8");
  for (const [rel, content] of Object.entries(files)) {
    if (rel === "offlineIcon.ts") continue;
    const full = join(dir, "frontend", "src", rel);
    mkdirSync(join(full, ".."), { recursive: true });
    writeFileSync(full, content, "utf8");
  }
  return dir;
}

function run(args = []) {
  const r = spawnSync(process.execPath, [script, ...args], { encoding: "utf8" });
  return { code: r.status, out: `${r.stdout || ""}${r.stderr || ""}` };
}

function withRoot(files, fn) {
  const dir = makeRoot(files);
  try {
    fn(dir);
  } finally {
    try {
      rmSync(dir, { recursive: true, force: true });
    } catch {
      // 临时目录清理失败不影响判据；Windows 上偶尔被句柄占用
    }
  }
}

/** 一个走离线通道、带静态 icon 属性的 .vue */
const vue = icon => `<template>
  <div><IconifyIconOffline icon="${icon}" /></div>
</template>
`;

// ── 1. 真实仓库不误伤 ────────────────────────────────────────────────────
test("真实仓库：存量离线图标全部已注册，exit 0", () => {
  const r = run();
  assert.equal(r.code, 0, r.out);
  assert.match(r.out, /OK/);
  // 扫到的处数必须是正数：为 0 说明通道判定已脱节，那时「绿」是假绿
  assert.match(r.out, /（\d+ 处图标引用）/);
});

test("真实仓库：以「在线组件套离线名字」的别名文件不被判红", () => {
  // views/asset/watchlist/columnRenderers.tsx 与 components/ImageUploader/index.vue
  // 都是 `import { Icon as IconifyIconOffline } from "@iconify/vue"` + mdi 图标，
  // 走在线通道、能正常出图。整体 exit 0 已含此证据，此处再钉一次定向探针。
  const r = run();
  assert.equal(r.code, 0, r.out);
  assert.doesNotMatch(r.out, /columnRenderers/);
  assert.doesNotMatch(r.out, /ImageUploader/);
});

// ── 2. 已注册前缀不报 ────────────────────────────────────────────────────
test("ep（已注册）+ 离线组件 ⇒ exit 0", () => {
  withRoot({ "views/a.vue": vue("ep:download") }, dir => {
    const r = run(["--root", dir]);
    assert.equal(r.code, 0, r.out);
  });
});

// ── 3. 四种写法各一条变异探针 ────────────────────────────────────────────
test("探针：静态属性 icon=\"lucide:x\" ⇒ exit 1 并点名 lucide", () => {
  withRoot({ "views/a.vue": vue("lucide:cloud-upload") }, dir => {
    const r = run(["--root", dir]);
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /lucide/);
    assert.match(r.out, /a\.vue:2/);
  });
});

test("探针：`:icon=\"'mdi:pin'\"` 绑定字面量 ⇒ exit 1", () => {
  const content = `<template>
  <div><IconifyIconOffline :icon="'mdi:pin'" /></div>
</template>
`;
  withRoot({ "views/b.vue": content }, dir => {
    const r = run(["--root", dir]);
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /mdi/);
  });
});

test("探针：三元里两个分支只坏一个 ⇒ exit 1（不能只看第一个）", () => {
  const content = `<template>
  <div><IconifyIconOffline :icon="ok ? 'ep:star' : 'ri:star-line'" /></div>
</template>
`;
  withRoot({ "views/c.vue": content }, dir => {
    const r = run(["--root", dir]);
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /ri/);
  });
});

test("探针：h(OfflineComp, { icon: \"lucide:x\" }) 渲染函数写法 ⇒ exit 1", () => {
  const content = `import { Icon as IconifyIconOffline } from "@iconify/vue/dist/offline";
import { h } from "vue";

export const render = () =>
  h(IconifyIconOffline, { icon: "lucide:check", class: "x" });
`;
  withRoot({ "views/d.ts": content }, dir => {
    const r = run(["--root", dir]);
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /lucide/);
  });
});

// ── 4. 别名：在线通道套离线名字，必须不报 ────────────────────────────────
test("不该报：在线 Icon 别名为 IconifyIconOffline 时 mdi 图标通过", () => {
  const content = `<template>
  <div><IconifyIconOffline icon="mdi:cloud-upload-outline" /></div>
</template>

<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";
</script>
`;
  withRoot({ "views/e.vue": content }, dir => {
    const r = run(["--root", dir]);
    // 该文件一处离线图标都没有 ⇒ 触发「模型脱节」失败态（exit 2）才是正确结论，
    // 绝不能是「exit 0 但有违规漏检」或「exit 1 误报在线通道」。
    assert.equal(r.code, 2, r.out);
    assert.match(r.out, /结论不可信/);
  });
});

test("不该报：同一文件里在线别名 + 一处真离线 ep ⇒ 绿，且只数 1 处", () => {
  const content = `<template>
  <div>
    <IconifyOnline icon="mdi:pin" />
    <IconifyIconOffline icon="ep:star" />
  </div>
</template>

<script setup lang="ts">
import { Icon as IconifyOnline } from "@iconify/vue";
</script>
`;
  withRoot({ "views/f.vue": content }, dir => {
    const r = run(["--root", dir]);
    assert.equal(r.code, 0, r.out);
    assert.match(r.out, /（1 处图标引用）/);
  });
});

// ── 5. 注释掉的 addCollection 不是注册 ───────────────────────────────────
test("注释不是注册：注册表里 ri 被注释掉，ri:search-line ⇒ exit 1", () => {
  withRoot({ "views/g.vue": vue("ri:search-line") }, dir => {
    const r = run(["--root", dir]);
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /「ri」/);
  });
});

test("同名注册上之后即通过：把 ri 的 addCollection 打开 ⇒ exit 0", () => {
  const registry = `import { addCollection } from "@iconify/vue/dist/offline";
import { icons as epIcons } from "@iconify-json/ep";
import { icons as riIcons } from "@iconify-json/ri";

addCollection(epIcons);
addCollection(riIcons);
`;
  withRoot({ "offlineIcon.ts": registry, "views/h.vue": vue("ri:search-line") }, dir => {
    const r = run(["--root", dir]);
    assert.equal(r.code, 0, r.out);
  });
});

// ── 6. 失败态 ────────────────────────────────────────────────────────────
test("注册文件缺失 ⇒ exit 2", () => {
  withRoot({ "offlineIcon.ts": null, "views/a.vue": vue("ep:download") }, dir => {
    const r = run(["--root", dir]);
    assert.equal(r.code, 2, r.out);
    assert.match(r.out, /结论不可信/);
  });
});

test("注册集合解析为空 ⇒ exit 2（不得当成「没有违规」）", () => {
  const registry = `import { addCollection } from "@iconify/vue/dist/offline";
// 只注册了离散图标，没有集合
addIcon("logo", { body: "<path/>" });
`;
  withRoot({ "offlineIcon.ts": registry, "views/a.vue": vue("ep:download") }, dir => {
    const r = run(["--root", dir]);
    assert.equal(r.code, 2, r.out);
  });
});

test("全仓扫不到离线图标 ⇒ exit 2（模型脱节时「0 违规」不可信）", () => {
  withRoot({ "views/a.vue": "<template><div>纯文本</div></template>\n" }, dir => {
    const r = run(["--root", dir]);
    assert.equal(r.code, 2, r.out);
    assert.match(r.out, /脱节|不可信/);
  });
});

test("--report 模式：有违规也只报告，退出码 0", () => {
  withRoot({ "views/a.vue": vue("lucide:x") }, dir => {
    const r = run(["--root", dir, "--report"]);
    assert.equal(r.code, 0, r.out);
    assert.match(r.out, /发现 1 处/);
  });
});
