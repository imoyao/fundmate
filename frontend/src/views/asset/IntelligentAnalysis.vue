<template>
  <div class="intelligent-analysis p-6">
    <div class="mb-8">
      <h2 class="text-2xl font-bold">智能分析</h2>
      <p class="text-gray-500 mt-1">AI 驱动的资产健康度诊断</p>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div class="lg:col-span-2 space-y-6">
        <div class="bg-white rounded-xl shadow-md p-6">
          <div class="flex justify-between items-center mb-6">
            <h3 class="text-lg font-bold flex items-center">
              <IconifyIconOffline
                icon="ep:scale-to-balance"
                class="text-orange-500 mr-2"
              />
              资产配置建议
            </h3>
            <button
              class="px-4 py-2 bg-orange-500 text-white rounded-lg text-sm hover:bg-orange-600 transition-colors shadow-sm"
            >
              重新评估
            </button>
          </div>

          <div class="bg-gray-50 rounded-xl p-6 border border-gray-100">
            <div class="flex flex-col md:flex-row md:items-center gap-8">
              <div class="flex-shrink-0 mx-auto md:mx-0">
                <div class="relative w-32 h-32">
                  <svg class="w-full h-full" viewBox="0 0 100 100">
                    <circle
                      cx="50"
                      cy="50"
                      r="42"
                      fill="none"
                      stroke="#F3F4F6"
                      stroke-width="10"
                    />
                    <circle
                      cx="50"
                      cy="50"
                      r="42"
                      fill="none"
                      stroke="#FF4500"
                      stroke-width="10"
                      stroke-dasharray="264"
                      stroke-dashoffset="66"
                      transform="rotate(-90 50 50)"
                      stroke-linecap="round"
                    />
                  </svg>
                  <div
                    class="absolute inset-0 flex flex-col items-center justify-center"
                  >
                    <span class="text-3xl font-bold text-orange-500">75%</span>
                    <span class="text-xs text-gray-500">匹配度</span>
                  </div>
                </div>
              </div>

              <div class="flex-1 w-full">
                <p class="text-base font-medium mb-4">
                  根据您的风险偏好，当前资产配置建议：
                </p>

                <div class="space-y-4">
                  <div class="space-y-1">
                    <div class="flex justify-between items-center">
                      <span class="font-medium text-gray-700 text-sm"
                        >股票类资产</span
                      >
                      <div class="flex items-center gap-3">
                        <span class="text-xs text-gray-500"
                          >当前:
                          <span class="font-medium text-red-500"
                            >36.5%</span
                          ></span
                        >
                        <span class="text-xs font-medium">建议: 40%</span>
                      </div>
                    </div>
                    <div
                      class="relative h-2.5 bg-gray-200 rounded-full overflow-hidden"
                    >
                      <div
                        class="absolute left-0 top-0 h-full bg-red-100 rounded-full"
                        style="width: 40%"
                      />
                      <div
                        class="absolute left-0 top-0 h-full bg-red-500 rounded-full"
                        style="width: 36.5%"
                      />
                    </div>
                  </div>

                  <div class="space-y-1">
                    <div class="flex justify-between items-center">
                      <span class="font-medium text-gray-700 text-sm"
                        >基金类资产</span
                      >
                      <div class="flex items-center gap-3">
                        <span class="text-xs text-gray-500"
                          >当前:
                          <span class="font-medium text-amber-500"
                            >28.9%</span
                          ></span
                        >
                        <span class="text-xs font-medium">建议: 30%</span>
                      </div>
                    </div>
                    <div
                      class="relative h-2.5 bg-gray-200 rounded-full overflow-hidden"
                    >
                      <div
                        class="absolute left-0 top-0 h-full bg-orange-100 rounded-full"
                        style="width: 30%"
                      />
                      <div
                        class="absolute left-0 top-0 h-full bg-amber-500 rounded-full"
                        style="width: 28.9%"
                      />
                    </div>
                  </div>

                  <div class="space-y-1">
                    <div class="flex justify-between items-center">
                      <span class="font-medium text-gray-700 text-sm"
                        >房产类资产</span
                      >
                      <div class="flex items-center gap-3">
                        <span class="text-xs text-gray-500"
                          >当前:
                          <span class="font-medium text-green-500"
                            >34.6%</span
                          ></span
                        >
                        <span class="text-xs font-medium">建议: 20%</span>
                      </div>
                    </div>
                    <div
                      class="relative h-2.5 bg-gray-200 rounded-full overflow-hidden"
                    >
                      <div
                        class="absolute left-0 top-0 h-full bg-green-100 rounded-full"
                        style="width: 20%"
                      />
                      <div
                        class="absolute left-0 top-0 h-full bg-green-600 rounded-full"
                        style="width: 34.6%"
                      />
                    </div>
                  </div>

                  <div class="space-y-1">
                    <div class="flex justify-between items-center">
                      <span class="font-medium text-gray-700 text-sm"
                        >贵金属类</span
                      >
                      <div class="flex items-center gap-3">
                        <span class="text-xs text-gray-500"
                          >当前:
                          <span class="font-medium text-yellow-500"
                            >9.0%</span
                          ></span
                        >
                        <span class="text-xs font-medium">建议: 10%</span>
                      </div>
                    </div>
                    <div
                      class="relative h-2.5 bg-gray-200 rounded-full overflow-hidden"
                    >
                      <div
                        class="absolute left-0 top-0 h-full bg-yellow-100 rounded-full"
                        style="width: 10%"
                      />
                      <div
                        class="absolute left-0 top-0 h-full bg-yellow-500 rounded-full"
                        style="width: 9%"
                      />
                    </div>
                  </div>
                </div>

                <div class="mt-4 flex items-start gap-2 text-gray-600 text-sm">
                  <IconifyIconOffline
                    icon="ep:info-filled"
                    class="text-orange-500 mt-0.5 flex-shrink-0"
                  />
                  <p>
                    您当前<span class="font-medium text-red-500"
                      >股票类资产占比略高</span
                    >，<span class="font-medium text-amber-500"
                      >基金类资产配置不足</span
                    >，建议适当增加基金和贵金属配置以分散风险。
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="bg-white rounded-xl shadow-md p-6">
          <h3 class="text-lg font-bold mb-4 flex items-center">
            <IconifyIconOffline
              icon="ep:lightbulb"
              class="text-amber-500 mr-2"
            />
            优化建议
          </h3>
          <div class="space-y-4">
            <div
              class="p-4 border-l-4 border-orange-500 bg-orange-50 rounded-r-lg"
            >
              <h5 class="font-medium mb-1 text-sm">1. 增加债券型基金配置</h5>
              <p class="text-xs text-gray-600">
                建议配置15%左右的债券型基金，以平衡整体组合风险。
              </p>
            </div>
            <div
              class="p-4 border-l-4 border-amber-500 bg-amber-50 rounded-r-lg"
            >
              <h5 class="font-medium mb-1 text-sm">2. 适当减仓腾讯控股</h5>
              <p class="text-xs text-gray-600">
                单只股票占比过高，建议分批减仓至总市值的5%以内。
              </p>
            </div>
          </div>
        </div>
      </div>

      <div class="space-y-6">
        <div class="bg-white rounded-xl shadow-md p-5">
          <h3 class="text-base font-bold mb-3">收益预测</h3>
          <div class="text-center mb-3">
            <p class="text-gray-500 text-xs">预计年末总资产</p>
            <p class="text-2xl font-bold text-orange-500 mt-1">¥2,580,000</p>
            <p
              class="text-green-600 text-xs mt-1 flex items-center justify-center"
            >
              <IconifyIconOffline
                icon="ep:arrow-up-bold"
                class="mr-0.5"
              />+10.0% 预期年化收益
            </p>
          </div>
          <div class="h-36">
            <canvas ref="predictionChartRef" />
          </div>
        </div>

        <div class="bg-white rounded-xl shadow-md p-5">
          <h3 class="text-base font-bold mb-3">风险预警</h3>
          <div class="space-y-2">
            <div class="flex items-center p-2.5 bg-red-50 rounded-lg">
              <div
                class="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center text-red-500 mr-2.5 flex-shrink-0"
              >
                <IconifyIconOffline icon="ep:bell" class="text-sm" />
              </div>
              <div>
                <p class="font-medium text-xs">市场波动加剧</p>
                <p class="text-[10px] text-gray-500">
                  港股市场近期波动较大，请注意风险控制
                </p>
              </div>
            </div>
            <div class="flex items-center p-2.5 bg-amber-50 rounded-lg">
              <div
                class="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center text-amber-500 mr-2.5 flex-shrink-0"
              >
                <IconifyIconOffline icon="ep:info-filled" class="text-sm" />
              </div>
              <div>
                <p class="font-medium text-xs">基金分红提醒</p>
                <p class="text-[10px] text-gray-500">
                  易方达消费精选即将分红，请注意查看
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from "vue";
import * as echarts from "echarts";
import { Icon as IconifyIconOffline } from "@iconify/vue";

const predictionChartRef = ref<HTMLCanvasElement | null>(null);
let predictionChart: echarts.ECharts | null = null;

const initPredictionChart = () => {
  if (!predictionChartRef.value) return;
  predictionChart = echarts.init(predictionChartRef.value);
  predictionChart.setOption({
    tooltip: { trigger: "axis" },
    grid: { left: "3%", right: "4%", bottom: "10%", containLabel: true },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: ["7月", "8月", "9月", "10月", "11月", "12月"],
      axisLabel: { fontSize: 10 }
    },
    yAxis: {
      type: "value",
      axisLabel: { fontSize: 10, formatter: "¥{value}" }
    },
    series: [
      {
        name: "预测总资产",
        type: "line",
        data: [234, 238, 242, 246, 252, 258],
        borderColor: "#006400",
        borderDash: [4, 4],
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(0, 100, 0, 0.15)" },
            { offset: 1, color: "rgba(0, 100, 0, 0.02)" }
          ])
        },
        smooth: true,
        lineStyle: { width: 2 },
        symbol: "circle",
        symbolSize: 4,
        itemStyle: { color: "#006400" }
      }
    ]
  });
};

const resizeChart = () => {
  predictionChart?.resize();
};

onMounted(() => {
  nextTick(() => {
    initPredictionChart();
    window.addEventListener("resize", resizeChart);
  });
});
</script>

<style scoped>
.intelligent-analysis {
  min-height: calc(100vh - 85px);
  background-color: #f5f5f5;
}
</style>
