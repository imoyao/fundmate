/**
 * 持仓重叠度面板纯逻辑的回归网（#2604）。
 *
 * 判据纪律：断言完整行为，不只断言「函数存在」。
 * **本文件钉的是最要命的那条纪律**：「pairs 为空」有三种完全不同的成因，
 * 一律渲染成「重叠 0%」就是**错误安心** —— 用户会以为查过了、结果是零重合。
 * 1. 取数失败（degraded）→ 「暂时取不到」；
 * 2. 可比基金不足 2 只 → 「算不出」；
 * 3. 算出来了且 pairs 为空 → 结论是**确实不重叠**。
 */
import { describe, it, expect } from "vitest";
import {
  describeBasis,
  describeCoverage,
  describePeriodMismatch,
  describeSkipped,
  formatJaccard,
  formatWeightedOverlap,
  resolveOverlapPanelState
} from "../holdingOverlapModel";
import type { HoldingOverlapData, OverlapPair } from "../holdingOverlapModel";

const pair = (over: Partial<OverlapPair> = {}): OverlapPair => ({
  fund_code_a: "110011",
  fund_name_a: "易方达优质精选",
  report_period_a: "2026Q2",
  fund_code_b: "005827",
  fund_name_b: "易方达蓝筹精选",
  report_period_b: "2026Q2",
  holding_basis: "top10",
  jaccard: 0.42,
  weighted_overlap: 18.6,
  common_holdings: [
    {
      stock_code: "600519",
      stock_name: "贵州茅台",
      ratio_a: 9.8,
      ratio_b: 8.4,
      min_ratio: 8.4
    }
  ],
  ...over
});

const data = (over: Partial<HoldingOverlapData> = {}): HoldingOverlapData => ({
  pairs: [pair()],
  fund_count: 3,
  skipped_basis_mismatch: 0,
  skipped_null_ratio: 0,
  total_market_value_cents: 1_000_000,
  coverage_pct: 82.5,
  uncovered: [],
  degraded: false,
  source: "fund_holdings",
  ...over
});

describe("重叠度面板状态判定（#2604）", () => {
  it("取数失败时是「暂时取不到」，不是「没有重叠」", () => {
    expect(resolveOverlapPanelState(data({ degraded: true, pairs: [] }))).toBe(
      "degraded"
    );
    expect(resolveOverlapPanelState(null)).toBe("degraded");
  });

  it("可比基金不足 2 只是「算不出」，不是「不重叠」", () => {
    expect(resolveOverlapPanelState(data({ fund_count: 1, pairs: [] }))).toBe(
      "not-computable"
    );
    expect(resolveOverlapPanelState(data({ fund_count: 0, pairs: [] }))).toBe(
      "not-computable"
    );
  });

  it("算出来了且没有共同重仓股，结论才是「确实不重叠」", () => {
    expect(resolveOverlapPanelState(data({ fund_count: 3, pairs: [] }))).toBe(
      "no-overlap"
    );
  });

  it("有重叠对时是「有重叠」", () => {
    expect(resolveOverlapPanelState(data())).toBe("has-pairs");
  });
});

describe("重叠度数值展示（#2604）", () => {
  it("加权口径按百分点展示", () => {
    // 用 18.66 而不是 18.65：后者在 IEEE754 下是 18.64999…，toFixed(1) 得 "18.6"
    expect(formatWeightedOverlap(18.66)).toBe("18.7%");
    expect(formatWeightedOverlap(18.6)).toBe("18.6%");
  });

  it("集合口径从 0~1 转成百分比", () => {
    expect(formatJaccard(0.42)).toBe("42%");
  });

  it("缺失值显示「—」而不是 0", () => {
    expect(formatWeightedOverlap(null)).toBe("—");
    expect(formatJaccard(undefined)).toBe("—");
    expect(formatJaccard(Number.NaN)).toBe("—");
  });
});

describe("重叠度口径说明（#2604）", () => {
  it("披露口径给出中文名", () => {
    expect(describeBasis("full")).toContain("全量");
    expect(describeBasis("top10")).toContain("前十大");
    expect(describeBasis("")).toBe("口径未知");
  });

  it("报告期错配时提示时点差，报告期相同则不提示", () => {
    expect(
      describePeriodMismatch(pair({ report_period_b: "2026Q1" }))
    ).toContain("报告期不同");
    expect(describePeriodMismatch(pair())).toBe("");
  });

  it("覆盖率说明带基金数", () => {
    expect(describeCoverage(data())).toContain("82.5%");
    expect(describeCoverage(data())).toContain("3");
  });

  it("披露口径不同而被跳过的对数要如实说出来", () => {
    const text = describeSkipped(data({ skipped_basis_mismatch: 2 }));
    expect(text).toContain("2");
    expect(text).toContain("披露口径");
  });

  it("占比缺失被排除的行数也要说出来", () => {
    const text = describeSkipped(data({ skipped_null_ratio: 5 }));
    expect(text).toContain("5");
    expect(text).toContain("占比缺失");
  });

  it("没有跳过项时不给空文案", () => {
    expect(describeSkipped(data())).toBe("");
  });
});
