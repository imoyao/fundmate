/**
 * #2050 回归探针：静态判定 OverviewSummaryCard 与 PnlCalendar 的契约是否对齐。
 *
 * 背景（实测）：`3eddf7f7f`（恢复 #2034 口径 tooltip 的提交）在解决同步合并冲突时
 * 取了较旧一侧，把宿主从 `<PnlCalendar host-header />` 改回 `<PnlCalendar hide-title />`。
 * 而 `hideTitle` 这个 prop 在 #2050 里已被删除 —— 它只落成 DOM 上的 `hidetitle=""`，
 * 组件走 `hostHeader=false` 默认分支，把完整 SectionHeader（标题 + ⓘ + 控件排）重画一遍。
 *
 * 判据：props 声明来自**组件源码**，不是记忆或注释。
 */
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..", "..");
const HOST =
  path.join(
    ROOT,
    "frontend/src/views/asset/panorama/components/OverviewSummaryCard.vue"
  );
const CAL =
  path.join(ROOT, "frontend/src/components/PnlCalendar/index.vue");

const host = fs.readFileSync(HOST, "utf8");
const cal = fs.readFileSync(CAL, "utf8");

let failed = 0;
function check(name, ok, detail) {
  if (ok) {
    console.log(`  PASS  ${name}`);
  } else {
    failed++;
    console.log(`  FAIL  ${name}${detail ? " :: " + detail : ""}`);
  }
}

// ---- 组件真实 props（判据的真相源）----
const propsBlock = cal.match(/defineProps<\{([\s\S]*?)\}>\(\)/);
if (!propsBlock) {
  console.error("无法从 PnlCalendar/index.vue 解析 defineProps");
  process.exit(1);
}
const declaredProps = new Set(
  [...propsBlock[1].matchAll(/^\s{4}([a-zA-Z][a-zA-Z0-9]*)\??:/gm)].map(
    (m) => m[1]
  )
);
console.log(`组件真实 props = [${[...declaredProps].join(", ")}]`);
console.log("");

// ---- 断言 1：宿主不得再传已删除的 hideTitle ----
check(
  "宿主不传已删除的 hide-title（#2050 回归根因）",
  !/<PnlCalendar[^>]*\bhide-title\b/.test(host),
  "命中 hide-title —— 该 prop 已从组件删除，只会成为 DOM 属性"
);

// ---- 断言 2：组件不声明 hideTitle ----
check(
  "PnlCalendar 不再声明 hideTitle prop",
  !declaredProps.has("hideTitle"),
  "组件里仍有 hideTitle，说明约定不一致"
);

// ---- 断言 3：宿主必须传 host-header ----
check(
  "宿主传 host-header（标题行交给宿主）",
  /<PnlCalendar[^>]*\bhost-header\b/.test(host)
);

// ---- 断言 4：PnlCalendarCaliberIcon 必须被 import 且被使用 ----
check(
  "宿主 import 了 PnlCalendarCaliberIcon",
  /import\s+PnlCalendarCaliberIcon\s+from/.test(host)
);
check(
  "宿主在标题行里渲染了 PnlCalendarCaliberIcon（ⓘ 与标题同行）",
  /<PnlCalendarCaliberIcon\b/.test(host)
);

// ---- 断言 5：ⓘ 必须在标题容器内，不能是 h3 的兄弟块级元素 ----
const titleGroup = host.match(
  /<div class="flex items-center gap-1\.5">([\s\S]*?)<\/div>\s*<!--/
);
check(
  "ⓘ 位于标题容器 .flex.items-center 内部（与 h3 同一行）",
  !!titleGroup && /PnlCalendarCaliberIcon/.test(titleGroup[1]),
  "未能在标题容器内找到 CaliberIcon"
);

// ---- 断言 6：反向验证 —— 若把 host-header 退回 hide-title，本探针必须变红 ----
{
  const sabotaged = host.replace(
    /<PnlCalendar[^>]*\bhost-header\b/,
    "<PnlCalendar hide-title"
  );
  const detected = /<PnlCalendar[^>]*\bhide-title\b/.test(sabotaged);
  check(
    "反向验证：还原成 hide-title 时断言 1 会命中（探针非恒真空过）",
    detected
  );
}

console.log("");
if (failed) {
  console.log(`发现 ${failed} 处问题`);
  process.exit(1);
}
console.log("全部通过");
