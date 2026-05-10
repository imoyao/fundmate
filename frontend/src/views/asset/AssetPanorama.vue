<template>
  <div class="panorama p-4 md:p-6 bg-[#f5f7fa] min-h-full">
    <!-- 页面标题 -->
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2 class="text-2xl font-bold text-gray-800">资产全景</h2>
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
            <!-- 净资产：居中突出 -->
            <!-- 净资产 -->
            <h2 class="text-4xl font-bold text-[#28A87E] tracking-tight">
              {{ (totalAssets - totalLiabilities).toLocaleString() }}
            </h2>
            <div class="flex items-center gap-2 mt-1">
              <span class="text-gray-400 text-xs">占比</span>
              <span class="font-bold text-[#28A87E] text-xs">
                {{ totalAssets > 0 ? (( (totalAssets - totalLiabilities) / totalAssets * 100).toFixed(1)) : 0 }}%
              </span>
            </div>

            <!-- 总资产和总负债左右分列 -->
            <div class="grid grid-cols-2 gap-6 py-4 border-b border-gray-100">
              <div>
                <p class="text-gray-400 text-xs mb-1">总资产</p>
                <p class="text-xl font-bold text-gray-800">
                  ¥{{ totalAssets.toLocaleString() }}
                </p>
                <p class="text-gray-400 text-xs mt-1">占比 100%</p>
              </div>
              <div>
                <p class="text-gray-400 text-xs mb-1">总负债</p>
                <p class="text-xl font-bold text-gray-800">¥{{ totalLiabilities.toLocaleString() }}</p>
                <p class="text-gray-400 text-xs mt-1">占比 0%</p>
              </div>
            </div>

            <!-- 总盈亏和本月变化 -->
            <div class="grid grid-cols-2 gap-4 pt-4">
              <div>
                <p class="text-gray-400 text-xs mb-1">总盈亏</p>
                <p
                  :class="[
                    'text-lg font-bold',
                    totalPnl >= 0 ? 'text-red-500' : 'text-green-500'
                  ]"
                >
                  {{ totalPnl >= 0 ? "+" : "" }}¥{{ totalPnl.toLocaleString() }}
                </p>
              </div>
              <div>
                <p class="text-gray-400 text-xs mb-1">本月资产变化</p>
                <p class="text-lg font-bold text-red-500">+¥28,973.83</p>
                <p class="text-xs text-gray-400 mt-1">较上月 +1.9%</p>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

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

    <!-- 桑基图：资产构成流向 -->
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
import { ref, computed, onMounted, onActivated, nextTick } from "vue";
import { Search } from "@element-plus/icons-vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import SankeyChart from "@/components/Charts/SankeyChart.vue";
import { getPositions } from "@/api/positions";
import { getSummary } from "@/api/summary";
import { getAssets } from '@/api/assets'
import { ElMessage } from "element-plus";
import * as echarts from "echarts";

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
  const nodeMap = new Map<string, any>()
  function addNode(name: string, extra?: any) {
    if (!nodeMap.has(name)) {
      nodeMap.set(name, { name, ...extra })
    }
    return nodeMap.get(name)!
  }

  const links: any[] = []
  const categoryColors: Record<string, string> = {
    '流动资产': '#3b82f6',
    '固定资产': '#8b5cf6',
    '投资理财': '#f59e0b',
    '应收款': '#10b981',
    '保险': '#ef4444',
    '负债': '#6b7280'
  }

  addNode('总资产', { itemStyle: { color: '#6366f1' } })

  // 投资理财大类 (来自 positions)
  const investmentItems: any[] = []
  allPositions.value.forEach(p => {
    const name = p.name || p.symbol
    addNode(name)
    investmentItems.push({ name, value: p.marketValue })
  })

  // 其他大类 (来自 assets)
  const assetCategories: Record<string, any[]> = {
    '流动资产': [],
    '固定资产': [],
    '应收款': [],
    '保险': [],
    '负债': []
  }

  allAssets.value.forEach(a => {
    const name = a.name
    addNode(name)
    const item = { name, value: a.marketValue }
    switch (a.major_category) {
      case 'cash': assetCategories['流动资产'].push(item); break
      case 'fixed': assetCategories['固定资产'].push(item); break
      case 'receivable': assetCategories['应收款'].push(item); break
      case 'insurance': assetCategories['保险'].push(item); break
      case 'liability': assetCategories['负债'].push(item); break
    }
  })

  for (const [cat, items] of Object.entries(assetCategories)) {
    if (items.length === 0) continue
    addNode(cat, { itemStyle: { color: categoryColors[cat] } })
    const catTotal = items.reduce((s, it) => s + it.value, 0)
    if (catTotal > 0) links.push({ source: '总资产', target: cat, value: catTotal })
    items.forEach(it => links.push({ source: cat, target: it.name, value: it.value }))
  }

  if (investmentItems.length > 0) {
    addNode('投资理财', { itemStyle: { color: categoryColors['投资理财'] } })
    const investTotal = investmentItems.reduce((s, it) => s + it.value, 0)
    links.push({ source: '总资产', target: '投资理财', value: investTotal })
    investmentItems.forEach(it => links.push({ source: '投资理财', target: it.name, value: it.value }))
  }

  return { nodes: Array.from(nodeMap.values()), links }
})


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
