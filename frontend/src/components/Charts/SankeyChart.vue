<!-- src/components/Charts/SankeyChart.vue -->
<template>
  <div class="sankey-chart-container">
    <!-- 空状态提示：用 v-show 而不是 v-if，避免 chartRef 被销毁 -->
    <div v-show="isEmpty" class="empty-state">
      <IconifyIconOffline
        icon="ep:folder-opened"
        class="text-4xl text-gray-300 mb-2"
      />
      <p class="text-gray-400">暂无资产构成数据</p>
    </div>
    <!-- 图表容器始终存在 -->
    <div
      ref="chartRef"
      class="chart"
      :style="{ visibility: isEmpty ? 'hidden' : 'visible' }"
    />
  </div>
</template>

<script setup lang="ts">
import {
  ref,
  onMounted,
  onBeforeUnmount,
  watch,
  computed,
  nextTick
} from "vue";
import * as echarts from "echarts";
import { IconifyIconOffline } from "@/components/ReIcon";

const props = defineProps<{
  data: { nodes: any[]; links: any[] };
  displayMode: "amount" | "percent" | "hidden";
}>();

const chartRef = ref<HTMLDivElement>();
let chart: echarts.ECharts | null = null;
const isEmpty = ref(true);

const totalValue = computed(() => {
  const totals: Record<string, number> = {};
  props.data.links.forEach(l => {
    totals[l.source] = (totals[l.source] || 0) + (l.value || 0);
  });
  return Math.max(...Object.values(totals), 1);
});

function formatLabel(params: any) {
  // 直接使用 echarts 自动计算的节点值
  const val = params.value ?? 0;
  if (props.displayMode === "hidden") return params.name;
  if (props.displayMode === "percent") {
    const pct =
      totalValue.value > 0
        ? ((val / totalValue.value) * 100).toFixed(1) + "%"
        : "0%";
    return `${params.name}\n${pct}`;
  }
  const amount =
    val >= 10000 ? (val / 10000).toFixed(1) + "万" : val.toLocaleString();
  return `${params.name}\n¥${amount}`;
}

function renderChart() {
  if (!chartRef.value) return;

  const hasData = props.data.nodes?.length > 0 && props.data.links?.length > 0;
  isEmpty.value = !hasData;

  if (!hasData) {
    chart?.dispose();
    chart = null;
    return;
  }

  if (!chart) {
    chart = echarts.init(chartRef.value);
  }

  chart.setOption({
    tooltip: {
      trigger: "item",
      triggerOn: "mousemove",
      backgroundColor: "rgba(255,255,255,0.95)",
      borderColor: "#e5e7eb",
      textStyle: { color: "#333", fontSize: 12 },
      formatter: (params: any) => {
        if (params.dataType === "node") {
          const disp =
            props.displayMode === "hidden"
              ? "***"
              : "¥" + (params.value || 0).toLocaleString();
          return `${params.name}<br/>${disp}`;
        }
        return `${params.data.source} → ${params.data.target}<br/>¥${(params.value || 0).toLocaleString()}`;
      }
    },
    series: [
      {
        type: "sankey",
        layout: "none",
        data: props.data.nodes,
        links: props.data.links,
        emphasis: { focus: "adjacency" },
        lineStyle: { color: "gradient", curveness: 0.5, opacity: 0.2 },
        nodeWidth: 20,
        nodeGap: 18,
        layoutIterations: 32,
        label: { show: true, formatter: formatLabel }
      }
    ]
  });
}

// 监听数据变化
watch(
  () => [props.data.nodes, props.data.links, props.displayMode],
  () => {
    nextTick(renderChart);
  },
  { deep: true, immediate: true }
);

const resizeHandler = () => chart?.resize();
window.addEventListener("resize", resizeHandler);

onBeforeUnmount(() => {
  chart?.dispose();
  window.removeEventListener("resize", resizeHandler);
});
</script>

<style scoped>
.sankey-chart-container {
  position: relative;
  width: 100%;
  height: 400px;
  contain: layout style;
}

.chart {
  width: 100%;
  height: 100%;
}

.empty-state {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
</style>
