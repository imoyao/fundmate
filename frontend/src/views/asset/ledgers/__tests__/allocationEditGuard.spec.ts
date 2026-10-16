/**
 * 配置目标行内编辑守卫（#1123 P0 回归网）：
 *
 * 持仓明细「配置目标」列必须是可编辑下拉并走嵌套持仓 PATCH 写回；
 * 回退形态：改回只读徽章（只渲染 allocation_label、无 updateLedgerPosition 调用），
 * P0 的「可编辑」验收即失效且无其它测试拦截（vitest 不挂载组件、E2E 非 per-PR 门禁）。
 *
 * 判据纪律：断言完整调用子串（含传参），不是裸标识符。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const source = readFileSync(
  fileURLToPath(
    new URL("../components/LedgerDetailHoldingsPane.vue", import.meta.url)
  ),
  "utf-8"
);

describe("持仓配置目标行内编辑（#1123 P0）", () => {
  it("列渲染为下拉（ALLOCATION_OPTIONS），不是只读徽章", () => {
    expect(source).toContain("ALLOCATION_OPTIONS");
    expect(source).toContain('v-model="row.allocation"');
  });

  it("保存走嵌套持仓 PATCH（updateLedgerPosition 传 allocation），失败以 loadHoldings 回滚", () => {
    expect(source).toContain("updateLedgerPosition(");
    expect(source).toContain("allocation: row.allocation");
    expect(source).toContain("p.loadHoldings()");
  });
});
