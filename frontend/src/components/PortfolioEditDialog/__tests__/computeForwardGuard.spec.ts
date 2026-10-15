/**
 * 计算前移守卫（#981 回归网）：
 *
 * 组合编辑的账户关联 diff 必须由后端事务内原子完成（PATCH /api/portfolios/{id}/
 * 的 ledger_ids），前端只传完整目标集合。回退形态有两种，都会让本卡症状复燃：
 *   1. 有人把 updateLedger 逐个调用加回来——非原子（中途失败留半更新），
 *      且逻辑只活在本对话框、其它入口无法复用；
 *   2. API 类型删掉 ledger_ids——调用方失去「传整集」的类型契约。
 *
 * 判据纪律：断言完整子串（含参数名），不是裸标识符。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");

const dialog = read("../index.vue");
const api = read("../../../api/portfolio.ts");

describe("账户关联计算前移守卫（#981）", () => {
  it("对话框传完整集合 ledger_ids，且不再逐个调 updateLedger", () => {
    expect(dialog).toContain("ledger_ids: selectedLedgerIds.value");
    expect(dialog).not.toContain("updateLedger(");
  });

  it("PortfolioUpdateInput 带 ledger_ids 可选字段（传整集的类型契约）", () => {
    expect(api).toContain("ledger_ids?: number[]");
  });
});
