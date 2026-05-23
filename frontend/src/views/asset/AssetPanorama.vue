<template>
  <div class="panorama p-4 md:p-6 bg-[#f5f7fa] min-h-full">
    <!-- 页面标题 -->
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2 class="text-2xl font-bold text-gray-800">资产总览</h2>
        <p class="text-gray-500 text-sm mt-1">多维度审视你的财富版图</p>
      </div>
      <el-button :loading="loading" @click="fetchData">
        <IconifyIconOffline icon="ep:refresh" class="mr-1" /> 刷新
      </el-button>
    </div>

    <!-- 总览大卡片 (整合左侧数据 + 右侧瀑布图) -->
    <el-row :gutter="16" class="mb-6">
      <el-col :xs="24" :md="12" class="mb-4 md:mb-0">
        <el-card shadow="never" class="summary-large-card">
          <div class="flex flex-col justify-between h-full">
            <!-- 总资产：主视觉 -->
            <div>
              <p class="text-gray-400 text-sm mb-1">总资产（本月）</p>
              <h2 class="text-5xl font-bold text-[#FF6B00] tracking-tight">
                ¥{{ totalAssets.toLocaleString() }}
              </h2>
              <div class="flex items-center gap-4 mt-2">
                <span class="text-green-600 text-sm font-medium flex items-center">
                  <IconifyIconOffline icon="ep:arrow-up-bold" class="mr-1" />
                  12.3% <span class="text-gray-400 ml-1 font-normal">较上月</span>
                </span>
                <span class="text-green-600 text-sm font-medium flex items-center">
                  <IconifyIconOffline icon="ep:arrow-up-bold" class="mr-1" />
                  8.7% <span class="text-gray-400 ml-1 font-normal">较去年同期</span>
                </span>
              </div>
              <div class="mt-3 flex items-center gap-2">
                <span class="px-2 py-0.5 bg-amber-100 text-amber-600 rounded-full text-xs font-medium">
                  中等风险
                </span>
                <span class="text-xs text-gray-400">风险评分：65/100</span>
              </div>
            </div>

            <!-- 分割线 -->
            <div class="border-t border-gray-100 my-5"></div>

            <!-- 次级信息：总负债、净资产、总盈亏 -->
            <div class="grid grid-cols-3 gap-4">
              <div>
                <p class="text-gray-400 text-xs mb-1">总负债</p>
                <p class="text-lg font-bold text-gray-800">
                  ¥{{ totalLiabilities.toLocaleString() }}
                </p>
              </div>
              <div>
                <p class="text-gray-400 text-xs mb-1">净资产</p>
                <p class="text-lg font-bold text-[#28A87E]">
                  ¥{{ (totalAssets - totalLiabilities).toLocaleString() }}
                </p>
              </div>
              <div>
                <p class="text-gray-400 text-xs mb-1">总盈亏</p>
                <p :class="['text-lg font-bold', totalPnl >= 0 ? 'text-red-500' : 'text-green-500']">
                  {{ totalPnl >= 0 ? "+" : "" }}¥{{ totalPnl.toLocaleString() }}
                </p>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：总资产变化图（保持原有不变） -->
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="h-full">
          <div class="flex justify-between items-center mb-4">
            <h3 class="font-semibold text-gray-800">总资产变化</h3>
            <el-tooltip content="资产月历（后续版本推出）" placement="top">
              <el-button text type="primary" size="small" class="!px-2">
                <IconifyIconOffline icon="ep:calendar" class="text-base" />
              </el-button>
            </el-tooltip>
          </div>
          <div ref="waterfallChartRef" class="h-[280px]" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 桑基图：资产构成流向（中心发散式单图） -->
    <el-card shadow="never" class="mb-4">
      <div class="flex items-center justify-between mb-4">
        <h3 class="font-semibold text-gray-800">资产构成流向</h3>
        <div class="flex items-center gap-2">
          <el-segmented
            v-model="sankeyDisplayMode"
            :options="sankeyDisplayOptions"
          />
        </div>
      </div>
      <SankeyChart :data="sankeyData" :display-mode="sankeyDisplayMode" />
    </el-card>

    <!-- 视图切换 + 图表 + 表格 -->
    <el-card shadow="never" class="mb-4">
      <div class="flex items-center mb-4">
        <span class="text-sm text-gray-500 mr-3">视图维度：</span>
        <el-segmented
          v-model="viewDimension"
          :options="dimensionOptions"
          @change="updatePieChart"
        />
      </div>
      <el-row :gutter="16">
        <el-col :xs="24" :md="12" class="mb-4 md:mb-0">
          <div ref="pieChartRef" class="h-[320px]" />
        </el-col>
        <el-col :xs="24" :md="12">
          <div ref="barChartRef" class="h-[320px]" />
        </el-col>
      </el-row>
    </el-card>

    <!-- 维度分组摘要卡片（动态切换，丰富的卡片样式） -->
    <el-row :gutter="12" class="mb-4">
      <el-col
        v-for="group in dimensionGroups"
        :key="group.name"
        :xs="12"
        :sm="6"
        :lg="4"
        class="mb-3"
      >
        <el-card shadow="never" class="dimension-card group-card">
          <div class="flex items-center gap-1 mb-2">
            <span class="text-sm font-semibold text-gray-700">{{
              group.name
            }}</span>
            <span class="text-xs text-gray-400 ml-auto"
              >{{ group.count }} 项</span
            >
          </div>
          <p class="text-lg font-bold text-gray-800">
            ¥{{ group.total.toLocaleString() }}
          </p>
          <div class="h-1.5 bg-gray-100 rounded-full mt-2 mb-1">
            <div
              class="h-full bg-primary rounded-full transition-all"
              :style="{ width: group.percent + '%' }"
            />
          </div>
          <div class="text-xs text-gray-400">占 {{ group.percent }}%</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 底部：资产/负债切换表格 -->
    <el-card shadow="never">
      <div class="flex items-center justify-between mb-6">
        <div class="flex bg-[#f0f2f5] p-1 rounded-lg">
          <button
            :class="[
              'px-5 py-1.5 text-sm rounded-sm transition-all duration-200',
              balanceTab === 'assets'
                ? 'bg-white text-gray-800 shadow-sm font-medium'
                : 'text-gray-500 hover:text-gray-700'
            ]"
            @click="balanceTab = 'assets'"
          >
            资产端
          </button>
          <button
            :class="[
              'px-5 py-1.5 text-sm rounded-sm transition-all duration-200',
              balanceTab === 'liabilities'
                ? 'bg-white text-gray-800 shadow-sm font-medium'
                : 'text-gray-500 hover:text-gray-700'
            ]"
            @click="balanceTab = 'liabilities'"
          >
            负债端
          </button>
        </div>
      </div>

      <!-- 资产端表格 -->
      <div v-if="balanceTab === 'assets'" class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="text-gray-400 border-b border-gray-50">
            <tr>
              <th class="text-left py-4 pl-4 font-normal">资产大类</th>
              <th class="text-right py-4 font-normal">占比</th>
              <th class="text-right py-4 font-normal">价值</th>
              <th class="text-right py-4 pr-4 font-normal">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in assetBalanceRows"
              :key="item.name"
              class="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
              @click="goToAssetEntry(item.categoryKey)"
            >
              <td class="py-4 pl-4 flex items-center gap-3">
                <span
                  class="w-2.5 h-2.5 rounded-full shrink-0"
                  :style="{ backgroundColor: item.color }"
                />
                <span class="font-medium text-gray-700">{{ item.name }}</span>
              </td>
              <td class="py-4 text-right text-gray-600">{{ item.percent }}%</td>
              <td class="py-4 text-right font-bold text-gray-800">
                {{ sankeyDisplayMode === "hidden" ? "****" : `¥${item.value.toLocaleString()}` }}
              </td>
              <td class="py-4 text-right pr-4">
                <IconifyIconOffline icon="ep:arrow-right" class="text-gray-400 text-sm" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 负债端表格 -->
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="text-gray-400 border-b border-gray-50">
            <tr>
              <th class="text-left py-4 pl-4 font-normal">负债项目</th>
              <th class="text-right py-4 font-normal">占比</th>
              <th class="text-right py-4 font-normal">金额</th>
              <th class="text-right py-4 pr-4 font-normal">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in liabilityBalanceRows"
              :key="item.name"
              class="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
              @click="goToAssetEntry('liability')"
            >
              <td class="py-4 pl-4 flex items-center gap-3">
                <span
                  class="w-2.5 h-2.5 rounded-full shrink-0"
                  :style="{ backgroundColor: item.color }"
                />
                <span class="font-medium text-gray-700">{{ item.name }}</span>
              </td>
              <td class="py-4 text-right text-gray-600">{{ item.percent }}%</td>
              <td class="py-4 text-right font-bold text-gray-800">
                {{ sankeyDisplayMode === "hidden" ? "****" : `¥${item.value.toLocaleString()}` }}
              </td>
              <td class="py-4 text-right pr-4">
                <IconifyIconOffline icon="ep:arrow-right" class="text-gray-400 text-sm" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 空状态 -->
      <div
        v-if="balanceTab === 'assets' ? assetBalanceRows.length === 0 : liabilityBalanceRows.length === 0"
        class="text-center py-12 text-gray-400"
      >
        <IconifyIconOffline icon="ep:folder-opened" class="text-4xl mb-2" />
        <p>暂无数据</p>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onActivated, nextTick } from "vue";
import { useRouter } from "vue-router";
import { IconifyIconOffline } from "@/components/ReIcon";
import SankeyChart from "@/components/Charts/SankeyChart.vue";
import { getPositions } from "@/api/positions";
import { getSummary, getSankeyData } from "@/api/summary";
import { getAssets } from "@/api/assets";
import { ElMessage } from "element-plus";
import * as echarts from "echarts";

defineOptions({ name: "AssetPanorama" });

const EXCHANGE_RATES: Record<string, number> = { CNY: 1, USD: 7.25, HKD: 0.92 };

// —— 数据 ——
const allPositions = ref<any[]>([]);
const loading = ref(false);
const totalAssets = ref(0);
const totalPnl = ref(0);
const totalLiabilities = ref(0);
const allAssets = ref<any[]>([]);

const viewDimension = ref("allocation");
const sankeyDisplayMode = ref<"amount" | "percent" | "hidden">("amount");
const balanceTab = ref<"assets" | "liabilities">("assets");
const sankeyData = ref<{ nodes: any[]; links: any[] }>({ nodes: [], links: [] });

const router = useRouter();

const pieChartRef = ref<HTMLDivElement>();
const barChartRef = ref<HTMLDivElement>();
const waterfallChartRef = ref<HTMLDivElement>();
let pieChart: echarts.ECharts | null = null;
let barChart: echarts.ECharts | null = null;
let waterfallChart: echarts.ECharts | null = null;

const dimensionOptions = [
  { label: "🏷️ 配置目标", value: "allocation" },
  { label: "📦 产品类型", value: "type" },
  { label: "🏦 账户", value: "account_name" },
  { label: "🌍 市场", value: "market" }
];

const sankeyDisplayOptions = [
  { label: "金额", value: "amount" },
  { label: "比例", value: "percent" },
  { label: "隐藏金额", value: "hidden" }
];

// —— 分组定义 ——
const ALLOC_META: Record<string, { label: string; icon: string }> = {
  liquid: { label: "活钱", icon: "💧" },
  stable: { label: "稳健底仓", icon: "🛡️" },
  longterm: { label: "长期增值", icon: "📈" },
  speculative: { label: "高风险博弈", icon: "⚡" },
  security: { label: "保险保障", icon: "🛟" }
};
const ALLOC_KEYS = ["liquid", "stable", "longterm", "speculative", "security"];

// —— 计算属性 ——
const allocationGroups = computed(() => {
  const groups: Record<string, any[]> = {};
  ALLOC_KEYS.forEach(k => (groups[k] = []));

  allPositions.value.forEach(p => {
    const a = p.allocation || "longterm";
    groups[a] ? groups[a].push(p) : groups["longterm"].push(p);
  });

  const grandTotal = allPositions.value.reduce((s, p) => s + p.marketValue, 0);

  return ALLOC_KEYS.map(key => {
    const items = groups[key];
    const total = items.reduce((s, p) => s + p.marketValue, 0);
    return {
      key,
      label: ALLOC_META[key]?.label || key,
      total,
      percent: grandTotal > 0 ? +((total / grandTotal) * 100).toFixed(1) : 0,
      count: items.length,
      topItems: items.slice(0, 3),
      items
    };
  });
});

const dimensionGroups = computed(() => {
  const dim = viewDimension.value;
  const map: Record<string, { name: string; total: number; count: number }> = {};

  const labelField =
    dim === "allocation"
      ? "allocation_label"
      : dim === "type"
      ? "type_label"
      : dim === "market"
      ? "market_label"
      : dim === "account_name"
      ? "account_name"
      : null;

  allPositions.value.forEach((p: any) => {
    const groupKey = (labelField ? (p[labelField] ?? p[dim]) : p[dim]) || "其他";
    const displayName = (labelField ? (p[labelField] ?? p[dim]) : p[dim]) || "其他";

    if (!map[groupKey]) map[groupKey] = { name: displayName, total: 0, count: 0 };
    map[groupKey].total += p.marketValue;
    map[groupKey].count++;
  });

  const grandTotal = allPositions.value.reduce((s, p) => s + p.marketValue, 0);
  return Object.values(map).map(g => ({
    ...g,
    percent: grandTotal > 0 ? +((g.total / grandTotal) * 100).toFixed(1) : 0
  }));
});

// —— 资产/负债表格数据 ——
const assetBalanceRows = computed(() => {
  const total = totalAssets.value;
  if (total === 0) return [];

  const categoryMap: Record<string, { name: string; value: number; color: string; categoryKey: string }> = {
    cash: { name: "流动资金", value: 0, color: "var(--tag-mint-green)", categoryKey: "cash" },
    fixed: { name: "固定资产", value: 0, color: "var(--tag-warm-taupe)", categoryKey: "fixed" },
    investment: { name: "投资理财", value: 0, color: "var(--tag-periwinkle)", categoryKey: "investment" },
    receivable: { name: "应收款", value: 0, color: "var(--tag-stone-gray)", categoryKey: "receivable" },
    insurance: { name: "保险项目", value: 0, color: "var(--color-accent)", categoryKey: "insurance" }
  };

  allAssets.value
    .filter(a => a.major_category !== "liability" && a.marketValue > 0)
    .forEach(a => {
      const key = a.major_category;
      if (categoryMap[key]) {
        categoryMap[key].value += a.marketValue;
      }
    });

  const positionsTotal = allPositions.value.reduce((s, p) => s + (p.marketValue || 0), 0);
  categoryMap.investment.value += positionsTotal;

  return Object.values(categoryMap)
    .filter(item => item.value > 0)
    .map(item => ({
      ...item,
      percent: +((item.value / total) * 100).toFixed(1)
    }));
});

const liabilityBalanceRows = computed(() => {
  const totalLiab = totalLiabilities.value;
  if (totalLiab === 0) return [];

  const liabilityMap: Record<string, { name: string; value: number }> = {};
  allAssets.value
    .filter(a => a.major_category === "liability" && a.marketValue > 0)
    .forEach(a => {
      const key = a.name || "其他负债";
      if (!liabilityMap[key]) liabilityMap[key] = { name: key, value: 0 };
      liabilityMap[key].value += a.marketValue;
    });

  return Object.values(liabilityMap).map(item => ({
    ...item,
    color: "var(--color-neutral)",
    percent: +((item.value / totalLiab) * 100).toFixed(1)
  }));
});

// —— 跳转 ——
function goToAssetEntry(categoryKey: string) {
  router.push(`/asset/asset-entry?tab=${categoryKey}`);
}

// —— 辅助函数 ——
function typeTag(type: string) {
  const m: Record<string, string> = {
    stock: "primary",
    fund: "warning",
    bond: "info",
    crypto: "danger",
    saving: "success",
    cash: "success",
    static: "info"
  };
  return m[type] || "info";
}
function allocationLabel(a: string | null) {
  return ALLOC_META[a || ""]?.label || a || "长期增值";
}

// —— 瀑布图 ——
function initWaterfallChart() {
  if (!waterfallChartRef.value || allPositions.value.length === 0) return;
  if (waterfallChart) waterfallChart.dispose();
  waterfallChart = echarts.init(waterfallChartRef.value);

  const start = 2800000;
  const changes = [
    { name: "流动资金", value: -233251 },
    { name: "固定资产", value: 0 },
    { name: "投资理财", value: 262225 },
    { name: "负债", value: -20406 }
  ];
  const end = start + changes.reduce((s, c) => s + c.value, 0);

  const cumulativeValues: number[] = [start];
  changes.forEach((item, index) => {
    cumulativeValues.push(cumulativeValues[index] + item.value);
  });

  const allData = [
    { name: "上期末", height: start, change: start, isEndpoint: true },
    ...changes.map((item, index) => ({
      name: item.name,
      height: cumulativeValues[index + 1],
      change: item.value,
      isEndpoint: false
    })),
    { name: "本期末", height: end, change: end, isEndpoint: true }
  ];

  const xData = allData.map(d => d.name);
  const heights = allData.map(d => d.height);

  waterfallChart.setOption({
    tooltip: {
      trigger: "axis",
      formatter: (params: any) => {
        const idx = params[0].dataIndex;
        const d = allData[idx];
        if (d.isEndpoint) {
          return `${d.name}总资产：¥${d.height.toLocaleString()}`;
        }
        return `${d.name}<br/>变化：${d.change >= 0 ? "+" : ""}¥${Math.abs(d.change).toLocaleString()}<br/>
        累积资产：¥${d.height.toLocaleString()}`;
      }
    },
    grid: { left: "8%", right: "4%", top: 20, bottom: 50, containLabel: true },
    xAxis: {
      type: "category",
      data: xData,
      axisLabel: { rotate: 30, fontSize: 10, interval: 0, color: "#999" },
      axisLine: { lineStyle: { color: "#eee" } }
    },
    yAxis: {
      type: "value",
      min: 0,
      splitLine: { lineStyle: { color: "#f5f5f5" } },
      axisLabel: {
        color: "#999",
        fontSize: 11,
        formatter: (v: number) => v.toLocaleString()
      }
    },
    series: [
      {
        type: "bar",
        data: heights,
        barWidth: "30%",
        barMinHeight: 4,
        itemStyle: {
          borderRadius: 4,
          color: (params: any) => {
            const d = allData[params.dataIndex];
            if (d.isEndpoint && d.name === "上期末") return "#2F5496";
            if (d.isEndpoint && d.name === "本期末") return "#6262A3";
            if (d.change > 0) return "#f5222d";
            if (d.change < 0) return "#52c41a";
            return "#d9d9d9";
          }
        },
        label: {
          show: true,
          position: "top",
          fontSize: 10,
          color: "#666",
          formatter: (params: any) => {
            const d = allData[params.dataIndex];
            if (d.isEndpoint) return "¥" + d.height.toLocaleString();
            if (d.change === 0) return "¥0";
            return (d.change >= 0 ? "+" : "") + d.change.toLocaleString();
          }
        }
      }
    ]
  });
}

// —— 饼图、柱状图 ——
function updatePieChart() {
  if (!pieChart || allPositions.value.length === 0) return;
  const dim = viewDimension.value;
  const labelField =
    dim === "allocation"
      ? "allocation_label"
      : dim === "type"
      ? "type_label"
      : dim === "market"
      ? "market_label"
      : null;
  const groups: Record<string, number> = {};
  allPositions.value.forEach((p: any) => {
    const key = (labelField ? (p[labelField] ?? p[dim]) : p[dim]) || "其他";
    groups[key] = (groups[key] || 0) + p.marketValue;
  });
  pieChart.setOption({
    series: [
      { data: Object.entries(groups).map(([name, value]) => ({ name, value })) }
    ]
  });
  if (barChart) {
    barChart.setOption({
      xAxis: { data: Object.keys(groups) },
      series: [{ data: Object.values(groups) }]
    });
  }
}

function initCharts() {
  if (pieChart || !pieChartRef.value) return;
  pieChart = echarts.init(pieChartRef.value);
  pieChart.setOption({
    tooltip: { trigger: "item" },
    legend: { bottom: 0 },
    series: [
      {
        type: "pie",
        radius: ["45%", "70%"],
        center: ["50%", "45%"],
        data: [],
        itemStyle: { borderRadius: 4, borderColor: "#fff", borderWidth: 2 }
      }
    ]
  });
  barChart = echarts.init(barChartRef.value);
  barChart.setOption({
    tooltip: { trigger: "axis" },
    grid: { left: "3%", right: "4%", bottom: "8%", top: "10%", containLabel: true },
    xAxis: { type: "category", data: [], axisLabel: { fontSize: 11 } },
    yAxis: {
      type: "value",
      axisLabel: { fontSize: 11, formatter: "¥{value}" }
    },
    series: [
      {
        type: "bar",
        data: [],
        barWidth: "40%",
        itemStyle: { borderRadius: [4, 4, 0, 0], color: "#FF4500" },
        label: { show: true, position: "top", fontSize: 10 }
      }
    ]
  });
  updatePieChart();
}

// —— 数据获取 ——
async function fetchData() {
  loading.value = true;
  try {
    const [posRes, sumRes, assetsRes, sankeyRes] = await Promise.all([
      getPositions({ per_page: 500 }),
      getSummary(),
      getAssets({ per_page: 500 }),
      getSankeyData() // 后端已合并为单个 { nodes, links }
    ]);

    // 处理 positions
    let positionsRaw: any[] = [];
    if (Array.isArray(posRes)) positionsRaw = posRes;
    else if (posRes && Array.isArray((posRes as any).data)) positionsRaw = (posRes as any).data;
    else if (posRes && (posRes as any).data && Array.isArray((posRes as any).data.data)) positionsRaw = (posRes as any).data.data;
    else {
      const maybe = (posRes as any)?.data ?? posRes ?? [];
      positionsRaw = Array.isArray(maybe) ? maybe : [];
    }

    // 处理 assets
    let assetsRaw: any[] = [];
    if (Array.isArray(assetsRes)) assetsRaw = assetsRes;
    else if (assetsRes && Array.isArray((assetsRes as any).data)) assetsRaw = (assetsRes as any).data;
    else if (assetsRes && (assetsRes as any).data && Array.isArray((assetsRes as any).data.data)) assetsRaw = (assetsRes as any).data.data;
    else {
      const maybe = (assetsRes as any)?.data ?? assetsRes ?? [];
      assetsRaw = Array.isArray(maybe) ? maybe : [];
    }

    // 处理桑基图数据（单图模式，后端已返回合并后的 nodes / links）
    let sankeyRaw: any = { nodes: [], links: [] };
    if ((sankeyRes as any)?.data) {
      sankeyRaw = (sankeyRes as any).data;
    } else if ((sankeyRes as any)?.data?.data) {
      sankeyRaw = (sankeyRes as any).data.data;
    }
    sankeyData.value = {
      nodes: sankeyRaw.nodes || [],
      links: sankeyRaw.links || []
    };

    // 汇总数据
    totalAssets.value =
      (sumRes as any)?.data?.total_assets_cny ??
      (sumRes as any)?.total_assets_cny ??
      0;
    totalPnl.value =
      (sumRes as any)?.data?.total_pnl_cny ??
      (sumRes as any)?.total_pnl_cny ??
      0;
    totalLiabilities.value =
      (sumRes as any)?.data?.total_liabilities_cny ?? 0;

    allPositions.value = positionsRaw.map((p: any) => {
      const rate = EXCHANGE_RATES[p.currency || "CNY"] || 1;
      const marketValue = (p.quantity || 0) * (p.current_price || 0) * rate;
      const pnl = ((p.current_price || 0) - (p.avg_price || 0)) * (p.quantity || 0) * rate;
      const pnlRate = (p.avg_price || 1) !== 0 ? ((p.current_price || 0) / (p.avg_price || 1) - 1) * 100 : 0;
      return { ...p, marketValue, pnl, pnlRate };
    });

    allAssets.value = assetsRaw.map((a: any) => ({
      ...a,
      marketValue: a.amount || 0
    }));
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
    await nextTick();
    initCharts();
    updatePieChart();
    initWaterfallChart();
  }
}

const handleResize = () => {
  pieChart?.resize();
  barChart?.resize();
  waterfallChart?.resize();
};

onMounted(async () => {
  await fetchData();
  window.addEventListener("resize", handleResize);
});

onActivated(() => {
  if (allPositions.value.length > 0) {
    nextTick(() => {
      initWaterfallChart();
      updatePieChart();
    });
  }
});
</script>

<style scoped>
.summary-large-card {
  height: 100%;
  border-radius: 12px;
  transition: all 0.2s;
}

.group-card {
  cursor: default;
  border-radius: 12px;
  transition: all 0.2s;
}

.group-card:hover {
  box-shadow: 0 4px 12px rgb(0 0 0 / 8%);
  transform: translateY(-2px);
}

</style>
