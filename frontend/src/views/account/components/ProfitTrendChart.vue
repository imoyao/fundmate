<template>
  <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
    <h3 class="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
      收益趋势
    </h3>
    <canvas ref="profitChartCanvas" />
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";
import Chart from "chart.js/auto";

const profitChartCanvas = ref(null);
let profitChartInstance = null;

onMounted(() => {
  if (profitChartCanvas.value) {
    const ctx = profitChartCanvas.value.getContext("2d");
    profitChartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: ["一月", "二月", "三月", "四月", "五月", "六月"],
        datasets: [
          {
            label: "总收益",
            data: [65, 59, 80, 81, 56, 55],
            fill: false,
            borderColor: "#4299e1", // blue-500
            tension: 0.1
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            labels: {
              color: "rgb(156 163 175)" // gray-400
            }
          }
        },
        scales: {
          x: {
            ticks: {
              color: "rgb(156 163 175)" // gray-400
            },
            grid: {
              color: "rgba(200, 200, 200, 0.1)"
            }
          },
          y: {
            ticks: {
              color: "rgb(156 163 175)" // gray-400
            },
            grid: {
              color: "rgba(200, 200, 200, 0.1)"
            }
          }
        }
      }
    });
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
  max-height: 300px; /* 限制图表高度 */
}
</style>
