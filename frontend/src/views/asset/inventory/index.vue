<template>
  <div
    class="inventory-home min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 页面页头（设计系统强制复用组件，自带内容列居中 + 内边距） -->
    <PageHeaderBar title="全面盘点" subtitle="选择资产大类，快速录入或导入" />

    <!-- 内容区：与页头同宽同内边距，保证左边缘严格对齐 -->
    <div class="inventory-shell">
      <!-- 第一层：大类标签栏 + 大类注释 -->
      <CategoryTabs
        v-model:active="activeCategory"
        :categories="INVENTORY_CATEGORIES"
        :total-of="getCategoryTotal"
      />
      <CategoryDescBar :desc="activeCategoryDesc" />

      <!-- ==================== 场景 A：投资理财 ==================== -->
      <template v-if="activeCategory === 'investment'">
        <!-- 1. 快捷操作：录入工作台的首屏应当是「怎么记」，不是一份只读分布 -->
        <section class="inventory-section">
          <SectionHeader title="快捷操作" />
          <QuickActionGrid
            :items="INVESTMENT_QUICK_ACTIONS"
            :columns="4"
            @select="onInvestmentQuickAction"
          />
        </section>

        <!-- 2. 持仓明细（#1104：盈亏双线 —— 已确认 / 当日预估）。
             原「投资分布」两张卡（股票 / 基金）已删除：它与下方明细读同一份持仓，
             却把「股票」「基金」各自定义成一套集合（漏 ETF、漏货基、按持仓行计数），
             与账户管理页的两张聚合卡同名不同义、数字对不上。品类全景只留一处：
             /asset/ledgers（可下钻 /funds、/stocks）。本页只保留「合计」用于盘点核对，
             口径与表格逐行同源（同一份持仓、同一个总笔数）。 -->
        <section class="inventory-section">
          <SectionHeader title="持仓明细" :info="PNL_DUAL_SCOPE_TIP">
            <template #badge>
              <span
                v-if="investmentTotal > 0 && positionsMarketValue !== null"
                class="positions-total"
              >
                <span class="positions-total__label"
                  >共 {{ investmentTotal }} 笔 · 持仓市值合计</span
                >
                <MoneyDisplay
                  :value="positionsMarketValue"
                  :show-sign="false"
                  :auto-color="false"
                  size="sm"
                />
              </span>
            </template>
            <template #action>
              <div class="positions-actions">
                <!-- 品类全景在这里只留一个指针：股票/基金各值多少钱只认账户管理页那一处，
                     避免同一个名词在两条链路上各有一套集合定义。 -->
                <el-button
                  text
                  size="small"
                  @click="router.push('/asset/ledgers')"
                >
                  基金/股票全景
                  <IconifyIconOffline icon="ep:right" class="ml-1" />
                </el-button>
                <RealtimeEstimateToggle
                  :enabled="investmentValuation.realtime.enabled.value"
                  :status="investmentValuation.realtime.status.value"
                  :last-update-time="
                    investmentValuation.realtime.lastUpdateTime.value
                  "
                  :text="investmentValuation.toggleText.value"
                  @toggle="investmentValuation.realtime.toggle"
                />
              </div>
            </template>
          </SectionHeader>
          <InvestmentPositionTable
            v-model:page="investmentPage"
            :positions="investmentPositions"
            :total="investmentTotal"
            :loading="investmentLoading"
            :valuation="investmentValuation"
            :portfolios="portfolios"
            :resolve-portfolio="resolvePortfolioOf"
            @ask="askAbout"
            @reassign="reassignPosition"
          />
        </section>

        <!-- 3.5 类现金（账外货基 / 逆回购，按流水净额记账、不建持仓行）
             它不属于「持仓」，但属于「我有什么」，所以放在持仓明细之后单列；
             金额已计入总资产，这里只展示、不再加总（见组件头注释）。 -->
        <section v-if="cashLikeItems.length > 0" class="inventory-section">
          <SectionHeader
            title="类现金"
            info="货币基金 / 逆回购按流水净额记账，不建持仓，因此不在持仓明细里；金额已包含在总资产中，此处仅为明细展示。"
          />
          <CashLikeTable
            :items="cashLikeItems"
            :total="cashLikeTotal"
            :loading="cashLikeLoading"
            @settled="fetchData"
          />
        </section>

        <!-- 4. 其他投资（非交易类投资理财资产，#1354：银行理财/信托等存量大类并入此处） -->
        <section v-if="currentAssets.length > 0" class="inventory-section">
          <SectionHeader title="其他投资" />
          <OtherInvestmentTable
            :assets="currentAssets"
            @edit="openEditAssetDialog"
            @detail="openValueHistory"
            @remove="removeAsset"
          />
        </section>

        <!-- 5. 策略洞察（#2237）：判断类内容默认收起、首次展开才取数，
             组件见 components/StrategyInsightSection.vue（本页只留一个引用位） -->
        <StrategyInsightSection v-if="activeCategory === 'investment'" />
      </template>

      <!-- ==================== 场景 B：其他大类 ==================== -->
      <template v-else>
        <!-- 1. 快捷操作（顺序调整到资产明细上方） -->
        <section class="inventory-section">
          <SectionHeader title="快捷操作" />
          <QuickActionGrid :items="activeAssetTypes" @select="handleAddType" />
        </section>

        <!-- 2. 资产明细 -->
        <section class="inventory-section">
          <SectionHeader title="资产明细" />
          <CategoryAssetTable
            :assets="currentAssets"
            @edit="openEditAssetDialog"
            @detail="openValueHistory"
            @remove="removeAsset"
          />
        </section>
      </template>
    </div>

    <!-- 编辑资产弹窗 -->
    <AssetEditDialog
      v-model="editDialogVisible"
      :asset="editingAsset"
      @saved="fetchData"
    />
    <!-- 单资产值变动时间线（只读）：数据来自 /value-events/，不写家庭快照 -->
    <AssetValueHistoryDrawer
      v-model="historyDrawerVisible"
      :asset="historyAsset"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * 全面盘点页（InventoryHome）· 页面编排层。
 *
 * 自 #955 拆分：本文件只负责「编排」——大类切换、区块顺序与事件转发。
 * 自 #1501 收敛：页头走 PageHeaderBar、区块标题走 SectionHeader、区块容器走 CardBlock。
 * - 目录数据与表格字号字重 → `./constants.ts`
 * - 纯函数（颜色 / 标签 / 分组口径）→ `./helpers.ts`
 * - 数据读写、缓存与全局刷新 → `./useInventoryData.ts`
 * - 区块 UI → `./components/*`
 */
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { AssetRecord } from "@/api/assets";
import type { Position } from "@/api/types";
import { INVESTMENT_MAJOR_KEYS } from "@/constants";
import { agentAskQuery } from "@/utils/agentAsk";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { INVENTORY_CATEGORIES, INVESTMENT_QUICK_ACTIONS } from "./constants";
import { getCategoryAssetTypes, getCategoryDesc } from "./helpers";
import { useInventoryData } from "./useInventoryData";
import {
  PNL_DUAL_SCOPE_TIP,
  usePositionValuation
} from "@/composables/usePositionValuation";
import CategoryTabs from "./components/CategoryTabs.vue";
import CategoryDescBar from "./components/CategoryDescBar.vue";
import QuickActionGrid from "./components/QuickActionGrid.vue";
import InvestmentPositionTable from "./components/InvestmentPositionTable.vue";
import RealtimeEstimateToggle from "@/components/RealtimeEstimateToggle/index.vue";
import OtherInvestmentTable from "./components/OtherInvestmentTable.vue";
import CashLikeTable from "./components/CashLikeTable.vue";
import CategoryAssetTable from "./components/CategoryAssetTable.vue";
import AssetEditDialog from "./components/AssetEditDialog.vue";
import AssetValueHistoryDrawer from "./components/AssetValueHistoryDrawer.vue";
import StrategyInsightSection from "./components/StrategyInsightSection.vue";

// 与路由 `router/modules/home.ts` 的 name 保持一致，保证 keep-alive 命中
defineOptions({ name: "Inventory" });

const router = useRouter();
const route = useRoute();

const activeCategory = ref("investment");

const {
  positionsMarketValue,
  investmentPositions,
  investmentTotal,
  investmentPage,
  investmentLoading,
  cashLikeItems,
  cashLikeTotal,
  cashLikeLoading,
  currentAssets,
  portfolios,
  resolvePortfolioOf,
  reassignPosition,
  getCategoryTotal,
  fetchData,
  removeAsset
} = useInventoryData(activeCategory);

/**
 * 持仓明细的盈亏双线估值接线（#1104）。
 *
 * 必须在页面 setup 顶层同步调用：`usePositionValuation` 内部注册了
 * `watch(positions)` 与 `onBeforeUnmount`，晚于 await 调用会脱离组件实例。
 * 传入当前页持仓 —— 预估只覆盖当前页，这与表格「后端分页、逐行展示」的口径一致；
 * 页面不做任何跨页汇总，避免出现「本页预估合计」这种会被误读成全仓的数字。
 */
const investmentValuation = usePositionValuation(investmentPositions);

/** 当前大类的说明文案 / 快捷录入入口（均由大类目录映射，见 helpers） */
const activeCategoryDesc = computed(() =>
  getCategoryDesc(activeCategory.value)
);
const activeAssetTypes = computed(() =>
  getCategoryAssetTypes(activeCategory.value)
);

/** 投资理财大类的快捷入口跳转 */
function onInvestmentQuickAction(key: string) {
  if (key === "manual") {
    router.push("/investment/manual");
    return;
  }
  if (key === "import_holding") {
    // 持仓快照导入：默认的文件 / AI 两档由后端按文件自动归因、无需先选账户
    //（#1788 新增的「手动录入」分段才要求先选归属账户）；用 name 跳转最稳妥：
    // 该路由经 formatTwoStageRoutes 拍平后注册为 /investment/holding-import
    router.push({ name: "InvestmentHoldingImport" });
    return;
  }
  if (key === "import_txn") {
    router.push("/inventory/investment/import");
    return;
  }
  handleAddType(key);
}

/** 其他大类的快捷录入跳转 */
function handleAddType(typeKey: string) {
  // #1354：投资理财下的「其他投资」没有独立大类，统一进通用资产录入页，
  // 银行理财/投顾/信托/私募/理财型保险 在表单里作为细分子类选择
  if (activeCategory.value === "investment") {
    router.push("/asset/asset-entry?category=investment");
    return;
  }
  router.push(
    `/asset/asset-entry?category=${activeCategory.value}&type=${typeKey}`
  );
}

/** 「问这个」（#1764）：带该行上下文跳账本精灵页，接收端预填不自动发送 */
function askAbout(row: Position) {
  router.push({
    name: "AgentChat",
    query: agentAskQuery({
      symbol: row.symbol,
      name: row.name,
      from: "inventory"
    })
  });
}

const editDialogVisible = ref(false);
const editingAsset = ref<AssetRecord | null>(null);

function openEditAssetDialog(row: AssetRecord) {
  editingAsset.value = row;
  editDialogVisible.value = true;
}

const historyDrawerVisible = ref(false);
const historyAsset = ref<AssetRecord | null>(null);

function openValueHistory(row: AssetRecord) {
  historyAsset.value = row;
  historyDrawerVisible.value = true;
}

/**
 * `?tab=` **只作入站寻址**（刷新 / 分享 / 首页·房产页「去盘点」带过来），
 * 页内切大类**刻意不写回 URL**。
 *
 * 原因只有一个：布局层 `layout/components/lay-content/index.vue` 用 `route.fullPath`
 * 作 `<component :key>`，**任何 query 改写都会让整页组件重挂载** —— 顶部 6 张大类卡重建、
 * `onMounted` 里的 `fetchData()` 连同汇总 / 分布 / 持仓分页 / 分类资产全套请求重跑一遍。
 * 用户看到的就是「点一下上面的卡片，整页闪一下」。同一根因已在
 * `reconcile-workbench`（#2706，那里记的原话是「改写 query 会整页重建并重跑所有加载器」）
 * 踩过并固化成「只读不写」，本页此前写成 `router.replace({ query })` 与那条结论相反。
 *
 * 代价：切完大类再刷新会回到默认的「投资理财」档（页内切换不再进地址栏）。
 * 换来的是切档只重拉**下方那一块表格**（`watch(activeCategory)` → `loadCategoryAssets`）。
 * ⚠️ 不要为了「刷新后停在当前档」把 `router.replace({ query })` 加回来 —— 那条路就是整页刷新。
 */
onMounted(() => {
  const tab = route.query.tab as string;
  // #1354：历史链接可能带已经取消的细分大类（?tab=bank_wealth），统一落到投资理财
  if (tab && INVESTMENT_MAJOR_KEYS.split(",").includes(tab)) {
    activeCategory.value = "investment";
  } else if (tab && INVENTORY_CATEGORIES.some(c => c.key === tab)) {
    activeCategory.value = tab;
  }
  fetchData();
  // 策略洞察不在这里发起：它默认收起，首次展开时才由 StrategyInsightSection 自己取数。
});
</script>

<style scoped>
/* 页面底部留白：页头自带 --space-section 下边距，这里补一个对称的底部。 */
.inventory-home {
  padding-bottom: var(--space-section);
}

/* 内容区与 PageHeaderBar 同宽同内边距（--layout-content-width / --space-standard），
   保证页头与内容左边缘严格对齐——页头自带 max-width + padding:0 + margin:0 auto，
   若内容区继续全宽铺开，宽屏下会出现「页头居中、内容顶边」的错位。
   与 PageHeaderBar / PageFooter / 探市页同值（#1501）；具体数值见 --layout-content-width 单一来源（#1506）。 */
.inventory-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-section);
  max-width: var(--layout-content-width);
  padding: 0 var(--space-standard);
  margin: 0 auto;
}

/* 区块：标题（SectionHeader 自带 12px 下边距）+ 内容，纵向间距交给 shell 的 gap */
.inventory-section {
  display: flex;
  flex-direction: column;
}

/* 持仓明细标题行的合计（SectionHeader #badge 槽）：
   中性底 + 数字等宽，只做「这页一共记了多少」的核对锚点，不上语义色
   ——它不是盈亏，染色会被读成涨跌。 */
.positions-total {
  display: inline-flex;
  gap: 6px;
  align-items: baseline;
  padding: 2px 10px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
  background: var(--bg-soft);
  border-radius: 999px;

  &__label {
    font-size: var(--text-label);
  }
}

/* 标题右侧操作槽：窄容器下折行而不是溢出（SectionHeader 的 #action 会收缩） */
.positions-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2, 8px);
  align-items: center;
}
</style>
