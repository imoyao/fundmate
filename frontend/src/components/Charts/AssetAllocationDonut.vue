<!--
  AssetAllocationDonut · 资产配置环形图（强制复用，见 docs/design/components.md）
  - 统一「环形 + 底部图例（分类名 + 占比）」的资产分布图，替代各页手写 pie option。
  - 基于 useEchartsLifecycle：自动 render / window resize / 卸载 dispose / keepAlive 重绘。
  - 颜色必须走 CSS 语义变量：colorMap 的值为变量名（如 "--invest-stock"）；不传或缺失时
    用 --chart-01~08 循环取色（design.md「Data Visualization」红线：禁止硬编码 hex）。
-->
<template>
  <div ref="chartRef" class="allocation-donut" />
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import echarts from "@/plugins/echarts";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";
import { getCssVar } from "@/composables/echarts/theme";

interface DonutDatum {
  name: string;
  value: number;
}

const props = withDefaults(
  defineProps<{
    /** 分布数据（name 分类名，value 数值） */
    data: DonutDatum[];
    /** 分类色映射：name -> CSS 变量名；不传或缺失用 --chart-01~08 循环 */
    colorMap?: Record<string, string>;
    /** 空态文案（中心显示），默认「暂无数据」 */
    emptyText?: string;
    /** 是否显示底部图例，默认 true */
    showLegend?: boolean;
  }>(),
  { colorMap: () => ({}), emptyText: "暂无数据", showLegend: true }
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

function colorFor(name: string): string {
  const varName = props.colorMap[name];
  if (varName) return getCssVar(varName, "#8E8B82");
  const idx = props.data.findIndex(d => d.name === name);
  return getCssVar(
    CHART_PALETTE_VARS[idx % CHART_PALETTE_VARS.length] ?? "--chart-01",
    "#8E8B82"
  );
}

function buildOption() {
  const isDataEmpty = props.data.length === 0;
  const total = props.data.reduce((s, d) => s + (d.value || 0), 0);
  const legendTextColor = getCssVar("--text-secondary", "#6b655c");
  const borderColor = getCssVar("--bg-card", "#ffffff");
  // 尊重系统减弱动效偏好：关闭 echarts 入场动画
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const showLegend = props.showLegend && !isDataEmpty;

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
      formatter: (params: { name: string; value: number }) => {
        const pct = total > 0 ? ((params.value / total) * 100).toFixed(1) : "0";
        return `${params.name}<br/>¥${Number(params.value).toLocaleString()}（${pct}%）`;
      }
    },
    legend: showLegend
      ? {
          bottom: 0,
          icon: "circle",
          itemWidth: 8,
          itemHeight: 8,
          itemGap: 12,
          textStyle: { color: legendTextColor, fontSize: 12 },
          // 分类名 + 占比（%），占比按 total 实时计算
          formatter: (name: string) => {
            const d = props.data.find(x => x.name === name);
            const pct =
              total > 0 ? (((d?.value || 0) / total) * 100).toFixed(1) : "0";
            return `${name} ${pct}%`;
          }
        }
      : undefined,
    series: [
      {
        type: "pie",
        radius: isDataEmpty ? "50%" : ["45%", "70%"],
        itemStyle: {
          color: (params: { name?: string }) => colorFor(params.name ?? ""),
          borderRadius: 6,
          borderColor,
          borderWidth: 2
        },
        label: isDataEmpty
          ? {
              show: true,
              position: "center",
              formatter: props.emptyText,
              color: getCssVar("--text-tertiary", "#999"),
              fontSize: 12
            }
          : { show: false },
        labelLine: { show: !isDataEmpty },
        data: isDataEmpty ? [{ name: props.emptyText, value: 1 }] : props.data
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

// 数据变化（父组件传新数组引用）时重绘
watch(
  () => props.data,
  () => render()
);
</script>

<style scoped>
.allocation-donut {
  width: 100%;

  /* 容器高度由调用方通过 class（如 flex-1）控制 */
  height: 100%;
  min-height: 200px;
}
</style>
