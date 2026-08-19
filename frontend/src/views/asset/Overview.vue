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
                {{ summaryAmount(netAssets) }}
              </h2>
            </div>
            <div class="flex items-center gap-2 text-sm">
              <span class="text-gray-400">占比</span>
              <span class="font-bold text-[#28A87E]">{{
                summaryRatio(netAssets)
              }}</span>
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
                    {{ summaryAmount(totalAssets) }}
                  </h3>
                </div>
                <div class="flex items-center gap-2 text-xs">
                  <span class="text-gray-400">占比</span>
                  <span class="font-bold text-gray-600">{{
                    totalAssets > 0 ? "100%" : "--"
                  }}</span>
                </div>
              </div>
              <!-- 总负债 -->
              <div class="flex flex-col justify-center">
                <p class="text-gray-400 text-xs mb-2">总负债</p>
                <div class="flex items-baseline gap-1 mb-1">
                  <span class="text-lg font-medium text-gray-800">¥</span>
                  <h3 class="text-2xl font-bold text-gray-800 tracking-tight">
                    {{ summaryAmount(totalLiabilities) }}
                  </h3>
                </div>
                <div class="flex items-center gap-2 text-xs">
                  <span class="text-gray-400">占比</span>
                  <span class="font-bold text-gray-600">{{
                    summaryRatio(totalLiabilities)
                  }}</span>
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

    <!-- 货币基金收益卡片（家庭维度，真实数据） -->
    <div class="bg-white rounded-xl shadow-sm p-6 mb-6">
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-gray-800 font-bold text-lg">货币基金收益</h3>
        <span class="text-gray-400 text-xs">按家庭维度统计</span>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div class="flex items-baseline justify-between">
          <span class="text-gray-400 text-sm">今日收益</span>
          <MoneyDisplay
            v-if="moneyFundData"
            :value="moneyFundData.today_income"
            size="lg"
          />
          <span v-else class="text-gray-400 text-sm">--</span>
        </div>
        <div class="flex items-baseline justify-between">
          <span class="text-gray-400 text-sm">累计收益</span>
          <MoneyDisplay
            v-if="moneyFundData"
            :value="moneyFundData.total_income"
            size="lg"
          />
          <span v-else class="text-gray-400 text-sm">--</span>
        </div>
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
      <SankeyChart :data="sankeyData" :display-mode="displayMode" />
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
                <template v-if="displayMode === 'hidden'">****</template>
                <MoneyDisplay v-else :value="item.value" />
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
                <template v-if="displayMode === 'hidden'">****</template>
                <MoneyDisplay
                  v-else
                  :value="item.change"
                  show-sign
                  auto-color
                />
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
                <template v-if="displayMode === 'hidden'">****</template>
                <MoneyDisplay v-else :value="item.value" />
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
                <template v-if="displayMode === 'hidden'">****</template>
                <MoneyDisplay
                  v-else
                  :value="item.change"
                  show-sign
                  auto-color
                />
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
            {{ row.allocation_label || getAllocationLabel(row.allocation) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="marketValue"
          label="市值(¥)"
          width="130"
          align="right"
          sortable
        >
          <template #default="{ row }">
            <MoneyDisplay
              :value="row.marketValue"
              :show-sign="false"
              :auto-color="false"
            />
          </template>
        </el-table-column>
        <el-table-column
          prop="pnl"
          label="盈亏(¥)"
          width="130"
          align="right"
          sortable
        >
          <template #default="{ row }">
            <MoneyDisplay :value="row.pnl" />
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
            <RiseFallText :value="row.pnlRate" />
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
import {
  ref,
  computed,
  onMounted,
  onActivated,
  nextTick,
  onUnmounted
} from "vue";
import { Search } from "@element-plus/icons-vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import SankeyChart from "@/components/Charts/SankeyChart.vue";
import { getPositions } from "@/api/positions";
import { getSummary, getSankeyData } from "@/api/summary";
import { getAssets } from "@/api/assets";
import {
  getMoneyFundIncome,
  type MoneyFundIncomeData
} from "@/api/performance";
import { ElMessage } from "element-plus";
import echarts from "@/plugins/echarts";
import { getAllocationLabel } from "@/constants";
import { EXCHANGE_RATES } from "@/constants/exchangeRates";
import { getCssVar } from "@/composables/echarts/theme";

// 工具函数：安全读取 CSS 变量（design.md 红线：涨跌色必须走语义变量，hex 仅作 SSR/未定义兜底）
const getCSSColor = (varName: string): string => {
  return getCssVar(varName);
};

const assetChangeChartRef = ref<HTMLDivElement | null>(null);

let assetChangeChart: echarts.ECharts | null = null;

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

// 注：历史遗留 name 曾与 AssetPanorama.vue 同名（影子页面，路由被遮蔽无法访问），
// 已改为唯一名，便于临时挂路由查看该页面现状（是否废弃待用户决策）。
defineOptions({ name: "LegacyAssetOverview" });

// —— 数据 ——
const allPositions = ref<any[]>([]);
const loading = ref(false);
const totalAssets = ref(0);
const totalPnl = ref(0);
const totalLiabilities = ref(0);
const netAssets = ref(0);
const searchKeyword = ref("");
const allAssets = ref<any[]>([]); // 用来存 assets 表的数据

// 桑基图数据（后端聚合出口，共享 SankeyChart 组件消费）
const sankeyData = ref<{ nodes: any[]; links: any[] }>({
  nodes: [],
  links: []
});

// 货币基金收益（家庭维度）
const moneyFundData = ref<MoneyFundIncomeData | null>(null);

async function loadMoneyFundIncome() {
  moneyFundData.value = null;
  try {
    const res = await getMoneyFundIncome({ scope: "family" });
    moneyFundData.value = res.data;
  } catch (e) {
    // 禁止静默吞错：失败保留占位 "--"，仅记日志不打断页面
    console.error("货基收益加载失败", e);
  }
}

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
// 汇总金额/占比展示：getSummary 无数据（totalAssets 为 0）时统一 "--"，避免显示 0/NaN
function summaryAmount(v: number): string {
  if (totalAssets.value <= 0) return "--";
  return v.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}
function summaryRatio(numerator: number): string {
  if (totalAssets.value <= 0) return "--";
  return ((numerator / totalAssets.value) * 100).toFixed(1) + "%";
}

function typeTag(
  type: string
): "primary" | "success" | "warning" | "info" | "danger" {
  const m: Record<
    string,
    "primary" | "success" | "warning" | "info" | "danger"
  > = {
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

// —— 数据获取 ——
async function fetchData() {
  loading.value = true;
  try {
    const [posRes, sumRes, assetsRes, sankeyRes] = await Promise.all([
      getPositions({ per_page: 500 }),
      getSummary(),
      getAssets({ per_page: 500 }),
      getSankeyData()
    ]);

    // 处理 positions
    let positionsRaw: any[] = [];
    if (Array.isArray(posRes)) positionsRaw = posRes;
    else if (posRes && Array.isArray((posRes as any).data))
      positionsRaw = (posRes as any).data;
    else if (
      posRes &&
      (posRes as any).data &&
      Array.isArray((posRes as any).data.data)
    )
      positionsRaw = (posRes as any).data.data;
    else {
      const maybe = (posRes as any)?.data ?? posRes ?? [];
      positionsRaw = Array.isArray(maybe) ? maybe : [];
    }

    // 处理 assets
    let assetsRaw: any[] = [];
    if (Array.isArray(assetsRes)) assetsRaw = assetsRes;
    else if (assetsRes && Array.isArray((assetsRes as any).data))
      assetsRaw = (assetsRes as any).data;
    else if (
      assetsRes &&
      (assetsRes as any).data &&
      Array.isArray((assetsRes as any).data.data)
    )
      assetsRaw = (assetsRes as any).data.data;
    else {
      const maybe = (assetsRes as any)?.data ?? assetsRes ?? [];
      assetsRaw = Array.isArray(maybe) ? maybe : [];
    }

    // 汇总数据
    totalAssets.value =
      (sumRes as any)?.data?.total_assets_cny ??
      (sumRes as any)?.total_assets_cny ??
      0;
    totalPnl.value =
      (sumRes as any)?.data?.total_pnl_cny ??
      (sumRes as any)?.total_pnl_cny ??
      0;
    totalLiabilities.value = (sumRes as any)?.data?.total_liabilities_cny ?? 0;
    netAssets.value =
      (sumRes as any)?.data?.net_assets_cny ??
      totalAssets.value - totalLiabilities.value;

    // 桑基图：后端聚合出口（节点不带色，共享 SankeyChart 组件内部按节点名映射配色）
    const sankeyRaw: any = (sankeyRes as any)?.data ?? {};
    sankeyData.value = {
      nodes: Array.isArray(sankeyRaw.nodes) ? sankeyRaw.nodes : [],
      links: Array.isArray(sankeyRaw.links) ? sankeyRaw.links : []
    };

    allPositions.value = positionsRaw.map((p: any) => {
      const rate = EXCHANGE_RATES[p.currency || "CNY"] || 1;
      const marketValue = (p.quantity || 0) * (p.current_price || 0) * rate;
      const pnl =
        ((p.current_price || 0) - (p.avg_price || 0)) *
        (p.quantity || 0) *
        rate;
      const pnlRate =
        (p.avg_price || 1) !== 0
          ? ((p.current_price || 0) / (p.avg_price || 1) - 1) * 100
          : 0;
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
  }
}

onMounted(async () => {
  await fetchData();
  await loadMoneyFundIncome();
});

onActivated(() => {
  if (allPositions.value.length > 0) {
    nextTick(() => {
      initAssetChangeChart();
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
            if (val > 0) return getCSSColor("--color-rise") || "#f5222d"; // 投资理财-红
            if (val < 0) return getCSSColor("--color-fall") || "#52c41a"; // 流动资金/负债-绿
            return getCSSColor("--color-neutral") || "#d9d9d9"; // 固定资产-灰
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
const handleResize = () => {
  assetChangeChart?.resize();
};

onMounted(() => {
  nextTick(() => {
    initAssetChangeChart();
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
