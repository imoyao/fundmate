<!--
  AssetAllocationBars · 横向条形图（与 AssetAllocationDonut 同级，强制复用）

  为什么在环形图之外另立一个组件：两者适配的**分类数量**差了一个量级。
  饼图 / 环形图靠**角度**传达比例，人眼对角度的分辨精度远低于长度——分类一多
  （行业配置后端按 `DEFAULT_INDUSTRY_TOP_N = 12` 截断，加上「其他」可达 13 个）
  就退化成「一堆细扇区 + 挤在一起的图例」，读者比不出「电子 8%」和「医药 7%」；
  横向条形图按长度排序后，长度差异一眼可辨。

  故取舍是：**少分类（≤6，如账本的「投资 / 现金」两类）用 AssetAllocationDonut 看构成，
  多分类（如行业配置的十余项）用本组件看排名**。两者都基于 `useEchartsLifecycle`。

  - 颜色必须走 CSS 语义变量（colorMap 的值为变量名，如 "--asset-cat-stock"）；不传或缺失时
    用 --chart-01~08 循环取色（design.md「Data Visualization」红线：禁止硬编码 hex）。
  - 不设图例：分类名已在 y 轴，重复一遍只会挤占宽度。
-->
<template>
  <div
    ref="chartRef"
    class="allocation-bars"
    :style="{ height: `${chartHeight}px` }"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import echarts from "@/plugins/echarts";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";
import { getCssVar } from "@/composables/echarts/theme";

const props = withDefaults(
  defineProps<{
    data: { name: string; value: number }[];
    /** 分类名 → CSS 变量名（如 `{ 股票: "--invest-stock" }`） */
    colorMap?: Record<string, string>;
    emptyText?: string;
    /** 条右侧数值标签；默认按百分比格式。**不要在这里塞「占比」的二次换算**——
     *  条长本身就是 value，再按总和折算一次会让人误以为那是另一个口径 */
    formatValue?: (value: number) => string;
    /** 单行高度（px），决定总高度；行多时容器自然变高，不会压扁 */
    rowHeight?: number;
  }>(),
  {
    colorMap: () => ({}),
    emptyText: "暂无数据",
    rowHeight: 26
  }
);

const chartRef = ref<HTMLElement | null>(null);

const CHART_PALETTE_VARS = [
  "--chart-01",
  "--chart-02",
  "--chart-03",
  "--chart-04",
  "--chart-05",
  "--chart-06",
  "--chart-07",
  "--chart-08"
];

/** 条形实际值；0 / 负值剔除（负占比没有「条」可画，且没有业务含义） */
const items = computed(() =>
  props.data
    .filter(d => d.value > 0)
    .map(d => ({ name: d.name, value: d.value }))
);

/**
 * 空态判定：数组为空 **或** 全部值非正 —— 与 `AssetAllocationDonut` 同口径。
 *
 * ECharts 在总和为 0 时不会画出错图，但坐标轴会退化成 0~1 的任意刻度，
 * 屏上是一条长度无意义的条，比「没有数据」更难读。
 */
const isDataEmpty = computed(() => items.value.length === 0);

/**
 * 容器高度随条目数增长（固定高度会把 13 行压成 13 根看不出差别的细线，
 * 那就退化成了另一种饼图）。上下各留 16px 给首末行的呼吸位。
 */
const chartHeight = computed(() =>
  isDataEmpty.value
    ? 160
    : Math.max(140, items.value.length * props.rowHeight + 32)
);

function colorFor(name: string, index: number): string {
  const varName = props.colorMap[name];
  if (varName) return getCssVar(varName, "#8E8B82");
  return getCssVar(
    CHART_PALETTE_VARS[index % CHART_PALETTE_VARS.length] ?? "--chart-01",
    "#8E8B82"
  );
}

function buildOption() {
  // 尊重系统减弱动效偏好：关闭 echarts 入场动画
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const rows = items.value;
  const format = props.formatValue ?? ((v: number) => `${v.toFixed(2)}%`);

  if (isDataEmpty.value) {
    return {
      animation: !reduceMotion,
      title: {
        text: props.emptyText,
        left: "center",
        top: "middle",
        textStyle: {
          color: getCssVar("--text-tertiary", "#999"),
          fontSize: 12,
          fontWeight: "normal"
        }
      }
    };
  }

  const maxValue = Math.max(...rows.map(r => r.value));

  return {
    animation: !reduceMotion,
    tooltip: {
      trigger: "item",
      backgroundColor: getCssVar("--bg-card", "#ffffff"),
      borderColor: getCssVar("--border-light", "#f0ebe4"),
      textStyle: {
        color: getCssVar("--text-primary", "#2d2a24"),
        fontSize: 12
      },
      formatter: (params: { name: string; value: number }) =>
        `${params.name}<br/>${format(params.value)}`
    },
    // grid 留右侧空间给数值标签；left/top/bottom 交给 containLabel 量出分类名宽度
    grid: { left: 4, right: 8, top: 8, bottom: 4, containLabel: true },
    xAxis: {
      type: "value",
      // 数值已直接标在条右侧，再画一套刻度只是噪音；轴线留着给「基线=0」一个视觉锚
      show: false,
      // 顶到最大值的 102%：否则最长那条的标签会顶出容器右缘被裁掉
      max: maxValue * 1.02
    },
    yAxis: {
      type: "category",
      data: rows.map(r => r.name),
      // ECharts 的 category 轴自下而上排，不 inverse 第一项会沉到最底下
      inverse: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: getCssVar("--text-primary", "#2d2a24"),
        fontSize: 12,
        // 行业名最长可达 6-7 个汉字，超出截断并靠 tooltip 兜全名
        width: 96,
        overflow: "truncate"
      }
    },
    series: [
      {
        type: "bar",
        // barMaxWidth 而非 barWidth：条目多时条会按行高分摊，
        // 写死 barWidth 会在条目少时显得过于粗重
        barMaxWidth: 14,
        data: rows.map((r, i) => ({
          value: r.value,
          itemStyle: { color: colorFor(r.name, i) }
        })),
        // 右端圆角、左端贴基线取直角：条是从 0 开始的，起点圆角会读成「不从 0 起」
        itemStyle: {
          borderRadius: [0, 4, 4, 0]
        },
        label: {
          show: true,
          position: "right",
          formatter: (params: { value: number }) => format(params.value),
          color: getCssVar("--text-secondary", "#6b655c"),
          fontSize: 12
        }
      }
    ]
  };
}

const { render } = useEchartsLifecycle(
  [
    {
      ref: chartRef,
      build: el => {
        const chart = echarts.init(el);
        chart.setOption(buildOption());
        return chart;
      }
    }
  ],
  { keepAlive: true }
);

/**
 * 数据变化时重绘。
 *
 * `flush: "post"` 不是随手写的：容器高度是 `chartHeight` 按条目数算出来的
 * inline style，而 `watch` 默认 `flush: "pre"` 在 DOM 更新**之前**触发 ——
 * 那时新高度还没落到 style 上，`echarts.init` 量到的是旧高度，图表就被画进一个
 * 即将变高的容器里（表现为底部一条空白）。改成 `post` 等 DOM 更新完再重建。
 *
 * `chartHeight` 一并列入依赖：条目数变了高度就要变，而它是由 `data` 推导的
 * computed，显式列出可避免将来有人改了推导链却忘了同步 watch。
 */
watch([() => props.data, chartHeight], () => render(), { flush: "post" });
</script>

<style scoped>
.allocation-bars {
  width: 100%;
}
</style>
