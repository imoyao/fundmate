<template>
  <div
    class="investment-analysis p-6"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <div class="mb-6">
      <h2 class="text-2xl font-bold" :style="{ color: 'var(--text-primary)' }">
        投资分析
      </h2>
      <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary)' }">
        查看投资收益与风险指标
      </p>
    </div>

    <div
      class="rounded-xl p-5 mb-5"
      :style="{
        backgroundColor: 'var(--bg-card)',
        boxShadow: 'var(--shadow-raised)',
        border: '1px solid var(--border-light)'
      }"
    >
      <div class="flex flex-wrap gap-3">
        <div class="flex items-center gap-2">
          <!-- 演示数据，待接入真实接口 -->
          <input
            type="date"
            value="2023-01-01"
            class="px-3 py-2 border rounded-lg focus:outline-none focus:border-(--brand-700) text-sm text-(--text-primary) bg-(--bg-card) border-(--border-default)"
          />
          <span class="text-sm" :style="{ color: 'var(--text-secondary)' }"
            >至</span
          >
          <!-- 演示数据，待接入真实接口 -->
          <input
            type="date"
            value="2023-12-31"
            class="px-3 py-2 border rounded-lg focus:outline-none focus:border-(--brand-700) text-sm text-(--text-primary) bg-(--bg-card) border-(--border-default)"
          />
        </div>
        <!-- 演示数据，待接入真实接口 -->
        <select
          class="px-3 py-2 border rounded-lg focus:outline-none focus:border-(--brand-700) text-sm text-(--text-primary) bg-(--bg-card) border-(--border-default)"
        >
          <option value="all">所有账户</option>
          <option value="personal">个人账户</option>
          <option value="family">家庭账户</option>
        </select>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-5">
      <div
        class="rounded-xl p-5"
        :style="{
          backgroundColor: 'var(--bg-card)',
          boxShadow: 'var(--shadow-raised)',
          border: '1px solid var(--border-light)'
        }"
      >
        <h3
          class="text-sm font-bold mb-4"
          :style="{ color: 'var(--text-primary)' }"
        >
          月度盈亏
        </h3>
        <div class="h-56">
          <canvas ref="monthlyProfitChartRef" />
        </div>
      </div>
      <div
        class="rounded-xl p-5"
        :style="{
          backgroundColor: 'var(--bg-card)',
          boxShadow: 'var(--shadow-raised)',
          border: '1px solid var(--border-light)'
        }"
      >
        <h3
          class="text-sm font-bold mb-4"
          :style="{ color: 'var(--text-primary)' }"
        >
          资产配置
        </h3>
        <div class="h-56">
          <canvas ref="assetAllocationChartRef" />
        </div>
      </div>
    </div>

    <div
      class="rounded-xl p-5 mb-5"
      :style="{
        backgroundColor: 'var(--bg-card)',
        boxShadow: 'var(--shadow-raised)',
        border: '1px solid var(--border-light)'
      }"
    >
      <h3
        class="text-sm font-bold mb-4"
        :style="{ color: 'var(--text-primary)' }"
      >
        收益对比
      </h3>
      <div class="h-56">
        <canvas ref="returnComparisonChartRef" />
      </div>
    </div>

    <div
      class="rounded-xl p-5"
      :style="{
        backgroundColor: 'var(--bg-card)',
        boxShadow: 'var(--shadow-raised)',
        border: '1px solid var(--border-light)'
      }"
    >
      <h3
        class="text-sm font-bold mb-4"
        :style="{ color: 'var(--text-primary)' }"
      >
        投资组合表现
      </h3>
      <!-- 演示数据，待接入真实接口 -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div
          class="text-center p-4 rounded-xl"
          :style="{ backgroundColor: 'var(--brand-100)' }"
        >
          <p class="text-xs mb-1" :style="{ color: 'var(--text-tertiary)' }">
            总收益率
          </p>
          <RiseFallText :value="15.3" suffix="%" size="lg" />
        </div>
        <div
          class="text-center p-4 rounded-xl"
          :style="{ backgroundColor: 'var(--brand-100)' }"
        >
          <p class="text-xs mb-1" :style="{ color: 'var(--text-tertiary)' }">
            年化收益率
          </p>
          <RiseFallText :value="12.5" suffix="%" size="lg" />
        </div>
        <!-- 最大回撤是风险警示指标，不是行情涨跌：底色用警示色（--color-warning-20），
             数值用主文字色保证可读性（亮色 --color-warning 对比度不足 WCAG AA），不误用涨跌色 -->
        <div
          class="text-center p-4 rounded-xl"
          :style="{ backgroundColor: 'var(--color-warning-20)' }"
        >
          <p class="text-xs mb-1" :style="{ color: 'var(--text-tertiary)' }">
            最大回撤
          </p>
          <RiseFallText
            :value="-8.2"
            suffix="%"
            size="lg"
            customColor="var(--text-primary)"
          />
        </div>
        <div
          class="text-center p-4 rounded-xl"
          :style="{ backgroundColor: 'var(--bg-soft)' }"
        >
          <p class="text-xs mb-1" :style="{ color: 'var(--text-tertiary)' }">
            夏普比率
          </p>
          <p
            class="text-xl font-bold"
            :style="{ color: 'var(--text-primary)' }"
          >
            1.2
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from "vue";
import echarts from "@/plugins/echarts";
import RiseFallText from "@/components/RiseFallText/index.vue";
import { getCssVar } from "@/composables/echarts/theme";

defineOptions({
  name: "InvestmentAnalysis"
});

const monthlyProfitChartRef = ref<HTMLCanvasElement | null>(null);
const assetAllocationChartRef = ref<HTMLCanvasElement | null>(null);
const returnComparisonChartRef = ref<HTMLCanvasElement | null>(null);

let monthlyProfitChart: echarts.ECharts | null = null;
let assetAllocationChart: echarts.ECharts | null = null;
let returnComparisonChart: echarts.ECharts | null = null;

// 工具函数：动态读取设计令牌（design.md 红线：图表颜色禁止硬编码，
// 须 getComputedStyle 读取 CSS 变量，亮/暗色模式自动适配）
const getCSSColor = (varName: string): string => {
  return getCssVar(varName);
};

// 图表配色：涨跌用 --color-rise/--color-fall，其余用图表色板 --chart-*
const chartColors = {
  rise: getCSSColor("--color-rise"),
  fall: getCSSColor("--color-fall"),
  neutral: getCSSColor("--color-neutral"),
  chart01: getCSSColor("--chart-01"),
  chart03: getCSSColor("--chart-03"),
  chart05: getCSSColor("--chart-05"),
  chart07: getCSSColor("--chart-07")
};

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
        // 演示数据，待接入真实接口
        data: [1000, 2500, -500, 1800, 3000, -1200],
        // 涨红跌绿：正收益=涨（红），负收益=跌（绿）
        itemStyle: {
          color: (params: { value: number }) =>
            params.value >= 0 ? chartColors.rise : chartColors.fall
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
        // 演示数据，待接入真实接口；配色取图表色板（--chart-*）与中性色
        data: [
          {
            value: 600000,
            name: "股票",
            itemStyle: { color: chartColors.chart01 }
          },
          {
            value: 300000,
            name: "基金",
            itemStyle: { color: chartColors.chart03 }
          },
          {
            value: 200000,
            name: "理财",
            itemStyle: { color: chartColors.chart05 }
          },
          {
            value: 100000,
            name: "REITs",
            itemStyle: { color: chartColors.chart07 }
          },
          {
            value: 34567.89,
            name: "现金",
            itemStyle: { color: chartColors.neutral }
          }
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
        // 演示数据，待接入真实接口；主数据用品牌红（--chart-01）
        data: [5, 8, 12, 10, 15, 18],
        smooth: true,
        itemStyle: { color: chartColors.chart01 },
        lineStyle: { width: 2 },
        symbol: "circle",
        symbolSize: 4
      },
      {
        name: "沪深300",
        type: "line",
        // 演示数据，待接入真实接口；指数为中性对比数据，用灰蓝（--chart-07）
        data: [4, 7, 10, 8, 12, 15],
        smooth: true,
        itemStyle: { color: chartColors.chart07 },
        lineStyle: { width: 2 },
        symbol: "circle",
        symbolSize: 4
      },
      {
        name: "上证指数",
        type: "line",
        // 演示数据，待接入真实接口；指数为中性对比数据，用奶油棕（--chart-05）
        data: [3, 6, 9, 7, 11, 14],
        smooth: true,
        itemStyle: { color: chartColors.chart05 },
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
}
</style>
