import { describe, expect, it } from "vitest";

import type { DistributionsData } from "@/api/summary";
import type { CompositionColors } from "../assetComposition";
import {
  buildCompositionOption,
  compositionItems,
  hasCompositionData
} from "../assetComposition";

/**
 * 资产大类构成柱状图的判据。
 *
 * 为什么需要单测：这张图的前身是瀑布图，它的两处固有误读（柱位当大小、同视口
 * 与左卡重复）**都不能靠肉眼发现**——看着"有柱子、有数字"就像是对的。本文件的
 * 断言钉的是「图说了什么」，不是像素：
 *
 * - 只画资产端（负债 / 净资产回归左卡），否则又变成一张桥；
 * - 一律从 0 起（`min: 0`），否则长度不再等于金额；
 * - 上限留余量（柱顶标签不出界），且是步长整数倍（刻度不出现半格）。
 */

const COLORS: CompositionColors = {
  bar: "#e34f38",
  barInk: "#c0341f",
  axis: "#716a60",
  border: "#f0ebe4",
  axisLine: "#e5ddd4"
};

function makeData(
  categories: Array<{ name: string; value: number }>,
  extra: Partial<DistributionsData> = {}
): DistributionsData {
  return {
    category_distribution: categories,
    type_distribution: [],
    allocation_distribution: [],
    market_distribution: [],
    account_distribution: [],
    liability_distribution: [],
    total_assets: categories.reduce((s, c) => s + c.value, 0),
    total_liabilities: 0,
    net_worth: categories.reduce((s, c) => s + c.value, 0),
    positions_total_mv: 0,
    ...extra
  };
}

/** 真实数据（用户 2026-10-25 的口径）：4 类资产 + 176 万负债 */
const REAL = makeData(
  [
    { name: "固定资产", value: 2_200_000 },
    { name: "流动资金", value: 993_800 },
    { name: "投资理财", value: 517_900 },
    { name: "应收款", value: 50_000 }
  ],
  { total_liabilities: 1_760_000, net_worth: 2_001_700 }
);

describe("compositionItems：图里画什么", () => {
  it("只取资产大类，负债与净资产不进图", () => {
    const names = compositionItems(REAL).map(i => i.name);
    expect(names).toEqual(["固定资产", "流动资金", "投资理财", "应收款"]);
    // 负债 / 净资产是**左卡**的三个数字，再画一遍就是同视口重复（#2034 / #2150）
    expect(names).not.toContain("负债");
    expect(names).not.toContain("净资产");
  });

  it("按金额降序：构成图的读法是「从大到小」", () => {
    const values = compositionItems(REAL).map(i => i.value);
    expect(values).toEqual([...values].sort((a, b) => b - a));
  });

  it("过滤 0 与非正值：0 值柱占类目位却不可见，留白比画出来诚实", () => {
    const data = makeData([
      { name: "固定资产", value: 100 },
      { name: "应收款", value: 0 },
      { name: "自定义", value: -20 }
    ]);
    expect(compositionItems(data).map(i => i.name)).toEqual(["固定资产"]);
  });

  it("不就地重排调用方的响应式数据", () => {
    const data = makeData([
      { name: "小额", value: 1 },
      { name: "大额", value: 100 }
    ]);
    const before = data.category_distribution.map(c => c.name);
    compositionItems(data);
    expect(data.category_distribution.map(c => c.name)).toEqual(before);
  });

  it("没有资产大类时 hasCompositionData 为 false（不画全 0 空图）", () => {
    expect(hasCompositionData(makeData([]))).toBe(false);
    // 只有负债也算"无可画"：负债不进这张图
    expect(
      hasCompositionData(makeData([], { total_liabilities: 1_760_000 }))
    ).toBe(false);
    expect(hasCompositionData(REAL)).toBe(true);
  });
});

describe("buildCompositionOption：图怎么画", () => {
  const option = buildCompositionOption(compositionItems(REAL), COLORS);
  const max = 2_200_000;

  it("y 轴从 0 起——长度必须等于金额", () => {
    expect(option.yAxis.min).toBe(0);
  });

  it("上限给柱顶标签留出余量，且是步长整数倍", () => {
    // 前身瀑布图把「应收款」标注顶到 400 万刻度线以上，根因就是上限压着数据顶部
    expect(option.yAxis.max).toBeGreaterThanOrEqual(max * 1.1);
    expect(option.yAxis.max % option.yAxis.interval).toBe(0);
    // 格数落在可读区间：太少没有可比刻度，太密压住柱子
    const splits = option.yAxis.max / option.yAxis.interval;
    expect(splits).toBeGreaterThanOrEqual(3);
    expect(splits).toBeLessThanOrEqual(6);
  });

  it("类目顺序与数据顺序一一对应，且全部降序", () => {
    expect(option.xAxis.data).toEqual([
      "固定资产",
      "流动资金",
      "投资理财",
      "应收款"
    ]);
    expect(option.series[0].data).toEqual([
      2_200_000, 993_800, 517_900, 50_000
    ]);
  });

  it("每根柱都带金额标签（只有 4 根，不需要按比例隐藏）", () => {
    expect(option.series[0].label.show).toBe(true);
    expect(option.series[0].label.color).toBe(COLORS.barInk);
    // formatter 是「万 / 亿」缩写，完整精度留给 tooltip
    expect(option.series[0].label.formatter({ value: 2_200_000 })).toBe(
      "¥220.00万"
    );
    expect(option.series[0].label.formatter({ value: 50_000 })).toBe("¥5.00万");
  });

  it("tooltip 给完整精度，不缩写", () => {
    expect(option.tooltip.valueFormatter(2_200_000)).toBe("¥2,200,000.00");
  });

  it("轴标签是整数万，不出现「50.0万」这种噪声", () => {
    const axis = option.yAxis.axisLabel.formatter;
    expect(option.yAxis.interval).toBe(500_000);
    expect(axis(500_000)).toBe("50万");
    expect(axis(0)).toBe("0");
    // 2.5 万这类半档仍保留一位小数
    expect(axis(25_000)).toBe("2.5万");
  });

  it("颜色全部来自入参（canvas 不认 CSS 变量，故由调用方解析后传入）", () => {
    expect(option.series[0].itemStyle.color).toBe(COLORS.bar);
    expect(option.xAxis.axisLine.lineStyle.color).toBe(COLORS.axisLine);
    expect(option.yAxis.axisLabel.color).toBe(COLORS.axis);
    expect(option.yAxis.splitLine.lineStyle.color).toBe(COLORS.border);
  });

  it("极小金额仍有可见高度：5 万在 376 万量级下只有几像素", () => {
    expect(option.series[0].barMinHeight).toBeGreaterThan(0);
  });
});
