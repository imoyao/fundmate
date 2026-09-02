<template>
  <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
    <h3 class="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
      资产分布
    </h3>
    <canvas v-show="hasData" ref="distributionChartCanvas" />
    <p v-if="!hasData" class="text-gray-400 text-sm text-center py-8">
      暂无分布数据
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue";
import Chart from "chart.js/auto";
import { getDistributions } from "@/api/summary";
import { getCssVar } from "@/composables/echarts/theme";

const distributionChartCanvas = ref<HTMLCanvasElement | null>(null);
let distributionChartInstance: Chart | null = null;
const hasData = ref(false);

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

onMounted(async () => {
  try {
    const res = (await getDistributions()) as any;
    const list = Array.isArray(res?.data?.category_distribution)
      ? res.data.category_distribution
      : [];
    if (distributionChartCanvas.value && list.length) {
      hasData.value = true;
      const ctx = distributionChartCanvas.value.getContext("2d");
      if (!ctx) return;
      distributionChartInstance = new Chart(ctx, {
        type: "pie",
        data: {
          labels: list.map((d: any) => d.name),
          datasets: [
            {
              data: list.map((d: any) => d.value),
              // 颜色走 CSS 语义变量（design.md 红线：禁止硬编码 hex）
              backgroundColor: list.map((_: any, i: number) =>
                getCssVar(CHART_PALETTE_VARS[i % 8], "#8E8B82")
              ),
              hoverOffset: 4
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: "bottom",
              labels: { color: "rgb(156 163 175)" }
            }
          }
        }
      });
    }
  } catch {
    hasData.value = false;
  }
});

onBeforeUnmount(() => {
  if (distributionChartInstance) {
    distributionChartInstance.destroy();
  }
});
</script>

<style scoped>
canvas {
  max-height: 300px;
}
</style>
