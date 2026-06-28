<template>
  <div
    class="panorama p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 页面标题 -->
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2
          class="text-2xl font-bold"
          :style="{ color: 'var(--text-primary)' }"
        >
          资产总览
        </h2>
        <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary)' }">
          多维度审视你的财富版图
        </p>
      </div>
      <el-button :loading="loading" @click="fetchData">
        <IconifyIconOffline icon="ep:refresh" class="mr-1" /> 刷新
      </el-button>
    </div>

    <!-- 总览大卡片 -->
    <el-row :gutter="16" class="mb-6">
      <el-col :xs="24" :md="12" class="mb-4 md:mb-0">
        <div
          class="summary-card rounded-2xl p-6 h-full"
          :style="{
            backgroundColor: 'var(--bg-card)',
            boxShadow: 'var(--shadow-raised)',
            border: '1px solid var(--border-light)'
          }"
        >
          <div class="flex flex-col justify-between h-full">
            <div>
              <p
                class="text-sm mb-2"
                :style="{ color: 'var(--text-tertiary)' }"
              >
                总资产（本月）
              </p>
              <MoneyDisplay
                :value="totalAssets"
                size="hero"
                :show-sign="false"
                :show-currency="true"
              />
              <div class="flex items-center gap-4 mt-3">
                <RiseFallText :value="12.3" suffix="%" size="sm" />
                <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }"
                  >较上月</span
                >
                <RiseFallText :value="8.7" suffix="%" size="sm" />
                <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }"
                  >较去年同期</span
                >
              </div>
              <div class="mt-4 flex items-center gap-2">
                <span
                  class="px-2 py-0.5 rounded-full text-xs font-medium"
                  :style="{
                    backgroundColor: 'var(--color-warning)',
                    color: 'var(--bg-card)'
                  }"
                >
                  中等风险
                </span>
                <span
                  class="text-xs"
                  :style="{ color: 'var(--text-tertiary)' }"
                >
                  风险评分：65/100
                </span>
              </div>
            </div>
            <div
              class="my-5"
              :style="{ borderTop: '1px solid var(--border-light)' }"
            />
            <div class="grid grid-cols-3 gap-4">
              <div>
                <p
                  class="text-xs mb-1"
                  :style="{ color: 'var(--text-tertiary)' }"
                >
                  总负债
                </p>
                <MoneyDisplay
                  :value="totalLiabilities"
                  size="md"
                  :show-sign="false"
                  :show-currency="true"
                />
              </div>
              <div>
                <p
                  class="text-xs mb-1"
                  :style="{ color: 'var(--text-tertiary)' }"
                >
                  净资产
                </p>
                <MoneyDisplay
                  :value="totalAssets - totalLiabilities"
                  size="md"
                  :show-sign="false"
                  :show-currency="true"
                />
              </div>
              <div>
                <p
                  class="text-xs mb-1"
                  :style="{ color: 'var(--text-tertiary)' }"
                >
                  总盈亏
                </p>
                <MoneyDisplay
                  :value="totalPnl"
                  size="md"
                  :show-currency="true"
                />
              </div>
            </div>
          </div>
        </div>
      </el-col>

      <el-col :xs="24" :md="12">
        <div
          class="rounded-2xl p-6 h-full"
          :style="{
            backgroundColor: 'var(--bg-card)',
            boxShadow: 'var(--shadow-raised)',
            border: '1px solid var(--border-light)'
          }"
        >
          <div class="flex justify-between items-center mb-4">
            <h3 class="font-semibold" :style="{ color: 'var(--text-primary)' }">
              总资产变化
            </h3>
            <el-tooltip content="资产月历（后续版本推出）" placement="top">
              <el-button text size="small">
                <IconifyIconOffline icon="ep:calendar" class="text-base" />
              </el-button>
            </el-tooltip>
          </div>
          <div ref="waterfallChartRef" class="h-[280px]" />
        </div>
      </el-col>
    </el-row>

    <!-- 桑基图 -->
    <div
      class="rounded-2xl p-6 mb-4"
      :style="{
        backgroundColor: 'var(--bg-card)',
        boxShadow: 'var(--shadow-raised)',
        border: '1px solid var(--border-light)'
      }"
    >
      <div class="flex items-center justify-between mb-4">
        <h3 class="font-semibold" :style="{ color: 'var(--text-primary)' }">
          资产构成流向
        </h3>
        <el-segmented
          v-model="sankeyDisplayMode"
          :options="sankeyDisplayOptions"
          size="small"
        />
      </div>
      <SankeyChart :data="sankeyData" :display-mode="sankeyDisplayMode" />
    </div>

    <!-- 多维视图表格 -->
    <div
      class="rounded-2xl p-6"
      :style="{
        backgroundColor: 'var(--bg-card)',
        boxShadow: 'var(--shadow-raised)',
        border: '1px solid var(--border-light)'
      }"
    >
      <div class="flex items-center justify-between mb-5">
        <el-segmented v-model="detailView" :options="detailViewOptions" />
        <el-button
          v-if="detailView === 'account'"
          text
          size="small"
          @click="$router.push('/asset/ledgers')"
        >
          管理账户
        </el-button>
      </div>

      <!-- 按资产大类 -->
      <div v-if="detailView === 'category'">
        <div class="flex justify-between items-center mb-6">
          <div class="balance-switch">
            <button
              class="balance-btn"
              :class="{ active: balanceTab === 'assets' }"
              @click="balanceTab = 'assets'"
            >
              资产端
            </button>
            <button
              class="balance-btn"
              :class="{ active: balanceTab === 'liabilities' }"
              @click="balanceTab = 'liabilities'"
            >
              负债端
            </button>
          </div>
          <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
            {{ balanceTab === "assets" ? "资产构成" : "负债明细" }}
          </span>
        </div>

        <table v-if="balanceTab === 'assets'" class="w-full text-sm">
          <thead
            class="text-left text-xs border-b"
            :style="{
              color: 'var(--text-tertiary)',
              borderColor: 'var(--border-light)'
            }"
          >
            <tr>
              <th class="py-3 pl-4 font-normal">资产大类</th>
              <th class="py-3 font-normal text-right w-24">占比</th>
              <th class="py-3 pr-4 font-normal text-right w-36">价值</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in assetBalanceRows"
              :key="item.name"
              class="border-b cursor-pointer transition-colors"
              :style="{ borderColor: 'var(--border-light)' }"
              @click="goToInventory(item.categoryKey)"
            >
              <td class="py-3 pl-4 flex items-center gap-3">
                <span
                  class="w-2.5 h-2.5 rounded-full shrink-0"
                  :style="{ backgroundColor: item.color }"
                />
                <span
                  class="font-medium"
                  :style="{ color: 'var(--text-primary)' }"
                >
                  {{ item.name }}
                </span>
              </td>
              <td
                class="py-3 text-right"
                :style="{ color: 'var(--text-secondary)' }"
              >
                <div class="flex items-center justify-end gap-2">
                  <div
                    class="h-1.5 w-16 rounded-full overflow-hidden"
                    :style="{ backgroundColor: 'var(--bg-soft)' }"
                  >
                    <div
                      class="h-full rounded-full"
                      :style="{
                        backgroundColor: item.color,
                        width: item.percent + '%'
                      }"
                    />
                  </div>
                  <span>{{ item.percent }}%</span>
                </div>
              </td>
              <td class="py-3 text-right pr-4">
                <MoneyDisplay
                  :value="item.value"
                  size="sm"
                  :show-sign="false"
                  :show-currency="true"
                />
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr :style="{ borderTop: '2px solid var(--border-light)' }">
              <td
                class="py-3 pl-4 font-medium"
                :style="{ color: 'var(--text-primary)' }"
              >
                合计
              </td>
              <td
                class="py-3 text-right"
                :style="{ color: 'var(--text-secondary)' }"
              >
                100%
              </td>
              <td class="py-3 text-right pr-4">
                <MoneyDisplay
                  :value="totalAssets"
                  size="sm"
                  :show-sign="false"
                  :show-currency="true"
                />
              </td>
            </tr>
          </tfoot>
        </table>

        <table v-else class="w-full text-sm">
          <thead
            class="text-left text-xs border-b"
            :style="{
              color: 'var(--text-tertiary)',
              borderColor: 'var(--border-light)'
            }"
          >
            <tr>
              <th class="py-3 pl-4 font-normal">负债项目</th>
              <th class="py-3 font-normal text-right w-24">占比</th>
              <th class="py-3 pr-4 font-normal text-right w-36">金额</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in liabilityBalanceRows"
              :key="item.name"
              class="border-b cursor-pointer transition-colors"
              :style="{ borderColor: 'var(--border-light)' }"
              @click="goToInventory('liability')"
            >
              <td class="py-3 pl-4 flex items-center gap-3">
                <span
                  class="w-2.5 h-2.5 rounded-full shrink-0"
                  :style="{ backgroundColor: item.color }"
                />
                <span
                  class="font-medium"
                  :style="{ color: 'var(--text-primary)' }"
                >
                  {{ item.name }}
                </span>
              </td>
              <td
                class="py-3 text-right"
                :style="{ color: 'var(--text-secondary)' }"
              >
                <div class="flex items-center justify-end gap-2">
                  <div
                    class="h-1.5 w-16 rounded-full overflow-hidden"
                    :style="{ backgroundColor: 'var(--bg-soft)' }"
                  >
                    <div
                      class="h-full rounded-full"
                      :style="{
                        backgroundColor: 'var(--color-neutral)',
                        width: item.percent + '%'
                      }"
                    />
                  </div>
                  <span>{{ item.percent }}%</span>
                </div>
              </td>
              <td class="py-3 text-right pr-4">
                <MoneyDisplay
                  :value="item.value"
                  size="sm"
                  :show-sign="false"
                  :show-currency="true"
                />
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr :style="{ borderTop: '2px solid var(--border-light)' }">
              <td
                class="py-3 pl-4 font-medium"
                :style="{ color: 'var(--text-primary)' }"
              >
                合计
              </td>
              <td
                class="py-3 text-right"
                :style="{ color: 'var(--text-secondary)' }"
              >
                100%
              </td>
              <td class="py-3 text-right pr-4">
                <MoneyDisplay
                  :value="totalLiabilities"
                  size="sm"
                  :show-sign="false"
                  :show-currency="true"
                />
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <!-- 按产品类型 / 账户 / 配置目标 -->
      <div v-else class="space-y-3">
        <div
          v-for="group in currentDetailGroups"
          :key="group.name"
          class="border rounded-xl overflow-hidden cursor-pointer transition-shadow hover:shadow-sm"
          :style="{ borderColor: 'var(--border-default)' }"
          @click="handleGroupClick(group)"
        >
          <div
            class="px-5 py-3 flex justify-between items-center font-medium"
            :style="{ backgroundColor: 'var(--bg-soft)' }"
          >
            <span :style="{ color: 'var(--text-primary)' }">{{
              group.name
            }}</span>
            <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              {{ group.items.length }} 项
            </span>
          </div>
          <div class="px-5 py-3 flex justify-between items-center text-sm">
            <div>
              <MoneyDisplay
                :value="group.total"
                size="sm"
                :show-sign="false"
                :show-currency="true"
              />
              <span
                class="ml-2 text-xs"
                :style="{ color: 'var(--text-tertiary)' }"
              >
                占
                {{ ((Math.abs(group.total) / totalAssets) * 100).toFixed(1) }}%
              </span>
            </div>
            <MoneyDisplay
              :value="group.totalPnl"
              size="sm"
              :show-currency="true"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import { IconifyIconOffline } from "@/components/ReIcon";
import SankeyChart from "@/components/Charts/SankeyChart.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import { getPositions } from "@/api/positions";
import { getSummary, getSankeyData } from "@/api/summary";
import { getAssets } from "@/api/assets";
import { getLedgers } from "@/api/ledger";
import { ElMessage } from "element-plus";
import * as echarts from "echarts";
import { getAllocationLabel } from "@/constants";

defineOptions({ name: "AssetPanorama" });

const EXCHANGE_RATES: Record<string, number> = { CNY: 1, USD: 7.25, HKD: 0.92 };

const allPositions = ref<any[]>([]);
const allAssets = ref<any[]>([]);
const ledgers = ref<any[]>([]);
const totalAssets = ref(0);
const totalLiabilities = ref(0);
const totalPnl = ref(0);
const sankeyData = ref<{ nodes: any[]; links: any[] }>({
  nodes: [],
  links: []
});
const loading = ref(false);

const sankeyDisplayMode = ref<"amount" | "percent" | "hidden">("amount");
const balanceTab = ref<"assets" | "liabilities">("assets");
const detailView = ref("category");
const waterfallChartRef = ref<HTMLDivElement>();
let waterfallChart: echarts.ECharts | null = null;

const router = useRouter();

const sankeyDisplayOptions = [
  { label: "金额", value: "amount" },
  { label: "比例", value: "percent" },
  { label: "隐藏金额", value: "hidden" }
];

const detailViewOptions = [
  { label: "资产大类", value: "category" },
  { label: "产品类型", value: "type" },
  { label: "账户", value: "account" },
  { label: "配置目标", value: "allocation" }
];

// 工具函数：安全读取 CSS 变量（无 fallback 硬编码）
const getCSSColor = (varName: string): string => {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement)
    .getPropertyValue(varName)
    .trim();
};

function getTypeRoute(typeName: string): string {
  const routes: Record<string, string> = {
    股票: "stocks",
    基金: "funds",
    可转债: "stocks",
    ETF: "stocks",
    虚拟货币: "precious",
    银行存款: "funds"
  };
  return routes[typeName] || "stocks";
}

function handleGroupClick(group: any) {
  if (detailView.value === "type") {
    router.push(`/asset/investment/${getTypeRoute(group.name)}`);
  } else if (detailView.value === "account") {
    router.push("/asset/ledgers");
  }
}

const currentDetailGroups = computed(() => {
  switch (detailView.value) {
    case "type":
      return typeDetailGroups.value;
    case "account":
      return accountDetailGroups.value;
    case "allocation":
      return allocationDetailGroups.value;
    default:
      return [];
  }
});

const assetBalanceRows = computed(() => {
  const total = totalAssets.value;
  if (total === 0) return [];
  const categoryMap: Record<string, any> = {
    cash: {
      name: "流动资金",
      value: 0,
      color: "var(--tag-mint-green)",
      categoryKey: "cash"
    },
    fixed: {
      name: "固定资产",
      value: 0,
      color: "var(--tag-warm-taupe)",
      categoryKey: "fixed"
    },
    investment: {
      name: "投资理财",
      value: 0,
      color: "var(--tag-periwinkle)",
      categoryKey: "investment"
    },
    receivable: {
      name: "应收款",
      value: 0,
      color: "var(--tag-stone-gray)",
      categoryKey: "receivable"
    },
    insurance: {
      name: "保险项目",
      value: 0,
      color: "var(--color-accent)",
      categoryKey: "insurance"
    }
  };
  allAssets.value
    .filter(a => a.major_category !== "liability" && a.marketValue > 0)
    .forEach(a => {
      if (categoryMap[a.major_category])
        categoryMap[a.major_category].value += a.marketValue;
    });
  const positionsTotal = allPositions.value.reduce(
    (s, p) => s + (p.marketValue || 0),
    0
  );
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
  const map: Record<string, any> = {};
  allAssets.value
    .filter(a => a.major_category === "liability" && a.marketValue < 0)
    .forEach(a => {
      const key = a.name || "其他负债";
      if (!map[key]) map[key] = { name: key, value: 0 };
      map[key].value += a.marketValue;
    });
  return Object.values(map).map(item => ({
    ...item,
    color: "var(--color-neutral)",
    percent: +((Math.abs(item.value) / totalLiab) * 100).toFixed(1),
    value: Math.abs(item.value)
  }));
});

const typeDetailGroups = computed(() => {
  const map: Record<string, { items: any[]; total: number; totalPnl: number }> =
    {};
  allPositions.value.forEach((p: any) => {
    const type = p.type_label || p.asset_type || p.type || "其他";
    if (!map[type]) map[type] = { items: [], total: 0, totalPnl: 0 };
    map[type].items.push(p);
    map[type].total += p.marketValue || 0;
    map[type].totalPnl += p.pnl || 0;
  });
  return Object.entries(map).map(([name, data]) => ({
    name,
    items: data.items,
    total: data.total,
    totalPnl: data.totalPnl
  }));
});

const accountDetailGroups = computed(() => {
  const map: Record<string, { items: any[]; total: number; totalPnl: number }> =
    {};
  allPositions.value.forEach((p: any) => {
    const acc = p.account_name || "未指定账户";
    if (!map[acc]) map[acc] = { items: [], total: 0, totalPnl: 0 };
    map[acc].items.push({
      ...p,
      type_label: p.type_label || p.asset_type || p.type
    });
    map[acc].total += p.marketValue || 0;
    map[acc].totalPnl += p.pnl || 0;
  });
  allAssets.value.forEach((a: any) => {
    const acc = a.account_name || "未指定账户";
    if (!map[acc]) map[acc] = { items: [], total: 0, totalPnl: 0 };
    const value = a.marketValue || a.amount || 0;
    map[acc].items.push({
      ...a,
      marketValue: value,
      type_label: a.minor_category || a.major_category,
      asset_type: a.major_category
    });
    map[acc].total += value;
  });
  return Object.entries(map).map(([name, data]) => ({
    name,
    items: data.items,
    total: data.total,
    totalPnl: data.totalPnl
  }));
});

const allocationDetailGroups = computed(() => {
  const map: Record<string, { items: any[]; total: number; totalPnl: number }> =
    {};
  allPositions.value.forEach((p: any) => {
    const alloc =
      p.allocation_label || getAllocationLabel(p.allocation) || "未配置";
    if (!map[alloc]) map[alloc] = { items: [], total: 0, totalPnl: 0 };
    map[alloc].items.push({
      ...p,
      type_label: p.type_label || p.asset_type || p.type
    });
    map[alloc].total += p.marketValue || 0;
    map[alloc].totalPnl += p.pnl || 0;
  });
  return Object.entries(map).map(([name, data]) => ({
    name,
    items: data.items,
    total: data.total,
    totalPnl: data.totalPnl
  }));
});

function goToInventory(categoryKey: string) {
  router.push(`/asset/inventory?tab=${categoryKey}`);
}

function initWaterfallChart() {
  if (!waterfallChartRef.value || allPositions.value.length === 0) return;
  if (waterfallChart) waterfallChart.dispose();
  waterfallChart = echarts.init(waterfallChartRef.value);

  const primaryColor = getCSSColor("--brand-700");
  const infoColor = getCSSColor("--color-info");
  const riseColor = getCSSColor("--color-rise");
  const fallColor = getCSSColor("--color-fall");
  const neutralColor = getCSSColor("--color-neutral");

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

  waterfallChart.setOption({
    tooltip: { trigger: "axis" },
    grid: { left: "8%", right: "4%", top: 20, bottom: 50, containLabel: true },
    xAxis: {
      type: "category",
      data: allData.map(d => d.name),
      axisLabel: {
        rotate: 30,
        fontSize: 10,
        color: getCSSColor("--text-tertiary")
      },
      axisLine: { lineStyle: { color: getCSSColor("--border-light") } }
    },
    yAxis: {
      type: "value",
      min: 0,
      splitLine: { lineStyle: { color: getCSSColor("--border-light") } },
      axisLabel: {
        color: getCSSColor("--text-tertiary"),
        fontSize: 11,
        formatter: (v: number) => v.toLocaleString()
      }
    },
    series: [
      {
        type: "bar",
        data: allData.map(d => d.height),
        barWidth: "30%",
        barMinHeight: 4,
        itemStyle: {
          borderRadius: 4,
          color: (params: any) => {
            const d = allData[params.dataIndex];
            if (d.isEndpoint && d.name === "上期末") return primaryColor;
            if (d.isEndpoint && d.name === "本期末") return infoColor;
            if (d.change > 0) return riseColor;
            if (d.change < 0) return fallColor;
            return neutralColor;
          }
        },
        label: {
          show: true,
          position: "top",
          fontSize: 10,
          color: getCSSColor("--text-secondary"),
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

async function fetchData() {
  loading.value = true;
  try {
    const [posRes, sumRes, assetsRes, sankeyRes, ledgerRes] = await Promise.all(
      [
        getPositions({ per_page: 500 }),
        getSummary(),
        getAssets({ per_page: 500 }),
        getSankeyData(),
        getLedgers()
      ]
    );

    let positionsRaw: any[] = [];
    const posData = (posRes as any)?.data || posRes;
    positionsRaw = Array.isArray(posData) ? posData : posData?.data || [];

    let assetsRaw: any[] = [];
    const assetData = (assetsRes as any)?.data || assetsRes;
    assetsRaw = Array.isArray(assetData) ? assetData : assetData?.data || [];

    let sankeyRaw: any = {};
    const sankData = (sankeyRes as any)?.data;
    sankeyRaw = sankData && typeof sankData === "object" ? sankData : {};

    const ledgerData = (ledgerRes as any)?.data || ledgerRes;
    ledgers.value = Array.isArray(ledgerData)
      ? ledgerData
      : ledgerData?.data || [];

    allPositions.value = positionsRaw.map((p: any) => {
      const rate = EXCHANGE_RATES[p.currency || "CNY"] || 1;
      const marketValue = (p.quantity || 0) * (p.current_price || 0) * rate;
      const pnl =
        ((p.current_price || 0) - (p.avg_price || 0)) *
        (p.quantity || 0) *
        rate;
      return { ...p, marketValue, pnl };
    });

    allAssets.value = assetsRaw.map((a: any) => ({
      ...a,
      marketValue: a.signed_amount ?? (a.amount || 0)
    }));

    totalAssets.value = (sumRes as any)?.data?.total_assets_cny || 0;
    totalLiabilities.value = (sumRes as any)?.data?.total_liabilities_cny || 0;
    totalPnl.value = (sumRes as any)?.data?.total_pnl_cny || 0;
    sankeyData.value = {
      nodes: sankeyRaw.nodes || [],
      links: sankeyRaw.links || []
    };
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
    await nextTick();
    initWaterfallChart();
  }
}

onMounted(() => {
  fetchData();
});
</script>

<style scoped>
.balance-switch {
  display: flex;
  gap: 4px;
}
.balance-btn {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  font-size: 14px;
  padding: 4px 14px;
  cursor: pointer;
  border-radius: 4px;
  transition: color 0.2s;
  position: relative;
  font-weight: 400;
}
.balance-btn.active {
  font-weight: 600;
  color: var(--text-primary);
}
.balance-btn.active::after {
  content: "";
  position: absolute;
  bottom: 0;
  left: 8px;
  right: 8px;
  height: 2px;
  background: var(--brand-700);
  border-radius: 1px;
}
.summary-card {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.summary-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-float);
}

/* 胶囊形状：el-tag */
:deep(.el-tag) {
  border-radius: 9999px;
}

/* 胶囊形状：el-segmented */
:deep(.el-segmented) {
  border-radius: 9999px;
}
:deep(.el-segmented .el-segmented__item) {
  border-radius: 9999px;
}

/* 胶囊形状：资产端/负债端切换按钮 */
.balance-btn {
  border-radius: 9999px;
}
</style>
