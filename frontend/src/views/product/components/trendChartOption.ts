// 走势图 ECharts 配置构建（#980 拆分，源自 ProductTrendSection.vue 的 chartOption）。
//
// 刻意做成**纯函数**：入参是一组 ref（直接沿用组件里的同名变量），体内不做任何取数，
// 因此可以脱离组件单测「给定数据 → 配置长什么样」。
// 颜色一律经 `getCssVar` 取真实色值——ECharts 不解析 `var(--x)`。
import type { useProductTrend } from "../composables/useProductTrend";
import {
  CHART_FALLBACKS,
  CHART_TOKENS,
  getCssVar
} from "@/composables/echarts/theme";
import { formatPrice, priceAxisLabelFormatter } from "@/utils/pricePrecision";
import { formatReturnPercent } from "./trendBasisMetrics";
import { UNIFIED_SIZE, clearingLabel } from "./trendMarkerMetrics";

type TrendState = ReturnType<typeof useProductTrend>;

/** 构建图表所需的组件状态（`Pick` 而非全量：改了无关状态不该重算配置）。 */
export type TrendChartContext = Pick<
  TrendState,
  | "themeTick"
  | "trend"
  | "hasVolume"
  | "candleCloses"
  | "candleData"
  | "basis"
  | "returnSeries"
  | "isCandle"
  | "useCandle"
  | "markersActive"
  | "clearingMarksList"
  | "costPlotSeries"
  | "costSeriesData"
  | "sizedMarkers"
> & {
  /** 品类（股价 2 位 / 净值 4 位） */
  assetType?: string;
};

/** hex → rgba：面积渐变需要具体色值（CSS 变量不能直接给 alpha） */
function hexToRgba(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec((hex || "").trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/**
 * 简单移动平均。
 *
 * 放在前端算：它是对已有收盘序列的**纯派生**（不跨表、不聚合明细），且切换区间时
 * 无需重新请求——后端只负责「数据从哪来、口径是什么」（数据策略约束针对的是跨表
 * 聚合，不是这种单序列滑窗）。
 */
function movingAverage(values: number[], window: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= window) sum -= values[i - window];
    out.push(i >= window - 1 ? +(sum / window).toFixed(3) : null);
  }
  return out;
}

export function buildTrendChartOption(ctx: TrendChartContext) {
  const {
    themeTick,
    trend,
    hasVolume,
    candleCloses,
    candleData,
    basis,
    returnSeries,
    isCandle,
    useCandle,
    markersActive,
    clearingMarksList,
    costPlotSeries,
    costSeriesData,
    sizedMarkers,
    assetType
  } = ctx;
  void themeTick.value; // 主题切换时重算，让曲线重读 CSS 变量
  const dates = trend.value?.dates ?? [];
  const values = trend.value?.values ?? [];
  const rise = getCssVar(CHART_TOKENS.rise, CHART_FALLBACKS.rise);
  const fall = getCssVar(CHART_TOKENS.fall, CHART_FALLBACKS.fall);

  // 网格线取**真实色值**并用实线：
  // · ECharts 不解析 `var(--x)`，直接给变量字符串等于给了一个无效色（旧版就是）；
  // · 虚线在密集 K 线与影线之间会糊成一片，是「看着杂乱」的一半原因（#1969）。
  const splitLine = {
    lineStyle: {
      color: getCssVar(CHART_TOKENS.borderLight, CHART_FALLBACKS.borderLight)
    }
  };

  if (useCandle.value) {
    // 成交量副图：与 K 线共用 x 轴（放下面一格），整段无量能时不渲染这一格
    const volumeSeries = hasVolume.value
      ? [
          {
            name: "成交量",
            type: "bar",
            xAxisIndex: 1,
            yAxisIndex: 1,
            // 量能柱与 K 线同色（阳红阴绿）：这样「放量下跌」一眼能看出来，
            // 全部涂成中性灰的话量能就只是个装饰（同花顺 / 雪球都是同色）
            data: (trend.value?.ohlc ?? []).map(o => ({
              value: o.volume ?? 0,
              itemStyle: {
                color: o.close >= (o.open ?? o.close) ? rise : fall
              }
            }))
          }
        ]
      : [];
    const maLine = (window: number, token: string, fallback: string) => ({
      name: `MA${window}`,
      type: "line",
      data: movingAverage(candleCloses.value, window),
      symbol: "none",
      smooth: false,
      lineStyle: { width: 1, color: getCssVar(token, fallback) }
    });

    return {
      animation: false,
      tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
      axisPointer: { link: [{ xAxisIndex: "all" }] },
      grid: [
        { left: 56, right: 16, top: 20, height: 176 },
        { left: 56, right: 16, top: 220, height: hasVolume.value ? 56 : 0 }
      ],
      xAxis: [
        {
          type: "category",
          data: dates,
          boundaryGap: true,
          axisTick: { show: false },
          // 日期轴只画在量能那格，K 线格不重复显示（两格共用同一轴）
          axisLabel: { show: !hasVolume.value, fontSize: 11, hideOverlap: true }
        },
        {
          type: "category",
          gridIndex: 1,
          data: dates,
          boundaryGap: true,
          axisTick: { show: false },
          axisLabel: { fontSize: 11, hideOverlap: true }
        }
      ],
      yAxis: [
        {
          scale: true,
          axisLabel: {
            fontSize: 11,
            formatter: priceAxisLabelFormatter(assetType)
          },
          splitLine
        },
        {
          gridIndex: 1,
          splitNumber: 2,
          axisLabel: { show: false },
          splitLine: { show: false }
        }
      ],
      series: [
        {
          name: "K 线",
          type: "candlestick",
          data: candleData.value,
          // 涨红跌绿：color 是阳线、color0 是阴线（与 A 股看盘习惯一致）
          itemStyle: {
            color: rise,
            color0: fall,
            borderColor: rise,
            borderColor0: fall
          }
        },
        maLine(5, CHART_TOKENS.warning, CHART_FALLBACKS.warning),
        maLine(10, CHART_TOKENS.info, CHART_FALLBACKS.info),
        maLine(20, CHART_TOKENS.textTertiary, CHART_FALLBACKS.textTertiary),
        ...volumeSeries
      ]
    };
  }

  // 场外（累计净值，#2171）或没有 OHLCV 的场内：一条线。
  // **不平滑**：平滑会画出实际不存在的峰谷，价格序列上那是失真（#1969）。
  const isReturn = basis.value === "return";
  // 业绩口径画收益率序列（与 values 等长按位对齐），否则画原始净值/收盘价
  const plotValues = isReturn ? returnSeries.value : values;
  const rising =
    plotValues.length >= 2 &&
    plotValues[plotValues.length - 1] >= plotValues[0];
  const lineColor = rising ? rise : fall;
  // 叠加层取色刻意避开 rise（红）/ fall（绿）：买卖点不是涨跌语义，
  // 涂红涂绿会让用户把「我买过」误读成「涨了」。蓝=买入、橙=卖出、
  // 中性灰虚线=成本线——与净值曲线（动态涨跌色）三层不打架（#2171 定稿）。
  const markerBuyColor = getCssVar(CHART_TOKENS.info, CHART_FALLBACKS.info);
  const markerSellColor = getCssVar(
    CHART_TOKENS.warning,
    CHART_FALLBACKS.warning
  );
  const costLineColor = getCssVar(
    CHART_TOKENS.textTertiary,
    CHART_FALLBACKS.textTertiary
  );
  // 清仓竖线用**点线**（成本线是虚线）：它标的是「一轮结束」这个事件，不是价格水平
  const clearingColor = getCssVar(
    CHART_TOKENS.textTertiary,
    CHART_FALLBACKS.textTertiary
  );
  // 业绩口径的 0% 基准线（#2454）：中性灰**实线**——与点线竖线（事件）、
  // 虚线成本线（水平）三层形态分层，不靠颜色区分（色弱用户也读得出）
  const zeroLineColor = getCssVar(
    CHART_TOKENS.textTertiary,
    CHART_FALLBACKS.textTertiary
  );

  /** 轴触发 tooltip：净值行 + 当日成本线 + 当日买卖汇总（#2171）。
      同日多笔在 markerData 已聚合，这里直接显示「N 笔合计」；
      低于当时成本线的点附偏离度（空心编码的文字版，色弱用户也能读到）。

      ⚠️ null 值行必须**整行跳过**（#2454 实测发现的既有缺陷）：成本线在首笔交易前
      为 null（那时还没有持仓成本），ECharts 会把 null 原样放进 params。旧代码
      `Number(p.value)` 把 null 压成 0，tooltip 于是显示一行「成本线：0.0000」——
      把「没有数据」伪装成「成本是 0」，正是设计 §6 禁的造假。业绩口径下同行
      会显示「0.00%」，同样必须跳过。 */
  const tooltipFormatter = (params: Array<Record<string, unknown>>) => {
    if (!params?.length) return "";
    const date = String(params[0].axisValue ?? "");
    const rows: string[] = [`<b>${date}</b>`];
    for (const p of params) {
      const data = (p.data ?? {}) as Record<string, unknown>;
      const seriesName = String(p.seriesName ?? "");
      if (p.seriesType === "scatter") {
        const amount = Number(data.amount ?? 0).toFixed(2);
        const count = Number(data.count ?? 1);
        const merged = count > 1 ? `（${count} 笔合计）` : "";
        const confirm = data.confirm ? `<br/>确认日 ${data.confirm}` : "";
        const closed = data.closed ? " · 当日清仓" : "";
        const deviation = data.deviation as number | null;
        const deviationText =
          deviation === null || deviation === undefined
            ? ""
            : `<br/>${deviation < 0 ? "低于" : "高于"}当时成本 ${Math.abs(deviation).toFixed(2)}%`;
        rows.push(
          `${p.marker ?? ""}${seriesName}${merged}：¥${amount}${closed}${deviationText}${confirm}`
        );
      } else if (isReturn) {
        // 首笔交易前成本线为 null：整行跳过（见 tooltipFormatter 头注释）
        const rawValue = Array.isArray(p.value) ? p.value[1] : p.value;
        if (rawValue === null || rawValue === undefined) continue;
        // 业绩口径（#2454）：主行给收益率，括号附当日净值/收盘价（或成本）——
        // 只看 % 不知道当时多少钱。tooltip 是解释层不是压缩层，两个数都给。
        const idx = Number(p.dataIndex ?? -1);
        const plotted = Number(rawValue);
        const isCost = seriesName === "成本线";
        const orig = isCost ? costSeriesData.value[idx] : values[idx];
        const origLabel = isCost ? "成本" : isCandle.value ? "收盘价" : "净值";
        const origText =
          orig === null || orig === undefined || !Number.isFinite(orig)
            ? ""
            : `（${origLabel} ${formatPrice(orig, assetType)}）`;
        rows.push(
          `${p.marker ?? ""}${seriesName}：${formatReturnPercent(plotted)}${origText}`
        );
      } else {
        // 同上：null 行跳过，不把「没有数据」显示成 0
        const rawValue = Array.isArray(p.value) ? p.value[1] : p.value;
        if (rawValue === null || rawValue === undefined) continue;
        const v = Number(rawValue);
        rows.push(
          `${p.marker ?? ""}${seriesName}：${formatPrice(v, assetType)}`
        );
      }
    }
    return rows.join("<br/>");
  };

  /**
   * 主系列 markLine 数据（#2171 P2 + #2454）。
   *
   * 清仓轮次竖线与 0% 基准线共用一次 markLine 配置（ECharts 一个系列只能挂一个
   * markLine），但**形态分层**：竖线是点线 + 编号（标事件），基准线是实线 + 无标签
   * （标水平）——不靠颜色区分，色弱用户也读得出。
   */
  const markLineData: Array<Record<string, unknown>> = [];
  if (markersActive.value) {
    for (const m of clearingMarksList.value) {
      markLineData.push({
        xAxis: m.date,
        label: {
          formatter: clearingLabel(m.round, clearingMarksList.value.length),
          position: "insideEndTop"
        }
      });
    }
  }
  if (isReturn) {
    // 0% 基准线：收益率曲线本身从 0 出发，但没有这条线时「高于/低于基准」
    // 要靠眼估刻度——一条实线把上下分区画出来（业绩走势的标准配法）。
    markLineData.push({
      yAxis: 0,
      lineStyle: { color: zeroLineColor, type: "solid", width: 1 },
      label: { show: false }
    });
  }

  return {
    tooltip: { trigger: "axis", formatter: tooltipFormatter },
    grid: { left: 52, right: 16, top: 16, bottom: 28 },
    xAxis: {
      type: "category",
      data: dates,
      boundaryGap: false,
      axisLabel: { fontSize: 11, hideOverlap: true }
    },
    yAxis: {
      type: "value",
      scale: true,
      // 净值 4 位、股价 2 位：不设 formatter 时 echarts 默认只给 1 位，
      // 净值 4.8124 在轴上会显示成 4.8（用户实测反馈）。
      // 业绩口径（#2454）画**带符号百分比**：「+12.3%」比「12.3」多一个「赚了」的确认。
      axisLabel: {
        fontSize: 11,
        formatter: isReturn
          ? (v: number) => formatReturnPercent(v, 1)
          : priceAxisLabelFormatter(assetType)
      },
      splitLine
    },
    series: [
      {
        // 场内折线视图画的是**收盘价**（与持仓成本同口径），场外才是净值——
        // 名字不能都叫「净值」，否则场内用户会拿它去对比基金净值（#2171 后续）；
        // 业绩口径（#2454）叫「业绩」：曲线画的是收益率，名字得跟着口径走
        name: isReturn ? "业绩" : isCandle.value ? "收盘价" : "净值",
        type: "line",
        data: plotValues,
        smooth: false,
        symbol: "none",
        lineStyle: { color: lineColor, width: 2 },
        areaStyle: { color: hexToRgba(lineColor, 0.08) },
        // 清仓轮次标记（#2171 P2）：每轮结束画一条点线竖线并编号。
        // `silent: true` —— 它只是刻度，不该抢 tooltip（悬停仍显示当日净值 / 成本 / 买卖）。
        // 业绩口径另含一条 0% 基准线（#2454，见 markLineData 构造处）。
        ...(markLineData.length
          ? {
              markLine: {
                silent: true,
                symbol: ["none", "none"],
                lineStyle: { color: clearingColor, type: "dotted", width: 1 },
                label: { fontSize: 10, color: clearingColor },
                data: markLineData
              }
            }
          : {})
      },
      // 成本线（#2171）：移动加权（含手续费），非交易日前向延续；清仓日断在
      // 最后一笔（costSeriesData 在首笔前为 null，天然不画）。虚线 + 中性灰，
      // 与净值曲线（实线 + 涨跌色）形态分层，不抢主视觉。
      // 业绩口径（#2454）下换算成同基准收益率（costPlotSeries）——y 轴已是 %。
      ...(markersActive.value
        ? [
            {
              name: "成本线",
              type: "line",
              data: costPlotSeries.value,
              symbol: "none",
              smooth: false,
              lineStyle: { color: costLineColor, width: 1, type: "dashed" }
            }
          ]
        : []),
      // 买卖点：三角朝上=买入、朝下=卖出（形状主编码，色弱用户也能分辨）。
      // 低于当时成本线的点改**空心**（填充透明 + 同色描边）：低吸/割肉一眼可辨，
      // 不引入第三种颜色——那会和涨跌语义打架（#2171 P1）。
      ...(markersActive.value
        ? [
            {
              name: "买入",
              type: "scatter",
              // 直径走**每条数据自带**的 symbolSize（#2171 §4.2 弱金额权重）；
              // 系列级那个值退化为兜底——写死它等于把整条点大小规格丢掉（首版就是 9）
              data: sizedMarkers.value.buy.map(m => ({
                ...m,
                itemStyle: m.below
                  ? {
                      color: "transparent",
                      borderColor: markerBuyColor,
                      borderWidth: 1.5
                    }
                  : { color: markerBuyColor }
              })),
              symbol: "triangle",
              symbolSize: UNIFIED_SIZE,
              z: 5
            },
            {
              name: "卖出",
              type: "scatter",
              data: sizedMarkers.value.sell.map(m => ({
                ...m,
                itemStyle: m.below
                  ? {
                      color: "transparent",
                      borderColor: markerSellColor,
                      borderWidth: 1.5
                    }
                  : { color: markerSellColor }
              })),
              symbol: "triangle",
              symbolRotate: 180,
              symbolSize: UNIFIED_SIZE,
              z: 5
            }
          ]
        : [])
    ]
  };
}
