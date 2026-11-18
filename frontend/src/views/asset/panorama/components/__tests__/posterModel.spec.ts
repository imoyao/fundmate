import { describe, expect, it } from "vitest";

import {
  buildPosterData,
  formatYuan,
  slicePercentages,
  type PosterSlice
} from "../posterModel";

/**
 * 海报数据模型的判据（#1016）。
 *
 * 钉的是「图上说了什么」而非像素：金额不印 NaN、占比分母是资产口径、
 * 空账户/脏数据下降级为 0 而不是崩——这正是 #1016 验收「弱网下不崩」
 * 在数据层的体现（网络失败时数据为空，绘制路径不能抛）。
 */

describe("formatYuan", () => {
  it("正数：¥ + 千分位 + 两位小数", () => {
    expect(formatYuan(1234567.891)).toBe("¥1,234,567.89");
  });

  it("负数：符号在前，金额取绝对值", () => {
    expect(formatYuan(-1234.5)).toBe("-¥1,234.50");
  });

  it("脏数据（NaN / Infinity）：回退 ¥0.00，不印 NaN", () => {
    expect(formatYuan(NaN)).toBe("¥0.00");
    expect(formatYuan(Infinity)).toBe("¥0.00");
  });

  it("零：¥0.00", () => {
    expect(formatYuan(0)).toBe("¥0.00");
  });
});

describe("slicePercentages", () => {
  it("占比分母为各项之和，结果保留一位小数", () => {
    // 250 / (250+250+500) = 25%, 25%, 50%
    expect(slicePercentages([250, 250, 500])).toEqual([25, 25, 50]);
  });

  it("非整除：每项独立四舍五入到一位小数", () => {
    // 1/3 = 33.3%，三项各自舍入（合计 99.9 是舍入的必然结果，不强凑到 100）
    expect(slicePercentages([1, 1, 1])).toEqual([33.3, 33.3, 33.3]);
  });

  it("分母为 0（空账户）：全部 0，不产生 NaN", () => {
    expect(slicePercentages([])).toEqual([]);
    expect(slicePercentages([0, 0])).toEqual([0, 0]);
  });

  it("负数/非有限值当 0，不会让分母变负", () => {
    expect(slicePercentages([-100, 100])).toEqual([0, 100]);
    expect(slicePercentages([NaN, 50, Infinity])).toEqual([0, 100, 0]);
  });
});

const base = {
  date: "2026-11-18",
  totalAssets: 1_000_000,
  totalLiabilities: 200_000,
  netAssets: 800_000,
  totalPnl: -12_345.67,
  colors: ["#e34f38", "#f0a202", "#3a7ca5"]
};

describe("buildPosterData", () => {
  it("金额走后端口径直出：总资产/净资产/负债/盈亏各就各位", () => {
    const data = buildPosterData({
      ...base,
      categories: [
        { name: "基金", value: 600_000 },
        { name: "股票", value: 400_000 }
      ]
    });
    expect(data.figures.map(f => [f.label, f.value])).toEqual([
      ["总资产", 1_000_000],
      ["净资产", 800_000],
      ["总负债", 200_000],
      ["总盈亏", -12_345.67]
    ]);
    expect(data.figures.find(f => f.label === "总盈亏")?.semantic).toBe("pnl");
  });

  it("负债不进资产分布：slices 只含正值的资产大类", () => {
    const data = buildPosterData({
      ...base,
      categories: [
        { name: "基金", value: 600_000 },
        { name: "负债", value: -200_000 },
        { name: "现金", value: 0 }
      ]
    });
    expect(data.slices.map(s => s.label)).toEqual(["基金"]);
  });

  it("颜色循环取值，类别多于颜色也不越界", () => {
    const data = buildPosterData({
      ...base,
      colors: ["#aaa"],
      categories: [
        { name: "A", value: 1 },
        { name: "B", value: 1 },
        { name: "C", value: 1 }
      ]
    });
    expect(data.slices.map(s => s.color)).toEqual(["#aaa", "#aaa", "#aaa"]);
  });

  it("空数据：slices 为空，figures 仍给出 0 值（不崩、不印 NaN）", () => {
    const data = buildPosterData({
      ...base,
      totalAssets: 0,
      totalLiabilities: 0,
      netAssets: 0,
      totalPnl: 0,
      categories: []
    });
    expect(data.slices).toEqual([]);
    expect(data.figures.every(f => f.value === 0)).toBe(true);
    expect(formatYuan(data.figures[0].value)).toBe("¥0.00");
  });
});

/** 反向验证锚点：占比条颜色来自 slice 自身，empty 时无 color 依赖。 */
describe("PosterSlice 契约", () => {
  it("每个 slice 都有非空 color", () => {
    const data = buildPosterData({
      ...base,
      categories: [{ name: "基金", value: 100 }]
    });
    (data.slices as PosterSlice[]).forEach(s => {
      expect(s.color).toMatch(/^#[0-9a-fA-F]{6}$/);
    });
  });
});
