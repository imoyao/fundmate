/**
 * 「账外类现金可搜、可管」接线守卫。
 *
 * 为什么用源码断言而不是挂载组件：本仓 vitest 跑在 node 环境、不挂载组件
 * （同 `cashLikeCardGuard.spec.ts`）。这里要防的是「组件写好了但没接线」——
 * 上一轮事故里，整块漏接线的形态组件层守卫完全抓不到。
 *
 * 验收项（用户拍板）：
 * ① 持仓明细搜索能命中账外类现金，且口径标注独立、不进持仓合计；
 * ② 补录支持「到期回款」，归置能表达「已由某持仓体现」；
 * ③ 增删改 / 归置成功后宿主必须刷新（不刷新就是旧净额）；
 * ④ 不做批量回填 trade_date，推断代码要标注。
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");

const pane = read("../../ledgers/components/LedgerDetailHoldingsPane.vue");
const card = read("../../ledgers/components/LedgerCashLikeCard.vue");
const hits = read("../components/CashLikeSearchHits.vue");
const dialog = read("../components/CashLikeManageDialog.vue");
const form = read("../components/CashLikeFlowForm.vue");
const table = read("../components/CashLikeTable.vue");
const index = read("../index.vue");
const api = read("../../../../api/cashLike.ts");
const composable = read("../composables/useCashLikeManage.ts");

/** 真的开标签：必须以标签名开头；注释里的同名标签行首是 `<!--`，不会被误判。 */
const realTag = (src: string, name: string) =>
  new RegExp(`^\\s*<${name}\\b`, "m").test(src);

describe("持仓明细搜索命中账外类现金", () => {
  it("账户详情持仓明细 Tab 真的挂了命中区，并传入当前搜索词与账户 id", () => {
    expect(realTag(pane, "CashLikeSearchHits")).toBe(true);
    expect(pane).toContain(':query="p.activeSearch"');
    expect(pane).toContain(':ledger-id="Number(p.ledgerId)"');
  });

  it("命中区独立于持仓表、明确标注不进持仓合计", () => {
    expect(hits).toContain("不建持仓、不进持仓合计");
    expect(hits).toContain("getCashLikeFlows");
    // 命中区不自己算合计、不把结果塞进持仓列表
    expect(hits).not.toContain("market_value");
  });

  it("证伪探针：注释掉的开标签不算接线", () => {
    const commented = `<!-- <CashLikeSearchHits :query="x" /> -->`;
    expect(realTag(commented, "CashLikeSearchHits")).toBe(false);
  });
});

describe("补录 / 到期回款 / 归置", () => {
  it("表单提供到期回款并把利息单独入收益桶", () => {
    expect(form).toContain('value="repayment"');
    expect(form).toContain("到期利息");
    expect(form).toMatch(/interest:\s*form\.kind === ["']repayment["']/);
  });

  it("不批量回填交易日；推断代码要标注来源", () => {
    expect(form).toContain("不做批量回填");
    expect(form).toContain("symbolInferred");
    expect(form).toMatch(/trade_date.*form\.tradeDate/);
    expect(composable).not.toContain("trade_date: confirmDate");
  });

  it("管理弹窗明示归置语义：只改 position_id、不再算成两笔钱", () => {
    expect(dialog).toContain("position_id");
    expect(dialog).toContain("不再被算成两笔钱");
    expect(dialog).toContain("m.openReconcile('attach')");
    expect(dialog).toContain("m.openReconcile('detach')");
  });

  it("补录 / 编辑 / 删除 / 归置都走同一套 API，端点带尾斜杠", () => {
    expect(api).toContain('BASE_URL + "flows/"');
    expect(api).toContain('BASE_URL + "reconcile/"');
    expect(api).toContain('BASE_URL + "targets/"');
    expect(api).toContain("{ data }");
  });
});

describe("写成功后宿主刷新", () => {
  it("账户详情类现金卡片挂了管理弹窗并把 changed 转成 saved", () => {
    expect(card).toContain("管理账外流水");
    expect(realTag(card, "CashLikeManageDialog")).toBe(true);
    expect(card).toContain("@changed=\"emit('saved')\"");
  });

  it("全面盘点类现金表每行可管理，并把 changed 接到 fetchData", () => {
    expect(table).toContain("openManage(row as CashLikeItem)");
    expect(realTag(table, "CashLikeManageDialog")).toBe(true);
    expect(index).toContain('@changed="fetchData"');
  });

  it("composable 的每个写路径都触发 onChanged", () => {
    const calls = composable.match(/onChanged\?\.\(\)/g) ?? [];
    // 补录 / 编辑 / 删除 / 归置四条写路径
    expect(calls.length).toBeGreaterThanOrEqual(4);
  });
});
