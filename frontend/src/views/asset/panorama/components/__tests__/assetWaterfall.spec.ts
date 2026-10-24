import { describe, expect, it } from "vitest";

import type { DistributionsData } from "@/api/summary";
import type { WaterfallColors } from "../assetWaterfall";
import { buildWaterfallBars, buildWaterfallOption } from "../assetWaterfall";

/**
 * 瀑布图标注层判据（B 车道：极小值柱引线标注）。
 *
 * 为什么需要单测：这一层的判定**全部是几何/像素推导**（柱高 px、绘图区高、轴上限），
 * 肉眼看图只能证明「这张数据下没事」，证明不了「换一份数据还对」。尤其是
 * 「8% 阈值的母体是谁」这条 —— 母体取错时画面依旧能看，只是某些档位**静默失去数字**，
 * 而那正是本轮要修的症状（30 万现金档曾被净资产抬高的阈值挤掉，差 40 元）。
 *
 * 断言只钉**不变式**（谁挂标注条、谁挂单行、错行是否生效、引线是否不进 tooltip），
 * 不钉具体像素值 —— 那些是 `TINY_BAR_PX` / `CHIP_*` 常量的领地，钉死会让每次
 * 调排版都要改测试。
 */

const COLORS: WaterfallColors = {
  rise: "#e05b4a",
  fall: "#2f9e6b",
  info: "#5b7f96",
  neutral: "#9a938a",
  axis: "#6b655c",
  border: "#e6e2db",
  connector: "#9a938a",
  riseInk: "#b8432f",
  fallInk: "#1f7a4d",
  neutralInk: "#6b655c",
  primaryInk: "#2d2a24",
  surface: "#ffffff"
};

/** 只声明本单测用到的形状，避免把 echarts 的宽类型拖进来 */
interface BarLabel {
  distance?: number;
  backgroundColor?: string;
  color?: string;
}
interface BarItem {
  value: number;
  label: BarLabel;
}
/** 逐条 label 只覆盖颜色/垫底，**取值文案在 series 级 formatter 上**（echarts 的契约） */
interface SeriesLabel {
  formatter: (p: { dataIndex: number }) => string;
}
interface MarkLineData {
  data: Array<Array<{ coord: [number, number] }>>;
}
interface OptionShape {
  series: Array<{
    name?: string;
    silent?: boolean;
    tooltip?: { show?: boolean };
    label?: SeriesLabel;
    data?: unknown[];
    markLine?: MarkLineData;
  }>;
}

function distributions(
  categories: Array<{ name: string; value: number }>,
  totalLiabilities = 0
): DistributionsData {
  const totalAssets = categories.reduce((sum, c) => sum + c.value, 0);
  return {
    category_distribution: categories,
    type_distribution: [],
    allocation_distribution: [],
    market_distribution: [],
    account_distribution: [],
    liability_distribution: [],
    total_assets: totalAssets,
    total_liabilities: totalLiabilities,
    net_worth: totalAssets - totalLiabilities,
    positions_total_mv: totalAssets
  };
}

/** 一个极小值柱（保险 5.05 万）夹在几个大档位之间 */
const SINGLE_TINY = distributions(
  [
    { name: "股票", value: 1_800_000 },
    { name: "基金", value: 1_200_000 },
    { name: "债券", value: 600_000 },
    { name: "保险", value: 50_500 },
    { name: "现金", value: 300_000 }
  ],
  200_000
);

/** 两个**相邻**的极小值柱（保险 + 固定收益类），用来验证错行 */
const TWO_ADJACENT_TINY = distributions(
  [
    { name: "股票", value: 1_800_000 },
    { name: "基金", value: 1_200_000 },
    { name: "债券", value: 600_000 },
    { name: "保险", value: 50_500 },
    { name: "固定收益类", value: 110_000 }
  ],
  200_000
);

function build(data: DistributionsData, height = 280) {
  const bars = buildWaterfallBars(data);
  const option = buildWaterfallOption(bars, COLORS, {
    height
  }) as unknown as OptionShape;
  /** 第 2 条 series 是柱体（第 1 条是透明基座），标注层挂在它的 data 上 */
  const barsSeries = option.series[1];
  const items = barsSeries.data as BarItem[];
  const label = (i: number) => items[i].label;
  const seriesLabel = barsSeries.label as SeriesLabel;
  const text = (i: number) => seriesLabel.formatter({ dataIndex: i });
  const isChip = (i: number) => label(i).backgroundColor === COLORS.surface;
  return { bars, option, items, label, text, isChip };
}

describe("瀑布图极小值柱标注层", () => {
  it("极小值柱挂两行标注条（名称 + 金额），普通柱保持单行金额", () => {
    const { text, isChip } = build(SINGLE_TINY);

    // 保险 = 5.05 万，在 376 万量级下柱高不足一像素级的可读高度 ⇒ 标注条
    expect(isChip(3)).toBe(true);
    expect(text(3)).toBe("{n|保险}\n{v|¥5.05万}");

    // 大档位仍是单行金额，且**没有**垫底色（垫底色是标注条专属）
    expect(isChip(0)).toBe(false);
    expect(text(0)).toBe("¥180.0万");
    expect(isChip(2)).toBe(false);
    expect(text(2)).toBe("¥60.00万");
  });

  it("8% 阈值的母体是「最大单笔变动」，不含终点柱（回归：30 万现金档曾被挤掉）", () => {
    const { text, isChip, bars } = build(SINGLE_TINY);

    // 净资产（375.05 万）是**合计**，不是一次变动。它一旦进母体，阈值被抬到
    // 30.004 万，30 万现金档差 40 元落榜、整根柱一个数字都没有。
    const cashIndex = bars.findIndex(b => b.name === "现金");
    const liabIndex = bars.findIndex(b => b.name === "负债");
    expect(cashIndex).toBeGreaterThan(-1);
    expect(liabIndex).toBeGreaterThan(-1);

    expect(isChip(cashIndex)).toBe(false);
    expect(text(cashIndex)).toBe("¥30.00万");
    // 20 万负债档比 30 万现金档更矮，更不该拿到标注条 —— 两档必须同档处理
    expect(isChip(liabIndex)).toBe(false);
    expect(text(liabIndex)).toBe("-¥20.00万");
  });

  it("终点柱永不改挂标注条（它是结论，恒有普通标签）", () => {
    const { bars, text, isChip } = build(SINGLE_TINY);
    const endIndex = bars.length - 1;
    expect(bars[endIndex].isEndpoint).toBe(true);
    expect(isChip(endIndex)).toBe(false);
    expect(text(endIndex)).toBe("¥375.1万");
  });

  it("相邻的两根极小值柱错行，不相邻的回到第一行", () => {
    const { label, isChip } = build(TWO_ADJACENT_TINY);
    const insurance = 3;
    const fixedIncome = 4; // 与保险相邻
    expect(isChip(insurance)).toBe(true);
    expect(isChip(fixedIncome)).toBe(true);
    // 错行的唯一可观测后果：两行标注条的 distance 不同（否则它们会压在一起）
    expect(label(fixedIncome).distance).not.toBe(label(insurance).distance);
  });

  it("标注条名称超长时截断成 4 字（含省略号），不撑破类目带宽", () => {
    const { text } = build(TWO_ADJACENT_TINY);
    expect(text(4)).toContain("{n|固定收…}");
  });

  it("有标注条时才追加引线 series，且引线不进 tooltip、不响应鼠标", () => {
    const withChips = build(SINGLE_TINY);
    expect(withChips.option.series).toHaveLength(3);

    const leader = withChips.option.series[2];
    expect(leader.silent).toBe(true);
    expect(leader.tooltip?.show).toBe(false);
    const segments = leader.markLine?.data ?? [];
    expect(segments.length).toBeGreaterThan(0);
    for (const seg of segments) {
      expect(seg).toHaveLength(2);
      // 引线向上画：终点坐标（金额）必须大于起点
      expect(seg[1].coord[1]).toBeGreaterThan(seg[0].coord[1]);
    }

    // 没有极小值柱时不该多出一条空 series（空 markLine 会在图上留下看不见的图层）
    const noChips = build(
      distributions([
        { name: "股票", value: 1_800_000 },
        { name: "基金", value: 1_200_000 }
      ])
    );
    expect(noChips.option.series).toHaveLength(2);
  });

  it("容器高度取不到时仍给得出标注（按锁高 280 兜底），不会整层消失", () => {
    const bars = buildWaterfallBars(SINGLE_TINY);
    const withoutLayout = buildWaterfallOption(
      bars,
      COLORS
    ) as unknown as OptionShape;
    const items = withoutLayout.series[1].data as BarItem[];
    expect(items[3].label.backgroundColor).toBe(COLORS.surface);
  });
});
