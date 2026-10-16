/**
 * 走势图买卖点大小口径（#2171 §4.2）。
 *
 * 为什么值得单独立锚点：这是一组**映射公式**（开方 + 上下限 + 密度降档 + 卖点降一档），
 * 算错了只表现为「点看起来差不多大」，肉眼几乎发现不了；而分母为 0 这类边界会让
 * ECharts 默默不画点——**交易记录凭空消失**，比画错更难发现。
 */
import { describe, it, expect } from "vitest";
import {
  DENSE_MAX_SIZE,
  MARKER_MAX_SIZE,
  MARKER_MIN_SIZE,
  SELL_SIZE_RATIO,
  markerMaxSize,
  markerSize,
  maxAmountOf
} from "../trendMarkerMetrics";

describe("markerSize：金额权重 → 直径", () => {
  it("权重为 1 时顶到上限，权重为 0 时落到下限", () => {
    expect(markerSize(1000, 1000, MARKER_MAX_SIZE)).toBe(MARKER_MAX_SIZE);
    expect(markerSize(0, 1000, MARKER_MAX_SIZE)).toBe(MARKER_MIN_SIZE);
  });

  it("按 **√权重** 映射，不是线性（长尾金额不至于把其余点压成米粒）", () => {
    // 权重 0.25：线性会给 6 + 10×0.25 = 8.5；开方给 6 + 10×0.5 = 11
    expect(markerSize(250, 1000, MARKER_MAX_SIZE)).toBe(11);
    // 权重 0.01：线性 6.1，开方 7
    expect(markerSize(10, 1000, MARKER_MAX_SIZE)).toBe(7);
  });

  it("权重超 1 被夹住（同日聚合额可能大于单笔最大值，不能让点无限大）", () => {
    expect(markerSize(5000, 1000, MARKER_MAX_SIZE)).toBe(MARKER_MAX_SIZE);
  });

  it("分母为 0 → 下限，不产生 NaN（NaN 会让 ECharts 默默不画这个点）", () => {
    expect(markerSize(100, 0, MARKER_MAX_SIZE)).toBe(MARKER_MIN_SIZE);
    expect(Number.isNaN(markerSize(0, 0, MARKER_MAX_SIZE))).toBe(false);
    // 负数金额（异常数据）同样落到下限，不产生「反向」尺寸
    expect(markerSize(-100, 1000, MARKER_MAX_SIZE)).toBe(MARKER_MIN_SIZE);
  });
});

describe("markerMaxSize：点数密度降档", () => {
  it("点数 ≤ 20 用满上限", () => {
    expect(markerMaxSize(0)).toBe(MARKER_MAX_SIZE);
    expect(markerMaxSize(20)).toBe(MARKER_MAX_SIZE);
  });

  it("点数 > 20 压低上限（不按周/月聚合——那会改变「哪天操作的」这个事实）", () => {
    expect(markerMaxSize(21)).toBe(DENSE_MAX_SIZE);
    expect(markerMaxSize(200)).toBe(DENSE_MAX_SIZE);
    expect(DENSE_MAX_SIZE).toBeLessThan(MARKER_MAX_SIZE);
  });

  it("分侧计算：买点 30 个不会把 2 个卖点一起压小", () => {
    expect(markerMaxSize(30)).toBe(DENSE_MAX_SIZE);
    expect(markerMaxSize(2)).toBe(MARKER_MAX_SIZE);
  });
});

describe("maxAmountOf：权重分母", () => {
  it("取本侧最大金额；空集为 0（调用方据此走下限分支）", () => {
    expect(
      maxAmountOf([{ amount: 10 }, { amount: 300 }, { amount: 200 }])
    ).toBe(300);
    expect(maxAmountOf([])).toBe(0);
  });
});

describe("卖点比买点小一号（#2171 §4.2）", () => {
  it("同样权重下，卖点直径小于买点，且不越过买点上限", () => {
    const buy = markerSize(1000, 1000, MARKER_MAX_SIZE);
    const sellMax = MARKER_MAX_SIZE * SELL_SIZE_RATIO;
    const sell = markerSize(1000, 1000, sellMax);

    expect(SELL_SIZE_RATIO).toBeLessThan(1);
    expect(sell).toBeLessThan(buy);
    expect(sell).toBeLessThanOrEqual(MARKER_MAX_SIZE);
    // 「小一号」要看得出来，但不能小到分不清——差距落在 20% 上下
    expect(buy - sell).toBeGreaterThan(2);
  });
});
