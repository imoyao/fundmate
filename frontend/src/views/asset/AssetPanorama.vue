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
              总资产构成
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
import { ref, computed, onMounted, nextTick, watch } from "vue";
import { useRouter } from "vue-router";
import { IconifyIconOffline } from "@/components/ReIcon";
import SankeyChart from "@/components/Charts/SankeyChart.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import {
  getSummary,
  getSankeyData,
  getDistributions,
  getPositionGroups,
  type GroupDimension
} from "@/api/summary";
import { getLedgers } from "@/api/ledger";
import { ElMessage } from "element-plus";
import echarts from "@/plugins/echarts";

defineOptions({ name: "AssetPanorama" });

const distributions = ref<any>(null);
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
const detailGroups = ref<any[]>([]);
const detailGroupsLoading = ref(false);
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

// 后端分组数据（detailView 切换时按需拉取，字段后端为 snake_case）
const currentDetailGroups = computed(() =>
  detailGroups.value.map(g => ({
    name: g.name,
    total: g.total,
    totalPnl: g.total_pnl,
    items: g.items
  }))
);

async function loadDetailGroups() {
  const dim = detailView.value;
  if (dim === "category") return;
  detailGroupsLoading.value = true;
  try {
    const res = await getPositionGroups(dim as GroupDimension);
    const raw = (res as any)?.data;
    detailGroups.value = Array.isArray(raw) ? raw : raw?.data || [];
  } catch (e: any) {
    detailGroups.value = [];
    ElMessage.error(e?.message || "分组加载失败");
  } finally {
    detailGroupsLoading.value = false;
  }
}

watch(detailView, loadDetailGroups);

const assetBalanceRows = computed(() => {
  const total = totalAssets.value;
  if (total === 0) return [];
  const labelMap: Record<string, { color: string; categoryKey: string }> = {
    流动资金: { color: "var(--tag-mint-green)", categoryKey: "cash" },
    固定资产: { color: "var(--tag-warm-taupe)", categoryKey: "fixed" },
    投资理财: { color: "var(--tag-periwinkle)", categoryKey: "investment" },
    应收款: { color: "var(--tag-stone-gray)", categoryKey: "receivable" },
    保险项目: { color: "var(--color-accent)", categoryKey: "insurance" }
  };
  // 消费后端 category_distribution（后端唯一聚合出口，含汇率换算）
  const categoryMap: Record<string, any> = {};
  for (const item of distributions.value?.category_distribution ?? []) {
    categoryMap[item.name] = {
      name: item.name,
      value: item.value,
      ...(labelMap[item.name] || {
        color: "var(--text-tertiary)",
        categoryKey: item.name
      })
    };
  }
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
  // 消费后端 liability_distribution（正数金额，负债明细按名称聚合）
  return (distributions.value?.liability_distribution ?? []).map(item => ({
    name: item.name,
    value: item.value,
    color: "var(--color-neutral)",
    percent: +((item.value / totalLiab) * 100).toFixed(1)
  }));
});

function goToInventory(categoryKey: string) {
  router.push(`/asset/inventory?tab=${categoryKey}`);
}

function initWaterfallChart() {
  if (!waterfallChartRef.value) return;
  if (waterfallChart) waterfallChart.dispose();
  waterfallChart = echarts.init(waterfallChartRef.value);

  // 消费后端 distributions：总资产构成瀑布（真实数据，非模拟）
  const categories = distributions.value?.category_distribution ?? [];
  const totalLiab = distributions.value?.total_liabilities ?? 0;
  const netWorth = distributions.value?.net_worth ?? 0;
  if (categories.length === 0 && totalLiab <= 0) return;

  const primaryColor = getCSSColor("--brand-700");
  const infoColor = getCSSColor("--color-info");
  const riseColor = getCSSColor("--color-rise");
  const fallColor = getCSSColor("--color-fall");
  const neutralColor = getCSSColor("--color-neutral");

  const start = 0;
  const changes = [
    ...categories.map(c => ({ name: c.name, value: c.value })),
    ...(totalLiab > 0 ? [{ name: "负债", value: -totalLiab }] : [])
  ];
  const end = netWorth;
  const cumulativeValues: number[] = [start];
  changes.forEach((item, index) => {
    cumulativeValues.push(cumulativeValues[index] + item.value);
  });
  const allData = [
    { name: "起点", height: start, change: start, isEndpoint: true },
    ...changes.map((item, index) => ({
      name: item.name,
      height: cumulativeValues[index + 1],
      change: item.value,
      isEndpoint: false
    })),
    { name: "净资产", height: end, change: end, isEndpoint: true }
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
            if (d.isEndpoint && d.name === "起点") return primaryColor;
            if (d.isEndpoint && d.name === "净资产") return infoColor;
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
    const [sumRes, sankeyRes, ledgerRes, distRes] = await Promise.all([
      getSummary(),
      getSankeyData(),
      getLedgers(),
      getDistributions()
    ]);

    let sankeyRaw: any = {};
    const sankData = (sankeyRes as any)?.data;
    sankeyRaw = sankData && typeof sankData === "object" ? sankData : {};

    const ledgerData = (ledgerRes as any)?.data || ledgerRes;
    ledgers.value = Array.isArray(ledgerData)
      ? ledgerData
      : ledgerData?.data || [];

    totalAssets.value = (sumRes as any)?.data?.total_assets_cny || 0;
    totalLiabilities.value = (sumRes as any)?.data?.total_liabilities_cny || 0;
    totalPnl.value = (sumRes as any)?.data?.total_pnl_cny || 0;
    distributions.value = (distRes as any)?.data || null;
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
  position: relative;
  padding: 4px 14px;
  font-size: 14px;
  font-weight: 400;
  color: var(--text-tertiary);
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: 4px;
  transition: color 0.2s;
}

.balance-btn.active {
  font-weight: 600;
  color: var(--text-primary);
}

.balance-btn.active::after {
  position: absolute;
  right: 8px;
  bottom: 0;
  left: 8px;
  height: 2px;
  content: "";
  background: var(--brand-700);
  border-radius: 1px;
}

.summary-card {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.summary-card:hover {
  box-shadow: var(--shadow-float);
  transform: translateY(-3px);
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
