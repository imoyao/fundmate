/**
 * 走势图配置构建（#980 拆分后新增的回归网）。
 *
 * ## WHY 有这份文件
 *
 * 这段配置原先活在 `ProductTrendSection.vue` 的 `chartOption` computed 里（345 行），
 * 被组件绑定掩盖，改错只会表现为「图看着不对」——没有判据。2026-10-24 拆成纯函数
 * `buildTrendChartOption` 后，**「零行为变更」这句话才第一次可以被机器验证**。
 *
 * 钉住五种形态（前三种对应本文件拆之前就有的分支，后两种对应叠加层）：
 * 1. 场内 K 线：蜡烛 + MA5/10/20 + 可选量能副图（日期轴只画一次）；
 * 2. 场外/折线净值：单条线，名为「净值」，无 markLine；
 * 3. 业绩口径：名为「业绩」，多一条 0% 基准线（实线、无标签）；
 * 4. 叠加层开着：成本线 + 买入/卖出散点，**直径取自每条数据**（弱金额权重）；
 * 5. 叠加层关着：三个系列都不出现，但 0% 基准线仍在。
 *
 * 颜色断言只用「等于 `getCssVar` 的返回值」这一层——本文件不重复测主题令牌，
 * 那是 `theme.ts` 的职责；这里只钉「配置有没有把这些值放对位置」。
 */
import { describe, it, expect } from "vitest";
import { computed, ref } from "vue";
import type { ProductTrendResult } from "@/api/products";
import { UNIFIED_SIZE } from "../trendMarkerMetrics";
import {
  buildTrendChartOption,
  type TrendChartContext
} from "../trendChartOption";

type Ctx = TrendChartContext;
type SizedMarkers = Ctx["sizedMarkers"]["value"];
type MarkerPoint = SizedMarkers["buy"][number];
type Series = Record<string, unknown>;

const NAV_TREND: ProductTrendResult = {
  symbol: "110011",
  kind: "nav",
  dates: ["2026-10-01", "2026-10-02", "2026-10-03"],
  values: [1.1, 1.2, 1.15],
  source: "天天基金",
  basis: "累计净值",
  range: "3M",
  requested_days: 90,
  available_days: 90,
  ohlc: []
};

const ETF_TREND: ProductTrendResult = {
  ...NAV_TREND,
  symbol: "510300",
  kind: "close",
  basis: "前复权收盘价",
  values: [10, 11, 10.5],
  ohlc: [
    {
      date: "2026-10-01",
      open: 10,
      close: 10.2,
      high: 10.5,
      low: 9.8,
      volume: 1000
    },
    {
      date: "2026-10-02",
      open: 10.2,
      close: 11,
      high: 11.2,
      low: 10.1,
      volume: 2200
    },
    {
      date: "2026-10-03",
      open: 11,
      close: 10.5,
      high: 11.1,
      low: 10.4,
      volume: 300
    }
  ]
} as ProductTrendResult;

const BUY_MARKER: MarkerPoint = {
  value: ["2026-10-02", 1.2],
  side: "buy",
  date: "2026-10-02",
  y: 1.2,
  amount: 1000,
  quantity: 100,
  count: 2,
  closed: false,
  confirm: null,
  account: null,
  costRef: 1.1,
  avgPrice: 10,
  below: false,
  deviation: 9.09,
  symbolSize: 14
};

const SELL_MARKER: MarkerPoint = {
  ...BUY_MARKER,
  value: ["2026-10-03", 1.15],
  side: "sell",
  date: "2026-10-03",
  y: 1.15,
  closed: true,
  below: true,
  symbolSize: 9
};

interface CtxOverrides {
  trend?: ProductTrendResult;
  basis?: "nav" | "return";
  useCandle?: boolean;
  hasVolume?: boolean;
  markersActive?: boolean;
  assetType?: string;
}

/** 组装一份最小可用的上下文；默认「场外 + 净值口径 + 无叠加层」。 */
function makeCtx(o: CtxOverrides = {}): Ctx {
  const trend = o.trend ?? NAV_TREND;
  const basis = o.basis ?? "nav";
  return {
    themeTick: ref(0),
    trend: ref(trend),
    basis: ref<"nav" | "return">(basis),
    hasVolume: computed(() => o.hasVolume ?? false),
    candleCloses: computed(() => (trend.ohlc ?? []).map(x => x.close)),
    candleData: computed(() =>
      (trend.ohlc ?? []).map(x => [
        x.open ?? x.close,
        x.close,
        x.low ?? x.close,
        x.high ?? x.close
      ])
    ),
    returnSeries: computed(() => trend.values.map(() => 0)),
    isCandle: computed(() => (trend.ohlc?.length ?? 0) >= 2),
    useCandle: computed(() => o.useCandle ?? false),
    markersActive: computed(() => o.markersActive ?? false),
    clearingMarksList: computed(() => [{ date: "2026-10-03", round: 1 }]),
    costPlotSeries: computed(() => [1.1, 1.1, 1.1]),
    costSeriesData: computed(() => [1.1, 1.1, 1.1]),
    sizedMarkers: computed(() => ({
      buy: [BUY_MARKER],
      sell: [SELL_MARKER]
    })),
    assetType: o.assetType
  };
}

const seriesOf = (opt: unknown): Series[] =>
  (opt as { series: Series[] }).series;

describe("场内 K 线视图", () => {
  it("蜡烛 + MA5/10/20，双 grid，日期轴只画在量能格", () => {
    const opt = buildTrendChartOption(
      makeCtx({ trend: ETF_TREND, useCandle: true, hasVolume: true })
    );
    const series = seriesOf(opt);
    expect(series.map(s => s.name)).toEqual([
      "K 线",
      "MA5",
      "MA10",
      "MA20",
      "成交量"
    ]);
    expect(series[0].type).toBe("candlestick");
    // ECharts candlestick 要 [open, close, low, high]（不是 OHLC 顺序）
    expect(series[0].data).toEqual([
      [10, 10.2, 9.8, 10.5],
      [10.2, 11, 10.1, 11.2],
      [11, 10.5, 10.4, 11.1]
    ]);
    const opt2 = opt as {
      grid: unknown[];
      xAxis: Array<Record<string, unknown>>;
    };
    expect(opt2.grid).toHaveLength(2);
    // 有量能：K 线格的日期轴隐藏，量能格显示
    expect((opt2.xAxis[0].axisLabel as { show: boolean }).show).toBe(false);
    expect(
      (opt2.xAxis[1].axisLabel as { show?: boolean }).show
    ).toBeUndefined();
  });

  it("整段无量能 → 不渲染量能系列，日期轴回到 K 线格", () => {
    const opt = buildTrendChartOption(
      makeCtx({ trend: ETF_TREND, useCandle: true, hasVolume: false })
    );
    const series = seriesOf(opt);
    expect(series.map(s => s.name)).toEqual(["K 线", "MA5", "MA10", "MA20"]);
    const opt2 = opt as { xAxis: Array<Record<string, unknown>> };
    expect((opt2.xAxis[0].axisLabel as { show: boolean }).show).toBe(true);
  });

  it("MA 序列按窗口滑窗，前 window-1 个为 null（不造数）", () => {
    const opt = buildTrendChartOption(
      makeCtx({ trend: ETF_TREND, useCandle: true, hasVolume: false })
    );
    const ma5 = seriesOf(opt)[1].data as Array<number | null>;
    // 3 根 K 线不足 5 日窗口 → 全是 null
    expect(ma5).toEqual([null, null, null]);
  });
});

describe("折线视图（场外 / 场内折线）", () => {
  it("场外净值：单条线，名字是「净值」，不带 markLine", () => {
    const opt = buildTrendChartOption(makeCtx({ trend: NAV_TREND }));
    const series = seriesOf(opt);
    expect(series).toHaveLength(1);
    expect(series[0].name).toBe("净值");
    expect(series[0].type).toBe("line");
    expect(series[0].markLine).toBeUndefined();
    expect(series[0].data).toEqual([1.1, 1.2, 1.15]);
    // 不平滑：平滑会画出不存在的峰谷
    expect(series[0].smooth).toBe(false);
  });

  it("场内折线视图名字是「收盘价」，不是「净值」（否则用户拿它比基金净值）", () => {
    const opt = buildTrendChartOption(
      makeCtx({ trend: ETF_TREND, useCandle: false })
    );
    expect(seriesOf(opt)[0].name).toBe("收盘价");
  });

  it("业绩口径：名字变「业绩」，并多一条 0% 基准实线", () => {
    const opt = buildTrendChartOption(
      makeCtx({ trend: NAV_TREND, basis: "return" })
    );
    const series = seriesOf(opt);
    expect(series[0].name).toBe("业绩");
    const markLine = series[0].markLine as {
      data: Array<Record<string, unknown>>;
    };
    expect(markLine.data).toHaveLength(1);
    expect(markLine.data[0].yAxis).toBe(0);
    expect(markLine.data[0].label).toEqual({ show: false });
  });

  it("业绩口径的 y 轴给带符号百分比（不是裸数字）", () => {
    const opt = buildTrendChartOption(
      makeCtx({ trend: NAV_TREND, basis: "return" })
    );
    const yAxis = (
      opt as { yAxis: { axisLabel: { formatter: (v: number) => string } } }
    ).yAxis;
    expect(yAxis.axisLabel.formatter(12.3)).toContain("%");
    expect(yAxis.axisLabel.formatter(12.3)).toContain("+");
  });
});

describe("买卖点 / 成本线叠加层", () => {
  it("开着：成本线 + 买入 + 卖出三个系列，且清仓竖线进 markLine", () => {
    const opt = buildTrendChartOption(
      makeCtx({ trend: NAV_TREND, markersActive: true })
    );
    const series = seriesOf(opt);
    expect(series.map(s => s.name)).toEqual(["净值", "成本线", "买入", "卖出"]);
    const markLine = series[0].markLine as {
      data: Array<Record<string, unknown>>;
    };
    expect(markLine.data.some(d => d.xAxis === "2026-10-03")).toBe(true);
  });

  it("直径取自每条数据（弱金额权重），系列级只是兜底", () => {
    const opt = buildTrendChartOption(
      makeCtx({ trend: NAV_TREND, markersActive: true })
    );
    const series = seriesOf(opt);
    const buy = series.find(s => s.name === "买入");
    const sell = series.find(s => s.name === "卖出");
    expect((buy?.data as MarkerPoint[])[0].symbolSize).toBe(14);
    expect((sell?.data as MarkerPoint[])[0].symbolSize).toBe(9);
    // 系列级那个值是兜底常量，不参与实际直径
    expect(buy?.symbolSize).toBe(UNIFIED_SIZE);
  });

  it("低于当时成本的点改空心（填充透明 + 同色描边），不加第三种颜色", () => {
    const opt = buildTrendChartOption(
      makeCtx({ trend: NAV_TREND, markersActive: true })
    );
    const series = seriesOf(opt);
    // `itemStyle` 是构建时逐条挂上去的（不在 MarkerPoint 契约里），故按 Record 读
    const styleOf = (name: string) =>
      (
        series.find(s => s.name === name)?.data as Array<
          Record<string, unknown>
        >
      )[0].itemStyle as { color: string; borderColor?: string };
    const buyStyle = styleOf("买入");
    const sellStyle = styleOf("卖出");
    expect(buyStyle.color).not.toBe("transparent");
    expect(sellStyle.color).toBe("transparent");
    expect(sellStyle.borderColor).toBeTruthy();
  });

  it("关着：三个系列都不出现，但业绩口径的 0% 基准线仍在", () => {
    const opt = buildTrendChartOption(
      makeCtx({ trend: NAV_TREND, basis: "return", markersActive: false })
    );
    const series = seriesOf(opt);
    expect(series.map(s => s.name)).toEqual(["业绩"]);
    const markLine = series[0].markLine as {
      data: Array<Record<string, unknown>>;
    };
    expect(markLine.data).toHaveLength(1);
    expect(markLine.data[0].yAxis).toBe(0);
  });
});

describe("品类与精度", () => {
  it("y 轴 formatter 跟随品类（净值 4 位 / 股价 2 位）", () => {
    const axis = (o: unknown) =>
      (o as { yAxis: { axisLabel: { formatter: (v: number) => string } } })
        .yAxis.axisLabel.formatter;
    expect(
      axis(buildTrendChartOption(makeCtx({ assetType: "fund" })))(10.5)
    ).toBe("10.5000");
    expect(
      axis(buildTrendChartOption(makeCtx({ assetType: "stock" })))(10.5)
    ).toBe("10.50");
  });
});
