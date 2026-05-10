<template>
  <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
    <h3 class="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
      资产分布
    </h3>
    <canvas ref="distributionChartCanvas" />
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";
import Chart from "chart.js/auto";

const distributionChartCanvas = ref(null);
let distributionChartInstance = null;

onMounted(() => {
  if (distributionChartCanvas.value) {
    const ctx = distributionChartCanvas.value.getContext("2d");
    distributionChartInstance = new Chart(ctx, {
      type: "pie",
      data: {
        labels: ["股票", "基金", "房地产", "贵金属", "现金"],
        datasets: [
          {
            data: [30, 20, 40, 5, 5],
            backgroundColor: [
              "#4299e1", // blue-500
              "#48bb78", // green-500
              "#ecc94b", // yellow-500
              "#ed8936", // orange-500
              "#a0aec0" // gray-500
            ],
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
            labels: {
              color: "rgb(156 163 175)" // gray-400
            }
          }
        }
      }
    });
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
  max-height: 300px; /* 限制图表高度 */
}
</style>
