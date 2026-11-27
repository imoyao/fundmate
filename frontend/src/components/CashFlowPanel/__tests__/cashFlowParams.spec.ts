import dayjs from "dayjs";
import { describe, expect, it } from "vitest";
import { chartRangeParams } from "@/utils/chartRange";
import { cashFlowParams } from "../cashFlowParams";

const NOW = dayjs("2026-11-09");

describe("cashFlowParams", () => {
  it("「成立来」把起点解析交给后端（inception 哨兵）", () => {
    expect(cashFlowParams("inception", { ledgerId: 26 }, NOW)).toEqual({
      start_date: "inception",
      ledger_id: 26
    });
  });

  it("近1年档按今天回退 12 个月，并带上组合作用域", () => {
    expect(cashFlowParams("1y", { portfolioId: 3 }, NOW)).toEqual({
      start_date: "2025-11-09",
      portfolio_id: 3
    });
  });

  it("普通档按所选档位回退，不带 inception 哨兵", () => {
    expect(cashFlowParams("6m", { ledgerId: 8 }, NOW)).toEqual({
      start_date: "2026-05-09",
      ledger_id: 8
    });
  });

  it("家庭级只带 scope，不带任何 id（两者互斥，同传后端 400）", () => {
    // 调用方即使误把 id 一起传进来，也以 family 为准、不把矛盾参数发出去
    expect(cashFlowParams("1y", { family: true, ledgerId: 26 }, NOW)).toEqual({
      start_date: "2025-11-09",
      scope: "family"
    });
  });

  it("档位口径同源：起点恒等于统一表 `chartRangeParams`（不许本模块自带天数）", () => {
    for (const key of ["1m", "3m", "6m", "1y", "2y", "ytd"] as const) {
      expect(cashFlowParams(key, {}, NOW).start_date).toBe(
        chartRangeParams(key, NOW).start_date
      );
    }
  });
});
