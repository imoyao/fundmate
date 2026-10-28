import { describe, expect, it } from "vitest";

import type { FundStyleItem, PortfolioStyleExposure } from "@/api/funds";
import {
  buildStyleBars,
  formatCoverage,
  isStyleEmpty,
  leadStyleLabel,
  periodLabel,
  uncoveredSummary
} from "../styleDistributionModel";

/**
 * 家庭级基金风格分布（#2628）的判据。
 *
 * 为什么值得单测：这张卡的两个错误形态肉眼都看不出来——
 * ① 把「算不出来」（styles 空数组）画成「全部 0%」的满格空条；
 * ② 全 0 时把第一条染色当「主导风格」，凭空造出一个结论。
 * 两者都「看起来有图表」，但说的是假话。
 */

const STYLES: FundStyleItem[] = [
  { style_name: "大盘成长", value: 3.02 },
  { style_name: "大盘价值", value: 41.84 },
  { style_name: "中盘成长", value: 7.47 },
  { style_name: "中盘价值", value: 5.35 },
  { style_name: "小盘成长", value: 8.75 },
  { style_name: "小盘价值", value: 27.94 },
  { style_name: "港股风格", value: 5.62 },
  { style_name: "固收风格", value: 0 }
];

const DATA: PortfolioStyleExposure = {
  styles: STYLES,
  fund_count: 2,
  covered_market_value_cents: 3173034,
  total_market_value_cents: 37990734,
  coverage_pct: 8.35,
  // 真实场景（#2628）：8.35% 是全量口径被货基稀释的结果，可覆盖口径其实 100%
  eligible_market_value_cents: 3173034,
  eligible_coverage_pct: 100,
  period_from: "2026-10-23",
  period_to: "2026-10-23",
  uncovered: [
    { symbol: "SH515120", name: "创新药", market_value_cents: 2432000 },
    { symbol: "023887", name: "永赢北证50", market_value_cents: 2291340 }
  ],
  has_qdii: false,
  source: "jiucaishuo_style"
};

describe("buildStyleBars", () => {
  it("保留后端给出的展示顺序，宽度等于暴露值（合计 100）", () => {
    const bars = buildStyleBars(STYLES);
    expect(bars.map(b => b.name)).toEqual(STYLES.map(s => s.style_name));
    expect(bars.find(b => b.name === "大盘价值")?.widthPct).toBeCloseTo(
      41.84,
      5
    );
  });

  it("只给最大值那一条上强调（并列取第一条）", () => {
    const bars = buildStyleBars(STYLES);
    expect(bars.filter(b => b.isLead).map(b => b.name)).toEqual(["大盘价值"]);
    expect(leadStyleLabel(bars)).toBe("大盘价值");
  });

  it("全 0 时不制造「主导风格」", () => {
    const zero = STYLES.map(s => ({ ...s, value: 0 }));
    const bars = buildStyleBars(zero);
    expect(bars.every(b => !b.isLead)).toBe(true);
    expect(leadStyleLabel(bars)).toBeNull();
  });

  it("null 暴露值归一为 0，且宽度不会越界", () => {
    const bars = buildStyleBars([
      { style_name: "大盘成长", value: null },
      { style_name: "大盘价值", value: 120 }
    ]);
    expect(bars[0].value).toBe(0);
    expect(bars[1].widthPct).toBe(100);
  });
});

describe("isStyleEmpty", () => {
  it("styles 为空数组 = 算不出来（后端明示 ≠ 全部为 0）", () => {
    expect(isStyleEmpty(data0())).toBe(true);
    expect(isStyleEmpty(null)).toBe(true);
    expect(isStyleEmpty(DATA)).toBe(false);
  });

  it("即使总市值 > 0，只要没有箱体仍判为空", () => {
    const d = { ...DATA, styles: [], fund_count: 0, coverage_pct: 0 };
    expect(isStyleEmpty(d)).toBe(true);
  });
});

describe("formatCoverage", () => {
  it("小数值保留两位（首批覆盖率往往只有个位数，取整会抹掉信息）", () => {
    expect(formatCoverage(8.35)).toBe("8.35%");
    expect(formatCoverage(0.4)).toBe("0.4%");
  });

  it("两位数百分比后取整，避免假精度", () => {
    expect(formatCoverage(41.84)).toBe("42%");
    expect(formatCoverage(100)).toBe("100%");
  });

  it("非法 / 零值统一 0%", () => {
    expect(formatCoverage(0)).toBe("0%");
    expect(formatCoverage(Number.NaN)).toBe("0%");
  });
});

describe("uncoveredSummary / periodLabel", () => {
  it("折叠摘要只切前 N 只，剩余给计数", () => {
    const list = Array.from({ length: 7 }, (_, i) => ({
      symbol: `00${i}`,
      name: `基金${i}`,
      market_value_cents: 100
    }));
    const { shown, restCount } = uncoveredSummary(list, 5);
    expect(shown).toHaveLength(5);
    expect(restCount).toBe(2);
  });

  it("时点同日只显示一天，跨月显示区间", () => {
    expect(periodLabel(DATA)).toBe("2026-10-23");
    expect(
      periodLabel({
        ...DATA,
        period_from: "2026-09-30",
        period_to: "2026-10-23"
      })
    ).toBe("2026-09-30 ~ 2026-10-23");
    expect(periodLabel({ ...DATA, period_to: null })).toBeNull();
  });
});

function data0(): PortfolioStyleExposure {
  return {
    ...DATA,
    styles: [],
    fund_count: 0,
    coverage_pct: 0,
    period_from: null,
    period_to: null,
    uncovered: []
  };
}
