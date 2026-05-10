<template>
  <div class="asset-overview p-6">
    <div
      class="mb-8 flex flex-col md:flex-row md:justify-between md:items-center"
    >
      <div>
        <h2 class="text-[clamp(1.5rem,3vw,2.5rem)] font-bold">资产总览</h2>
        <p class="text-gray-500 mt-2">全面管理您的投资组合和财务状况</p>
      </div>
      <div class="mt-4 md:mt-0 flex space-x-3">
        <button
          class="px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm hover:bg-gray-50 flex items-center transition-colors shadow-sm"
        >
          <IconifyIconOffline icon="ep:download" class="mr-2 text-gray-500" />
          导出报表
        </button>
        <button
          class="px-4 py-2 bg-orange-500 text-white rounded-lg text-sm hover:bg-orange-600 flex items-center transition-colors shadow-sm"
        >
          <IconifyIconOffline icon="ep:refresh" class="mr-2" />
          刷新数据
        </button>
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-md p-6 mb-6">
      <div
        class="flex flex-col md:flex-row md:items-center justify-between mb-6"
      >
        <div class="mb-6 md:mb-0">
          <p class="text-gray-500">总资产 (本月)</p>
          <h3 class="text-4xl font-bold mt-1 text-orange-500">¥2,345,678</h3>
          <div class="flex items-center mt-2 space-x-4">
            <p class="text-green-600 text-lg flex items-center">
              <IconifyIconOffline icon="ep:arrow-up-bold" class="mr-1" />
              <span>12.3%</span>
              <span class="text-gray-500 ml-2">较上月</span>
            </p>
            <p class="text-green-600 text-lg flex items-center">
              <IconifyIconOffline icon="ep:arrow-up-bold" class="mr-1" />
              <span>8.7%</span>
              <span class="text-gray-500 ml-2">较去年同期</span>
            </p>
          </div>
          <div class="mt-3 flex items-center">
            <span
              class="px-2 py-1 bg-amber-100 text-amber-600 rounded-full text-xs font-medium"
              >中等风险</span
            >
            <span class="text-xs text-gray-500 ml-2">风险评分：65/100</span>
          </div>
        </div>

        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div
            class="bg-gradient-to-br from-orange-50 to-orange-100 rounded-lg p-4 border border-orange-200 hover:shadow-lg transition-shadow cursor-pointer"
          >
            <div class="flex justify-between items-start mb-2">
              <div
                class="w-10 h-10 bg-orange-200 rounded-lg flex items-center justify-center"
              >
                <IconifyIconOffline
                  icon="ep:data-line"
                  class="text-orange-500 text-lg"
                />
              </div>
            </div>
            <p class="text-gray-500 text-xs font-medium">股票资产</p>
            <h4 class="text-lg font-bold text-orange-600">¥856,240</h4>
            <div class="mt-2">
              <div class="flex justify-between text-[10px] text-gray-500 mb-1">
                <span>占比 36.5%</span>
                <span class="px-1.5 py-0.5 bg-red-100 text-red-600 rounded"
                  >高风险</span
                >
              </div>
              <div class="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div
                  class="bg-orange-500 h-full rounded-full"
                  style="width: 36.5%"
                />
              </div>
            </div>
            <p class="text-green-600 text-xs mt-2 flex items-center">
              <IconifyIconOffline
                icon="ep:arrow-up-bold"
                class="mr-0.5 text-[10px]"
              />
              <span>5.3%</span>
              <span class="text-gray-500 ml-1">较上月</span>
            </p>
          </div>

          <div
            class="bg-gradient-to-br from-amber-50 to-amber-100 rounded-lg p-4 border border-amber-200 hover:shadow-lg transition-shadow cursor-pointer"
          >
            <div class="flex justify-between items-start mb-2">
              <div
                class="w-10 h-10 bg-amber-200 rounded-lg flex items-center justify-center"
              >
                <IconifyIconOffline
                  icon="ep:box"
                  class="text-amber-500 text-lg"
                />
              </div>
            </div>
            <p class="text-gray-500 text-xs font-medium">基金资产</p>
            <h4 class="text-lg font-bold text-amber-600">¥678,950</h4>
            <div class="mt-2">
              <div class="flex justify-between text-[10px] text-gray-500 mb-1">
                <span>占比 28.9%</span>
                <span class="px-1.5 py-0.5 bg-amber-100 text-amber-600 rounded"
                  >中风险</span
                >
              </div>
              <div class="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div
                  class="bg-amber-500 h-full rounded-full"
                  style="width: 28.9%"
                />
              </div>
            </div>
            <p class="text-red-600 text-xs mt-2 flex items-center">
              <IconifyIconOffline
                icon="ep:arrow-down-bold"
                class="mr-0.5 text-[10px]"
              />
              <span>1.2%</span>
              <span class="text-gray-500 ml-1">较上月</span>
            </p>
          </div>

          <div
            class="bg-gradient-to-br from-green-50 to-green-100 rounded-lg p-4 border border-green-200 hover:shadow-lg transition-shadow cursor-pointer"
          >
            <div class="flex justify-between items-start mb-2">
              <div
                class="w-10 h-10 bg-green-200 rounded-lg flex items-center justify-center"
              >
                <IconifyIconOffline
                  icon="ep:house"
                  class="text-green-600 text-lg"
                />
              </div>
            </div>
            <p class="text-gray-500 text-xs font-medium">房产资产</p>
            <h4 class="text-lg font-bold text-green-600">¥810,488</h4>
            <div class="mt-2">
              <div class="flex justify-between text-[10px] text-gray-500 mb-1">
                <span>占比 34.6%</span>
                <span class="px-1.5 py-0.5 bg-green-100 text-green-600 rounded"
                  >低风险</span
                >
              </div>
              <div class="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div
                  class="bg-green-600 h-full rounded-full"
                  style="width: 34.6%"
                />
              </div>
            </div>
            <p class="text-green-600 text-xs mt-2 flex items-center">
              <IconifyIconOffline
                icon="ep:arrow-up-bold"
                class="mr-0.5 text-[10px]"
              />
              <span>3.7%</span>
              <span class="text-gray-500 ml-1">较上月</span>
            </p>
          </div>

          <div
            class="bg-gradient-to-br from-yellow-50 to-yellow-100 rounded-lg p-4 border border-yellow-200 hover:shadow-lg transition-shadow cursor-pointer"
          >
            <div class="flex justify-between items-start mb-2">
              <div
                class="w-10 h-10 bg-yellow-200 rounded-lg flex items-center justify-center"
              >
                <IconifyIconOffline
                  icon="ep:star"
                  class="text-yellow-600 text-lg"
                />
              </div>
            </div>
            <p class="text-gray-500 text-xs font-medium">贵金属</p>
            <h4 class="text-lg font-bold text-yellow-600">¥212,400</h4>
            <div class="mt-2">
              <div class="flex justify-between text-[10px] text-gray-500 mb-1">
                <span>占比 9.0%</span>
                <span class="px-1.5 py-0.5 bg-amber-100 text-amber-600 rounded"
                  >中风险</span
                >
              </div>
              <div class="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div
                  class="bg-yellow-500 h-full rounded-full"
                  style="width: 9%"
                />
              </div>
            </div>
            <p class="text-green-600 text-xs mt-2 flex items-center">
              <IconifyIconOffline
                icon="ep:arrow-up-bold"
                class="mr-0.5 text-[10px]"
              />
              <span>2.1%</span>
              <span class="text-gray-500 ml-1">较上月</span>
            </p>
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
      <div class="bg-white rounded-xl shadow-md p-5">
        <h4 class="font-semibold text-gray-800 mb-4">资产分布</h4>
        <div class="h-52">
          <canvas ref="distributionChartRef" />
        </div>
      </div>

      <div class="bg-white rounded-xl shadow-md p-5">
        <div class="flex justify-between items-center mb-4">
          <h4 class="font-semibold text-gray-800">收益趋势</h4>
          <div class="flex space-x-1">
            <button
              class="px-2 py-0.5 text-[10px] bg-orange-500 text-white rounded"
              @click="setProfitPeriod('monthly')"
            >
              月度
            </button>
            <button
              class="px-2 py-0.5 text-[10px] bg-gray-200 text-gray-600 rounded hover:bg-gray-300"
              @click="setProfitPeriod('quarterly')"
            >
              季度
            </button>
            <button
              class="px-2 py-0.5 text-[10px] bg-gray-200 text-gray-600 rounded hover:bg-gray-300"
              @click="setProfitPeriod('yearly')"
            >
              年度
            </button>
          </div>
        </div>
        <div class="h-52">
          <canvas ref="profitTrendChartRef" />
        </div>
      </div>

      <div class="bg-white rounded-xl shadow-md p-5">
        <h4 class="font-semibold text-gray-800 mb-4">风险热力图</h4>
        <div class="h-52">
          <canvas ref="riskHeatmapChartRef" />
        </div>
        <div
          class="mt-3 flex justify-center space-x-4 text-[10px] text-gray-500"
        >
          <span class="flex items-center"
            ><span class="w-2 h-2 bg-green-500 rounded mr-1" />低风险</span
          >
          <span class="flex items-center"
            ><span class="w-2 h-2 bg-amber-500 rounded mr-1" />中风险</span
          >
          <span class="flex items-center"
            ><span class="w-2 h-2 bg-red-500 rounded mr-1" />高风险</span
          >
        </div>
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-md p-6">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold flex items-center">
          <IconifyIconOffline
            icon="ep:data-analysis"
            class="text-orange-500 mr-2"
          />
          近期持仓表现 · 实时盈亏
        </h3>
        <button
          class="text-orange-500 text-sm flex items-center hover:underline"
        >
          查看全部持仓 <IconifyIconOffline icon="ep:right" class="ml-1" />
        </button>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="bg-gray-50 text-gray-500">
            <tr>
              <th class="px-4 py-3 text-left font-medium">资产名称</th>
              <th class="px-4 py-3 text-left font-medium">持仓市值</th>
              <th class="px-4 py-3 text-left font-medium">盈亏(元)</th>
              <th class="px-4 py-3 text-left font-medium">盈亏比例</th>
              <th class="px-4 py-3 text-left font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr class="border-t hover:bg-gray-50">
              <td class="px-4 py-3 font-medium">腾讯控股 (00700)</td>
              <td class="px-4 py-3">¥172,800</td>
              <td class="px-4 py-3 text-green-600">+¥12,800</td>
              <td class="px-4 py-3 text-green-600">+8.00%</td>
              <td class="px-4 py-3">
                <button
                  class="px-3 py-1.5 bg-orange-500 text-white text-xs rounded-lg hover:bg-orange-600 transition-colors"
                >
                  交易
                </button>
              </td>
            </tr>
            <tr class="border-t bg-gray-50/50 hover:bg-gray-100">
              <td class="px-4 py-3 font-medium">易方达消费精选</td>
              <td class="px-4 py-3">¥62,250</td>
              <td class="px-4 py-3 text-red-600">-¥1,750</td>
              <td class="px-4 py-3 text-red-600">-2.73%</td>
              <td class="px-4 py-3">
                <button
                  class="px-3 py-1.5 bg-orange-500 text-white text-xs rounded-lg hover:bg-orange-600 transition-colors"
                >
                  交易
                </button>
              </td>
            </tr>
            <tr class="border-t hover:bg-gray-50">
              <td class="px-4 py-3 font-medium">贵州茅台 (600519)</td>
              <td class="px-4 py-3">¥215,000</td>
              <td class="px-4 py-3 text-green-600">+¥15,200</td>
              <td class="px-4 py-3 text-green-600">+7.61%</td>
              <td class="px-4 py-3">
                <button
                  class="px-3 py-1.5 bg-orange-500 text-white text-xs rounded-lg hover:bg-orange-600 transition-colors"
                >
                  交易
                </button>
              </td>
            </tr>
            <tr class="border-t bg-gray-50/50 hover:bg-gray-100">
              <td class="px-4 py-3 font-medium">纳斯达克100ETF</td>
              <td class="px-4 py-3">¥86,500</td>
              <td class="px-4 py-3 text-green-600">+¥3,200</td>
              <td class="px-4 py-3 text-green-600">+3.84%</td>
              <td class="px-4 py-3">
                <button
                  class="px-3 py-1.5 bg-orange-500 text-white text-white text-xs rounded-lg hover:bg-orange-600 transition-colors"
                >
                  交易
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from "vue";
import * as echarts from "echarts";
import { Icon as IconifyIconOffline } from "@iconify/vue";

const distributionChartRef = ref<HTMLCanvasElement | null>(null);
const profitTrendChartRef = ref<HTMLCanvasElement | null>(null);
const riskHeatmapChartRef = ref<HTMLCanvasElement | null>(null);

let distributionChart: echarts.ECharts | null = null;
let profitTrendChart: echarts.ECharts | null = null;
let riskHeatmapChart: echarts.ECharts | null = null;

const initDistributionChart = () => {
  if (!distributionChartRef.value) return;
  distributionChart = echarts.init(distributionChartRef.value);
  distributionChart.setOption({
    tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
    legend: {
      position: "bottom",
      itemWidth: 12,
      itemHeight: 12,
      textStyle: { fontSize: 11 }
    },
    series: [
      {
        type: "pie",
        radius: ["40%", "65%"],
        center: ["50%", "45%"],
        data: [
          { value: 36.5, name: "股票", itemStyle: { color: "#FF6B00" } },
          { value: 28.9, name: "基金", itemStyle: { color: "#FF7D00" } },
          { value: 34.6, name: "房产", itemStyle: { color: "#006400" } },
          { value: 9.0, name: "贵金属", itemStyle: { color: "#FFD700" } }
        ]
      }
    ]
  });
};

const initProfitTrendChart = () => {
  if (!profitTrendChartRef.value) return;
  profitTrendChart = echarts.init(profitTrendChartRef.value);
  profitTrendChart.setOption({
    tooltip: { trigger: "axis" },
    grid: { right: "4%", bottom: "8%", containLabel: true, left: "4%" },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: ["1月", "2月", "3月", "4月", "5月", "6月", "7月"],
      axisLabel: { fontSize: 10 }
    },
    yAxis: {
      type: "value",
      axisLabel: { fontSize: 10, formatter: "¥{value}" }
    },
    series: [
      {
        name: "累计收益",
        type: "line",
        smooth: true,
        data: [120, 190, 170, 220, 280, 250, 310],
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(255, 107, 0, 0.3)" },
            { offset: 1, color: "rgba(255, 107, 0, 0.05)" }
          ])
        },
        itemStyle: { color: "#FF6B00" },
        lineStyle: { width: 2 },
        symbol: "circle",
        symbolSize: 4
      }
    ]
  });
};

const initRiskHeatmapChart = () => {
  if (!riskHeatmapChartRef.value) return;
  riskHeatmapChart = echarts.init(riskHeatmapChartRef.value);
  riskHeatmapChart.setOption({
    tooltip: { trigger: "axis" },
    grid: { right: "4%", bottom: "8%", containLabel: true, left: "4%" },
    xAxis: {
      type: "category",
      data: ["股票", "基金", "房产", "贵金属"],
      axisLabel: { fontSize: 10 }
    },
    yAxis: { type: "value", max: 100, axisLabel: { fontSize: 10 } },
    series: [
      {
        label: { show: true, fontSize: 10, formatter: "{c}" },
        data: [85, 60, 30, 55],
        type: "bar",
        itemStyle: {
          color: (params: any) => {
            const colors = ["#EF4444", "#F59E0B", "#22C55E", "#F59E0B"];
            return colors[params.dataIndex];
          },
          borderRadius: 4
        },
        barWidth: "50%"
      }
    ]
  });
};

const setProfitPeriod = (period: string) => {
  console.log("切换收益周期:", period);
};

const resizeCharts = () => {
  distributionChart?.resize();
  profitTrendChart?.resize();
  riskHeatmapChart?.resize();
};

onMounted(() => {
  nextTick(() => {
    initDistributionChart();
    initProfitTrendChart();
    initRiskHeatmapChart();
    window.addEventListener("resize", resizeCharts);
  });
});
</script>

<style scoped>
.asset-overview {
  min-height: calc(100vh - 85px);
  background-color: #f5f5f5;
}
</style>
