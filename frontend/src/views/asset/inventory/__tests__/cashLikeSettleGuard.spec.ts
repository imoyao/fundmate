/**
 * 逆回购「到期回款」入口守卫（#3087 / D114）。
 *
 * 背景：逆回购不建持仓、按孤儿流水记账，导入只带来「买入」那一半——真库 4 笔全是
 * `buy`（202,000.84 元在途），没有任何回款。所以这条入口是**唯一**能让在途本金回到 0
 * 的地方；它一旦被改坏，账面上的钱会继续虚高，而**没有任何报错**会提示这件事。
 *
 * 本守卫钉住三件「改回去也不会有人发现」的形态：
 * 1. 按钮只出现在「逆回购 + 在途本金 > 0」的行上——货基没有到期，给它按钮只会引导
 *    用户用「回款」去做「赎回」；
 * 2. 提交真的调了受限接口（`settleReverseRepo`），而不是随便写一笔流水；
 * 3. 成功后必须 `emit("settled")` 且宿主页接了它——否则页面数字停在旧值，
 *    用户会以为没生效、再点一次（后端会拒，但体验上像坏了）。
 *
 * 判据纪律：断言**模板里的真实标签与绑定**，不是「标识符出现过」（同
 * `ledgers/__tests__/cashLikeCardGuard.spec.ts` 的 F1/F5 教训）；本仓 vitest 不挂载
 * 组件，故用源码断言。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");

const table = read("../components/CashLikeTable.vue");
const page = read("../index.vue");

/** 取 `<template>` 段（`<script` 之前的最后一个 `</template>`，兼容嵌套 template）。 */
function templateOf(sfc: string): string {
  const scriptAt = sfc.indexOf("<script");
  const head = scriptAt === -1 ? sfc : sfc.slice(0, scriptAt);
  const end = head.lastIndexOf("</template>");
  return end === -1 ? head : head.slice(0, end);
}

function scriptOf(sfc: string): string {
  const at = sfc.indexOf("<script");
  return at === -1 ? "" : sfc.slice(at);
}

const template = templateOf(table);
const script = scriptOf(table);

describe("逆回购到期回款入口", () => {
  it("模板里有真实的「到期回款」按钮，且只由 canSettle 控制显隐", () => {
    // 真开标签：要求 `<el-button` 与 `到期回款` 在同一个标签块里，避免被注释满足
    const button = template.match(
      /<el-button[\s\S]{0,200}?>\s*到期回款\s*<\/el-button>/
    );
    expect(button).not.toBeNull();
    expect(template).toContain('v-if="canSettle(row as CashLikeItem)"');
    expect(template).toContain('@click="openSettle(row as CashLikeItem)"');
  });

  it("canSettle 只放行逆回购、且要求在途本金 > 0", () => {
    expect(script).toContain('row.asset_type === "reverse_repo"');
    expect(script).toContain("row.net_amount > 0");
  });

  it("提交调的是受限回款接口（不是通用流水写入）", () => {
    expect(script).toContain("settleReverseRepo(row.ledger_id");
    expect(script).toContain("symbol: row.symbol");
  });

  it("成功后 emit settled，宿主页真的接了它（否则数字停在旧值）", () => {
    expect(script).toContain('emit("settled")');
    const host = page.match(/<CashLikeTable[\s\S]{0,300}?\/>/);
    expect(host).not.toBeNull();
    expect(host?.[0]).toContain('@settled="fetchData"');
  });
});
