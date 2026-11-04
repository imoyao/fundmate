import { describe, expect, it } from "vitest";
import type { AdvisorProfileResult } from "@/api/products";
import {
  DASH,
  buildReturnMetrics,
  buildRiskMetrics,
  fmtPct,
  riseFallClass,
  strategyText
} from "../advisorModel";

const profile = (over: Partial<AdvisorProfileResult> = {}) =>
  ({ ...over }) as unknown as AdvisorProfileResult;

describe("buildReturnMetrics：只渲染有值的项", () => {
  it("没有档案 → 空（不画一排「—」）", () => {
    expect(buildReturnMetrics(null)).toEqual([]);
    expect(buildReturnMetrics(undefined)).toEqual([]);
  });

  it("全 null → 空数组", () => {
    expect(buildReturnMetrics(profile())).toEqual([]);
  });

  it("保留有值的项，且顺序固定（近1月 → 年化）", () => {
    const rows = buildReturnMetrics(
      profile({ annual_return: 8.1, return_1m: 1.2, return_3m: null } as never)
    );
    expect(rows.map(r => r.label)).toEqual(["近 1 月", "年化"]);
  });

  it("0 是有效值（0% 收益要显示，不是缺失）", () => {
    const rows = buildReturnMetrics(profile({ return_1m: 0 } as never));
    expect(rows).toHaveLength(1);
    expect(rows[0].value).toBe(0);
  });
});

describe("buildRiskMetrics：与收益分开、不涂涨跌色", () => {
  it("缺失项不出现", () => {
    expect(buildRiskMetrics(null)).toEqual([]);
    expect(buildRiskMetrics(profile())).toEqual([]);
  });

  it("回撤 / 波动率按百分比 2 位，夏普按比值 3 位", () => {
    const rows = buildRiskMetrics(
      profile({
        max_drawdown: -12.345,
        volatility: 18.6,
        sharpe_ratio: 0.9876
      } as never)
    );
    expect(rows).toEqual([
      { label: "最大回撤", text: "-12.35%" },
      { label: "年化波动率", text: "18.60%" },
      { label: "夏普比率", text: "0.988" }
    ]);
  });

  it("0 夏普仍然渲染（0 是「没有超额」，不是缺失）", () => {
    const rows = buildRiskMetrics(profile({ sharpe_ratio: 0 } as never));
    expect(rows).toEqual([{ label: "夏普比率", text: "0.000" }]);
  });
});

describe("strategyText：摘优先于详情", () => {
  it("两者都有时取短的摘要", () => {
    expect(
      strategyText(
        profile({ strategy_summary: "摘要", strategy_desc: "长详情" } as never)
      )
    ).toBe("摘要");
  });

  it("只有详情时退回详情", () => {
    expect(strategyText(profile({ strategy_desc: "长详情" } as never))).toBe(
      "长详情"
    );
  });

  it("都没有返回空串（模板按 falsy 跳过整段）", () => {
    expect(strategyText(profile())).toBe("");
    expect(strategyText(null)).toBe("");
  });
});

describe("fmtPct / riseFallClass", () => {
  it("正数显式带 +，负数带自己的符号", () => {
    expect(fmtPct(2.5)).toBe("+2.50%");
    expect(fmtPct(-2.5)).toBe("-2.50%");
    expect(fmtPct(0)).toBe("0.00%");
  });

  it("缺失降级「—」", () => {
    expect(fmtPct(null)).toBe(DASH);
  });

  it("0 与缺失都不涂色", () => {
    expect(riseFallClass(0)).toBe("");
    expect(riseFallClass(null)).toBe("");
  });

  it("正负分档走文字级色 class", () => {
    expect(riseFallClass(0.01)).toBe("is-rise");
    expect(riseFallClass(-0.01)).toBe("is-fall");
  });
});
