import { describe, expect, it } from "vitest";
import {
  MARQUEE_SPEED_PX_PER_SEC,
  MAX_INDEX_COUNT,
  marqueeDurationSeconds,
  shouldMarquee
} from "@/views/asset/watchlist/composables/indexBarModel";

describe("shouldMarquee", () => {
  it("内容窄于容器时不启用（放得下就别晃）", () => {
    expect(shouldMarquee(600, 1080)).toBe(false);
  });

  it("内容与容器等宽时不启用", () => {
    expect(shouldMarquee(1080, 1080)).toBe(false);
  });

  it("只超出 1px 视为亚像素舍入，不算溢出", () => {
    expect(shouldMarquee(1081, 1080)).toBe(false);
    expect(shouldMarquee(1082, 1080)).toBe(true);
  });

  it("量不到宽度（0 / NaN）时不启用，避免误判成分溢出", () => {
    expect(shouldMarquee(500, 0)).toBe(false);
    expect(shouldMarquee(Number.NaN, 1080)).toBe(false);
    expect(shouldMarquee(500, Number.NaN)).toBe(false);
  });
});

describe("marqueeDurationSeconds", () => {
  it("一圈时长 = 内容宽 ÷ 恒定速度", () => {
    expect(marqueeDurationSeconds(1400)).toBeCloseTo(50, 5);
  });

  it("内容翻倍时时长翻倍、速度不变（不会「选得越多跑得越快」）", () => {
    const short = marqueeDurationSeconds(1400);
    const long = marqueeDurationSeconds(2800);
    expect(long).toBeCloseTo(short * 2, 5);
    expect(1400 / short).toBeCloseTo(MARQUEE_SPEED_PX_PER_SEC, 5);
    expect(2800 / long).toBeCloseTo(MARQUEE_SPEED_PX_PER_SEC, 5);
  });

  it("非法速度回落到默认速度，不产生 Infinity", () => {
    expect(marqueeDurationSeconds(1400, 0)).toBeCloseTo(50, 5);
    expect(Number.isFinite(marqueeDurationSeconds(1400, -1))).toBe(true);
    expect(Number.isFinite(marqueeDurationSeconds(1400, Number.NaN))).toBe(
      true
    );
  });

  it("宽度为 0 / 非法时时长为 0（不启动动画）", () => {
    expect(marqueeDurationSeconds(0)).toBe(0);
    expect(marqueeDurationSeconds(Number.NaN)).toBe(0);
  });
});

describe("MAX_INDEX_COUNT", () => {
  // 改动这个数必须同步复核两件事：① 每 30s 的分时请求量 = N；② 展开态网格是否仍为两行
  it("上限为 8（请求量与展开高度两条约束的交点）", () => {
    expect(MAX_INDEX_COUNT).toBe(8);
  });
});
