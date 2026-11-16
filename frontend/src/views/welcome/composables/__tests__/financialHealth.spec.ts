/**
 * 财务晴雨表四项健康度的口径判据（#3165，纯函数 node 环境可测）。
 *
 * 这里钉的是最容易退化的四条边界：
 * 1. **null 不是 0**：分母缺失 / 未设目标必须给 null，组件显示「—」，
 *    写 0 就是把「算不了」伪装成「没有」。
 * 2. **集中度金额同源**：金额只能由「持仓市值 × 后端比率」反推，
 *    不能另算一遍 Top5（两套排名必然分叉）。
 * 3. **类现金分母是家庭总资产**，不是持仓市值；且金额本身已含在总资产里。
 * 4. **分红金额与股息率不同源**：金额含已清仓、股息率只算在管，
 *    脚注必须写明，禁止把两者相除反算比率冒充同源。
 */
import { describe, expect, it } from "vitest";
import type { PositionStructureData, CashLikeBreakdown } from "@/api/summary";
import type { DividendSummary } from "@/api/dividends";
import type { PortfolioItem } from "@/api/portfolio";
import type { SummaryData } from "@/api/types";
import { buildFinancialHealthView } from "../financialHealth";

function makeStructure(
  overrides: Partial<PositionStructureData> = {}
): PositionStructureData {
  return {
    scope: "family",
    ledger_id: null,
    portfolio_id: null,
    total_cny: 632543.1,
    position_count: 166,
    view: null,
    ledger_type: null,
    cash_like_cny: 0,
    by_asset_class: [],
    groups: {} as PositionStructureData["groups"],
    concentration: {
      top5_ratio_of_total: 20.72,
      top5_ratio_of_stock: 33.94,
      top5_ratio_of_fund: 37.7
    },
    notes: [],
    ...overrides
  };
}

function makeCash(
  overrides: Partial<CashLikeBreakdown> = {}
): CashLikeBreakdown {
  return {
    items: [],
    total_net_amount: 470264.42,
    total_income_amount: 0,
    total_amount: 470264.42,
    ...overrides
  };
}

function makeDividend(
  overrides: Partial<DividendSummary> = {}
): DividendSummary {
  const zero = {
    cash_cents: 0,
    reinvest_cents: 0,
    tax_cents: 0,
    net_cents: 0,
    event_count: 0,
    split_count: 0
  };
  return {
    as_of: "2026-11-16",
    period: { months: 12, start: "2025-11-16", end: "2026-11-16" },
    totals: {
      ...zero,
      ttm: { ...zero, net_cents: 250964 },
      all_time: zero,
      first_date: null,
      last_date: null
    },
    by_year: [],
    portfolio: {
      ...zero,
      holding_count: 168,
      paying_count: 17,
      cost_cents: 0,
      market_value_cents: 63256732,
      yield_on_cost_pct: 0.21,
      cash_yield_on_cost_pct: 0.21,
      yield_on_value_pct: 0.23,
      reinvest_gain_cents: null
    },
    holdings: [],
    target: {
      configured: false,
      target_yield_pct: null,
      notes: null,
      progress_pct: null,
      gap_pct: null,
      met: null
    },
    ...overrides
  };
}

function makePortfolios(): PortfolioItem[] {
  return [
    { id: 1, name: "A", market_value: 490231.73, target_progress: 163.4 },
    { id: 2, name: "B", market_value: 30187.51, target_progress: 15.1 },
    // 未设目标：既不进均值也不进金额
    { id: 4, name: "C", market_value: 120027.23, target_progress: null }
  ];
}

function makeSummary(overrides: Partial<SummaryData> = {}): SummaryData {
  return { total_assets_cny: 3352922.74, ...overrides } as SummaryData;
}

const allArgs = () => ({
  structure: makeStructure(),
  cashLike: makeCash(),
  dividend: makeDividend(),
  portfolios: makePortfolios(),
  summary: makeSummary()
});

describe("buildFinancialHealthView 四项口径", () => {
  it("四项都从真实响应派生，比率与金额均非空", () => {
    const view = buildFinancialHealthView(allArgs());
    expect(view.metrics).toHaveLength(4);
    for (const m of view.metrics) {
      expect(m.ratio).not.toBeNull();
      expect(m.amount).not.toBeNull();
      expect(m.basis.length).toBeGreaterThan(0);
    }
  });

  it("集中度金额 = 持仓市值 × 后端比率（同源反推，不另算排名）", () => {
    const m = buildFinancialHealthView(allArgs()).metrics[0];
    expect(m.ratio).toBe(20.72);
    expect(m.amount).toBe(Math.round(632543.1 * 0.2072 * 10) / 10);
    expect(m.derivedRatio).toBe(false); // 比率后端直出
  });

  it("类现金占比的分母是家庭总资产，不是持仓市值", () => {
    const m = buildFinancialHealthView(allArgs()).metrics[1];
    expect(m.ratio).toBe(Math.round((470264.42 / 3352922.74) * 1000) / 10);
    expect(m.derivedRatio).toBe(true);
    expect(m.amountNote).toContain("已含在家庭总资产中"); // 防双计提示
  });

  it("分红金额含已清仓、股息率只算在管：脚注写明不同源", () => {
    const m = buildFinancialHealthView(allArgs()).metrics[2];
    expect(m.amount).toBe(2509.64); // 250964 分 → 元
    expect(m.ratio).toBe(0.23); // 后端 yield_on_value_pct
    expect(m.amountNote).toContain("含已清仓");
    expect(m.basis).toContain("在管持仓");
  });

  it("组合达成率只统计已设目标组合，未设目标不进分子也不进分母", () => {
    const m = buildFinancialHealthView(allArgs()).metrics[3];
    expect(m.ratio).toBe(Math.round(((163.4 + 15.1) / 2) * 10) / 10);
    expect(m.amount).toBe(Math.round((490231.73 + 30187.51) * 10) / 10);
    expect(m.basis).toContain("2 个");
  });

  it("分母缺失 / 未设目标一律给 null，绝不写 0", () => {
    const none = buildFinancialHealthView({
      structure: makeStructure({
        total_cny: 0,
        concentration: {
          top5_ratio_of_total: null,
          top5_ratio_of_stock: null,
          top5_ratio_of_fund: null
        }
      }),
      cashLike: makeCash({ total_net_amount: 0 }),
      dividend: null,
      portfolios: [{ id: 9, name: "未设", target_progress: null }],
      summary: makeSummary({ total_assets_cny: 0 })
    });
    for (const m of none.metrics) {
      expect(m.ratio).toBeNull();
    }
    expect(none.metrics[2].amount).toBeNull();
    expect(none.metrics[3].amount).toBeNull();
  });

  it("单项接口失败（null）不影响其余三项照常派生", () => {
    const view = buildFinancialHealthView({
      ...allArgs(),
      dividend: null
    });
    expect(view.metrics[2].ratio).toBeNull();
    expect(view.metrics[0].ratio).toBe(20.72);
    expect(view.metrics[1].ratio).not.toBeNull();
    expect(view.metrics[3].ratio).not.toBeNull();
  });
});
