/**
 * 组合风格面板纯逻辑的回归网（#2603）。
 *
 * 判据纪律：断言完整行为，不只断言「函数存在」。
 * 重点是三处容易做错的口径：
 * 1. **「算不出来」与「算出来很均衡」必须分开** —— styles 为空是前者，不是「全部为 0」；
 * 2. **覆盖率不足时结论要降级** —— 不能拿少量样本说「某风格占 62%」；
 * 3. **QDII 的风格分类口径存疑**，含 QDII 时必须让用户看见这句说明。
 */
import { describe, it, expect } from "vitest";
import {
  STYLE_COVERAGE_FLOOR,
  describeQdiiCaveat,
  describeStyleCoverage,
  describeUncovered,
  formatStyleValue,
  resolveStylePanelState,
  styleBarWidth
} from "../portfolioStyleModel";
import type { PortfolioStyleData } from "../portfolioStyleModel";

const data = (over: Partial<PortfolioStyleData> = {}): PortfolioStyleData => ({
  styles: [
    { style_name: "大盘成长", value: 45.2 },
    { style_name: "中盘价值", value: 30.1 },
    { style_name: "固收风格", value: 24.7 }
  ],
  fund_count: 4,
  coverage_pct: 88.6,
  period_from: "2026-09-30",
  period_to: "2026-09-30",
  uncovered: [],
  has_qdii: false,
  ...over
});

describe("风格面板状态判定（#2603）", () => {
  it("没有风格数据时是「算不出来」而不是「全部为 0」", () => {
    expect(resolveStylePanelState(data({ styles: [] }))).toBe("empty");
    expect(resolveStylePanelState(null)).toBe("empty");
    expect(resolveStylePanelState(undefined)).toBe("empty");
  });

  it("覆盖率不足时降级为「算得不全」", () => {
    expect(
      resolveStylePanelState(
        data({ coverage_pct: STYLE_COVERAGE_FLOOR - 0.01 })
      )
    ).toBe("low-coverage");
  });

  it("覆盖率达标时是「算得全」", () => {
    expect(resolveStylePanelState(data())).toBe("ready");
    expect(
      resolveStylePanelState(data({ coverage_pct: STYLE_COVERAGE_FLOOR }))
    ).toBe("ready");
  });
});

describe("风格数值展示（#2603）", () => {
  it("缺失值显示「—」而不是 0", () => {
    expect(formatStyleValue(null)).toBe("—");
    expect(formatStyleValue(undefined)).toBe("—");
    expect(formatStyleValue(Number.NaN)).toBe("—");
  });

  it("正常值保留一位小数", () => {
    expect(formatStyleValue(45.26)).toBe("45.3%");
    expect(formatStyleValue(0)).toBe("0.0%");
  });

  it("条形宽度夹在 0~100%，异常值不撑破布局", () => {
    expect(styleBarWidth(45.2)).toBe("45.2%");
    expect(styleBarWidth(-3)).toBe("0%");
    expect(styleBarWidth(180)).toBe("100%");
    expect(styleBarWidth(null)).toBe("0%");
  });
});

describe("风格口径说明（#2603）", () => {
  it("覆盖率文案带基金数", () => {
    expect(describeStyleCoverage(data())).toContain("88.6%");
    expect(describeStyleCoverage(data())).toContain("4");
  });

  it("未覆盖持仓如实在文案里列出", () => {
    const text = describeUncovered(
      data({
        uncovered: [
          { symbol: "000001", name: "华夏成长", market_value_cents: 100 },
          { symbol: "000002", name: "易方达蓝筹", market_value_cents: 200 }
        ]
      })
    );
    expect(text).toContain("华夏成长");
    expect(text).toContain("易方达蓝筹");
    expect(text).toContain("2");
  });

  it("未覆盖持仓超过 3 个时给总数而不是全列", () => {
    const text = describeUncovered(
      data({
        uncovered: [
          { symbol: "1", name: "甲", market_value_cents: 1 },
          { symbol: "2", name: "乙", market_value_cents: 1 },
          { symbol: "3", name: "丙", market_value_cents: 1 },
          { symbol: "4", name: "丁", market_value_cents: 1 },
          { symbol: "5", name: "戊", market_value_cents: 1 }
        ]
      })
    );
    expect(text).toContain("甲、乙、丙");
    expect(text).not.toContain("丁");
    expect(text).toContain("5");
  });

  it("没有未覆盖持仓时不给空文案", () => {
    expect(describeUncovered(data())).toBe("");
  });

  it("含 QDII 时给出口径存疑说明，不含时不出现", () => {
    expect(describeQdiiCaveat(data({ has_qdii: true }))).toContain("QDII");
    expect(describeQdiiCaveat(data({ has_qdii: true }))).toContain("存疑");
    expect(describeQdiiCaveat(data({ has_qdii: false }))).toBe("");
  });
});
