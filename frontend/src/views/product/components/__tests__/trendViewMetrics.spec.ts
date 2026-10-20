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
  effectiveUseCandle,
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

describe("effectiveUseCandle：当前实际在画什么", () => {
  it("有 OHLCV + 选 K 线 → 真的在画 K 线", () => {
    expect(effectiveUseCandle(60, "candle")).toBe(true);
  });

  it("有 OHLCV + 选折线 → 画的是折线（场内切折线就为看叠加层）", () => {
    expect(effectiveUseCandle(60, "line")).toBe(false);
  });

  it("无 OHLCV（场外基金）→ 无论选中值是什么都画折线", () => {
    // ⚠️ 这条是 #2446 的核心：场外切换器不渲染，选中值恒为初值 'candle'，
    // **没有语义**。判定只能落在「实际在画什么」上。
    expect(effectiveUseCandle(0, "candle")).toBe(false);
    expect(effectiveUseCandle(0, "line")).toBe(false);
  });

  it("只有 1 根 OHLCV → 画不出 K 线形态，退化为折线", () => {
    expect(effectiveUseCandle(1, "candle")).toBe(false);
  });
});

describe("overlayAvailable：买卖点 / 成本线叠加层", () => {
  it("画折线 → 可用；画 K 线 → 不可用（另一套坐标语义）", () => {
    expect(overlayAvailable(false)).toBe(true);
    expect(overlayAvailable(true)).toBe(false);
  });

  it("#2446 回归：场外基金（无 OHLCV）的叠加层必须可用", () => {
    // 反例 = 拿「切换器选中值」当判据：选中值在切换器不渲染时没有语义，
    // 会得到「画的是折线、叠加层却不可用」→ 勾选框可见但买卖点一个都不画。
    expect(showViewToggle(0)).toBe(false); // 前置：切换器不渲染
    expect(overlayAvailable(effectiveUseCandle(0, "candle"))).toBe(true);
  });

  it("#2446 回归：场内 K 线视图下叠加层不可用（要看就切折线）", () => {
    expect(effectiveUseCandle(60, "candle")).toBe(true);
    expect(overlayAvailable(effectiveUseCandle(60, "candle"))).toBe(false);
    expect(overlayAvailable(effectiveUseCandle(60, "line"))).toBe(true);
  });
});

describe("TREND_VIEW_OPTIONS", () => {
  it("K 线在前（场内默认视图，既有观感不变）", () => {
    expect(TREND_VIEW_OPTIONS.map(o => o.value)).toEqual(["candle", "line"]);
    expect(TREND_VIEW_OPTIONS[0].label).toBe("K线");
  });
});
