<template>
  <div
    class="welcome-container p-4 md:p-8 bg-[#f5f7fa] min-h-full font-sans text-[#333]"
  >
    <!-- 顶部欢迎语 -->
    <div class="flex justify-between items-center mb-6">
      <div class="flex items-center gap-2">
        <span class="text-sm font-medium text-gray-400"
          >别人恐惧我贪婪，别人贪婪我更贪婪</span
        >
      </div>
    </div>

    <!-- 第一部分：核心资产看板 + 收益趋势 -->
    <div class="grid grid-cols-1 xl:grid-cols-12 gap-6 mb-8">
      <!-- 左侧：家庭资产看板 (2/3 宽度) -->
      <div
        class="xl:col-span-8 bg-white rounded-2xl p-8 shadow-sm border border-gray-100 relative group"
      >
        <router-link
          to="/account/overview"
          class="absolute top-6 right-8 p-2 rounded-full bg-gray-50 text-gray-400 hover:bg-[#a6a6d2] hover:text-white transition-all shadow-sm z-20"
          title="查看资产详情"
        >
          <IconifyIconOffline icon="ep:full-screen" class="text-lg" />
        </router-link>

        <div class="flex justify-between items-start mb-8">
          <div>
            <h3 class="text-gray-800 font-bold text-lg mb-1">家庭资产看板</h3>
            <p class="text-gray-300 text-xs">{{ lastUpdate }} 更新</p>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          <!-- 左侧：资产概览数据（从 API 动态获取） -->
          <div class="flex flex-col gap-6">
            <div>
              <p class="text-gray-400 text-sm mb-2">家庭总资产</p>
              <div class="flex items-baseline gap-1">
                <h2
                  class="text-4xl md:text-5xl font-bold text-[#ff4d00] tracking-tight"
                >
                  {{ summary?.total_assets_cny?.toLocaleString() ?? "--" }}
                </h2>
                <span class="text-gray-400 text-sm">元</span>
              </div>
            </div>

            <!-- 总盈亏 -->
            <div class="flex gap-6">
              <div class="flex flex-col">
                <span class="text-gray-400 text-[10px] mb-1"
                  >总盈亏 (人民币)</span
                >
                <div
                  :class="[
                    'flex items-center font-bold text-sm',
                    (summary?.total_pnl_cny ?? 0) >= 0
                      ? 'text-red-500'
                      : 'text-green-500'
                  ]"
                >
                  <IconifyIconOffline
                    :icon="
                      (summary?.total_pnl_cny ?? 0) >= 0
                        ? 'ep:caret-top'
                        : 'ep:caret-bottom'
                    "
                    class="mr-1"
                  />
                  {{
                    summary?.total_pnl_cny != null
                      ? `${summary.total_pnl_cny >= 0 ? "+" : ""}${summary.total_pnl_cny.toLocaleString()}`
                      : "--"
                  }}
                </div>
              </div>
            </div>

            <!-- 资产增加/负债减少文字显示 -->
            <div class="grid grid-cols-2 gap-4 pt-6 border-t border-gray-50">
              <div class="flex flex-col">
                <span class="text-gray-400 text-[10px] mb-1">本月资产增加</span>
                <span class="text-base font-bold text-red-400"
                  >+28,973.83
                  <span class="text-[10px] font-normal">元</span></span
                >
              </div>
              <div class="flex flex-col">
                <span class="text-gray-400 text-[10px] mb-1">本月负债减少</span>
                <span class="text-base font-bold text-green-400"
                  >-20,406.12
                  <span class="text-[10px] font-normal">元</span></span
                >
              </div>
            </div>
          </div>

          <!-- 右侧：资产构成图表（暂保留静态模拟） -->
          <div
            class="flex flex-col items-center justify-center border-l border-gray-50 pl-8 h-full"
          >
            <div class="w-full flex justify-between items-center mb-4">
              <span class="text-gray-500 font-bold text-sm">资产构成分布</span>
              <div class="flex items-center gap-2">
                <span
                  class="px-2 py-0.5 bg-orange-50 text-orange-400 text-[10px] rounded font-bold"
                  >中等风险</span
                >
              </div>
            </div>
            <div ref="distributionChartRef" class="h-[240px] w-full" />
          </div>
        </div>
      </div>

      <!-- 右侧：收益趋势 (保留静态) -->
      <div
        class="xl:col-span-4 bg-white rounded-2xl p-6 shadow-sm border border-gray-100"
      >
        <div class="flex justify-between items-center mb-6">
          <h3 class="text-gray-800 font-bold">收益趋势</h3>
          <div class="flex bg-gray-100 p-1 rounded-lg text-[10px]">
            <button
              class="px-3 py-1 bg-white text-[#ff4d00] rounded shadow-sm font-bold"
            >
              月度
            </button>
            <button class="px-3 py-1 text-gray-400">季度</button>
          </div>
        </div>
        <div ref="trendChartRef" class="h-[220px] w-full" />
        <div class="mt-4 pt-4 border-t border-gray-50">
          <p class="text-[10px] text-gray-400 mb-2">风险评分建议</p>
          <div class="flex items-center justify-between">
            <span class="text-sm font-bold text-gray-700">65/100</span>
            <span class="text-[10px] text-orange-400">建议增加稳健型配置</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 第二部分：高风险资产卡片与风险热力图 -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-8">
      <!-- 自选资产卡片区域（替代原硬编码卡片） -->
       <div class="lg:col-span-8">
        <WatchlistWidget
            :key="watchlistWidgetKey"
            @select="onWatchlistSelect"
            @add="showAddWatchlistModal = true"
        />
    </div>


      <!-- 风险热力图 -->
      <div
        class="lg:col-span-4 bg-white rounded-2xl p-6 shadow-sm border border-gray-100"
      >
        <h3 class="text-gray-800 font-bold mb-4">风险热力图</h3>
        <div ref="riskHeatmapRef" class="h-[180px] w-full" />
        <div class="flex justify-center gap-4 mt-2 text-[8px] text-gray-400">
          <div class="flex items-center gap-1">
            <span class="w-2 h-2 bg-[#52c41a] rounded-sm" />低风险
          </div>
          <div class="flex items-center gap-1">
            <span class="w-2 h-2 bg-[#fa8c16] rounded-sm" />中风险
          </div>
          <div class="flex items-center gap-1">
            <span class="w-2 h-2 bg-[#ff4d4f] rounded-sm" />高风险
          </div>
        </div>
      </div>
    </div>

    <!-- 第三部分：有知有行特色指标与心理账户 -->
    <div class="flex flex-col lg:flex-row gap-8">
      <!-- 财务晴雨表群 -->
      <div class="flex-1">
        <h3 class="text-gray-800 font-bold mb-4 flex items-center gap-2">
          财务晴雨表
          <IconifyIconOffline
            icon="ep:info-filled"
            class="text-gray-300 text-sm cursor-help"
          />
        </h3>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div
            class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100"
          >
            <p class="text-gray-400 text-[10px] mb-2">资产负债率</p>
            <p class="text-xl font-bold">
              49.03<span class="text-[10px] font-normal ml-0.5">%</span>
            </p>
            <p class="text-[8px] text-orange-300 mt-2 font-medium">偿债能力</p>
          </div>
          <div
            class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100"
          >
            <p class="text-gray-400 text-[10px] mb-2">预估储蓄率</p>
            <p class="text-xl font-bold">
              46.06<span class="text-[10px] font-normal ml-0.5">%</span>
            </p>
            <p class="text-[8px] text-orange-300 mt-2 font-medium">储蓄能力</p>
          </div>
          <div
            class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100"
          >
            <p class="text-gray-400 text-[10px] mb-2">财务自由度</p>
            <p class="text-xl font-bold">
              22.83<span class="text-[10px] font-normal ml-0.5">%</span>
            </p>
            <p class="text-[8px] text-orange-300 mt-2 font-medium">自由指标</p>
          </div>
          <div
            class="bg-white rounded-2xl p-5 shadow-sm border border-gray-100"
          >
            <p class="text-gray-400 text-[10px] mb-2">躺平度</p>
            <p class="text-xl font-bold">
              12.31<span class="text-[10px] font-normal ml-0.5">%</span>
            </p>
            <p class="text-[8px] text-gray-300 mt-2 font-medium">2026年</p>
          </div>
        </div>

        <!-- 家庭资产变动微图 -->
        <div class="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
          <div class="flex justify-between items-center mb-4">
            <span class="text-gray-700 font-bold text-sm">资产变动趋势</span>
            <div ref="miniAssetChartRef" class="w-48 h-12" />
          </div>
        </div>
      </div>

      <!-- 右侧：心理账户 -->
      <div class="w-full lg:w-80 shrink-0">
        <div
          class="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 h-full flex flex-col"
        >
          <div class="flex justify-between items-center mb-6">
            <h3 class="font-bold text-gray-700">心理账户</h3>
            <IconifyIconOffline
              icon="ep:plus"
              class="text-gray-300 cursor-pointer hover:text-[#a6a6d2]"
            />
          </div>

          <div class="flex flex-col gap-4">
            <div
              class="p-3 rounded-xl border border-gray-50 hover:bg-gray-50 transition-colors cursor-pointer group"
            >
              <div class="flex justify-between items-center mb-1">
                <span class="text-xs font-bold text-gray-700">不动如山</span>
                <span class="text-[10px] font-bold text-[#a6a6d2]">72%</span>
              </div>
              <div
                class="w-full bg-gray-100 h-1.5 rounded-full overflow-hidden"
              >
                <div
                  class="bg-[#a6a6d2] h-full rounded-full"
                  style="width: 72%"
                />
              </div>
              <p class="text-[10px] text-gray-400 mt-2 font-bold">¥2,150,000</p>
            </div>

            <div
              class="p-3 rounded-xl border border-gray-50 hover:bg-gray-50 transition-colors cursor-pointer group"
            >
              <div class="flex justify-between items-center mb-1">
                <span class="text-xs font-bold text-gray-700">自由计划</span>
                <span class="text-[10px] font-bold text-[#ffbb96]">19%</span>
              </div>
              <div
                class="w-full bg-gray-100 h-1.5 rounded-full overflow-hidden"
              >
                <div
                  class="bg-[#ffbb96] h-full rounded-full"
                  style="width: 19%"
                />
              </div>
              <p class="text-[10px] text-gray-400 mt-2 font-bold">¥561,043</p>
            </div>

            <div
              class="p-3 rounded-xl border border-gray-50 hover:bg-gray-50 transition-colors cursor-pointer group"
            >
              <div class="flex justify-between items-center mb-1">
                <span class="text-xs font-bold text-gray-700">生活备用金</span>
                <span class="text-[10px] font-bold text-[#b7eb8f]">65%</span>
              </div>
              <div
                class="w-full bg-gray-100 h-1.5 rounded-full overflow-hidden"
              >
                <div
                  class="bg-[#b7eb8f] h-full rounded-full"
                  style="width: 65%"
                />
              </div>
              <p class="text-[10px] text-gray-400 mt-2 font-bold">¥196,136</p>
            </div>
          </div>
        </div>
      </div>
    </div>
   <!-- 添加自选弹窗（独立于记账弹窗） -->
    <AddToWatchlistModal v-model="showAddWatchlistModal" @submitted="onWatchlistChanged" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, onUnmounted } from "vue";
import * as echarts from "echarts";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import { getSummary } from "@/api/summary";
import type { SummaryData } from "@/api/types";
import WatchlistWidget from "@/components/WatchlistWidget.vue";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";


defineOptions({
  name: "Welcome"
});

// 仪表盘核心数据
const summary = ref<SummaryData | null>(null);
const lastUpdate = ref<string>("");

const distributionChartRef = ref<HTMLDivElement | null>(null);
const trendChartRef = ref<HTMLDivElement | null>(null);
const riskHeatmapRef = ref<HTMLDivElement | null>(null);
const miniAssetChartRef = ref<HTMLDivElement | null>(null);
const showAddWatchlistModal = ref(false);

let charts: echarts.ECharts[] = [];

// 获取真实汇总数据
const fetchSummary = async () => {
  try {
    const res = await getSummary();
    summary.value = res.data;
    const now = new Date();
    lastUpdate.value = `${now.getFullYear()}.${now.getMonth() + 1}.${now.getDate()}`;
  } catch (e) {
    console.error("Failed to fetch summary:", e);
  }
};

const onWatchlistSelect = (item: any) => {
  // 这里可以设置 TransactionModal 的默认值，或直接跳转。简单起见，打开弹窗并传递 symbol
  // 需要改造 TransactionModal 支持预填，或直接打开弹窗后由用户操作。
  // 目前弹窗组件没有接收预设 symbol 的 props，我们可以先打开弹窗，让用户在弹窗里搜索。
  // 或者我们增加一个 props 传递预填代码。简单处理：打开弹窗并自动聚焦搜索框，需要扩展 TransactionModal。
  // 但轻量级方案：唤起弹窗，用户手动记账，因为弹窗支持搜索，用户可快速找到该资产。
  // 为了体验，后续可以优化 TransactionModal 接受 initialSymbol prop。
  // 如果需要自动填充，可以 emit 一个事件携带 symbol，由父组件传递给弹窗。
  // 暂时不做，后续优化。
};


const onWatchlistChanged = () => {
  // 通知 WatchlistWidget 刷新数据
  // 简单做法：通过 key 触发重新挂载，或直接调用其内部的 fetchData
  // 这里我们使用 watchlistWidgetKey 强制刷新
  watchlistWidgetKey.value++;
};
const watchlistWidgetKey = ref(0);


// 原有的图表初始化函数（完全保留）
const initCharts = () => {
  // 1. 资产分布饼图（可以先使用 market_distribution 数据）
  if (distributionChartRef.value) {
    const chart = echarts.init(distributionChartRef.value);
    // 为了初步效果，可以继续使用模拟分布，后续接入 summary.market_distribution
    chart.setOption({
      tooltip: { trigger: "item" },
      legend: {
        bottom: "0%",
        left: "center",
        icon: "circle",
        itemWidth: 8,
        textStyle: { fontSize: 10 }
      },
      series: [
        {
          type: "pie",
          radius: ["50%", "80%"],
          avoidLabelOverlap: false,
          itemStyle: { borderRadius: 6, borderColor: "#fff", borderWidth: 2 },
          label: { show: false },
          data: summary.value?.market_distribution
            ? Object.entries(summary.value.market_distribution).map(
                ([name, value]) => ({
                  name,
                  value,
                  itemStyle: {
                    color:
                      name === "US"
                        ? "#ff4d00"
                        : name === "CN_A"
                          ? "#fa8c16"
                          : "#52c41a"
                  }
                })
              )
            : [
                {
                  value: 856240,
                  name: "股票",
                  itemStyle: { color: "#ff4d00" }
                },
                {
                  value: 678950,
                  name: "基金",
                  itemStyle: { color: "#fa8c16" }
                },
                {
                  value: 810488,
                  name: "房产",
                  itemStyle: { color: "#006d1f" }
                },
                {
                  value: 212400,
                  name: "贵金属",
                  itemStyle: { color: "#ffe7ba" }
                }
              ]
        }
      ]
    });
    charts.push(chart);
  }

  // 2. 收益趋势折线图
  if (trendChartRef.value) {
    const chart = echarts.init(trendChartRef.value);
    chart.setOption({
      grid: {
        left: "3%",
        right: "4%",
        top: "10%",
        bottom: "3%",
        containLabel: true
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: ["1月", "2月", "3月", "4月", "5月", "6月", "7月"],
        axisLine: { lineStyle: { color: "#f0f0f0" } },
        axisLabel: { color: "#999", fontSize: 10 }
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#f5f5f5" } },
        axisLabel: { color: "#999", fontSize: 10 }
      },
      series: [
        {
          data: [120, 190, 170, 220, 280, 250, 310],
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 6,
          itemStyle: { color: "#ff4d00" },
          lineStyle: { width: 3, color: "#ff4d00" },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(255, 77, 0, 0.2)" },
              { offset: 1, color: "rgba(255, 77, 0, 0)" }
            ])
          }
        }
      ]
    });
    charts.push(chart);
  }

  // 3. 风险热力图 (柱状图)
  if (riskHeatmapRef.value) {
    const chart = echarts.init(riskHeatmapRef.value);
    chart.setOption({
      grid: {
        left: "3%",
        right: "4%",
        top: "10%",
        bottom: "3%",
        containLabel: true
      },
      xAxis: {
        type: "category",
        data: ["股票", "基金", "房产", "贵金属"],
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: "#999", fontSize: 10 }
      },
      yAxis: {
        type: "value",
        max: 100,
        splitLine: { lineStyle: { color: "#f5f5f5" } },
        axisLabel: { color: "#999", fontSize: 10 }
      },
      series: [
        {
          data: [
            { value: 85, itemStyle: { color: "#ff4d4f" } },
            { value: 60, itemStyle: { color: "#fa8c16" } },
            { value: 30, itemStyle: { color: "#52c41a" } },
            { value: 55, itemStyle: { color: "#fa8c16" } }
          ],
          type: "bar",
          barWidth: 20,
          itemStyle: { borderRadius: [4, 4, 0, 0] }
        }
      ]
    });
    charts.push(chart);
  }

  // 4. 有知有行版小柱状图
  if (miniAssetChartRef.value) {
    const chart = echarts.init(miniAssetChartRef.value);
    chart.setOption({
      grid: { left: 0, right: 0, top: 10, bottom: 0 },
      xAxis: {
        type: "category",
        data: ["1月", "2月", "3月", "4月"],
        show: false
      },
      yAxis: { show: false },
      series: [
        {
          type: "bar",
          data: [
            { value: 15, itemStyle: { color: "#f0f2f5" } },
            { value: 25, itemStyle: { color: "#f0f2f5" } },
            { value: 45, itemStyle: { color: "#a6a6d2" } },
            { value: 65, itemStyle: { color: "#a6a6d2" } }
          ],
          barWidth: 10,
          itemStyle: { borderRadius: [2, 2, 0, 0] }
        }
      ]
    });
    charts.push(chart);
  }
};

const handleResize = () => {
  charts.forEach(chart => chart.resize());
};

onMounted(() => {
  fetchSummary().then(() => {
    nextTick(() => {
      initCharts();
    });
  });
  window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  charts.forEach(chart => chart.dispose());
  charts = [];
});


</script>

<style scoped>
.welcome-container {
  font-family:
    "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue",
    Helvetica, Arial, sans-serif;
}
</style>
