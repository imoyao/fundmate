<template>
  <div class="panorama p-4 md:p-6 bg-[#f5f7fa] min-h-full">
    <!-- 页面标题 -->
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2 class="text-2xl font-bold text-[var(--text-primary)]">资产总览</h2>
        <p class="text-[var(--text-tertiary)] text-sm mt-1">多维度审视你的财富版图</p>
      </div>
      <el-button :loading="loading" @click="fetchData">
        <IconifyIconOffline icon="ep:refresh" class="mr-1" /> 刷新
      </el-button>
    </div>

    <!-- 总览大卡片 -->
    <el-row :gutter="16" class="mb-6">
      <el-col :xs="24" :md="12" class="mb-4 md:mb-0">
        <el-card shadow="never" class="summary-large-card">
          <div class="flex flex-col justify-between h-full">
            <div>
              <p class="text-[var(--text-tertiary)] text-sm mb-1">总资产（本月）</p>
              <h2 class="text-5xl font-bold text-[var(--color-primary)] tracking-tight">
                ¥{{ totalAssets.toLocaleString() }}
              </h2>
              <div class="flex items-center gap-4 mt-2">
                <span class="text-[var(--color-success)] text-sm font-medium flex items-center">
                  <IconifyIconOffline icon="ep:arrow-up-bold" class="mr-1" />
                  12.3% <span class="text-[var(--text-tertiary)] ml-1 font-normal">较上月</span>
                </span>
                <span class="text-[var(--color-success)] text-sm font-medium flex items-center">
                  <IconifyIconOffline icon="ep:arrow-up-bold" class="mr-1" />
                  8.7% <span class="text-[var(--text-tertiary)] ml-1 font-normal">较去年同期</span>
                </span>
              </div>
              <div class="mt-3 flex items-center gap-2">
                <span class="px-2 py-0.5 text-[var(--color-warning)] rounded-full text-xs font-medium"
                  style="background-color: var(--color-warning-20)">
                  中等风险
                </span>
                <span class="text-xs text-[var(--text-tertiary)]">风险评分：65/100</span>
              </div>
            </div>
            <div class="border-t border-[var(--divider-default)] my-5"></div>
            <div class="grid grid-cols-3 gap-4">
              <div>
                <p class="text-[var(--text-tertiary)] text-xs mb-1">总负债</p>
                <p class="text-lg font-bold text-[var(--text-primary)]">¥{{ totalLiabilities.toLocaleString() }}</p>
              </div>
              <div>
                <p class="text-[var(--text-tertiary)] text-xs mb-1">净资产</p>
                <p class="text-lg font-bold text-[var(--color-success)]">¥{{ (totalAssets - totalLiabilities).toLocaleString() }}</p>
              </div>
              <div>
                <p class="text-[var(--text-tertiary)] text-xs mb-1">总盈亏</p>
                <p :class="['text-lg font-bold', totalPnl >= 0 ? 'text-[var(--color-danger)]' : 'text-[var(--color-success)]']">
                  {{ totalPnl >= 0 ? "+" : "" }}¥{{ totalPnl.toLocaleString() }}
                </p>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="h-full">
          <div class="flex justify-between items-center mb-4">
            <h3 class="font-semibold text-[var(--text-primary)]">总资产变化</h3>
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

    <!-- 桑基图 -->
    <el-card shadow="never" class="mb-4">
      <div class="flex items-center justify-between mb-4">
        <h3 class="font-semibold text-[var(--text-primary)]">资产构成流向</h3>
        <el-segmented v-model="sankeyDisplayMode" :options="sankeyDisplayOptions" size="small" class="sub-segmented" />
      </div>
      <SankeyChart :data="sankeyData" :display-mode="sankeyDisplayMode" />
    </el-card>

    <!-- 多维视图切换表格 -->
    <el-card shadow="never">
      <div class="flex items-center justify-between mb-5">
        <el-segmented v-model="detailView" :options="detailViewOptions" />
        <el-button v-if="detailView === 'account'" text size="small" @click="$router.push('/asset/ledgers')">
          管理账户
        </el-button>
      </div>

      <!-- 按资产大类 -->
      <div v-if="detailView === 'category'">
        <div class="flex justify-between items-center mb-6">
          <div class="balance-switch">
            <button class="balance-btn" :class="{ active: balanceTab === 'assets' }" @click="balanceTab = 'assets'">
              资产端
            </button>
            <button class="balance-btn" :class="{ active: balanceTab === 'liabilities' }" @click="balanceTab = 'liabilities'">
              负债端
            </button>
          </div>
          <span class="text-xs text-[var(--text-tertiary)]">
            {{ balanceTab === 'assets' ? '资产构成' : '负债明细' }}
          </span>
        </div>

        <table v-if="balanceTab === 'assets'" class="w-full text-sm">
          <thead class="text-[var(--text-tertiary)] border-b border-[var(--divider-default)]">
            <tr>
              <th class="text-left py-3 pl-4 font-normal">资产大类</th>
              <th class="text-right py-3 font-normal w-24">占比</th>
              <th class="text-right py-3 pr-4 font-normal w-36">价值</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in assetBalanceRows" :key="item.name" class="border-b border-[var(--divider-default)] cursor-pointer transition-colors" @click="goToInventory(item.categoryKey)">
              <td class="py-3 pl-4 flex items-center gap-3">
                <span class="w-2.5 h-2.5 rounded-full shrink-0" :style="{ backgroundColor: item.color }" />
                <span class="font-medium text-[var(--text-primary)]">{{ item.name }}</span>
              </td>
              <td class="py-3 text-right text-[var(--text-secondary)]">
                <div class="flex items-center justify-end gap-2">
                  <div class="h-1.5 w-16 bg-[var(--bg-muted)] rounded-full overflow-hidden">
                    <div class="h-full bg-primary rounded-full" :style="{ width: item.percent + '%' }" />
                  </div>
                  <span>{{ item.percent }}%</span>
                </div>
              </td>
              <td class="py-3 text-right pr-4 font-semibold text-[var(--text-primary)] tabular-nums">
                ¥{{ item.value.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="border-t-2 border-[var(--divider-default)]">
              <td class="py-3 pl-4 font-medium text-[var(--text-primary)]">合计</td>
              <td class="py-3 text-right text-[var(--text-secondary)]">100%</td>
              <td class="py-3 text-right pr-4 font-bold text-[var(--text-primary)] tabular-nums">
                ¥{{ totalAssets.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}
              </td>
            </tr>
          </tfoot>
        </table>

        <table v-else class="w-full text-sm">
          <thead class="text-[var(--text-tertiary)] border-b border-[var(--divider-default)]">
            <tr>
              <th class="text-left py-3 pl-4 font-normal">负债项目</th>
              <th class="text-right py-3 font-normal w-24">占比</th>
              <th class="text-right py-3 pr-4 font-normal w-36">金额</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in liabilityBalanceRows" :key="item.name" class="border-b border-[var(--divider-default)] cursor-pointer transition-colors" @click="goToInventory('liability')">
              <td class="py-3 pl-4 flex items-center gap-3">
                <span class="w-2.5 h-2.5 rounded-full shrink-0" :style="{ backgroundColor: item.color }" />
                <span class="font-medium text-[var(--text-primary)]">{{ item.name }}</span>
              </td>
              <td class="py-3 text-right text-[var(--text-secondary)]">
                <div class="flex items-center justify-end gap-2">
                  <div class="h-1.5 w-16 bg-[var(--bg-muted)] rounded-full overflow-hidden">
                    <div class="h-full bg-[var(--color-danger)] rounded-full" :style="{ width: item.percent + '%' }" />
                  </div>
                  <span>{{ item.percent }}%</span>
                </div>
              </td>
              <td class="py-3 text-right pr-4 font-semibold text-[var(--text-primary)] tabular-nums">
                ¥{{ item.value.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="border-t-2 border-[var(--divider-default)]">
              <td class="py-3 pl-4 font-medium text-[var(--text-primary)]">合计</td>
              <td class="py-3 text-right text-[var(--text-secondary)]">100%</td>
              <td class="py-3 text-right pr-4 font-bold text-[var(--text-primary)] tabular-nums">
                ¥{{ totalLiabilities.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <!-- 按产品类型 / 账户 / 配置目标 -->
      <div v-else class="space-y-3">
        <div v-for="group in currentDetailGroups" :key="group.name" class="border rounded-xl overflow-hidden cursor-pointer hover:shadow-sm transition-shadow" :style="{ borderColor: 'var(--border-default)' }" @click="handleGroupClick(group)">
          <div class="px-5 py-3 flex justify-between items-center font-medium bg-[var(--bg-muted)]">
            <span :style="{ color: 'var(--text-primary)' }">{{ group.name }}</span>
            <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }">{{ group.items.length }} 项</span>
          </div>
          <div class="px-5 py-2 flex justify-between items-center text-sm">
            <div>
              <span class="font-semibold" :style="{ color: group.total < 0 ? 'var(--color-success)' : 'var(--text-primary)' }">
                {{ group.total < 0 ? '−' : '' }}¥{{ Math.abs(group.total).toLocaleString(undefined, { maximumFractionDigits: 0 }) }}
              </span>
              <span class="ml-2 text-xs" :style="{ color: 'var(--text-tertiary)' }">
                占 {{ (Math.abs(group.total) / totalAssets * 100).toFixed(1) }}%
              </span>
            </div>
            <span :class="group.totalPnl >= 0 ? 'text-[var(--color-danger)]' : 'text-[var(--color-success)]'">
              {{ group.totalPnl >= 0 ? '+' : '' }}¥{{ Math.round(group.totalPnl).toLocaleString() }}
            </span>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import { IconifyIconOffline } from "@/components/ReIcon";
import SankeyChart from "@/components/Charts/SankeyChart.vue";
import { getPositions } from "@/api/positions";
import { getSummary, getSankeyData } from "@/api/summary";
import { getAssets } from "@/api/assets";
import { getLedgers } from "@/api/ledger";
import { ElMessage } from "element-plus";
import * as echarts from "echarts";
import { useEnumOptions } from '@/composables/useEnumOptions'
import { ALLOCATION_OPTIONS, getAllocationLabel } from '@/constants'

defineOptions({ name: "AssetPanorama" });

const EXCHANGE_RATES: Record<string, number> = { CNY: 1, USD: 7.25, HKD: 0.92 };

const allPositions = ref<any[]>([]);
const allAssets = ref<any[]>([]);
const ledgers = ref<any[]>([]);
const totalAssets = ref(0);
const totalLiabilities = ref(0);
const totalPnl = ref(0);
const sankeyData = ref<{ nodes: any[]; links: any[] }>({ nodes: [], links: [] });
const loading = ref(false);

const sankeyDisplayMode = ref<"amount" | "percent" | "hidden">("amount");
const balanceTab = ref<"assets" | "liabilities">("assets");
const detailView = ref("category");
const waterfallChartRef = ref<HTMLDivElement>();
let waterfallChart: echarts.ECharts | null = null;

// 从 CSS 变量提取颜色（在 onMounted 中赋值）
const cssColors = ref<Record<string, string>>({})

const router = useRouter();

const fallbackColors = {
  primary: '#7A7FA8',
  success: '#81B29A',
  danger: '#C83E66',
  info: '#7A9AA8',
  neutral: '#8E8B82',
};

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

function getTypeRoute(typeName: string): string {
  const routes: Record<string, string> = {
    '股票': 'stocks', '基金': 'funds', '可转债': 'stocks',
    'ETF': 'stocks', '虚拟货币': 'precious', '银行存款': 'funds'
  };
  return routes[typeName] || 'stocks';
}

function handleGroupClick(group: any) {
  if (detailView.value === 'type') {
    router.push(`/asset/investment/${getTypeRoute(group.name)}`);
  } else if (detailView.value === 'account') {
    router.push('/asset/ledgers');
  }
}

const currentDetailGroups = computed(() => {
  switch (detailView.value) {
    case 'type': return typeDetailGroups.value;
    case 'account': return accountDetailGroups.value;
    case 'allocation': return allocationDetailGroups.value;
    default: return [];
  }
});

const assetBalanceRows = computed(() => {
  const total = totalAssets.value;
  if (total === 0) return [];
  const categoryMap: Record<string, any> = {
    cash: { name: "流动资金", value: 0, color: "var(--tag-mint-green)", categoryKey: "cash" },
    fixed: { name: "固定资产", value: 0, color: "var(--tag-warm-taupe)", categoryKey: "fixed" },
    investment: { name: "投资理财", value: 0, color: "var(--tag-periwinkle)", categoryKey: "investment" },
    receivable: { name: "应收款", value: 0, color: "var(--tag-stone-gray)", categoryKey: "receivable" },
    insurance: { name: "保险项目", value: 0, color: "var(--color-accent)", categoryKey: "insurance" }
  };
  allAssets.value.filter(a => a.major_category !== "liability" && a.marketValue > 0).forEach(a => {
    if (categoryMap[a.major_category]) categoryMap[a.major_category].value += a.marketValue;
  });
  const positionsTotal = allPositions.value.reduce((s, p) => s + (p.marketValue || 0), 0);
  categoryMap.investment.value += positionsTotal;
  return Object.values(categoryMap).filter(item => item.value > 0).map(item => ({
    ...item,
    percent: +((item.value / total) * 100).toFixed(1)
  }));
});

const liabilityBalanceRows = computed(() => {
  const totalLiab = totalLiabilities.value;
  if (totalLiab === 0) return [];
  const map: Record<string, any> = {};
  allAssets.value.filter(a => a.major_category === "liability" && a.marketValue < 0).forEach(a => {
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
  const map: Record<string, { items: any[]; total: number; totalPnl: number }> = {};
  allPositions.value.forEach((p: any) => {
    const type = p.type_label || p.asset_type || p.type || '其他';
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
  const map: Record<string, { items: any[]; total: number; totalPnl: number }> = {};
  allPositions.value.forEach((p: any) => {
    const acc = p.account_name || '未指定账户';
    if (!map[acc]) map[acc] = { items: [], total: 0, totalPnl: 0 };
    map[acc].items.push({ ...p, type_label: p.type_label|| p.asset_type || p.type });
    map[acc].total += p.marketValue || 0;
    map[acc].totalPnl += p.pnl || 0;
  });
  allAssets.value.forEach((a: any) => {
    const acc = a.account_name || '未指定账户';
    if (!map[acc]) map[acc] = { items: [], total: 0, totalPnl: 0 };
    const value = a.marketValue || a.amount || 0;
    map[acc].items.push({ ...a, marketValue: value, type_label: a.minor_category || a.major_category, asset_type: a.major_category });
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
  const map: Record<string, { items: any[]; total: number; totalPnl: number }> = {};
  allPositions.value.forEach((p: any) => {
    const alloc = p.allocation_label || getAllocationLabel (p.allocation) || '未配置';
    if (!map[alloc]) map[alloc] = { items: [], total: 0, totalPnl: 0 };
    map[alloc].items.push({ ...p, type_label: p.type_label || p.asset_type || p.type });
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
  const primaryColor = cssColors.value['--color-primary'] || fallbackColors.primary
  const infoColor    = cssColors.value['--color-info'] || fallbackColors.info
  const dangerColor  = cssColors.value['--color-danger'] || fallbackColors.danger
  const successColor = cssColors.value['--color-success'] || fallbackColors.success
  const neutralColor = cssColors.value['--color-neutral'] || fallbackColors.neutral

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
      axisLabel: { rotate: 30, fontSize: 10, interval: 0, color: "#999" },
      axisLine: { lineStyle: { color: "#eee" } }
    },
    yAxis: {
      type: "value",
      min: 0,
      splitLine: { lineStyle: { color: "#f5f5f5" } },
      axisLabel: { color: "#999", fontSize: 11, formatter: (v: number) => v.toLocaleString() }
    },
    series: [{
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
          if (d.change > 0) return dangerColor;
          if (d.change < 0) return successColor;
          return neutralColor;
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
    }]
  });
}

async function fetchData() {
  loading.value = true;
  try {
    const [posRes, sumRes, assetsRes, sankeyRes, ledgerRes] = await Promise.all([
      getPositions({ per_page: 500 }),
      getSummary(),
      getAssets({ per_page: 500 }),
      getSankeyData(),
      getLedgers()
    ]);

    let positionsRaw: any[] = [];
    const posData = (posRes as any)?.data || posRes;
    positionsRaw = Array.isArray(posData) ? posData : posData?.data || [];

    let assetsRaw: any[] = [];
    const assetData = (assetsRes as any)?.data || assetsRes;
    assetsRaw = Array.isArray(assetData) ? assetData : assetData?.data || [];

    let sankeyRaw: any = {};
    const sankData = (sankeyRes as any)?.data;
    sankeyRaw = sankData && typeof sankData === 'object' ? sankData : {};

    const ledgerData = (ledgerRes as any)?.data || ledgerRes;
    ledgers.value = Array.isArray(ledgerData) ? ledgerData : ledgerData?.data || [];

    allPositions.value = positionsRaw.map((p: any) => {
      const rate = EXCHANGE_RATES[p.currency || "CNY"] || 1;
      const marketValue = (p.quantity || 0) * (p.current_price || 0) * rate;
      const pnl = ((p.current_price || 0) - (p.avg_price || 0)) * (p.quantity || 0) * rate;
      return { ...p, marketValue, pnl };
    });

    allAssets.value = assetsRaw.map((a: any) => ({
      ...a,
      marketValue: a.signed_amount ?? (a.amount || 0)
    }));

    totalAssets.value = (sumRes as any)?.data?.total_assets_cny || 0;
    totalLiabilities.value = (sumRes as any)?.data?.total_liabilities_cny || 0;
    totalPnl.value = (sumRes as any)?.data?.total_pnl_cny || 0;
    sankeyData.value = { nodes: sankeyRaw.nodes || [], links: sankeyRaw.links || [] };
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
    await nextTick();
    initWaterfallChart();
  }
}

onMounted(async () => {
  const style = getComputedStyle(document.documentElement)
  const keys = [
    '--color-primary', '--color-success', '--color-danger', '--color-warning',
    '--color-info', '--color-neutral', '--color-accent',
    '--tag-mint-green', '--tag-warm-taupe', '--tag-periwinkle', '--tag-stone-gray',
    '--sankey-total-assets', '--sankey-net-worth', '--sankey-liability',
    '--sankey-liquid', '--sankey-stable', '--sankey-longterm',
    '--sankey-speculative', '--sankey-security',
    '--category-cash', '--category-fixed', '--category-investment',
    '--category-receivable', '--category-liability', '--category-insurance',
    ...ALLOCATION_OPTIONS.map(opt => `--sankey-${opt.value}`) // 动态覆盖
  ]
  const map: Record<string, string> = {}
  keys.forEach(k => {
    const val = style.getPropertyValue(k).trim()
    if (val) map[k] = val
  })
  cssColors.value = map

  await fetchData()
})
</script>

<style scoped>
.summary-large-card {
  height: 100%;
  border-radius: 12px;
  transition: all 0.2s;
}
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
}
.balance-btn.active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 8px;
  right: 8px;
  height: 2px;
  background: var(--color-primary);
  border-radius: 1px;
}

</style>
