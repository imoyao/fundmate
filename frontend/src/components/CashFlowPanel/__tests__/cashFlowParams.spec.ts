import dayjs from "dayjs";
import { describe, expect, it } from "vitest";
import { RANGE_OPTIONS, cashFlowParams } from "../cashFlowParams";

const NOW = dayjs("2026-11-09");

describe("cashFlowParams", () => {
  it("「投资以来」把起点解析交给后端（inception 哨兵）", () => {
    expect(cashFlowParams("inception", { ledgerId: 26 }, NOW)).toEqual({
      start_date: "inception",
      ledger_id: 26
    });
  });

  it("近一年档按今天回退 365 天，并带上组合作用域", () => {
    expect(cashFlowParams(365, { portfolioId: 3 }, NOW)).toEqual({
      start_date: "2025-11-09",
      portfolio_id: 3
    });
  });

  it("普通档按所选天数回退，不带 inception 哨兵", () => {
    const expected = NOW.subtract(180, "day").format("YYYY-MM-DD");
    expect(cashFlowParams(180, { ledgerId: 8 }, NOW)).toEqual({
      start_date: expected,
      ledger_id: 8
    });
    expect(expected).not.toBe("inception");
  });

  it("区间枚举含「投资以来」，且是最后一档", () => {
    expect(RANGE_OPTIONS.map(o => o.value)).toEqual([
      180,
      365,
      1095,
      "inception"
    ]);
  });
});
