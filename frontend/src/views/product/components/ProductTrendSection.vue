<script setup lang="ts">
import { computed, ref, watch } from "vue";
import VChart from "vue-echarts";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import {
  getProductTrend,
  type ProductTrendResult,
  type TrendRange
} from "@/api/products";
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
 *   与持仓成本可比）；场外基金只有单位净值 → 净值线；
 * - 图表颜色一律经 `getCssVar` 取**真实色值**：ECharts 不解析 `var(--x)`，给变量字符串
 *   等于给了一个无效色（旧版 splitLine 的写法就是这么错的，也会让网格看起来发黑发乱）；
 * - 线条**不平滑**：smooth 会画出实际不存在的峰谷，价格序列上属失真；
 * - **无数据就显示空态**，绝不用 mock 顶替（设计 G1 教训）；
 * - 脚注写明「数据日期 · 来源 · 口径」——来源是站点名，不是内部表名（#1969）。
 */

const props = defineProps<{
  symbol: string;
  /** 品类：由 #1963 resolve 判定后回传，后端据此选收盘价 / 净值口径 */
  assetType?: string;
}>();

const RANGE_OPTIONS: { label: string; value: TrendRange }[] = [
  { label: "1月", value: "1M" },
  { label: "3月", value: "3M" },
  { label: "6月", value: "6M" },
  { label: "1年", value: "1Y" }
];

const range = ref<TrendRange>("3M");
const loading = ref(false);
const trend = ref<ProductTrendResult | null>(null);

const themeTick = useThemeTick();

/** hex → rgba：面积渐变需要具体色值（CSS 变量不能直接给 alpha） */
function hexToRgba(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec((hex || "").trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

const hasData = computed(() => (trend.value?.values.length ?? 0) >= 2);

/** 场内 = 有 OHLCV → 画 K 线；场外基金只有单位净值 → 退回净值线（品类差异化） */
const isCandle = computed(() => (trend.value?.ohlc?.length ?? 0) >= 2);

/** 成交量副图：整段都没有量能数据时（个别来源缺列）不占版面 */
const hasVolume = computed(
  () =>
    isCandle.value && (trend.value?.ohlc ?? []).some(o => (o.volume ?? 0) > 0)
);

const candleCloses = computed(() =>
  (trend.value?.ohlc ?? []).map(o => o.close)
);

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

  // 场外（单位净值）或没有 OHLCV 的场内：一条线。
  // **不平滑**：平滑会画出实际不存在的峰谷，价格序列上那是失真（#1969）。
  const rising = values.length >= 2 && values[values.length - 1] >= values[0];
  const lineColor = rising ? rise : fall;
  return {
    tooltip: { trigger: "axis" },
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
        type: "line",
        data: values,
        smooth: false,
        symbol: "none",
        lineStyle: { color: lineColor, width: 2 },
        areaStyle: { color: hexToRgba(lineColor, 0.08) }
      }
    ]
  };
});

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  try {
    const res = await getProductTrend({
      symbol: props.symbol,
      range: range.value,
      asset_type: props.assetType
    });
    trend.value = res.data;
  } catch {
    // 拉不到就当无数据：区块降级为空态，不影响详情页其余部分
    trend.value = null;
  } finally {
    loading.value = false;
  }
}

// 区块懒加载：走势图数据不阻塞 Hero 渲染（设计 §5 取数编排）
watch(() => props.symbol, load, { immediate: true });
watch(range, load);
</script>

<template>
  <CardBlock class="trend-section">
    <SectionHeader title="走势">
      <template #action>
        <SegmentedControl
          v-model="range"
          :options="RANGE_OPTIONS"
          size="small"
          ariaLabel="切换走势区间"
        />
      </template>
    </SectionHeader>

    <p v-if="loading" class="trend-section__hint">正在读取走势…</p>

    <p v-else-if="!hasData" class="trend-section__hint">
      {{ trend?.kind ? "暂无该区间的历史数据" : "该品类暂不提供走势" }}
    </p>

    <template v-else>
      <v-chart
        :option="chartOption"
        :autoresize="true"
        class="trend-section__chart"
      />
      <p v-if="spanNotice" class="trend-section__hint">{{ spanNotice }}</p>
      <!-- 来源说「哪个网站」，口径说「怎么算的」——后端分开给，前端只排版，
           不在这里推断「close 就等于前复权」（#1969） -->
      <p class="trend-section__footnote">
        数据日期：{{ trend?.dates?.[0] }} 至
        {{ trend?.dates?.[trend.dates.length - 1] }}
        <template v-if="trend?.source">
          · 数据来源：{{ trend.source }}（{{ trend.basis }}）
        </template>
      </p>
    </template>
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
</style>
