/**
 * 「不进组合」单元格渲染守卫（#2786 / D20 二期开口项 4 回归网）。
 *
 * ## 为什么还要一条组件级守卫
 * `portfolioAssignModel.spec.ts` 只钉住**判断**（`in_portfolio === false` → `excluded`）；
 * 判断对了、渲染没跟上，界面照样把货基画成一个可点的改派入口 —— 而这正是 #2786 的病根。
 * 映射是「mode 字面量 → 模板分支」，改回 `v-else` 一路到底不会有任何报错，只能靠守卫。
 *
 * ## 判据纪律（沿用本仓 `cashLikeCardGuard.spec.ts`）
 * - **断言模板绑定，不是标识符出现过**：`mode === "excluded"` 在 `<script>` 里也出现
 *   （`triggerLabel` 附近），只查全文会对着 script 里的字符串下结论，模板改坏也全绿。
 * - **必须断言顺序**：模板里排除分支若排在 `<button>` **之后**，`v-else` 就绑到了
 *   前者身上，货基会渲染成按钮 —— 语法合法、Vue 不报错、行为全错。
 *
 * 为什么用源码断言而不是挂载组件：本仓 vitest 跑在 node 环境、不挂载组件
 * （`vitest.config.ts`），既有同类守卫（`allocationEditGuard.spec.ts` /
 * `cashLikeCardGuard.spec.ts`）即此范式。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const source = readFileSync(
  fileURLToPath(
    new URL("../components/PortfolioAssignCell.vue", import.meta.url)
  ),
  "utf-8"
);

/** 只取 `<template>` 段：`<script setup>` 在前、`<style>` 在后。 */
const template = source.slice(
  source.indexOf("\n<template>"),
  source.indexOf("<style")
);

/** 取某个开标签的完整属性区（到第一个 `>` 为止，属性里没有裸 `>`）。 */
function openTag(tagName: string): string {
  const start = template.indexOf(`<${tagName}`);
  expect(start, `模板里找不到 <${tagName}>`).toBeGreaterThan(-1);
  return template.slice(start, template.indexOf(">", start));
}

describe("PortfolioAssignCell · 不进组合（excluded）", () => {
  it("浮层对 excluded 禁用，点不出改派列表", () => {
    // 不禁用的话：点开浮层 → 选一个组合 → PATCH 成功 → 组合页看不到（#2786 原病）
    expect(openTag("el-popover")).toContain(`:disabled="mode === 'excluded'"`);
  });

  it("excluded 分支渲染「— 不进组合」，且是 v-if 而非混进 else", () => {
    const span = openTag("span");
    expect(span).toContain(`v-if="mode === 'excluded'"`);
    expect(template).toContain("— 不进组合");
  });

  it("排除分支必须排在 <button> 之前：否则按钮的 v-else 会绑到它身上", () => {
    const body = template.indexOf(`v-if="mode === 'excluded'"`);
    const button = template.indexOf("<button");
    expect(body).toBeGreaterThan(-1);
    expect(button).toBeGreaterThan(-1);
    expect(body).toBeLessThan(button);
    // 按钮仍要是 v-else（承接三种可改派态），不能被改成 v-if="true" 之类
    expect(openTag("button")).toContain("v-else");
  });

  it("原因挂在 title 上：不可交互的结论必须能解释自己为什么不可交互", () => {
    // 货基这格和别的行长得不一样，没有说明就会被当成 bug 去排查
    expect(openTag("span")).toContain(`:title="excludedHint"`);
    expect(source).toContain("不计入投资组合");
  });

  it("excluded 分支不得带交互属性（不能是长得像文本的按钮）", () => {
    const span = openTag("span");
    expect(span).not.toContain("@click");
    expect(span).not.toContain("aria-haspopup");
  });
});
