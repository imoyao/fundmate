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

    <!-- 底部明细表格 -->
    <el-card shadow="never">
      <div class="flex items-center justify-between mb-4">
        <h3 class="font-semibold text-gray-800">全部资产明细</h3>
        <el-input
          v-model="searchKeyword"
          placeholder="搜索资产名称..."
          clearable
          class="max-w-[300px]"
          :prefix-icon="Search"
        />
      </div>
      <el-table
        :data="filteredTableData"
        stripe
        size="default"
        :default-sort="{ prop: 'marketValue', order: 'descending' }"
      >
        <el-table-column prop="name" label="名称" min-width="140" sortable>
          <template #default="{ row }">{{ row.name || row.symbol }}</template>
        </el-table-column>
        <el-table-column prop="type_label" label="类型" width="80" sortable>
          <template #default="{ row }">
            <el-tag :type="typeTag(row.type)" size="small" effect="plain">{{
              row.type_label || row.type
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="account_name"
          label="账户"
          width="100"
          sortable
        />
        <el-table-column
          prop="allocation_label"
          label="配置目标"
          width="100"
          sortable
        >
          <template #default="{ row }">
            {{ row.allocation_label || allocationLabel(row.allocation) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="marketValue"
          label="市值(¥)"
          width="130"
          align="right"
          sortable
        >
          <template #default="{ row }"
            >¥{{ row.marketValue.toLocaleString() }}</template
          >
        </el-table-column>
        <el-table-column
          prop="pnl"
          label="盈亏(¥)"
          width="130"
          align="right"
          sortable
        >
          <template #default="{ row }">
            <span :class="row.pnl >= 0 ? 'text-red-500' : 'text-green-500'">
              {{ row.pnl >= 0 ? "+" : "" }}¥{{ row.pnl.toLocaleString() }}
            </span>
          </template>
        </el-table-column>
        <el-table-column
          prop="pnlRate"
          label="盈亏率"
          width="90"
          align="right"
          sortable
        >
          <template #default="{ row }">
            <span :class="row.pnlRate >= 0 ? 'text-red-500' : 'text-green-500'">
              {{ row.pnlRate >= 0 ? "+" : "" }}{{ row.pnlRate.toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
      </el-table>
      <div
        v-if="filteredTableData.length === 0"
        class="text-center py-12 text-gray-400"
      >
        <IconifyIconOffline icon="ep:folder-opened" class="text-4xl mb-2" />
        <p>暂无数据</p>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onActivated, nextTick ,onUnmounted,watch} from "vue";
import { Search } from "@element-plus/icons-vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import SankeyChart from "@/components/Charts/SankeyChart.vue";
import { getPositions } from "@/api/positions";
import { getSummary } from "@/api/summary";
import { getAssets } from '@/api/assets'
import { ElMessage } from "element-plus";
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


defineOptions({ name: "AssetPanorama" });

const EXCHANGE_RATES: Record<string, number> = { CNY: 1, USD: 7.25, HKD: 0.92 };

// —— 数据 ——
const allPositions = ref<any[]>([]);
const loading = ref(false);
const totalAssets = ref(0);
const totalPnl = ref(0);
const totalLiabilities = ref(0)
const searchKeyword = ref("");
const viewDimension = ref("allocation");
const allAssets = ref<any[]>([])   // 用来存 assets 表的数据

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

// —— 分组定义 ——
const ALLOC_META: Record<string, { label: string; icon: string }> = {
  liquid: { label: "活钱", icon: "💧" },
  stable: { label: "稳健底仓", icon: "🛡️" },
  longterm: { label: "长期增值", icon: "📈" },
  speculative: { label: "高风险博弈", icon: "⚡" },
  security: { label: "保险保障", icon: "🛟" }
};
const ALLOC_KEYS = ["liquid", "stable", "longterm", "speculative", "security"];

// 桑基图相关
const sankeyDisplayMode = ref<"amount" | "percent" | "hidden">("amount");
const sankeyDisplayOptions = [
  { label: "金额", value: "amount" },
  { label: "比例", value: "percent" },
  { label: "隐藏金额", value: "hidden" }
];

const sankeyData = computed(() => {
  const nodeMap = new Map<string, any>();
  function addNode(name: string, extra?: any) {
    if (!nodeMap.has(name)) {
      nodeMap.set(name, { name, ...extra });
    }
    return nodeMap.get(name)!;
  }

  const links: any[] = [];

  // 莫兰迪色系配色
  const colors: Record<string, string> = {
    '负债': '#C4A0A8',
    '净资产': '#28A87E',
    '总资产': '#7A7FA8',
    '活钱': '#B5C4B1',
    '稳健底仓': '#9CAF88',
    '长期增值': '#E8D5C4',
    '高风险博弈': '#C85A6A',
    '保险保障': '#9D81A9',
  };

  // ========== 左一：各项资产 → 总资产 ==========
  const assetItems: any[] = [];
  // 来自 assets 表（非负债）
  allAssets.value
    .filter(a => a.major_category !== 'liability' && a.marketValue > 0)
    .forEach(a => {
      addNode(a.name);
      assetItems.push({ name: a.name, value: a.marketValue });
    });
  // 来自 positions 表（投资理财）
  allPositions.value.forEach(p => {
    const name = p.name || p.symbol;
    addNode(name);
    assetItems.push({ name, value: p.marketValue });
  });

  addNode('总资产', { itemStyle: { color: colors['总资产'] } });
  assetItems.forEach(it => {
    links.push({ source: it.name, target: '总资产', value: it.value });
  });

  // ========== 总资产 → 负债 + 净资产 ==========
  const totalLiabilities = allAssets.value
    .filter(a => a.major_category === 'liability')
    .reduce((s, a) => s + (a.marketValue || 0), 0);

  const totalEquity = totalAssets.value - totalLiabilities;

  addNode('负债', { itemStyle: { color: colors['负债'] } });
  addNode('净资产', { itemStyle: { color: colors['净资产'] } });

  if (totalLiabilities > 0) {
    links.push({ source: '总资产', target: '负债', value: Math.round(totalLiabilities) });
  }
  if (totalEquity > 0) {
    links.push({ source: '总资产', target: '净资产', value: Math.round(totalEquity) });
  }

  // ========== 负债 → 具体负债项 ==========
  allAssets.value
    .filter(a => a.major_category === 'liability' && a.marketValue > 0)
    .forEach(a => {
      addNode(a.name, { itemStyle: { color: colors['负债'] } });
      links.push({ source: '负债', target: a.name, value: a.marketValue });
    });

  // ========== 净资产 → 五笔钱 → 产品类型 ==========
  const allocMap: Record<string, number> = {};
  allPositions.value.forEach(p => {
    const alloc = p.allocation || 'longterm';
    allocMap[alloc] = (allocMap[alloc] || 0) + (p.marketValue || 0);
  });

  const allocLabels: Record<string, string> = {
    liquid: '活钱',
    stable: '稳健底仓',
    longterm: '长期增值',
    speculative: '高风险博弈',
    security: '保险保障'
  };

  Object.entries(allocMap).forEach(([key, value]) => {
    const label = allocLabels[key] || key;
    addNode(label, { itemStyle: { color: colors[label] || '#C5C9B8' } });
    links.push({ source: '净资产', target: label, value: Math.round(value) });
  });

  // 五笔钱 → 产品类型
  const allocTypeMap: Record<string, Record<string, number>> = {};
  allPositions.value.forEach(p => {
    const alloc = allocLabels[p.allocation] || '长期增值';
    const type = p.type_label || p.type;
    if (!allocTypeMap[alloc]) allocTypeMap[alloc] = {};
    allocTypeMap[alloc][type] = (allocTypeMap[alloc][type] || 0) + (p.marketValue || 0);
  });

  Object.entries(allocTypeMap).forEach(([allocLabel, typeMap]) => {
    Object.entries(typeMap).forEach(([typeName, value]) => {
      addNode(typeName);
      links.push({ source: allocLabel, target: typeName, value: Math.round(value) });
    });
  });

  return { nodes: Array.from(nodeMap.values()), links };
});

const allocationGroups = computed(() => {
  const groups: Record<string, any[]> = {}
  ALLOC_KEYS.forEach(k => (groups[k] = []))

  allPositions.value.forEach(p => {
    const a = p.allocation || 'longterm'
    groups[a] ? groups[a].push(p) : groups['longterm'].push(p)
  })

  const grandTotal = allPositions.value.reduce((s, p) => s + p.marketValue, 0)

  return ALLOC_KEYS.map(key => {
    const items = groups[key]
    const total = items.reduce((s, p) => s + p.marketValue, 0)
    return {
      key,
      label: ALLOC_META[key]?.label || key,
      total,
      percent: grandTotal > 0 ? +((total / grandTotal) * 100).toFixed(1) : 0,
      count: items.length,
      topItems: items.slice(0, 3),
      items
    }
  })
})

function getColorForAlloc(key: string): string {
  const colors: Record<string, string> = {
    liquid: "#3b82f6",
    stable: "#10b981",
    longterm: "#f59e0b",
    speculative: "#ef4444",
    security: "#8b5cf6"
  };
  return colors[key] || "#6b7280";
}

const dimensionGroups = computed(() => {
  const dim = viewDimension.value;
  const map: Record<string, { name: string; total: number; count: number }> =
    {};

  // 决定使用哪个 label 字段
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
    // 分组键：用 label（如果有），否则用原始字段
    const groupKey =
      (labelField ? (p[labelField] ?? p[dim]) : p[dim]) || "其他";
    const displayName =
      (labelField ? (p[labelField] ?? p[dim]) : p[dim]) || "其他";

    if (!map[groupKey])
      map[groupKey] = { name: displayName, total: 0, count: 0 };
    map[groupKey].total += p.marketValue;
    map[groupKey].count++;
  });

  const grandTotal = allPositions.value.reduce((s, p) => s + p.marketValue, 0);
  return Object.values(map).map(g => ({
    ...g,
    percent: grandTotal > 0 ? +((g.total / grandTotal) * 100).toFixed(1) : 0
  }));
});


const filteredTableData = computed(() => {
  let list = allPositions.value;
  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase();
    list = list.filter((p: any) =>
      (p.name || p.symbol).toLowerCase().includes(kw)
    );
  }
  return list;
});

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

// —— 瀑布图初始化（模拟总资产变化） ——
function initWaterfallChart() {
  if (!waterfallChartRef.value || allPositions.value.length === 0) return;
  if (waterfallChart) waterfallChart.dispose();
  waterfallChart = echarts.init(waterfallChartRef.value);

  // 示例数据
  const start = 2800000;
  const changes = [
    { name: "流动资金", value: -233251 },
    { name: "固定资产", value: 0 },
    { name: "投资理财", value: 262225 },
    { name: "负债", value: -20406 }
  ];
  const end = start + changes.reduce((s, c) => s + c.value, 0);

  // 计算每一项的累积值（柱子高度）
  const cumulativeValues: number[] = [start];
  changes.forEach((item, index) => {
    cumulativeValues.push(cumulativeValues[index] + item.value);
  });

  // 构建所有柱子的数据：柱高、变化值、名称
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

  // 现代化色彩配置
  const endpointStartColor = "#3B82F6"; // 上期末：现代蓝
  const endpointEndColor = "#6366F1"; // 本期末：现代靛蓝/紫
  const positiveColor = "#F43F5E"; // 增加：玫瑰红（现代化红）
  const negativeColor = "#10B981"; // 减少：翠绿
  const zeroColor = "#A1A1AA"; // 无变化：锌灰

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
            if (d.isEndpoint && d.name === "上期末") return endpointStartColor; // 上期末
            if (d.isEndpoint && d.name === "本期末") return endpointEndColor; // 本期末
            if (d.change > 0) return positiveColor; // 增加
            if (d.change < 0) return negativeColor; // 减少
            return zeroColor; // 无变化
          }
        },
        label: {
          show: true,
          position: "top",
          fontSize: 10,
          color: "#666",
          formatter: (params: any) => {
            const d = allData[params.dataIndex];
            if (d.isEndpoint) {
              // 端点显示值，加上 "¥" 符号，格式化显示
              return "¥" + d.height.toLocaleString();
            }
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
    grid: {
      left: "3%",
      right: "4%",
      bottom: "8%",
      top: "10%",
      containLabel: true
    },
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
  loading.value = true
  try {
    const [posRes, sumRes, assetsRes] = await Promise.all([
      getPositions({ per_page: 500 }),
      getSummary(),
      getAssets({ per_page: 500 })
    ])

    // 处理 positions
    let positionsRaw: any[] = []
    if (Array.isArray(posRes)) positionsRaw = posRes
    else if (posRes && Array.isArray((posRes as any).data))
      positionsRaw = (posRes as any).data
    else if (
      posRes &&
      (posRes as any).data &&
      Array.isArray((posRes as any).data.data)
    )
      positionsRaw = (posRes as any).data.data
    else {
      const maybe = (posRes as any)?.data ?? posRes ?? []
      positionsRaw = Array.isArray(maybe) ? maybe : []
    }

    // 处理 assets
    let assetsRaw: any[] = []
    if (Array.isArray(assetsRes)) assetsRaw = assetsRes
    else if (assetsRes && Array.isArray((assetsRes as any).data))
      assetsRaw = (assetsRes as any).data
    else if (assetsRes && (assetsRes as any).data && Array.isArray((assetsRes as any).data.data))
      assetsRaw = (assetsRes as any).data.data
    else {
      const maybe = (assetsRes as any)?.data ?? assetsRes ?? []
      assetsRaw = Array.isArray(maybe) ? maybe : []
    }

    // 汇总数据
    totalAssets.value =
      (sumRes as any)?.data?.total_assets_cny ??
      (sumRes as any)?.total_assets_cny ??
      0
    totalPnl.value =
      (sumRes as any)?.data?.total_pnl_cny ??
      (sumRes as any)?.total_pnl_cny ??
      0
    totalLiabilities.value =
      (sumRes as any)?.data?.total_liabilities_cny ?? 0

    allPositions.value = positionsRaw.map((p: any) => {
      const rate = EXCHANGE_RATES[p.currency || 'CNY'] || 1
      const marketValue = (p.quantity || 0) * (p.current_price || 0) * rate
      const pnl = ((p.current_price || 0) - (p.avg_price || 0)) * (p.quantity || 0) * rate
      const pnlRate = (p.avg_price || 1) !== 0 ? ((p.current_price || 0) / (p.avg_price || 1) - 1) * 100 : 0
      return { ...p, marketValue, pnl, pnlRate }
    })

    allAssets.value = assetsRaw.map((a: any) => ({
      ...a,
      marketValue: a.amount || 0
    }))
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
    await nextTick()
    initCharts()
    updatePieChart()
    initWaterfallChart()
  }
}
// const handleResize = () => {
//   pieChart?.resize();
//   barChart?.resize();
//   waterfallChart?.resize();
// };

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
