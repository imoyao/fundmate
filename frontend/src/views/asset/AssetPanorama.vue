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

    <!-- 总览大卡片 -->
    <el-row :gutter="16" class="mb-6">
      <el-col :xs="24" :md="12" class="mb-4 md:mb-0">
        <el-card shadow="never" class="summary-large-card">
          <div class="flex flex-col justify-between h-full">
            <div>
              <p class="text-gray-400 text-sm mb-1">总资产（本月）</p>
              <h2 class="text-5xl font-bold text-[#FF6B00] tracking-tight">
                ¥{{ totalAssets.toLocaleString() }}
              </h2>
            </div>
            <div class="border-t border-gray-100 my-5"></div>
            <div class="grid grid-cols-3 gap-4">
              <div>
                <p class="text-gray-400 text-xs mb-1">总负债</p>
                <p class="text-lg font-bold text-gray-800">¥{{ totalLiabilities.toLocaleString() }}</p>
              </div>
              <div>
                <p class="text-gray-400 text-xs mb-1">净资产</p>
                <p class="text-lg font-bold text-[#28A87E]">¥{{ (totalAssets - totalLiabilities).toLocaleString() }}</p>
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

      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="h-full">
          <div class="flex justify-between items-center mb-4">
            <h3 class="font-semibold text-gray-800">总资产变化</h3>
          </div>
          <div ref="waterfallChartRef" class="h-[280px]" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 桑基图 -->
    <el-card shadow="never" class="mb-4">
      <div class="flex items-center justify-between mb-4">
        <h3 class="font-semibold text-gray-800">资产构成流向</h3>
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
          <!-- 使用独立容器包裹 -->
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
            {{ balanceTab === 'assets' ? '资产构成' : '负债明细' }}
          </span>
        </div>

        <table v-if="balanceTab === 'assets'" class="w-full text-sm">
          <thead class="text-gray-400 border-b border-gray-50">
            <tr>
              <th class="text-left py-3 pl-4 font-normal">资产大类</th>
              <th class="text-right py-3 font-normal w-24">占比</th>
              <th class="text-right py-3 pr-4 font-normal w-36">价值</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in assetBalanceRows"
              :key="item.name"
              class="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
              @click="goToInventory(item.categoryKey)"
            >
              <td class="py-3 pl-4 flex items-center gap-3">
                <span class="w-2.5 h-2.5 rounded-full shrink-0" :style="{ backgroundColor: item.color }" />
                <span class="font-medium text-gray-700">{{ item.name }}</span>
              </td>
              <td class="py-3 text-right text-gray-500">
                <div class="flex items-center justify-end gap-2">
                  <div class="h-1.5 w-16 bg-gray-100 rounded-full overflow-hidden">
                    <div class="h-full bg-primary rounded-full" :style="{ width: item.percent + '%' }" />
                  </div>
                  <span>{{ item.percent }}%</span>
                </div>
              </td>
              <td class="py-3 text-right pr-4 font-semibold text-gray-800 tabular-nums">
                ¥{{ item.value.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="border-t-2 border-gray-200">
              <td class="py-3 pl-4 font-medium text-gray-800">合计</td>
              <td class="py-3 text-right text-gray-500">100%</td>
              <td class="py-3 text-right pr-4 font-bold text-gray-800 tabular-nums">
                ¥{{ totalAssets.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}
              </td>
            </tr>
          </tfoot>
        </table>

        <table v-else class="w-full text-sm">
          <thead class="text-gray-400 border-b border-gray-50">
            <tr>
              <th class="text-left py-3 pl-4 font-normal">负债项目</th>
              <th class="text-right py-3 font-normal w-24">占比</th>
              <th class="text-right py-3 pr-4 font-normal w-36">金额</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in liabilityBalanceRows"
              :key="item.name"
              class="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
              @click="goToInventory('liability')"
            >
              <td class="py-3 pl-4 flex items-center gap-3">
                <span class="w-2.5 h-2.5 rounded-full shrink-0" :style="{ backgroundColor: item.color }" />
                <span class="font-medium text-gray-700">{{ item.name }}</span>
              </td>
              <td class="py-3 text-right text-gray-500">
                <div class="flex items-center justify-end gap-2">
                  <div class="h-1.5 w-16 bg-gray-100 rounded-full overflow-hidden">
                    <div class="h-full bg-red-400 rounded-full" :style="{ width: item.percent + '%' }" />
                  </div>
                  <span>{{ item.percent }}%</span>
                </div>
              </td>
              <td class="py-3 text-right pr-4 font-semibold text-gray-800 tabular-nums">
                ¥{{ item.value.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="border-t-2 border-gray-200">
              <td class="py-3 pl-4 font-medium text-gray-800">合计</td>
              <td class="py-3 text-right text-gray-500">100%</td>
              <td class="py-3 text-right pr-4 font-bold text-gray-800 tabular-nums">
                ¥{{ totalLiabilities.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}
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
          class="border rounded-xl overflow-hidden cursor-pointer hover:shadow-sm transition-shadow"
          :style="{ borderColor: 'var(--border-default)' }"
          @click="handleGroupClick(group)"
        >
          <div class="px-5 py-3 flex justify-between items-center font-medium bg-gray-50">
            <span :style="{ color: 'var(--text-primary)' }">{{ group.name }}</span>
            <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }">{{ group.items.length }} 项</span>
          </div>
          <div class="px-5 py-2 flex justify-between items-center text-sm">
            <div>
              <span class="font-semibold" :style="{ color: 'var(--text-primary)' }">
                ¥{{ group.total.toLocaleString(undefined, { maximumFractionDigits: 0 }) }}
              </span>
              <span class="ml-2 text-xs" :style="{ color: 'var(--text-tertiary)' }">
                占 {{ ((group.total / totalAssets) * 100).toFixed(1) }}%
              </span>
            </div>
            <span :class="group.totalPnl >= 0 ? 'text-red-500' : 'text-green-500'">
              {{ group.totalPnl >= 0 ? '+' : '' }}¥{{ Math.round(group.totalPnl).toLocaleString() }}
            </span>
          </div>
        </div>
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
import { getLedgers } from "@/api/ledger";

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

// 将 balanceTabOptions 添加到数据声明区域
const balanceTabOptions = [
  { label: '资产', value: 'assets' },
  { label: '负债', value: 'liabilities' }
];

// 统一其他视图的点击跳转函数
function handleGroupClick(group: any) {
  if (detailView.value === 'type') {
    router.push(`/asset/investment/${getTypeRoute(group.name)}`);
  } else if (detailView.value === 'account') {
    router.push('/asset/ledgers');
  }
  // 配置目标暂不跳转
}

const currentDetailGroups = computed(() => {
  switch (detailView.value) {
    case 'type': return typeDetailGroups.value;
    case 'account': return accountDetailGroups.value;
    case 'allocation': return allocationDetailGroups.value;
    default: return [];
  }
});

// 资产/负债表格数据
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
  allAssets.value.filter(a => a.major_category === "liability" && a.marketValue > 0).forEach(a => {
    const key = a.name || "其他负债";
    if (!map[key]) map[key] = { name: key, value: 0 };
    map[key].value += a.marketValue;
  });
  return Object.values(map).map(item => ({
    ...item,
    color: "var(--color-neutral)",
    percent: +((item.value / totalLiab) * 100).toFixed(1)
  }));
});

// 多维视图分组
const TYPE_LABELS: Record<string, string> = {
  stock: "股票", fund: "基金", bond: "可转债", etf: "ETF",
  crypto: "虚拟货币", saving: "银行存款", cash: "现金"
};

// 按产品类型分组（增加盈亏汇总）
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

// 按账户分组（增加盈亏汇总）
const accountDetailGroups = computed(() => {
  const map: Record<string, { items: any[]; total: number; totalPnl: number }> = {};
  allPositions.value.forEach((p: any) => {
    const acc = p.account_name || '未指定账户';
    if (!map[acc]) map[acc] = { items: [], total: 0, totalPnl: 0 };
    map[acc].items.push({ ...p, type_label: TYPE_LABELS[p.asset_type || p.type] || p.asset_type || p.type });
    map[acc].total += p.marketValue || 0;
    map[acc].totalPnl += p.pnl || 0;
  });
  allAssets.value.forEach((a: any) => {
    const acc = a.account_name || '未指定账户';
    if (!map[acc]) map[acc] = { items: [], total: 0, totalPnl: 0 };
    const value = a.marketValue || a.amount || 0;
    map[acc].items.push({
      ...a,
      marketValue: value,
      type_label: a.minor_category || a.major_category,
      asset_type: a.major_category
    });
    map[acc].total += value;
    // 通用资产默认无盈亏
  });
  return Object.entries(map).map(([name, data]) => ({
    name,
    items: data.items,
    total: data.total,
    totalPnl: data.totalPnl
  }));
});

// 按配置目标分组（增加盈亏汇总）
const allocationDetailGroups = computed(() => {
  const map: Record<string, { items: any[]; total: number; totalPnl: number }> = {};
  allPositions.value.forEach((p: any) => {
    const alloc = p.allocation_label || allocationLabel(p.allocation) || '未配置';
    if (!map[alloc]) map[alloc] = { items: [], total: 0, totalPnl: 0 };
    map[alloc].items.push({ ...p, type_label: TYPE_LABELS[p.asset_type || p.type] || p.asset_type || p.type });
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

function goToAccount(accountName: string) {
  // 查找对应 ledger id，若不存在则跳转到未归类页面
  const ledger = ledgers.find((l: any) => l.name === accountName);
  if (ledger) {
    router.push(`/asset/ledgers/${ledger.id}`);
  } else {
    router.push(`/asset/ledgers/unclassified?name=${encodeURIComponent(accountName)}`);
  }
}

// 产品类型名称到路由路径的映射
function getTypeRoute(typeName: string): string {
  const routes: Record<string, string> = {
    '股票': 'stocks',
    '基金': 'funds',
    '可转债': 'stocks',   // 假设跳转到股票页或转债页
    'ETF': 'stocks',
    '虚拟货币': 'precious',  // 暂时放在贵金属或自定义
    '银行存款': 'funds'
  };
  return routes[typeName] || 'stocks';
}

function allocationLabel(a: string | null): string {
  const meta: Record<string, string> = {
    liquid: "活钱", stable: "稳健底仓", longterm: "长期增值",
    speculative: "高风险博弈", security: "保险保障"
  };
  return meta[a || ""] || a || "长期增值";
}

function goToInventory(categoryKey: string) {
  router.push(`/asset/inventory?tab=${categoryKey}`);
}

async function fetchData() {
  console.log('[AssetPanorama] fetchData 开始')
  loading.value = true;
  try {
    const [posRes, sumRes, assetsRes, sankeyRes,ledgerRes] = await Promise.all([
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
      marketValue: (a.amount || 0) * (EXCHANGE_RATES[a.currency || "CNY"] || 1)
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
    // 瀑布图可在此初始化
  }
}

onMounted(() => fetchData());
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
  color: var(--color-primary);
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

.balance-btn:hover:not(.active) {
  color: var(--color-primary);
}
</style>
