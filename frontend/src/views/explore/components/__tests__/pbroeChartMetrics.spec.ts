/**
 * 行业 PB-ROE 散点数据口径测试（#2481）。
 *
 * 重点钉：负 ROE 行业（房地产实测 -16.78）**不被过滤**——
 * 「收益率为负就剔点」是净值曲线的惯性，在 PB-ROE 模型下是错的。
 */
import { describe, it, expect } from "vitest";
import { toScatterPoints, hasScatterPoints } from "../pbroeChartMetrics";
import type { IndustryPbroePoint } from "@/api/market";

const point = (over: Partial<IndustryPbroePoint>): IndustryPbroePoint => ({
  industry: "某行业",
  roe: 1,
  pb: 1,
  ...over
});

describe("toScatterPoints", () => {
  it("负 ROE 行业保留（房地产 -16.78 是有效点）", () => {
    const pts = toScatterPoints([point({ industry: "房地产", roe: -16.78, pb: 0.78 })]);
    expect(pts).toHaveLength(1);
    expect(pts[0].roe).toBe(-16.78);
  });

  it("roe/pb 缺失的点过滤（上游形态异常防御）", () => {
    const pts = toScatterPoints([
      point({ industry: "农林牧渔", roe: 2.71, pb: 2.4 }),
      point({ industry: "坏点A", roe: null, pb: 2.4 }),
      point({ industry: "坏点B", roe: 2.71, pb: null })
    ]);
    expect(pts.map(p => p.industry)).toEqual(["农林牧渔"]);
  });

  it("null / undefined 序列回空数组", () => {
    expect(toScatterPoints(null)).toEqual([]);
    expect(toScatterPoints(undefined)).toEqual([]);
  });
});

describe("hasScatterPoints", () => {
  it("全坏点等同无数据（走同一条空态提示）", () => {
    expect(hasScatterPoints([point({ roe: null, pb: null })])).toBe(false);
    expect(hasScatterPoints(null)).toBe(false);
    expect(hasScatterPoints([])).toBe(false);
  });

  it("有有效点为 true", () => {
    expect(hasScatterPoints([point({ roe: 0, pb: 0 })])).toBe(true);
  });
});
