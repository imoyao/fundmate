/**
 * 「展开详情按需请求」守卫（流水页重设计 §十二 第 4 条）。
 *
 * ## 守的是什么
 *
 * 展开详情的数据**不是**从列表带下来的：行被展开时才按 id 单独取一次
 * `GET /api/transactions/<id>/`。这条契约有一个特点——**改坏了不会报错，只会变慢**：
 *
 * 1. 改成「列表里预取所有行的详情」：功能完全正常，但每页 20 行各打一次接口，
 *    而真正被展开的可能一行都没有；
 * 2. 收起也请求：`el-table` 的 `expand-change` 在**收起**时同样触发（第二个参数变空数组），
 *    漏掉提前返回就是每次收起白跑一次；
 * 3. 不缓存：用户来回展开同几行会连打十几次接口。
 *
 * 三条都不会有测试变红、不会在控制台留下痕迹，只会在真机上慢到有人抱怨。故用源码判据
 * 钉住（本仓范式：`vitest` 跑 node 环境、不挂载组件，见 `cashLikeCardGuard.spec.ts`）。
 *
 * ## 为什么用源码断言而不是挂载组件
 *
 * 本仓 vitest 不挂载组件（`vitest.config.ts` 无 jsdom）。要真测这三条得引入 jsdom +
 * Element Plus 全量注册 + mock 接口——为三条「行为对只是慢」的约定改测试基建，成本远大于
 * 收益；而它们要防的是**静默退化**，源码判据已经足够。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");

const tableView = read("../TransactionTableView.vue");
const table = read("../../../../components/TransactionTable/index.vue");
const page = read("../../TransactionList.vue");

/** 只取 `<script setup>` 段：模板与样式里的字符串不能参与判据 */
function scriptOf(source: string): string {
  const start = source.indexOf("<script setup");
  const end = source.indexOf("</script>", start);
  expect(start, "找不到 <script setup> 段").toBeGreaterThan(-1);
  return source.slice(start, end);
}

const tableViewScript = scriptOf(tableView);
const tableScript = scriptOf(table);
const pageScript = scriptOf(page);

describe("展开详情 · 按需请求", () => {
  it("详情接口只在 loadDetail 里调用一次（没有第二处取数）", () => {
    const calls = tableViewScript.match(/getTransactionDetail\(/g) ?? [];
    // 一处是 loadDetail 里的实际调用；多出第二处通常意味着有人加了「预取全部」
    expect(calls.length).toBe(1);
  });

  it("已有数据 / 正在取 → 直接返回，不重复打接口", () => {
    expect(tableViewScript).toContain(
      "if (existing && (existing.loading || existing.data)) return;"
    );
  });

  it("展开事件只把 id 交给 loader，不把整行数据当详情用", () => {
    // onExpand 只该做一件事：拿 id 去取。若它开始读 row.notes / row.amount 拼详情，
    // 说明详情又回到了「从列表数据拼」的老路。
    const onExpand = tableViewScript.slice(
      tableViewScript.indexOf("function onExpand"),
      tableViewScript.indexOf("function onRetryDetail")
    );
    expect(onExpand).toContain("loadDetail(row.id)");
    expect(onExpand).not.toContain("row.notes");
    expect(onExpand).not.toContain("row.amount");
  });

  it("编辑保存后清掉详情缓存（否则展开行还显示改之前的备注）", () => {
    const handleSaved = pageScript.slice(
      pageScript.indexOf("function handleSaved"),
      pageScript.indexOf("// 导出全部交易流水")
    );
    expect(handleSaved).toContain("clearDetails()");
  });
});

describe("展开详情 · 收起不请求", () => {
  it("expand-change 在收起（第二个参数为空数组）时提前返回", () => {
    const fn = tableScript.slice(tableScript.indexOf("function onExpandChange"));
    expect(fn).toContain("expanded.length === 0");
    expect(fn).toContain("return");
  });
});

describe("展开详情 · 默认关闭（账本 Tab / 持仓抽屉零影响）", () => {
  it("showExpand 默认 false", () => {
    expect(tableScript).toContain("showExpand: false");
  });

  it("展开列由 showExpand 控制，而不是无条件渲染", () => {
    const template = table.slice(
      table.indexOf("\n<template>"),
      table.indexOf("<style")
    );
    const expandColumn = template.slice(template.indexOf('<el-table-column'));
    expect(expandColumn.slice(0, 200)).toContain(`v-if="showExpand"`);
    expect(expandColumn.slice(0, 200)).toContain(`type="expand"`);
  });
});
