/**
 * 账户详情页「区块清单」判据单测（#3222）。
 *
 * 钉死 ledger_type → 区块可见性的映射，防止回归：
 * - property（实物资产）必须显示「资产明细」，且**隐藏**净值型区块
 *   （类现金 / 收益日历 / 收益归因 / 持仓结构穿透）——这正是本次修复要拦的
 *   「实物账户吃投资账户骨架」的病灶；
 * - stock / fund / e_account 保持完整净值区块，且不显示「资产明细」；
 * - bank 显示类现金、不显示净值区块；
 * - 未知 / 空类型按最保守处理：overview 恒显、净值区块一律不显。
 */
import { describe, it, expect } from "vitest";
import {
  isSectionVisible,
  isInvestmentLedger,
  isPropertyLedger,
  type LedgerDetailSection
} from "../ledgerDetailSections";

const ALL_SECTIONS: LedgerDetailSection[] = [
  "overview",
  "assetList",
  "cashLike",
  "calendar",
  "attribution",
  "depthAnalysis"
];

describe("isSectionVisible（ledger_type → 区块可见性）", () => {
  it("overview 恒显（总资产是通用概念）", () => {
    for (const t of [
      "stock",
      "fund",
      "e_account",
      "bank",
      "property",
      null,
      undefined
    ]) {
      expect(isSectionVisible("overview", t)).toBe(true);
    }
  });

  it("property：资产明细显示，净值型区块全部隐藏", () => {
    expect(isSectionVisible("assetList", "property")).toBe(true);
    expect(isSectionVisible("cashLike", "property")).toBe(false);
    expect(isSectionVisible("calendar", "property")).toBe(false);
    expect(isSectionVisible("attribution", "property")).toBe(false);
    expect(isSectionVisible("depthAnalysis", "property")).toBe(false);
  });

  it("stock / fund / e_account：净值区块全显，资产明细不显", () => {
    for (const t of ["stock", "fund", "e_account"]) {
      expect(isSectionVisible("cashLike", t)).toBe(true);
      expect(isSectionVisible("calendar", t)).toBe(true);
      expect(isSectionVisible("attribution", t)).toBe(true);
      expect(isSectionVisible("depthAnalysis", t)).toBe(true);
      expect(isSectionVisible("assetList", t)).toBe(false);
    }
  });

  it("bank：类现金显示，净值区块隐藏", () => {
    expect(isSectionVisible("cashLike", "bank")).toBe(true);
    expect(isSectionVisible("calendar", "bank")).toBe(false);
    expect(isSectionVisible("attribution", "bank")).toBe(false);
    expect(isSectionVisible("depthAnalysis", "bank")).toBe(false);
    expect(isSectionVisible("assetList", "bank")).toBe(false);
  });

  it("未知 / 空类型：净值区块一律不显（保守，不误判成投资账户）", () => {
    for (const t of ["unknown", "", null, undefined]) {
      for (const s of [
        "assetList",
        "cashLike",
        "calendar",
        "attribution",
        "depthAnalysis"
      ] as const) {
        expect(isSectionVisible(s, t)).toBe(false);
      }
    }
  });

  it("清单声明了全部区块键，无遗漏", () => {
    for (const s of ALL_SECTIONS) {
      // 每个区块至少对一个已知类型可见，否则就是死区块
      expect(
        isSectionVisible(s, "stock") || isSectionVisible(s, "property")
      ).toBe(true);
    }
  });
});

describe("isInvestmentLedger（净值 + 盈亏口径）", () => {
  it("仅 stock / fund / e_account 为投资账户", () => {
    expect(isInvestmentLedger("stock")).toBe(true);
    expect(isInvestmentLedger("fund")).toBe(true);
    expect(isInvestmentLedger("e_account")).toBe(true);
    expect(isInvestmentLedger("bank")).toBe(false);
    expect(isInvestmentLedger("property")).toBe(false);
    expect(isInvestmentLedger(null)).toBe(false);
    expect(isInvestmentLedger(undefined)).toBe(false);
  });
});

describe("isPropertyLedger（实物资产口径）", () => {
  it("仅 property 为实物资产账户", () => {
    expect(isPropertyLedger("property")).toBe(true);
    expect(isPropertyLedger("stock")).toBe(false);
    expect(isPropertyLedger("fund")).toBe(false);
    expect(isPropertyLedger("e_account")).toBe(false);
    expect(isPropertyLedger("bank")).toBe(false);
    expect(isPropertyLedger(null)).toBe(false);
    expect(isPropertyLedger(undefined)).toBe(false);
  });
});
