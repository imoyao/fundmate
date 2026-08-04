<template>
  <div class="investment-analysis p-6">
    <div class="mb-6">
      <h2 class="text-2xl font-bold">投资分析</h2>
      <p class="text-gray-500 mt-1">全面分析您的投资表现</p>
    </div>

    <div class="bg-white rounded-xl shadow-md p-5 mb-5">
      <div class="flex flex-wrap gap-3">
        <div class="flex items-center gap-2">
          <input
            type="date"
            value="2023-01-01"
            class="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-orange-500 text-sm shadow-sm"
          />
          <span class="text-gray-500 text-sm">至</span>
          <input
            type="date"
            value="2023-12-31"
            class="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-orange-500 text-sm shadow-sm"
          />
        </div>
        <select
          class="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-orange-500 text-sm shadow-sm"
        >
          <option value="all">所有账户</option>
          <option value="personal">个人账户</option>
          <option value="family">家庭账户</option>
        </select>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-5">
      <div class="bg-white rounded-xl shadow-md p-5">
        <h3 class="text-sm font-bold mb-4">月度盈亏</h3>
        <div class="h-56">
          <canvas ref="monthlyProfitChartRef" />
        </div>
      </div>
      <div class="bg-white rounded-xl shadow-md p-5">
        <h3 class="text-sm font-bold mb-4">资产配置</h3>
        <div class="h-56">
          <canvas ref="assetAllocationChartRef" />
        </div>
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-md p-5 mb-5">
      <h3 class="text-sm font-bold mb-4">收益对比</h3>
      <div class="h-56">
        <canvas ref="returnComparisonChartRef" />
      </div>
    </div>

    <div class="bg-white rounded-xl shadow-md p-5">
      <h3 class="text-sm font-bold mb-4">投资组合表现</h3>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="text-center p-4 bg-green-50 rounded-xl">
          <p class="text-gray-500 text-xs mb-1">总收益率</p>
          <p class="text-xl font-bold text-green-600">+15.3%</p>
        </div>
        <div class="text-center p-4 bg-green-50 rounded-xl">
          <p class="text-gray-500 text-xs mb-1">年化收益率</p>
          <p class="text-xl font-bold text-green-600">+12.5%</p>
        </div>
        <div class="text-center p-4 bg-red-50 rounded-xl">
          <p class="text-gray-500 text-xs mb-1">最大回撤</p>
          <p class="text-xl font-bold text-red-600">-8.2%</p>
        </div>
        <div class="text-center p-4 bg-blue-50 rounded-xl">
          <p class="text-gray-500 text-xs mb-1">夏普比率</p>
          <p class="text-xl font-bold text-blue-600">1.2</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from "vue";
import echarts from "@/plugins/echarts";

const monthlyProfitChartRef = ref<HTMLCanvasElement | null>(null);
const assetAllocationChartRef = ref<HTMLCanvasElement | null>(null);
const returnComparisonChartRef = ref<HTMLCanvasElement | null>(null);

let monthlyProfitChart: echarts.ECharts | null = null;
let assetAllocationChart: echarts.ECharts | null = null;
let returnComparisonChart: echarts.ECharts | null = null;

const initMonthlyProfitChart = () => {
  if (!monthlyProfitChartRef.value) return;
  monthlyProfitChart = echarts.init(monthlyProfitChartRef.value);
  monthlyProfitChart.setOption({
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: "3%", right: "4%", bottom: "8%", containLabel: true },
    xAxis: {
      type: "category",
      data: ["1月", "2月", "3月", "4月", "5月", "6月"],
      axisLabel: { fontSize: 10 }
    },
    yAxis: {
      type: "value",
      axisLabel: { fontSize: 10, formatter: "¥{value}" }
    },
    series: [
      {
        name: "月度盈亏",
        type: "bar",
        barWidth: "50%",
        data: [1000, 2500, -500, 1800, 3000, -1200],
        itemStyle: {
          color: (params: any) => (params.value >= 0 ? "#22c55e" : "#ef4444")
        },
        label: { show: true, fontSize: 10, position: "top" }
      }
    ]
  });
};

const initAssetAllocationChart = () => {
  if (!assetAllocationChartRef.value) return;
  assetAllocationChart = echarts.init(assetAllocationChartRef.value);
  assetAllocationChart.setOption({
    tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
    legend: {
      position: "bottom",
      itemWidth: 12,
      itemHeight: 12,
      textStyle: { fontSize: 10 }
    },
    series: [
      {
        type: "pie",
        radius: ["35%", "60%"],
        center: ["50%", "45%"],
        data: [
          { value: 600000, name: "股票", itemStyle: { color: "#FF6B00" } },
          { value: 300000, name: "基金", itemStyle: { color: "#FF7D00" } },
          { value: 200000, name: "理财", itemStyle: { color: "#4CAF50" } },
          { value: 100000, name: "REITs", itemStyle: { color: "#2196F3" } },
          { value: 34567.89, name: "现金", itemStyle: { color: "#9C27B0" } }
        ]
      }
    ]
  });
};

const initReturnComparisonChart = () => {
  if (!returnComparisonChartRef.value) return;
  returnComparisonChart = echarts.init(returnComparisonChartRef.value);
  returnComparisonChart.setOption({
    tooltip: { trigger: "axis" },
    legend: {
      data: ["我的投资组合", "沪深300", "上证指数"],
      bottom: 0,
      textStyle: { fontSize: 10 }
    },
    grid: { left: "3%", right: "4%", bottom: "15%", containLabel: true },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: ["1月", "2月", "3月", "4月", "5月", "6月"],
      axisLabel: { fontSize: 10 }
    },
    yAxis: {
      type: "value",
      axisLabel: { fontSize: 10, formatter: "{value}%" }
    },
    series: [
      {
        name: "我的投资组合",
        type: "line",
        data: [5, 8, 12, 10, 15, 18],
        smooth: true,
        itemStyle: { color: "#FF6B00" },
        lineStyle: { width: 2 },
        symbol: "circle",
        symbolSize: 4
      },
      {
        name: "沪深300",
        type: "line",
        data: [4, 7, 10, 8, 12, 15],
        smooth: true,
        itemStyle: { color: "#4CAF50" },
        lineStyle: { width: 2 },
        symbol: "circle",
        symbolSize: 4
      },
      {
        name: "上证指数",
        type: "line",
        data: [3, 6, 9, 7, 11, 14],
        smooth: true,
        itemStyle: { color: "#2196F3" },
        lineStyle: { width: 2 },
        symbol: "circle",
        symbolSize: 4
      }
    ]
  });
};

const resizeCharts = () => {
  monthlyProfitChart?.resize();
  assetAllocationChart?.resize();
  returnComparisonChart?.resize();
};

onMounted(() => {
  nextTick(() => {
    initMonthlyProfitChart();
    initAssetAllocationChart();
    initReturnComparisonChart();
    window.addEventListener("resize", resizeCharts);
  });
});
</script>

<style scoped>
.investment-analysis {
  min-height: calc(100vh - 85px);
  background-color: #f5f5f5;
}
</style>
