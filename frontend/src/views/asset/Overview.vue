<template>
  <div class="asset-overview-container p-6 bg-gray-50 min-h-full font-sans">
    <!-- 核心资产与变化合并卡片 -->
    <div class="flex flex-col lg:flex-row gap-6 mb-6">
      <!-- 左侧：核心资产卡片 (2/3) -->
      <div class="lg:w-2/3 bg-white rounded-xl shadow-sm p-8">
        <div class="flex flex-col gap-8 h-full">
          <!-- 净资产突出显示 -->
          <div
            class="flex flex-col justify-center items-center border-b border-gray-100 pb-6"
          >
            <p class="text-gray-400 text-sm mb-2">净资产</p>
            <div class="flex items-baseline gap-1 mb-2">
              <span class="text-2xl font-medium text-gray-800">¥</span>
              <h2 class="text-5xl font-bold text-[#28A87E] tracking-tight">
                1,487,482.95
              </h2>
            </div>
            <div class="flex items-center gap-2 text-sm">
              <span class="text-gray-400">占比</span>
              <span class="font-bold text-[#28A87E]">51.0%</span>
            </div>
          </div>

          <!-- 总资产和总负债二级显示 -->
          <div class="flex flex-col justify-center flex-1">
            <div class="grid grid-cols-1 gap-6">
              <!-- 总资产 -->
              <div class="flex flex-col justify-center">
                <p class="text-gray-400 text-xs mb-2">总资产</p>
                <div class="flex items-baseline gap-1 mb-1">
                  <span class="text-lg font-medium text-gray-800">¥</span>
                  <h3 class="text-2xl font-bold text-gray-800 tracking-tight">
                    2,918,379.83
                  </h3>
                </div>
                <div class="flex items-center gap-2 text-xs">
                  <span class="text-gray-400">占比</span>
                  <span class="font-bold text-gray-600">100%</span>
                </div>
              </div>
              <!-- 总负债 -->
              <div class="flex flex-col justify-center">
                <p class="text-gray-400 text-xs mb-2">总负债</p>
                <div class="flex items-baseline gap-1 mb-1">
                  <span class="text-lg font-medium text-gray-800">¥</span>
                  <h3 class="text-2xl font-bold text-gray-800 tracking-tight">
                    1,430,896.88
                  </h3>
                </div>
                <div class="flex items-center gap-2 text-xs">
                  <span class="text-gray-400">占比</span>
                  <span class="font-bold text-gray-600">49.0%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：总资产变化卡片 (1/3) -->
      <div class="lg:w-1/3 bg-white rounded-xl shadow-sm p-6">
        <div class="flex justify-between items-center mb-6">
          <h3 class="text-gray-800 font-bold text-lg">总资产变化</h3>
          <div class="flex items-center gap-2">
            <span class="text-gray-400 text-xs">本月变动：</span>
            <span class="text-sm font-bold text-red-500"
              >+¥28,973.83 (+1.9%)</span
            >
          </div>
        </div>
        <div ref="assetChangeChartRef" class="h-[300px] w-full" />
      </div>
    </div>

    <!-- 资产构成卡片 -->
    <div class="bg-white rounded-xl shadow-sm p-6 mb-6">
      <div class="flex items-center justify-between mb-6">
        <h3 class="text-gray-800 font-bold text-lg">资产构成</h3>
        <div class="flex bg-[#f0f2f5] p-1 rounded-lg">
          <button
            :class="[
              'px-4 py-1.5 text-xs rounded-sm transition-all duration-200',
              displayMode === 'amount'
                ? 'bg-white text-gray-800 shadow-sm font-medium'
                : 'text-gray-500 hover:text-gray-700'
            ]"
            @click="displayMode = 'amount'"
          >
            金额
          </button>
          <button
            :class="[
              'px-4 py-1.5 text-xs rounded-sm transition-all duration-200',
              displayMode === 'percent'
                ? 'bg-white text-gray-800 shadow-sm font-medium'
                : 'text-gray-500 hover:text-gray-700'
            ]"
            @click="displayMode = 'percent'"
          >
            比例
          </button>
          <button
            :class="[
              'px-4 py-1.5 text-xs rounded-sm transition-all duration-200',
              displayMode === 'hidden'
                ? 'bg-white text-gray-800 shadow-sm font-medium'
                : 'text-gray-500 hover:text-gray-700'
            ]"
            @click="displayMode = 'hidden'"
          >
            隐藏金额
          </button>
        </div>
      </div>
      <div ref="sankeyChartRef" class="h-[400px] w-full" />
    </div>

    <!-- 资产/负债切换卡片 -->
    <div class="bg-white rounded-xl shadow-sm p-6">
      <div class="flex items-center justify-between mb-6">
        <div class="flex bg-[#f0f2f5] p-1 rounded-lg w-[200px]">
          <button
            :class="[
              'flex-1 px-4 py-1.5 text-xs rounded-sm transition-all duration-200',
              activeTab === 'assets'
                ? 'bg-white text-gray-800 shadow-sm font-medium'
                : 'text-gray-500 hover:text-gray-700'
            ]"
            @click="activeTab = 'assets'"
          >
            资产
          </button>
          <button
            :class="[
              'flex-1 px-4 py-1.5 text-xs rounded-sm transition-all duration-200',
              activeTab === 'liabilities'
                ? 'bg-white text-gray-800 shadow-sm font-medium'
                : 'text-gray-500 hover:text-gray-700'
            ]"
            @click="activeTab = 'liabilities'"
          >
            负债
          </button>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-gray-400 text-xs">家庭成员：</span>
          <select
            v-model="selectedMember"
            class="text-xs border border-gray-200 rounded-md px-2 py-1 focus:outline-none focus:ring-1 focus:ring-[#a6a6d2]"
          >
            <option value="all">全部</option>
            <option value="me">我</option>
            <option value="spouse">配偶</option>
          </select>
        </div>
      </div>

      <!-- 资产列表 -->
      <div v-if="activeTab === 'assets'" class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="text-gray-400 border-b border-gray-50 bg-white">
            <tr>
              <th class="text-left py-4 pl-4 font-normal">名称</th>
              <th class="text-right py-4 font-normal">资产占比</th>
              <th class="text-right py-4 font-normal">价值</th>
              <th class="text-right py-4 pr-4 font-normal">变化</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in assetList"
              :key="item.name"
              class="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors group"
            >
              <td class="py-4 pl-4 flex items-center gap-3">
                <span
                  class="w-2 h-2 rounded-full"
                  :style="{ backgroundColor: item.color }"
                />
                <span class="font-medium text-gray-700">{{ item.name }}</span>
                <span v-if="item.member" class="text-[10px] text-gray-300"
                  >({{ item.member }})</span
                >
              </td>
              <td class="py-4 text-right text-gray-600">
                {{ item.percent }} %
              </td>
              <td class="py-4 text-right font-bold text-gray-800">
                {{ displayMode === "hidden" ? "****" : `¥ ${item.value}` }}
              </td>
              <td
                class="py-4 text-right pr-4 font-medium"
                :class="
                  item.change > 0
                    ? 'text-red-500'
                    : item.change < 0
                      ? 'text-green-500'
                      : 'text-gray-400'
                "
              >
                {{ item.change > 0 ? "+" : ""
                }}{{ item.change ? `¥${item.change}` : "-" }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 负债列表 -->
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="text-gray-400 border-b border-gray-50 bg-white">
            <tr>
              <th class="text-left py-4 pl-4 font-normal">名称</th>
              <th class="text-right py-4 font-normal">负债占比</th>
              <th class="text-right py-4 font-normal">金额</th>
              <th class="text-right py-4 pr-4 font-normal">变化</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in liabilityList"
              :key="item.name"
              class="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors group"
            >
              <td class="py-4 pl-4 flex items-center gap-3">
                <span
                  class="w-2 h-2 rounded-full"
                  :style="{ backgroundColor: item.color }"
                />
                <span class="font-medium text-gray-700">{{ item.name }}</span>
                <span v-if="item.member" class="text-[10px] text-gray-300"
                  >({{ item.member }})</span
                >
              </td>
              <td class="py-4 text-right text-gray-600">
                {{ item.percent }} %
              </td>
              <td class="py-4 text-right font-bold text-gray-800">
                {{ displayMode === "hidden" ? "****" : `¥ ${item.value}` }}
              </td>
              <td
                class="py-4 text-right pr-4 font-medium"
                :class="
                  item.change > 0
                    ? 'text-red-500'
                    : item.change < 0
                      ? 'text-green-500'
                      : 'text-gray-400'
                "
              >
                {{ item.change > 0 ? "+" : ""
                }}{{ item.change ? `¥${item.change}` : "-" }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, onUnmounted, watch } from "vue";
import * as echarts from "echarts";

const assetChangeChartRef = ref<HTMLDivElement | null>(null);
const sankeyChartRef = ref<HTMLDivElement | null>(null);

let assetChangeChart: echarts.ECharts | null = null;
let sankeyChart: echarts.ECharts | null = null;

const displayMode = ref<"amount" | "percent" | "hidden">("amount");
const activeTab = ref<"assets" | "liabilities">("assets");
const selectedMember = ref<string>("all");

const assetList = ref([
  {
    name: "流动资金",
    percent: 7.1,
    value: "207,336.63",
    change: -233251.37,
    color: "#B85828",
    member: "我"
  },
  {
    name: "固定资产",
    percent: 73.67,
    value: "2,150,000.00",
    change: 0,
    color: "#4D8599",
    member: "我"
  },
  {
    name: "投资理财",
    percent: 19.22,
    value: "561,043.20",
    change: 262225.2,
    color: "#695499",
    member: "我"
  }
]);

const liabilityList = ref([
  {
    name: "房屋贷款",
    percent: 100,
    value: "1,430,896.88",
    change: -20406.12,
    color: "#81808F",
    member: "我"
  }
]);

watch([displayMode, selectedMember], () => {
  initSankeyChart();
});

const initAssetChangeChart = () => {
  if (!assetChangeChartRef.value) return;
  if (assetChangeChart) assetChangeChart.dispose();
  assetChangeChart = echarts.init(assetChangeChartRef.value);

  // 精准匹配参考图的核心数据
  const start = 2889406; // 上期末总资产
  const changes = [
    { name: "流动资金", value: -233251 }, // 绿色下跌
    { name: "固定资产", value: 0 }, // 灰色无变化
    { name: "投资理财", value: 262225 }, // 红色上涨（精准匹配参考图+262225）
    { name: "负债", value: -20406 } // 绿色下跌
  ];
  const end = 2918380; // 本期末总资产

  // 瀑布图双层堆叠核心逻辑（修复绝对值问题）
  const data = []; // 显示柱数据（变化值/总计值）
  const bottomData = []; // 底部透明柱（支撑高度）
  let current = start;

  // 1. 上期末：底柱0，显示柱为start（首柱单独配色）
  data.push(start);
  bottomData.push(0);

  // 2. 中间变化项：底柱为当前值，显示柱为变化值（非绝对值）
  changes.forEach(item => {
    bottomData.push(current); // 底柱高度=当前总资产
    data.push(item.value); // 显示柱=变化值（正负保留）
    current += item.value; // 更新当前总资产
  });

  // 3. 本期末：底柱0，显示柱为end（尾柱单独配色）
  data.push(end);
  bottomData.push(0);

  const xData = [
    "上期末",
    "流动资金",
    "固定资产",
    "投资理财",
    "负债",
    "本期末"
  ];

  const option = {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: params => {
        const idx = params[0].dataIndex;
        let name = xData[idx];
        let val = data[idx];
        // 提示框显示逻辑匹配参考图
        if (idx === 0) val = `¥${start.toLocaleString()}（上期末）`;
        else if (idx === 5) val = `¥${end.toLocaleString()}（本期末）`;
        else val = `${val > 0 ? "+" : ""}¥${Math.abs(val).toLocaleString()}`;
        return `${name}<br/>${val}`;
      }
    },
    grid: {
      left: "8%",
      right: "8%",
      top: "10%",
      bottom: "25%",
      containLabel: true
    },
    xAxis: {
      type: "category",
      data: xData,
      axisLabel: {
        fontSize: 10,
        rotate: 30,
        color: "#999",
        interval: 0,
        align: "center"
      },
      axisLine: { lineStyle: { color: "#eee" } }
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#f5f5f5" } },
      axisLabel: {
        color: "#999",
        fontSize: 11,
        formatter: v => v.toLocaleString()
      },
      // 修复Y轴范围，避免柱子超出可视区域
      min: Math.min(start - 500000, 0),
      max: Math.max(end + 500000, 3000000)
    },
    series: [
      // 底部透明柱（支撑瀑布图高度，不可省略）
      {
        name: "底柱",
        type: "bar",
        stack: "total",
        silent: true,
        itemStyle: { color: "transparent", borderWidth: 0 },
        data: bottomData
      },
      // 核心显示柱（解决3个核心问题）
      {
        name: "变化值",
        type: "bar",
        stack: "total",
        barWidth: "25%", // 匹配参考图柱子宽度
        itemStyle: {
          borderRadius: 4,
          // 修复：首尾柱子不同色 + 中间项配色匹配参考图
          color: params => {
            const idx = params.dataIndex;
            const val = data[idx];
            // 首柱（上期末）：深蓝色
            if (idx === 0) return "#2F5496";
            // 尾柱（本期末）：深紫色
            if (idx === 5) return "#6262A3";
            // 中间项：涨红/跌绿/不变灰（匹配参考图）
            if (val > 0) return "#f5222d"; // 投资理财-红
            if (val < 0) return "#52c41a"; // 流动资金/负债-绿
            return "#d9d9d9"; // 固定资产-灰
          }
        },
        data: data,
        label: {
          show: true,
          position: "top",
          fontSize: 10,
          color: "#666",
          // 修复：投资理财标签显示+262225（和参考图一致）
          formatter: params => {
            const idx = params.dataIndex;
            const val = data[idx];
            // 首尾柱子不显示标签
            if (idx === 0 || idx === 5) return "";
            // 固定资产显示“无变化”
            if (val === 0) return "无变化";
            // 投资理财/流动资金/负债显示带符号数值（匹配参考图）
            return (val > 0 ? "+" : "") + Math.abs(val).toLocaleString();
          }
        }
      }
    ]
  };

  assetChangeChart.setOption(option);
};
const initSankeyChart = () => {
  if (!sankeyChartRef.value) return;
  if (sankeyChart) sankeyChart.dispose();
  sankeyChart = echarts.init(sankeyChartRef.value);

  const getLabel = (name: string, val: number, member?: string) => {
    const memberSuffix =
      member && selectedMember.value !== "all" ? `(${member})` : "";
    if (displayMode.value === "hidden") {
      return `${name}${memberSuffix}`;
    }
    const valStr = val + "万";
    const pctStr = ((val / 291.8) * 100).toFixed(1) + "%";
    return displayMode.value === "amount"
      ? `${name}${memberSuffix} ${valStr}`
      : `${name}${memberSuffix} ${pctStr}`;
  };

  const data = {
    nodes: [
      {
        name: "房屋贷款",
        value: 143.1,
        itemStyle: { color: "#81808F" },
        member: "我"
      },
      { name: "负债", value: 143.1, itemStyle: { color: "#81808F" } },
      { name: "净资产", value: 148.7, itemStyle: { color: "#28A87E" } },
      { name: "总资产", value: 291.8, itemStyle: { color: "#6262A3" } },
      {
        name: "流动资金",
        value: 20.7,
        itemStyle: { color: "#B85828" },
        member: "我"
      },
      {
        name: "固定资产",
        value: 215.0,
        itemStyle: { color: "#4D8599" },
        member: "我"
      },
      {
        name: "投资理财",
        value: 56.1,
        itemStyle: { color: "#695499" },
        member: "我"
      },
      {
        name: "微众银行",
        value: 19.6,
        itemStyle: { color: "#B85828" },
        member: "我"
      },
      {
        name: "房产(自住)",
        value: 215.0,
        itemStyle: { color: "#4D8599" },
        member: "我"
      },
      {
        name: "基金",
        value: 21.8,
        itemStyle: { color: "#695499" },
        member: "我"
      },
      {
        name: "股票",
        value: 34.3,
        itemStyle: { color: "#695499" },
        member: "我"
      }
    ],
    links: [
      { source: "房屋贷款", target: "负债", value: 143.1 },
      { source: "负债", target: "总资产", value: 143.1 },
      { source: "净资产", target: "总资产", value: 148.7 },
      { source: "总资产", target: "流动资金", value: 20.7 },
      { source: "总资产", target: "固定资产", value: 215.0 },
      { source: "总资产", target: "投资理财", value: 56.1 },
      { source: "流动资金", target: "微众银行", value: 19.6 },
      { source: "固定资产", target: "房产(自住)", value: 215.0 },
      { source: "投资理财", target: "基金", value: 21.8 },
      { source: "投资理财", target: "股票", value: 34.3 }
    ]
  };

  const mappedNodes = data.nodes.map(n => ({
    ...n,
    name: getLabel(n.name, n.value, n.member)
  }));
  const mappedLinks = data.links.map(l => ({
    source:
      mappedNodes.find(n => n.name.startsWith(l.source))?.name || l.source,
    target:
      mappedNodes.find(n => n.name.startsWith(l.target))?.name || l.target,
    value: l.value
  }));

  sankeyChart.setOption({
    tooltip: {
      trigger: "item",
      triggerOn: "mousemove",
      backgroundColor: "rgba(255, 255, 255, 0.95)",
      borderWidth: 0,
      shadowBlur: 10,
      shadowColor: "rgba(0, 0, 0, 0.1)",
      formatter: (params: any) => {
        if (params.dataType === "node") {
          const val = params.data.value;
          const pct = ((val / 291.8) * 100).toFixed(2);
          const member = params.data.member ? ` (${params.data.member})` : "";
          return `<div class="p-2">
            <div class="text-gray-400 text-xs mb-1">${params.name.split(" ")[0]}${member}</div>
            <div class="font-bold text-gray-800">¥ ${val}万</div>
            <div class="text-blue-500 text-xs mt-1">占比 ${pct}%</div>
          </div>`;
        }
        return null;
      }
    },
    series: [
      {
        type: "sankey",
        data: mappedNodes,
        links: mappedLinks,
        emphasis: { focus: "adjacency" },
        lineStyle: { color: "gradient", curveness: 0.5, opacity: 0.3 },
        label: {
          fontSize: 12,
          color: "#333",
          formatter: "{b}"
        },
        nodeAlign: "justify",
        nodeGap: 18,
        nodeWidth: 20,
        layoutIterations: 32,
        silent: false
      }
    ]
  });
};

const handleResize = () => {
  assetChangeChart?.resize();
  sankeyChart?.resize();
};

onMounted(() => {
  nextTick(() => {
    initAssetChangeChart();
    initSankeyChart();
    window.addEventListener("resize", handleResize);
  });
});

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
});
</script>

<style scoped>
.asset-overview-container {
  font-family:
    "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue",
    Helvetica, Arial, sans-serif;
}
</style>
