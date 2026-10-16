<script setup lang="ts">
import { computed, ref, watch } from "vue";
import VChart from "vue-echarts";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import {
  getProductTrend,
  getTradeTimeline,
  type ProductTrendResult,
  type TradeTimelineResult,
  type TrendRange
} from "@/api/products";
import ProductProfitPanel from "./ProductProfitPanel.vue";
import {
  CHART_TOKENS,
  getCssVar,
  useThemeTick
} from "@/composables/echarts/theme";

/**
 * 详情页「走势」区块（#1967 · 设计 §5 B 区块）。
 *
 * 口径与红线：
 * - 区间 `1M/3M/6M/1Y`，**默认 3M**（设计 §12 ⑤）；历史不够长时由 `available_days`
 *   判断并提示收敛，不画一条只有几天的曲线假装是 3M；
 * - **品类差异化**（#1969）：场内有 OHLCV → K 线 + 成交量 + MA5/10/20（口径未复权，
 *   与持仓成本可比）；场外基金只有净值 → 净值线（#2171 起为**累计净值**，
 *   缺失回退单位净值，与业绩卡同源——单位净值遇分红除息跳空是假暴跌）；
 * - 图表颜色一律经 `getCssVar` 取**真实色值**：ECharts 不解析 `var(--x)`，给变量字符串
 *   等于给了一个无效色（旧版 splitLine 的写法就是这么错的，也会让网格看起来发黑发乱）；
 * - 线条**不平滑**：smooth 会画出实际不存在的峰谷，价格序列上属失真；
 * - **无数据就显示空态**，绝不用 mock 顶替（设计 G1 教训）；
 * - 脚注写明「数据日期 · 来源 · 口径」——来源是站点名，不是内部表名（#1969）；
 * - **品类无序列源时整卡不渲染**（#1967 后续）：后端对 manager / portfolio /
 *   无日线的 index 返回 `kind=''` + 空序列，此时渲染出的只有标题的卡片是纯噪声。
 *   走势区块已从最后一屏移回首屏（设计 §5 B 位），这条降级从「脚注」升级为
 *   「区块整体不渲染」（设计 §6 降级规则）。判据取后端 `kind` 而非在前端镜像
 *   一份「哪些品类没序列」的类型清单——后端 `product_trend._NO_SERIES_TYPES`
 *   是权威，前端不复制它。
 *
 * ## 买卖点 / 成本线叠加（#2171）
 *
 * - **首版只叠场外净值线**：买卖点与成本线都是「元/份」的日序列，与净值曲线同构；
 *   场内 K 线是未复权价格且 tooltip 为 cross 模式，叠加属另一套坐标语义，留 P1；
 * - **取色避开 rise/fall**：买卖点不是涨跌语义，红绿会让「我买过」被误读成「涨了」。
 *   蓝（info）三角朝上=买入、橙（warning）三角朝下=卖出、中性灰虚线=成本线——
 *   形状主编码，色弱用户也能分辨；
 * - **低于当时成本线 → 空心**（P1）：当日均价 < 当日最后一笔之前的持仓均价。
 *   低吸 / 割肉一眼可辨，tooltip 附偏离度；首笔前无持仓不判（无参照不下结论）。
 *   不引入第三种颜色——那会和涨跌语义打架；
 * - **同日多笔聚合**为一个点（金额合计 + 笔数），tooltip 显示「N 笔合计」；
 * - **成本线前向填充**：非交易日延续前值，首笔交易前为 null 不画，清仓日断在最后一笔；
 * - **「历轮」开关**（P1）：清仓后重建仓的用户可关掉旧轮次，只看最近一轮；
 * - **建仓期区间**（P1）：有流水时区间栏追加「建仓」档——首笔买入日至今，
 *   显式起始日走后端 `start` 参数（档位表达不了因人而异的长度）；
 * - **时间线不分区间**：后端一次返回全量重放结果，前端按当前区间过滤展示；
 * - 拉取失败 / 未持有 → 静默不渲染叠加层，主曲线不受影响（设计 §6）。
 *
 * ## 累计收益面板（P1，见 ProductProfitPanel.vue）
 *
 * 与叠加层共用同一次时间线请求（detail 层不重复取数）：累计已实现盈亏 +
 * 金额 / 收益率切换 + 紧凑统计条。曲线**全程展示不随区间缩放**——区间是看净值
 * 波动的窗口，不是看盈亏历史的窗口。
 */

const props = defineProps<{
  symbol: string;
  /** 品类：由 #1963 resolve 判定后回传，后端据此选收盘价 / 净值口径 */
  assetType?: string;
  /** 当前家庭是否持有该产品（详情页 resolve 回传）。仅持有时拉交易时间线——
      流水是私有数据，未持有用户发请求只会拿到空结构，还多一次往返（#2104 同款教训）。 */
  hasPosition?: boolean;
}>();

const RANGE_BASE_OPTIONS: { label: string; value: RangeValue }[] = [
  { label: "1月", value: "1M" },
  { label: "3月", value: "3M" },
  { label: "6月", value: "6M" },
  { label: "1年", value: "1Y" }
];

/**
 * 区间取值：固定档位 + 「建仓」（#2171 P1）。
 *
 * 建仓期 = 首笔买入日至今，长度因人而异（有人三年有人三天），档位表达不了——
 * 合并 research 纪要 §6 待办 #6（原计划单独一张卡）：落成走势卡的一个区间选项，
 * 复用同一张图与口径脚注，不为同一条曲线新开一张卡。仅在有流水时出现
 * （没买过就没有「建仓期」可言）。
 */
type RangeValue = TrendRange | "HOLDING";

const range = ref<RangeValue>("3M");
const loading = ref(false);
const failed = ref(false);
const trend = ref<ProductTrendResult | null>(null);

const themeTick = useThemeTick();

/** 品类无序列数据源（manager / portfolio / 无日线的 index）：后端 kind 返回空串。
    整卡不渲染，不在首屏顶一张空卡（设计 §6 降级规则；判据说明见组件头注释）。 */
const noSeries = computed(
  () => trend.value !== null && trend.value.kind === ""
);

/** hex → rgba：面积渐变需要具体色值（CSS 变量不能直接给 alpha） */
function hexToRgba(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec((hex || "").trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

const hasData = computed(() => (trend.value?.values.length ?? 0) >= 2);

/** 场内 = 有 OHLCV → 画 K 线；场外基金只有净值 → 退回净值线（品类差异化） */
const isCandle = computed(() => (trend.value?.ohlc?.length ?? 0) >= 2);

/** 成交量副图：整段都没有量能数据时（个别来源缺列）不占版面 */
const hasVolume = computed(
  () =>
    isCandle.value && (trend.value?.ohlc ?? []).some(o => (o.volume ?? 0) > 0)
);

const candleCloses = computed(() =>
  (trend.value?.ohlc ?? []).map(o => o.close)
);

// ── 买卖点 / 成本线叠加（#2171）────────────────────────────────────
/**
 * 交易时间线（私有数据，仅持有时拉）。
 *
 * 未登录 / 无流水后端返回**同构空结构**（points/cost_line 为空数组），
 * 因此这里只判 `points.length`，不分支解析；拉取失败静默降级——
 * 叠加层是增量信息，主曲线不因为它挂掉（设计 §6 诚实降级）。
 */
const timeline = ref<TradeTimelineResult | null>(null);

/** 叠加层开关：默认开（「我买在了哪」是买方核心诉求），信息过载时可关 */
const showMarkers = ref(true);

async function loadTimeline() {
  if (!props.symbol || props.hasPosition !== true) {
    timeline.value = null;
    return;
  }
  try {
    const res = await getTradeTimeline({ symbol: props.symbol });
    timeline.value = res.data;
  } catch {
    timeline.value = null;
  }
}

// 时间线不分区间（全量重放），symbol / 持有状态变化才重拉
watch(() => [props.symbol, props.hasPosition], loadTimeline, {
  immediate: true
});

/** 首笔交易日（建仓期区间的起点；无流水为 null） */
const firstTradeDate = computed(
  () => timeline.value?.summary.first_trade_date ?? null
);

/** 区间选项：有流水才追加「建仓」（没买过就没有建仓期可言） */
const rangeOptions = computed(() =>
  firstTradeDate.value
    ? [...RANGE_BASE_OPTIONS, { label: "建仓", value: "HOLDING" as RangeValue }]
    : RANGE_BASE_OPTIONS
);

/** 「历轮买卖」开关（#2171 P1）：默认开=显示全部轮次；关=只看最近一轮。
    清仓后重建仓的用户，旧轮次的点会让「我现在的成本线」难以认读。 */
const showHistoryRounds = ref(true);

/** 最近一轮的起点下标：最后一笔清仓（closed）的下一笔（无清仓则 0） */
const currentRoundStart = computed(() => {
  const pts = timeline.value?.points ?? [];
  for (let i = pts.length - 1; i >= 0; i--) {
    if (pts[i].closed) return i + 1;
  }
  return 0;
});

/** 是否存在历史轮次（决定「历轮」开关可不可见） */
const hasHistoryRounds = computed(() => currentRoundStart.value > 0);

/** 当前展示的交易点（历轮开关过滤后） */
const visiblePoints = computed(() => {
  const pts = timeline.value?.points ?? [];
  return showHistoryRounds.value ? pts : pts.slice(currentRoundStart.value);
});

/** 当前展示的成本线（与可见交易点同轮次；成本线在清仓后自然重启，
    按首个可见点的日期截断即可，不另造轮次概念） */
const visibleCostLine = computed(() => {
  const line = timeline.value?.cost_line ?? [];
  if (showHistoryRounds.value) return line;
  const pts = visiblePoints.value;
  if (!pts.length) return [];
  const from = pts[0].date;
  return line.filter(c => c.date >= from);
});

/** 日期 → 净值：买卖点画在当日净值位置（用户实际按净值成交，#2171 定稿） */
const navByDate = computed(() => {
  const m = new Map<string, number>();
  const dates = trend.value?.dates ?? [];
  const values = trend.value?.values ?? [];
  dates.forEach((d, i) => m.set(d, values[i]));
  return m;
});

/**
 * 买卖点 scatter 数据。
 *
 * **同日多笔按方向聚合**（金额合计、笔数计数）——不合并会两个点重叠成一个，
 * tooltip 也说不清「那天到底操作了几笔」。区间外的交易日（point.date 不在
 * trend.dates 里）直接丢弃：曲线没画到那天，点画上去是悬空的。
 *
 * **低于当时成本线的空心编码**（#2171 P1）：当日均价 < 当日最后一笔之前的持仓均价
 * → 空心三角。买在成本线下=低吸、卖在成本线下=割肉，都是买方要一眼看到的「这笔
 * 划不划算」（吸收自评估期砍掉的「越跌越买评分」）。首笔前无持仓（参照为 null）
 * 不判——没有参照就不下结论。
 */
const markerData = computed(() => {
  const nav = navByDate.value;
  type MarkerMeta = {
    side: "buy" | "sell";
    date: string;
    y: number;
    amount: number;
    quantity: number;
    count: number;
    closed: boolean;
    confirm: string | null;
    account: string | null;
    /** 当日最后一笔之前的持仓均价（元/份）；无参照为 null */
    costRef: number | null;
  };
  const agg = new Map<string, MarkerMeta>();
  for (const p of visiblePoints.value) {
    const y = nav.get(p.date);
    if (y === undefined || !Number.isFinite(y)) continue;
    const key = `${p.side}@${p.date}`;
    const cur =
      agg.get(key) ??
      ({
        side: p.side,
        date: p.date,
        y,
        amount: 0,
        quantity: 0,
        count: 0,
        closed: false,
        confirm: p.confirm_date,
        account: p.account_name,
        costRef: null
      } as MarkerMeta);
    cur.amount += p.amount_yuan;
    cur.quantity += p.quantity;
    cur.count += 1;
    cur.closed = cur.closed || p.closed;
    // 取当日最后一笔的参照均价（聚合后与当日均价比较）
    if (p.cost_before_avg_yuan !== null) cur.costRef = p.cost_before_avg_yuan;
    agg.set(key, cur);
  }
  const decorate = (meta: MarkerMeta) => {
    const avgPrice = meta.quantity > 0 ? meta.amount / meta.quantity : null;
    const below =
      avgPrice !== null && meta.costRef !== null && avgPrice < meta.costRef;
    const deviation =
      avgPrice !== null && meta.costRef && meta.costRef > 0
        ? +(((avgPrice - meta.costRef) / meta.costRef) * 100).toFixed(2)
        : null;
    return {
      value: [meta.date, meta.y] as [string, number],
      ...meta,
      avgPrice,
      below,
      deviation
    };
  };
  const buy: ReturnType<typeof decorate>[] = [];
  const sell: ReturnType<typeof decorate>[] = [];
  for (const meta of agg.values()) {
    (meta.side === "buy" ? buy : sell).push(decorate(meta));
  }
  return { buy, sell };
});

/** 成本线：cost_line 前向填充到区间每一天（非交易日延续前值；首笔交易前为 null 不画） */
const costSeriesData = computed(() => {
  const m = new Map(visibleCostLine.value.map(c => [c.date, c.cost_yuan]));
  let last: number | null = null;
  return (trend.value?.dates ?? []).map(d => {
    if (m.has(d)) last = m.get(d) ?? null;
    return last;
  });
});

/** 叠加层是否有效：开关开着 + 有交易点 + 场外净值线（首版不叠 K 线，见组件头注释） */
const markersActive = computed(
  () =>
    showMarkers.value &&
    !isCandle.value &&
    markerData.value.buy.length + markerData.value.sell.length > 0
);

/** 有交易点（决定开关可不可见；与 markersActive 的区别是不受开关自身影响） */
const hasMarkers = computed(
  () => markerData.value.buy.length + markerData.value.sell.length > 0
);

/** 有流水（决定累计收益面板可不可见；含只有分红没有买卖的边界） */
const hasTrades = computed(() => {
  const s = timeline.value?.summary;
  if (!s) return false;
  return s.buy_count + s.sell_count + s.dividend_count > 0;
});

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

/**
 * 蜡烛图数据。
 *
 * ECharts 的 `candlestick` 要求 `[open, close, low, high]` 这个**固定顺序**（不是
 * OHLC 顺序）——写错不会报错，只会画出一条形状诡异的图。
 *
 * 盘中价缺失时用收盘价兜底：ECharts 不接受 null，而「没有盘中数据」在图上表现为
 * 一根没有上下影线的横线，比整段图缺一根要诚实。
 */
const candleData = computed(() =>
  (trend.value?.ohlc ?? []).map(o => [
    o.open ?? o.close,
    o.close,
    o.low ?? o.close,
    o.high ?? o.close
  ])
);

/** 历史不足：实际跨度不到请求区间的一半 → 提示已收敛（长区间待 #1535 落库后放开） */
const spanNotice = computed(() => {
  const t = trend.value;
  if (!t || !hasData.value) return "";
  if (t.available_days >= t.requested_days * 0.5) return "";
  return `历史数据仅覆盖 ${t.available_days} 天，短于所选区间`;
});

const chartOption = computed(() => {
  void themeTick.value; // 主题切换时重算，让曲线重读 CSS 变量
  const dates = trend.value?.dates ?? [];
  const values = trend.value?.values ?? [];
  const rise = getCssVar(CHART_TOKENS.rise, "#e34f38");
  const fall = getCssVar(CHART_TOKENS.fall, "#287d51");

  // 网格线取**真实色值**并用实线：
  // · ECharts 不解析 `var(--x)`，直接给变量字符串等于给了一个无效色（旧版就是）；
  // · 虚线在密集 K 线与影线之间会糊成一片，是「看着杂乱」的一半原因（#1969）。
  const splitLine = {
    lineStyle: { color: getCssVar(CHART_TOKENS.borderLight, "#e8e8e8") }
  };

  if (isCandle.value) {
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
        { scale: true, axisLabel: { fontSize: 11 }, splitLine },
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
        maLine(5, CHART_TOKENS.warning, "#e6a23c"),
        maLine(10, CHART_TOKENS.info, "#409eff"),
        maLine(20, CHART_TOKENS.textTertiary, "#9aa0a6"),
        ...volumeSeries
      ]
    };
  }

  // 场外（累计净值，#2171）或没有 OHLCV 的场内：一条线。
  // **不平滑**：平滑会画出实际不存在的峰谷，价格序列上那是失真（#1969）。
  const rising = values.length >= 2 && values[values.length - 1] >= values[0];
  const lineColor = rising ? rise : fall;
  // 叠加层取色刻意避开 rise（红）/ fall（绿）：买卖点不是涨跌语义，
  // 涂红涂绿会让用户把「我买过」误读成「涨了」。蓝=买入、橙=卖出、
  // 中性灰虚线=成本线——与净值曲线（动态涨跌色）三层不打架（#2171 定稿）。
  const markerBuyColor = getCssVar(CHART_TOKENS.info, "#409eff");
  const markerSellColor = getCssVar(CHART_TOKENS.warning, "#e6a23c");
  const costLineColor = getCssVar(CHART_TOKENS.textTertiary, "#9aa0a6");

  /** 轴触发 tooltip：净值行 + 当日成本线 + 当日买卖汇总（#2171）。
      同日多笔在 markerData 已聚合，这里直接显示「N 笔合计」；
      低于当时成本线的点附偏离度（空心编码的文字版，色弱用户也能读到）。 */
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
      } else {
        const v = Array.isArray(p.value) ? Number(p.value[1]) : Number(p.value);
        rows.push(
          `${p.marker ?? ""}${seriesName}：${Number.isFinite(v) ? v.toFixed(4) : "—"}`
        );
      }
    }
    return rows.join("<br/>");
  };

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
      axisLabel: { fontSize: 11 },
      splitLine
    },
    series: [
      {
        name: "净值",
        type: "line",
        data: values,
        smooth: false,
        symbol: "none",
        lineStyle: { color: lineColor, width: 2 },
        areaStyle: { color: hexToRgba(lineColor, 0.08) }
      },
      // 成本线（#2171）：移动加权（含手续费），非交易日前向延续；清仓日断在
      // 最后一笔（costSeriesData 在首笔前为 null，天然不画）。虚线 + 中性灰，
      // 与净值曲线（实线 + 涨跌色）形态分层，不抢主视觉。
      ...(markersActive.value
        ? [
            {
              name: "成本线",
              type: "line",
              data: costSeriesData.value,
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
              data: markerData.value.buy.map(m => ({
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
              symbolSize: 9,
              z: 5
            },
            {
              name: "卖出",
              type: "scatter",
              data: markerData.value.sell.map(m => ({
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
              symbolSize: 9,
              z: 5
            }
          ]
        : [])
    ]
  };
});

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  // 建仓期：显式起始日（首笔买入日）覆盖档位。拿不到起始日（换标的后尚无流水，
  // 或时间线还没回来）时退回 3M——绝不把「建仓」这个前端档位当 range 发给后端。
  const useHolding = range.value === "HOLDING" && firstTradeDate.value !== null;
  try {
    const res = await getProductTrend({
      symbol: props.symbol,
      range: range.value === "HOLDING" ? "3M" : (range.value as TrendRange),
      asset_type: props.assetType,
      ...(useHolding ? { start: firstTradeDate.value as string } : {})
    });
    trend.value = res.data;
  } catch {
    // 拉不到就当无数据：区块降级为空态，不影响详情页其余部分。
    // 与「品类无序列源」（kind 空串，整卡不渲染）是两回事——这里是取数失败，
    // 卡片要留在原处并告知可重试，不能装作「这个品类没有走势」。
    trend.value = null;
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

// 区块懒加载：走势图数据不阻塞 Hero 渲染（设计 §5 取数编排）
watch(() => props.symbol, load, { immediate: true });
watch(range, load);
// 起始日晚于走势请求回来（时间线是并行拉的）：停在「建仓」档时补一次，
// 避免用上一个标的的起始日画窗口
watch(firstTradeDate, () => {
  if (range.value === "HOLDING") void load();
});
</script>

<template>
  <CardBlock v-if="!noSeries" class="trend-section">
    <SectionHeader title="走势">
      <template #action>
        <SegmentedControl
          v-model="range"
          :options="rangeOptions"
          size="small"
          ariaLabel="切换走势区间"
        />
        <!-- 买卖点 / 成本线开关（#2171）：有交易点才可开；关掉后只剩净值曲线。
             默认开——「我买在了哪」是买方核心诉求；信息过载的用户可自行关闭。 -->
        <el-checkbox
          v-if="hasMarkers"
          v-model="showMarkers"
          size="small"
          class="trend-section__marker-toggle"
        >
          买卖点
        </el-checkbox>
        <!-- 历轮买卖（#2171 P1）：仅清仓后重建仓的用户可见。关掉只看最近一轮——
             旧轮次的点会让「现在的成本线」难以认读。 -->
        <el-checkbox
          v-if="hasHistoryRounds && showMarkers"
          v-model="showHistoryRounds"
          size="small"
          class="trend-section__marker-toggle"
        >
          历轮
        </el-checkbox>
      </template>
    </SectionHeader>

    <p v-if="loading" class="trend-section__hint">正在读取走势…</p>

    <p v-else-if="failed" class="trend-section__hint">
      走势读取失败，可稍后重试
    </p>

    <p v-else-if="!hasData" class="trend-section__hint">暂无该区间的历史数据</p>

    <template v-else>
      <v-chart
        :option="chartOption"
        :autoresize="true"
        class="trend-section__chart"
      />
      <p v-if="spanNotice" class="trend-section__hint">{{ spanNotice }}</p>
      <!-- 来源说「哪个网站」，口径说「怎么算的」——后端分开给，前端只排版，
           不在这里推断「close 就等于前复权」（#1969）。
           空心买卖点（#2171 P1）：成交价低于当时持仓成本——低吸 / 割肉。 -->
      <p class="trend-section__footnote">
        数据日期：{{ trend?.dates?.[0] }} 至
        {{ trend?.dates?.[trend.dates.length - 1] }}
        <template v-if="trend?.source">
          · 数据来源：{{ trend.source }}（{{ trend.basis }}）
        </template>
        <template v-if="hasMarkers"> · 空心△ = 低于当时成本</template>
      </p>
    </template>

    <!-- 累计收益面板（#2171 P1）：全程累计已实现 + 紧凑统计条。
         有流水才渲染；数据来自与叠加层同一次时间线请求，不重复取数。 -->
    <ProductProfitPanel v-if="hasTrades" :timeline="timeline" />
  </CardBlock>
</template>

<style scoped>
.trend-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.trend-section__chart {
  width: 100%;

  /* K 线格 + 量能格叠放（见 chartOption 的 grid 高度），故比单线图高一截 */
  height: 300px;
}

.trend-section__hint {
  margin: 0;
  font-size: 13px;
  color: var(--text-tertiary-ink);
}

.trend-section__footnote {
  margin: 0;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

/* 买卖点开关：与区间切换胶囊同处 action 槽，拉开间距不贴在一起 */
.trend-section__marker-toggle {
  margin-left: var(--space-2, 8px);
}
</style>
