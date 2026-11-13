/**
 * 账户详情页「到期回款」入口守卫（#3087 的出口不止一处）。
 *
 * 背景：D114 的回款端点最初只接在「全面盘点」页 `CashLikeTable`。账户详情页
 * 能看到 R-007 / GC007 这类只有买入的逆回购孤儿流水，却没有任何结清入口——
 * 用户看到的是「这些产品还是无法卖出」。这条入口一旦被删/被挪回说明文字堆里，
 * 页面上不会报错，只是在途本金继续虚高。
 *
 * 本守卫钉住四件不会自己暴露的形态：
 * 1. 操作在区块标题行 #action，不夹在指标卡与说明段落之间；
 * 2. 按钮判据与后端 `cash_like_settle.outstanding_cents` 同源；
 * 3. 弹窗真的调受限端点、成功后真的刷新概览（数字不能停在旧值）；
 * 4. 逻辑留在子组件里，卡片不越过 400 行体量门禁。
 *
 * 判据纪律：断言模板里的真实标签与绑定，不是「标识符出现过」。本仓 vitest
 * 不挂载组件（node 环境），故沿用同目录 `cashLikeCardGuard.spec.ts` 的源码断言。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");

const card = read("../components/LedgerCashLikeCard.vue");
const settle = read("../components/LedgerCashLikeSettle.vue");
const dialog = read("../components/LedgerReverseRepoSettleDialog.vue");
const overview = read("../components/LedgerDetailOverview.vue");

/** 取根 `<template>` 段：模板里有嵌套 `<template v-if>` 与 `#action` 槽。 */
const cardTemplate = card.slice(
  card.indexOf("<template>"),
  card.lastIndexOf("</template>", card.indexOf("<script"))
);

describe("账户详情页逆回购到期回款", () => {
  it("操作按钮在 SectionHeader 的 #action 槽里，不再夹在说明文字流中", () => {
    const action = cardTemplate.match(/<template #action>[\s\S]*?<\/template>/);
    expect(action, "找不到 SectionHeader #action 槽").not.toBeNull();
    expect(action?.[0]).toMatch(/^\s*<LedgerCashLikeSettle\b/m);
    expect(action?.[0]).toContain("录入账户现金");
    expect(action?.[0]).toContain(':rows="breakdown"');
    // 旧形态：按钮 + hint 挤在 CardBlock 内的独立行，视觉上像说明段落的行首
    expect(cardTemplate).not.toContain(
      '<div v-if="ledgerId" class="cash-like-actions">'
    );
    expect(cardTemplate).not.toContain("cash-like-actions__hint");
  });

  it("候选取自逐产品明细，判据 = 逆回购 + 在途本金 > 0 + 有标的代码", () => {
    expect(settle).toContain('v-if="candidates.length"');
    expect(settle).toContain("props.rows.filter(canSettle)");
    expect(settle).toContain('row.asset_type === "reverse_repo"');
    expect(settle).toContain("row.net_amount > 0");
    expect(settle).toContain("!!row.symbol");
    const button = settle.match(
      /<el-button[\s\S]{0,200}?>\s*到期回款\s*<\/el-button>/
    );
    expect(button, "找不到真实的「到期回款」按钮").not.toBeNull();
  });

  it("弹窗调的是 #3087 受限端点，成功后由父页刷新概览", () => {
    expect(dialog).toContain("settleReverseRepo(");
    expect(dialog).toContain("symbol: row.symbol");
    expect(dialog).toContain('emit("settled")');
    expect(settle).toMatch(/^\s*<LedgerReverseRepoSettleDialog\b/m);
    expect(settle).toContain(`@settled="emit('saved')"`);
    expect(cardTemplate).toContain(`@saved="emit('saved')"`);
    expect(overview).toContain('@saved="p.loadSummary"');
  });

  it("每次打开重置表单，缺账户 / 代码 / 回款日不提交", () => {
    expect(dialog).toContain("watch(");
    expect(dialog).toContain("props.ledgerId == null");
    expect(dialog).toContain("!settleDate.value");
    expect(dialog).toContain("todayIso()");
  });

  it("回款逻辑留在子组件里，卡片不越过 400 行体量门禁", () => {
    expect(card.split("\n").length).toBeLessThan(400);
    expect(card).not.toContain("function canSettle(");
    expect(cardTemplate).not.toContain('<th scope="col">操作</th>');
  });
});
