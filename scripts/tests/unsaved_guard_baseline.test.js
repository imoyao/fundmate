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
  // 三个弹窗都必须用共享 helper，不允许各自再写一份快照比较
  for (const f of [
    "frontend/src/views/asset/ledgers/components/TransactionEditDialog.vue",
    "frontend/src/views/asset/inventory/components/AssetEditDialog.vue",
    "frontend/src/views/asset/ledgers/components/CreateAccountDialog.vue"
  ]) {
    const t = readFileSync(join(process.cwd(), f), "utf8");
    assert.match(t, /useFormDirty/, `${f} 应改用 useFormDirty`);
    assert.doesNotMatch(t, /JSON\.stringify\([^)]*\) !== initialSnapshot/);
  }
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