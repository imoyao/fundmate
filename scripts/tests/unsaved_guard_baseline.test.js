/**
 * 未保存守卫的基线语义（#1845 回归钉死）。
 *
 * 回归本身只有一行「基线为 null 时不算脏」，但它是**用户可见的骚扰**：
 * 取错基线 → 弹窗没打开就算「有未保存修改」→ 叠上 onBeforeRouteLeave，
 * 用户在账户列表点一张卡片都被问「确定放弃吗？」。
 *
 * 抽成纯函数就是为了能在这里断言 —— composable 本身依赖 vue / vue-router / element-plus，
 * node:test 环境解析不了那条 ESM 依赖链。故这里读源码文本做等价实现，
 * 并用第一条用例把两者钉在一起（实现改了而测试没改，第一条会失败）。
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/** 去掉注释再匹配——否则文档里写「旧写法是 ref("")」这类说明会被当成代码（今天已被咬第三次）。 */
function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

const SRC_RAW = readFileSync(
  join(process.cwd(), "frontend", "src", "composables", "useUnsavedChangesGuard.ts"),
  "utf8"
);
const SRC = stripComments(SRC_RAW);

/** 与源码 isFormDirtyJson 保持一致的实现 */
function isFormDirtyJson(baseline, currentJson) {
  if (baseline === null) return false;
  return currentJson !== baseline;
}

test("源码里确实有「基线为 null 视为不脏」这行（防实现与测试漂移）", () => {
  assert.match(SRC, /if \(baseline === null\) return false;/);
  // 旧写法（拿空串当基线）不得复活
  assert.doesNotMatch(SRC, /initialSnapshot = ref\(""\)/);
  // 三个弹窗都必须用共享 helper，不允许各自再写一份快照比较。
  // #1880 起新增 useDialogForm（内部转调 useFormDirty），两者都算「共享 helper」。
  for (const f of [
    "frontend/src/views/asset/ledgers/components/TransactionEditDialog.vue",
    "frontend/src/views/asset/inventory/components/AssetEditDialog.vue",
    "frontend/src/views/asset/ledgers/components/CreateAccountDialog.vue"
  ]) {
    const t = readFileSync(join(process.cwd(), f), "utf8");
    assert.match(t, /useFormDirty|useDialogForm/, `${f} 应改用 useFormDirty/useDialogForm`);
    assert.doesNotMatch(t, /JSON\.stringify\([^)]*\) !== initialSnapshot/);
  }
});

test("#1880：弹窗关闭侧也必须复位基线（否则「保存后」仍弹未保存修改）", () => {
  // 关闭只有两条路：保存成功、放弃修改——两者都只把 modelValue 置 false。
  // 若 watch / 事件处理器只处理打开分支，表单留着改后的值而基线还是打开时的值，
  // isDirty 仍为 true，叠上 onBeforeRouteLeave 就是「关掉弹窗后点侧边栏仍被拦」。
  const cases = [
    {
      f: "frontend/src/views/asset/inventory/components/AssetEditDialog.vue",
      // 关闭分支不能是早退
      mustNotMatch: /if \(!open\) \{\s*return;/,
      mustMatch: /fillOnOpen\(open/
    },
    {
      f: "frontend/src/views/asset/ledgers/components/CreateAccountDialog.vue",
      mustNotMatch: /if \(val\) \{\s*markClean\(\);?\s*\}\s*\);/,
      mustMatch: /fillOnOpen\(val/
    },
    {
      f: "frontend/src/views/asset/ledgers/components/TransactionEditDialog.vue",
      // 挂 @close（关闭后复位）而不是 before-close（那是「询问是否关闭」）
      mustMatch: /@close="resetAfterClose"/
    }
  ];
  for (const c of cases) {
    const t = readFileSync(join(process.cwd(), c.f), "utf8");
    assert.match(t, c.mustMatch, `${c.f} 应有 ${c.mustMatch}`);
    if (c.mustNotMatch) {
      assert.doesNotMatch(t, c.mustNotMatch, `${c.f} 不应有关闭分支早退`);
    }
  }
});

test("#1880：useDialogForm 打开与关闭两种态都同步基线", () => {
  const guard = readFileSync(
    join(process.cwd(), "frontend/src/composables/useUnsavedChangesGuard.ts"),
    "utf8"
  );
  // 填值与 markClean 必须在同一个函数体内——只做一半会复现 #1845 的变种
  const m = guard.match(/function fillOnOpen[\s\S]*?\n  }/);
  assert.ok(m, "应有 fillOnOpen");
  assert.match(m[0], /form\.value = next;/, "fillOnOpen 应写回表单");
  assert.match(m[0], /markClean\(\)/, "fillOnOpen 应同步基线");
});

test("弹窗未打开（基线 null）→ 不算脏，即使表单初值是对象", () => {
  assert.equal(isFormDirtyJson(null, JSON.stringify({})), false);
  assert.equal(isFormDirtyJson(null, JSON.stringify({ notes: "" })), false);
});

test("打开后未改动 → 不算脏", () => {
  const snap = JSON.stringify({ notes: "x" });
  assert.equal(isFormDirtyJson(snap, JSON.stringify({ notes: "x" })), false);
});

test("打开后有改动 → 算脏", () => {
  const snap = JSON.stringify({ notes: "x" });
  assert.equal(isFormDirtyJson(snap, JSON.stringify({ notes: "y" })), true);
});

test("把 null 误当空串基线就是 #1845 那个 bug（此用例即回归本身）", () => {
  const current = JSON.stringify({});
  assert.equal(isFormDirtyJson(null, current), false); // 正确
  assert.equal("" !== current, true); // 旧实现：永远脏 → 用户什么都没填也被拦
});
/**
 * 成功路径必须清脏基线（#1884 补漏）。
 *
 * ## 为什么要有这条
 *
 * #1883 把三个弹窗的脏基线收口进 `useDialogForm` / `useFormDirty`，但只在 watch 的
 * 「打开」分支同步了基线——**成功路径漏了**。缺这一句的后果不是报错，而是
 * `isDirty` 在操作成功后仍为 true；叠上守卫里的 `onBeforeRouteLeave`（它在 setup 里
 * 无条件注册、不随弹窗开关注销），用户就带着一件「已经做完的事」被问
 * 「确定放弃吗？」。
 *
 * `MigrateDialog` 是同一问题的另一种形态：它的脏状态不是表单快照，而是一个选中的
 * id（`migrateTargetLedgerId !== null`），所以压根不进 `useFormDirty` /
 * `useDialogForm` 那套机制，只能手动复位——也最容易漏。
 */

/**
 * 按花括号配对提取 async 函数体，**不靠缩进猜**。
 *
 * `CreateAccountDialog.handleCreate` 就是反例：函数从 94 行开始，第 98 行的
 * `\n  }` 闭的是 `if (!name.trim())` 而非函数本身——按缩进截断会把 115 行的
 * `markSaved()` 判成「不在函数体内」，得到一个假失败。
 */
function extractAsyncFunctionBody(src, name) {
  const start = src.search(new RegExp(`async function ${name}\\s*\\(`));
  if (start === -1) return null;
  const open = src.indexOf("{", start);
  if (open === -1) return null;
  let depth = 0;
  for (let i = open; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") {
      depth--;
      if (depth === 0) return src.slice(open, i + 1);
    }
  }
  return null;
}

test("#1884：成功路径内必须复位脏基线（打开时复位不算）", () => {
  const cases = [
    {
      f: "frontend/src/views/asset/inventory/components/AssetEditDialog.vue",
      fn: "save",
      reset: /markSaved\(\)|markClean\(\)/
    },
    {
      f: "frontend/src/views/asset/ledgers/components/CreateAccountDialog.vue",
      fn: "handleCreate",
      reset: /markSaved\(\)|markClean\(\)/
    },
    {
      f: "frontend/src/views/asset/ledgers/components/TransactionEditDialog.vue",
      fn: "handleSave",
      reset: /markClean\(\)/
    },
    {
      // 非表单型脏状态：复位的是被选中的 id 本身
      f: "frontend/src/views/asset/ledgers/components/MigrateDialog.vue",
      fn: "handleMigrate",
      reset: /migrateTargetLedgerId\.value = null/
    }
  ];

  for (const c of cases) {
    const t = stripComments(readFileSync(join(process.cwd(), c.f), "utf8"));
    const body = extractAsyncFunctionBody(t, c.fn);
    assert.ok(body, `${c.f} 应能提取 async function ${c.fn} 的函数体`);
    assert.match(
      body,
      c.reset,
      `${c.f} 的 ${c.fn}() 成功后必须复位脏基线，否则「保存完离开页面」会被问「确定放弃」`
    );
  }
});

/**
 * 已声明脏基线的快速录入表单，挂载时必须先复位一次。
 *
 * `BuyForm` / `SellForm` 目前是**安全的**——各自声明了 `initialSnapshot` 且挂载即
 * `markFormClean()`，不会复现 #1845 那个「弹窗没打开就算脏」的回归。但这份安全靠
 * 「每个作者都记得写初始化那一行」维持：少写一次就是一个用户可见的拦截。
 *
 * 判据按「已声明脏基线」触发，而不是要求所有表单都接入——未接入的表单不归这条管，
 * 否则这条守门会变成「暗中逼所有表单加守卫」的隐藏规范。
 */
test("已声明脏基线的快速录入表单，挂载时必须先复位一次", () => {
  let checked = 0;
  for (const f of [
    "frontend/src/components/QuickEntry/BuyForm.vue",
    "frontend/src/components/QuickEntry/SellForm.vue",
    "frontend/src/components/QuickEntry/DividendForm.vue"
  ]) {
    const t = stripComments(readFileSync(join(process.cwd(), f), "utf8"));
    if (!/initialSnapshot = ref\(|useFormDirty|useDialogForm/.test(t)) continue;
    checked++;
    assert.match(
      t,
      /markFormClean\(\)|markClean\(\)|fillOnOpen\(/,
      `${f} 声明脏基线后必须在挂载时复位一次，否则未打开即判定为「有未保存修改」`
    );
  }
  assert.ok(checked > 0, "至少应检查到一个表单，否则本条守门是空转");
});
