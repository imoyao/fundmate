/**
 * 财务晴雨表六项健康度的口径判据（#3165 四项 + v2 两项自由度，纯函数 node 环境可测）。
 *
 * 钉的是最容易退化的边界：
 * 1. null 不是 0：分母缺失 / 未配置 / 无现金流必须给 null，组件显示「—」；
 * 2. 集中度金额同源：金额只能由「持仓市值 × 后端比率」反推；
 * 3. 类现金分母是家庭总资产，金额已含在总资产里；
 * 4. XIRR 无现金流时后端给 0.0 假值，必须守卫为 null（不能显示 0% 收益）；
 * 5. 自由度分子（年可提取额 = 可投资资产×3%）与配置无关恒真实，分母未配置才 null；
 * 6. 可投资资产只认 cash + investment 两项，缺一项宁可给 null（金额偏小比没有更坏）。
 */
import { describe, expect, it } from "vitest";
import type { PositionStructureData, CashLikeBreakdown } from "@/api/summary";
import type { XirrData } from "@/api/performance";
import type { AssetSummaryItem } from "@/api/assets";
import type { FinancialPlanData } from "@/api/financialPlan";
import type { SummaryData } from "@/api/types";
import {
  buildFinancialHealthView,
  SAFE_WITHDRAWAL_RATE
} from "../financialHealth";

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

function makeSummary(overrides: Partial<SummaryData> = {}): SummaryData {
  return {
    total_assets_cny: 3352922.74,
    total_liabilities_cny: 126812.5,
    liability_ratio: 3.78,
    ...overrides
  } as SummaryData;
}

function makeXirr(overrides: Partial<XirrData> = {}): XirrData {
  return {
    xirr: 0.087,
    cashflow_count: 42,
    total_return: 286000,
    total_invested: 1000000,
    total_withdrawn: 0,
    current_value: 1286000,
    ...overrides
  };
}

function makeAssets(): AssetSummaryItem[] {
  return [
    { code: "investment", label: "投资理财", value: 2200000 },
    { code: "cash", label: "流动资金", value: 830000 },
    { code: "liability", label: "负债", value: -126812.5 }
  ];
}

const allArgs = () => ({
  structure: makeStructure(),
  cashLike: makeCash(),
  summary: makeSummary(),
  xirr: makeXirr(),
  assetsSummary: makeAssets(),
  plan: {
    estimated_annual_expense: 120000,
    estimated_annual_income: 300000
  } as FinancialPlanData
});

describe("buildFinancialHealthView 六项口径", () => {
  it("六项都从真实响应派生，比率与金额均非空", () => {
    const view = buildFinancialHealthView(allArgs());
    expect(view.metrics).toHaveLength(6);
    for (const m of view.metrics) {
      expect(m.ratio).not.toBeNull();
      expect(m.amount).not.toBeNull();
      expect(m.basis.length).toBeGreaterThan(0);
      expect(["asset", "freedom"]).toContain(m.group);
    }
  });

  it("资产负债率比率后端直出、金额是总负债", () => {
    const m = buildFinancialHealthView(allArgs()).metrics[0];
    expect(m.key).toBe("liability");
    expect(m.ratio).toBe(3.78);
    expect(m.amount).toBe(126812.5);
  });

  it("投资年化收益率把 XIRR 小数转百分数，金额是累计收益（不同源）", () => {
    const m = buildFinancialHealthView(allArgs()).metrics[1];
    expect(m.ratio).toBe(8.7); // 0.087 × 100
    expect(m.amount).toBe(286000);
    expect(m.amountNote).toContain("口径不同");
  });

  it("XIRR 无现金流（后端给 0.0 假值）必须守卫为 null，不能显示 0%", () => {
    const view = buildFinancialHealthView({
      ...allArgs(),
      xirr: makeXirr({ xirr: 0, cashflow_count: 0, total_return: 0 })
    });
    const m = view.metrics[1];
    expect(m.ratio).toBeNull();
    expect(m.amount).toBeNull();
  });

  it("集中度金额 = 持仓市值 × 后端比率（同源反推，不另算排名）", () => {
    const m = buildFinancialHealthView(allArgs()).metrics[2];
    expect(m.ratio).toBe(20.72);
    expect(m.amount).toBe(Math.round(632543.1 * 0.2072 * 10) / 10);
    expect(m.derivedRatio).toBe(false);
  });

  it("类现金占比的分母是家庭总资产，不是持仓市值", () => {
    const m = buildFinancialHealthView(allArgs()).metrics[3];
    expect(m.ratio).toBe(Math.round((470264.42 / 3352922.74) * 1000) / 10);
    expect(m.derivedRatio).toBe(true);
    expect(m.amountNote).toContain("已含在家庭总资产中");
  });

  it("财务自由度 = 可投资资产×3% / 年支出，分子恒真实", () => {
    const m = buildFinancialHealthView(allArgs()).metrics[4];
    // 可投资资产 = 2200000 + 830000 = 3030000；×3% = 90900
    expect(m.amount).toBe(round(3030000 * SAFE_WITHDRAWAL_RATE));
    expect(m.amount).toBe(90900);
    // 90900 / 120000 = 75.75% → 75.8%
    expect(m.ratio).toBe(75.8);
    expect(m.needsConfig).toBe(false);
  });

  it("时间自由度 = 可投资资产×3% / 年收入", () => {
    const m = buildFinancialHealthView(allArgs()).metrics[5];
    expect(m.amount).toBe(90900);
    expect(m.ratio).toBe(30.3); // 90900 / 300000
  });

  it("自由度分母未配置：金额照显（分子真实），比率 null + needsConfig 引导", () => {
    const view = buildFinancialHealthView({
      ...allArgs(),
      plan: { estimated_annual_expense: null, estimated_annual_income: null }
    });
    const ff = view.metrics[4];
    const tf = view.metrics[5];
    expect(ff.amount).toBe(90900); // 分子与配置无关
    expect(ff.ratio).toBeNull();
    expect(ff.needsConfig).toBe(true);
    expect(ff.amountNote).toContain("个人中心");
    expect(tf.amount).toBe(90900);
    expect(tf.ratio).toBeNull();
    expect(tf.needsConfig).toBe(true);
  });

  it("可投资资产缺 cash 或 investment 任一项 → 自由度金额 null（不显示偏小数）", () => {
    for (const missing of ["cash", "investment"]) {
      const view = buildFinancialHealthView({
        ...allArgs(),
        assetsSummary: makeAssets().filter(a => a.code !== missing)
      });
      expect(view.metrics[4].amount).toBeNull();
      expect(view.metrics[5].amount).toBeNull();
      expect(view.metrics[4].ratio).toBeNull();
    }
  });

  it("负债与类现金接口失败（null）不影响其余四格照常派生", () => {
    const view = buildFinancialHealthView({
      ...allArgs(),
      summary: null,
      cashLike: null
    });
    expect(view.metrics[0].ratio).toBeNull(); // 负债率缺 summary
    expect(view.metrics[3].ratio).toBeNull(); // 类现金缺 cashLike
    expect(view.metrics[1].ratio).toBe(8.7);
    expect(view.metrics[2].ratio).toBe(20.72);
    expect(view.metrics[4].ratio).toBe(75.8); // 自由度不依赖这两项
  });
});

const round = (n: number) => Math.round(n * 10) / 10;
