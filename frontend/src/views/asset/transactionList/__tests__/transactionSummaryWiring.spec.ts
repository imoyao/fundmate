/**
 * 汇总条接线守卫（设计 §四 + §十二-1）。
 *
 * ## 守的是什么
 *
 * 汇总条有三个**不会报错**的坏法：
 *
 * 1. 前端拿当页数据求和 → 数字看起来正常，实际只覆盖 20 行（「列表 3 条、汇总按全量」
 *    或反过来）。判据是「只有一处取数，且来自汇总接口」。
 * 2. 翻页 / 触底加载时重取 → 功能正确、请求翻倍，而且汇总与分页无关，重取纯属浪费。
 * 3. 没数据时渲染空容器 → 用户以为这里坏了，而它只是接口还没回来。
 *
 * 本仓 vitest 不挂载组件（无 jsdom），故用源码判据钉住（同
 * `transactionDetailOnDemand.spec.ts` 的范式）。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");

const page = read("../../TransactionList.vue");
const bar = read("../TransactionSummaryBar.vue");

function scriptOf(source: string): string {
  const start = source.indexOf("<script setup");
  const end = source.indexOf("</script>", start);
  expect(start, "找不到 <script setup> 段").toBeGreaterThan(-1);
  return source.slice(start, end);
}

function fnBody(source: string, name: string, until: string): string {
  const from = source.indexOf(name);
  expect(from, `找不到 ${name}`).toBeGreaterThan(-1);
  return source.slice(from, source.indexOf(until, from));
}

const pageScript = scriptOf(page);
const barScript = scriptOf(bar);

describe("汇总条 · 取数", () => {
  it("只有一处汇总取数（第二处通常意味着有人又拼了一份）", () => {
    const calls = pageScript.match(/getTransactionSummary\(/g) ?? [];
    expect(calls.length).toBe(1);
  });

  it("汇总请求走筛选参数，不带分页（分页与汇总无关）", () => {
    expect(pageScript).toContain("getTransactionSummary(buildFilterParams(");
  });

  it("翻页与触底加载不重取汇总", () => {
    // 这两个 handler 只该动列表：汇总回答「这段时间怎么样」，与看到第几页无关
    for (const [name, until] of [
      ["const onPageChange", "const onSizeChange"],
      ["const onLoadMore", "function clearSymbolFilter"]
    ] as const) {
      const body = fnBody(pageScript, name, until);
      expect(body).not.toContain("fetchSummary(");
    }
  });

  it("筛选变化 / 首次进入 / 行内编辑保存后都会重取", () => {
    expect(
      fnBody(pageScript, "const resetAndFetch", "const onFilterChange")
    ).toContain("fetchSummary()");
    expect(fnBody(pageScript, "onMounted", "<\/script>")).toContain(
      "fetchSummary()"
    );
    expect(
      fnBody(pageScript, "function handleSaved", "// 导出全部交易流水")
    ).toContain("fetchSummary()");
  });

  it("过期响应不许覆盖新结果（连点筛选时数字会对不上筛选）", () => {
    expect(pageScript).toContain("if (seq !== summarySeq) return;");
  });
});

describe("汇总条 · 渲染", () => {
  it("未取到数据时整块不渲染（不留空容器）", () => {
    const template = bar.slice(
      bar.indexOf("\n<template>"),
      bar.indexOf("<style")
    );
    const section = template.slice(template.indexOf("<section"));
    expect(section.slice(0, 200)).toContain(`v-if="summary"`);
  });

  it("净投入显示正负号（正＝净投入，负＝净取出，是相反的事）", () => {
    expect(barScript).toContain('amount < 0 ? "-" : "+"');
  });

  it("前端不二次求和：净投入直接取后端字段", () => {
    expect(barScript).toContain("signedMoney(s.net_invested)");
    // 只要出现「自己把四个桶加起来」的算式，就说明口径又长出了第二份
    expect(barScript).not.toContain("s.buy.amount +");
    expect(barScript).not.toContain("s.sell.amount +");
  });
});
