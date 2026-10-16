/**
 * 走势卡视图口径（#2171 后续：场内 K线 / 折线）。
 *
 * 钉住三条容易悄悄退化的口径：
 * 1. 场外（无 OHLCV）**不给**视图切换器（假选择）；
 * 2. 成交量副图只在 K 线视图出现（折线视图留一个空格子就是半吊子）；
 * 3. 买卖点 / 成本线叠加层只在折线视图可用（K 线是另一套坐标语义）。
 */
import { describe, it, expect } from "vitest";
import {
  TREND_VIEW_OPTIONS,
  overlayAvailable,
  showViewToggle,
  showVolumeSeries
} from "../trendViewMetrics";

describe("showViewToggle：谁能有视图切换", () => {
  it("有 OHLCV（≥2 根）→ 场内，给切换器", () => {
    expect(showViewToggle(2)).toBe(true);
    expect(showViewToggle(60)).toBe(true);
  });

  it("无 OHLCV → 场外基金 / 指数，**不给**切换器（只有一条线，切换是假选择）", () => {
    expect(showViewToggle(0)).toBe(false);
  });

  it("只有 1 根 → 不算（画不出 K 线形态），与 isCandle 判据一致", () => {
    expect(showViewToggle(1)).toBe(false);
  });
});

describe("showVolumeSeries：成交量副图", () => {
  it("K 线视图 + 有量能数据 → 显示", () => {
    expect(showVolumeSeries("candle", true)).toBe(true);
  });

  it("折线视图**一律不显示**（哪怕有量能数据）——否则会留一个空网格", () => {
    expect(showVolumeSeries("line", true)).toBe(false);
    expect(showVolumeSeries("line", false)).toBe(false);
  });

  it("K 线视图但整段无量能 → 也不显示（不占版面）", () => {
    expect(showVolumeSeries("candle", false)).toBe(false);
  });
});

describe("overlayAvailable：买卖点 / 成本线叠加层", () => {
  it("只在折线视图可用", () => {
    expect(overlayAvailable("line")).toBe(true);
    expect(overlayAvailable("candle")).toBe(false);
  });
});

describe("TREND_VIEW_OPTIONS", () => {
  it("K 线在前（场内默认视图，既有观感不变）", () => {
    expect(TREND_VIEW_OPTIONS.map(o => o.value)).toEqual(["candle", "line"]);
    expect(TREND_VIEW_OPTIONS[0].label).toBe("K线");
  });
});
