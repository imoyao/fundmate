<template>
  <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
    <h3 class="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
      收益趋势
    </h3>
    <canvas ref="profitChartCanvas" v-show="hasData" />
    <p v-if="!hasData" class="text-gray-400 text-sm text-center py-8">
      暂无收益数据
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue";
import Chart from "chart.js/auto";
import { getSnapshots } from "@/api/summary";

const profitChartCanvas = ref<HTMLCanvasElement | null>(null);
let profitChartInstance: Chart | null = null;
const hasData = ref(false);

onMounted(async () => {
  try {
    const res = (await getSnapshots()) as any;
    const list = Array.isArray(res?.data) ? res.data : [];
    if (profitChartCanvas.value && list.length) {
      hasData.value = true;
      const ctx = profitChartCanvas.value.getContext("2d");
      if (!ctx) return;
      profitChartInstance = new Chart(ctx, {
        type: "line",
        data: {
          labels: list.map((i: any) => i.snapshot_date),
          datasets: [
            {
              label: "净资产",
              data: list.map((i: any) => i.net_worth),
              fill: false,
              borderColor: "#4299e1",
              tension: 0.1
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              labels: { color: "rgb(156 163 175)" }
            }
          },
          scales: {
            x: {
              ticks: { color: "rgb(156 163 175)" },
              grid: { color: "rgba(200, 200, 200, 0.1)" }
            },
            y: {
              ticks: { color: "rgb(156 163 175)" },
              grid: { color: "rgba(200, 200, 200, 0.1)" }
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
  if (profitChartInstance) {
    profitChartInstance.destroy();
  }
});
</script>

<style scoped>
canvas {
  max-height: 300px;
}
</style>
