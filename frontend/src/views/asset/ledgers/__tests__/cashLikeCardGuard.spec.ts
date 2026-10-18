/**
 * 账外类现金出口守卫（#2155 / CNB #479 回归网）。
 *
 * 背景：`get_cash_like_stats` 一向只给一个 `cash_like_amount` 汇总数，
 * 账户详情页没有任何出口。真机账户「同花顺——银河」（id=12）持仓市值 296,042 元、
 * 账外孤儿货基流水净额 476,951 元 —— 后者完全不显示。
 *
 * 本守卫钉住三件事（都是「改回去也不会有人发现」的形态）：
 * 1. 四项**分列**展示（卡面明确要求「不要合并成一个数，否则又回到口径混淆」）；
 * 2. 逐产品明细存在（只给汇总数字不构成「解释去向」，验收第 2 条交不了）；
 * 3. 页面必须说清与「总资产」的关系（环形图合计 ≠ 类现金合计）。
 *
 * 判据纪律（本仓「守门通过 ≠ 守门有效」）：
 * - **断言的是模板绑定，不是标识符出现过**。第一版判据只查
 *   `cash_like_in_positions_amount` 是否出现在文件里——而它出现在 `<script>` 里，
 *   于是把该 MetricCard 的 `title` 改掉、那一项实际不再展示，判据仍然全绿
 *   （探针 F1 MISSED 实测）。现改为断言模板里的 `:value="..."` 绑定。
 * - **宿主接线必须真断言**（探针 F5 MISSED 实测）：`expect(overview).toContain(
 *   "<LedgerCashLikeCard")` 会被 `<!-- <LedgerCashLikeCard ... -->` 注释满足。
 *   现用正则要求它是一枚**真的开标签**（行首非 `<!--`）。
 *
 * 为什么用源码断言而不是挂载组件：本仓 vitest 跑在 node 环境、不挂载组件
 * （`vitest.config.ts`），既有同类守卫（`allocationEditGuard.spec.ts`）即此范式。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");

const card = read("../components/LedgerCashLikeCard.vue");
const overview = read("../components/LedgerDetailOverview.vue");

/**
 * 取 `<template>` 段（判据只认「渲染出来的东西」，script 里的标识符不算数）。
 *
 * ⚠️ 不能用 `indexOf("</template>")` 截取：本组件的模板里有**嵌套** `<template
 * v-if>`，第一个 `</template>` 是内层的，会把下半张表（含明细列）整段切掉 ——
 * 判据就会对着残缺样本下结论。故取「`<script` 之前的最后一个 `</template>`」。
 */
const cardTemplate = card.slice(
  card.indexOf("<template>"),
  card.lastIndexOf("</template>", card.indexOf("<script"))
);

describe("账外类现金出口（#2155）", () => {
  it("四项分列，各自绑定到模板（不合并成一个数）", () => {
    // 每一项都必须在模板里被真正渲染出来
    for (const binding of [
      "formatAmount(inPositions)",
      "formatAmount(orphanNet)",
      "formatAmount(accountCash)",
      "formatAmount(total)"
    ]) {
      expect(cardTemplate, `模板未渲染 ${binding}`).toContain(binding);
    }
    const cards = cardTemplate.match(/<MetricCard/g) ?? [];
    expect(cards.length).toBeGreaterThanOrEqual(4);
  });

  it("渲染逐产品明细（验收第 2 条：给出可见的解释与去向）", () => {
    // 模板只认 `breakdown`（computed 名）；字段名 `cash_like_breakdown` 出现在 script 里，
    // 断言模板必须用它真正绑定的那个名字。
    expect(cardTemplate).toContain('v-for="row in breakdown"');
    // 必须有金额列 + 笔数列，缺任一项都读不出「哪只产品占大头 / 是不是被重复导入」
    expect(cardTemplate).toMatch(/:value="row\.net_amount"/);
    expect(cardTemplate).toContain("row.txn_count");
  });

  it("说清与总资产的关系：环形图合计 ≠ 类现金合计", () => {
    // 这句是验收第 2 条的落点。删掉它，用户会怀疑同一笔钱被算了两遍
    // ——D59 把口径解耦了，UI 不说就等于新增一个困惑。
    expect(cardTemplate).toContain("环形图合计 ≠ 类现金合计");
    expect(cardTemplate).toContain("formatAmount(totalMarketValue)");
  });

  it("账外孤儿非 0 时即使合计为 0 也要显示（否则回到「钱在库里、页面没出口」）", () => {
    // 买 1000 卖 1000 的账户合计为 0，但账外流水真实存在，明细仍应可见。
    const match = card.match(/const visible = computed\(\s*([\s\S]*?)\n\);/);
    expect(match, "找不到 visible 的 computed 定义").not.toBeNull();
    expect(match![1]).toContain("orphanNet.value !== 0");
  });

  it("已挂到账户详情页（真的开标签，不是注释掉的一行）", () => {
    // 组件存在但没人引用 = 没有出口。判据必须排除注释形态（探针 F5 踩过）。
    expect(overview).toMatch(/^\s*<LedgerCashLikeCard\b/m);
    expect(overview).toMatch(
      /<LedgerCashLikeCard[^>]*:summary="p\.summaryData"/
    );
  });

  it("账户概览接口类型含分项与明细字段", () => {
    const composable = read("../../../../composables/useLedgerDetail.ts");
    for (const field of [
      "orphan_amount",
      "orphan_income_amount",
      "account_cash_amount",
      "cash_like_breakdown"
    ]) {
      expect(composable, `缺字段 ${field}`).toContain(field);
    }
  });
});
