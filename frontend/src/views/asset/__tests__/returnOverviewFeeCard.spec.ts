/**
 * 「累计费用」卡守卫。
 *
 * ## 守的是什么
 *
 * 这张卡最坏的坏法不是算错，而是**把「不知道」显示成 0**：
 *
 * 1. `method=twr` 走日净资产序列，没有交易级费用，响应里**没有** `fees` 字段。
 *    若前端写成 `d.fees ?? 0`，卡片会显示「¥0」——用户读到的是「这几年一分
 *    手续费都没花」，而真相是「这个口径算不出费用」。
 * 2. 文案必须写明「已从累计收益中扣除」。费用在 XIRR 现金流里已经扣过一次，
 *    用户若以为还要再减一次，就会拿两个数相减去核对，越核越乱。
 *
 * 本仓 vitest 不挂载组件（无 jsdom），故沿用 `transactionSummaryWiring.spec.ts`
 * 的源码判据范式。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");

const section = read("../ReturnOverviewSection.vue");

describe("收益概览 · 累计费用", () => {
  it("有一张「累计费用」卡", () => {
    expect(section).toContain('title="累计费用"');
  });

  it("缺字段时返回 null（显示 --），不得补 0", () => {
    // 正面：显式判 null
    expect(section).toContain("d.fees == null");
    // 反面：任何 `?? 0` / `|| 0` 兜底都会把「算不出」显示成「没花过钱」
    expect(section).not.toContain("d.fees ?? 0");
    expect(section).not.toContain("d.fees || 0");
  });

  it("文案写明费用已从累计收益中扣除（避免用户二次扣减）", () => {
    expect(section).toMatch(/累计费用[\s\S]{0,200}已从累计收益中扣除/);
  });

  it("累计收益的说明也标了「已扣手续费」", () => {
    expect(section).toMatch(/累计收益[\s\S]{0,120}已扣手续费/);
  });
});
