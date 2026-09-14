<template>
  <div
    class="inventory-home p-4 md:p-8 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 页面标题 -->
    <div class="mb-10">
      <h2 class="text-2xl font-bold" :style="{ color: 'var(--text-primary)' }">
        全面盘点
      </h2>
      <p class="text-sm mt-3" :style="{ color: 'var(--text-tertiary)' }">
        选择资产大类，快速录入或导入
      </p>
    </div>

    <!-- 顶部资产分类标签栏 -->
    <CategoryTabs
      v-model:active="activeCategory"
      :categories="INVENTORY_CATEGORIES"
      :total-of="getCategoryTotal"
    />

    <!-- 下方内容区域 -->
    <div class="content-area">
      <!-- 第一层：大类注释卡片 -->
      <CategoryDescBar :desc="activeCategoryDesc" />

      <!-- ==================== 场景 A：投资理财 ==================== -->
      <template v-if="activeCategory === 'investment'">
        <!-- 1. 投资分布 -->
        <h4
          class="text-lg font-semibold mt-10 mb-10"
          :style="{ color: 'var(--text-primary)' }"
        >
          投资分布
        </h4>
        <InvestmentDistribution :groups="investmentGroups" />

        <!-- 2. 快捷操作 -->
        <h4
          class="text-lg font-semibold mt-10 mb-10"
          :style="{ color: 'var(--text-primary)' }"
        >
          快捷操作
        </h4>
        <QuickActionGrid
          :items="INVESTMENT_QUICK_ACTIONS"
          :columns="3"
          @select="onInvestmentQuickAction"
        />

        <!-- 3. 持仓明细 -->
        <h4
          class="text-lg font-semibold mt-10 mb-10"
          :style="{ color: 'var(--text-primary)' }"
        >
          持仓明细
        </h4>
        <InvestmentPositionTable
          v-model:page="investmentPage"
          :positions="investmentPositions"
          :total="investmentTotal"
          :loading="investmentLoading"
        />

        <!-- 4. 其他投资（非交易类投资理财资产，#1354：银行理财/信托等存量大类并入此处） -->
        <template v-if="currentAssets.length > 0">
          <h4
            class="text-lg font-semibold mt-10 mb-10"
            :style="{ color: 'var(--text-primary)' }"
          >
            其他投资
          </h4>
          <OtherInvestmentTable
            :assets="currentAssets"
            @edit="openEditAssetDialog"
            @remove="removeAsset"
          />
        </template>
      </template>

      <!-- ==================== 场景 B：其他大类 ==================== -->
      <template v-else>
        <!-- 1. 快捷操作（顺序调整到资产明细上方） -->
        <h4
          class="text-lg font-semibold mt-10 mb-10"
          :style="{ color: 'var(--text-primary)' }"
        >
          快捷操作
        </h4>
        <QuickActionGrid :items="activeAssetTypes" @select="handleAddType" />

        <!-- 2. 资产明细 -->
        <h4
          class="text-lg font-semibold mt-10 mb-10"
          :style="{ color: 'var(--text-primary)' }"
        >
          资产明细
        </h4>
        <CategoryAssetTable
          :assets="currentAssets"
          @edit="openEditAssetDialog"
          @remove="removeAsset"
        />
      </template>
    </div>

    <!-- 编辑资产弹窗 -->
    <AssetEditDialog
      v-model="editDialogVisible"
      :asset="editingAsset"
      @saved="fetchData"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * 全面盘点页（InventoryHome）· 页面编排层。
 *
 * 自 #955 拆分：本文件只负责「编排」——大类切换、区块顺序与事件转发。
 * - 目录数据与表格基线样式 → `./constants.ts`
 * - 纯函数（颜色 / 标签 / 分组口径）→ `./helpers.ts`
 * - 数据读写、缓存与全局刷新 → `./useInventoryData.ts`
 * - 区块 UI → `./components/*`
 */
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { AssetRecord } from "@/api/assets";
import { INVESTMENT_MAJOR_KEYS } from "@/constants";
import {
  ASSET_TYPE_MAP,
  INVENTORY_CATEGORIES,
  type QuickActionItem
} from "./constants";
import { useInventoryData } from "./useInventoryData";
import CategoryTabs from "./components/CategoryTabs.vue";
import CategoryDescBar from "./components/CategoryDescBar.vue";
import InvestmentDistribution from "./components/InvestmentDistribution.vue";
import QuickActionGrid from "./components/QuickActionGrid.vue";
import InvestmentPositionTable from "./components/InvestmentPositionTable.vue";
import OtherInvestmentTable from "./components/OtherInvestmentTable.vue";
import CategoryAssetTable from "./components/CategoryAssetTable.vue";
import AssetEditDialog from "./components/AssetEditDialog.vue";

// 与路由 `router/modules/home.ts` 的 name 保持一致，保证 keep-alive 命中
defineOptions({ name: "Inventory" });

const router = useRouter();
const route = useRoute();

const activeCategory = ref("investment");

const {
  investmentGroups,
  investmentPositions,
  investmentTotal,
  investmentPage,
  investmentLoading,
  currentAssets,
  getCategoryTotal,
  fetchData,
  removeAsset
} = useInventoryData(activeCategory);

/** 当前大类的说明文案 */
const activeCategoryDesc = computed(
  () =>
    INVENTORY_CATEGORIES.find(c => c.key === activeCategory.value)?.desc || ""
);

/** 其他大类下的快捷录入入口（由大类目录映射） */
const activeAssetTypes = computed(
  () => ASSET_TYPE_MAP[activeCategory.value] || []
);

/**
 * 投资理财大类的固定快捷入口。
 *
 * #1354：银行理财/投顾/信托/私募/理财型保险 收敛为投资理财的细分，
 * 统一走「记录其他投资」这一个入口，不再各占一个大类标签。
 */
const INVESTMENT_QUICK_ACTIONS: QuickActionItem[] = [
  {
    key: "manual",
    icon: "ep:trend-charts",
    label: "记录投资交易",
    desc: "记录股票、基金、可转债、ETF",
    color: "var(--brand-700)"
  },
  {
    key: "import",
    icon: "ep:upload",
    label: "导入投资记账",
    desc: "批量导入基金/股票交割单",
    color: "var(--brand-700)"
  },
  {
    key: "other_invest",
    icon: "ep:briefcase",
    label: "记录其他投资",
    desc: "银行理财、投顾、信托、私募、理财型保险",
    color: "var(--invest-saving)"
  }
];

/** 投资理财大类的快捷入口跳转 */
function onInvestmentQuickAction(key: string) {
  if (key === "manual") {
    router.push("/investment/manual");
    return;
  }
  if (key === "import") {
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

const editDialogVisible = ref(false);
const editingAsset = ref<AssetRecord | null>(null);

function openEditAssetDialog(row: AssetRecord) {
  editingAsset.value = row;
  editDialogVisible.value = true;
}

onMounted(() => {
  const tab = route.query.tab as string;
  // #1354：历史链接可能带已经取消的细分大类（?tab=bank_wealth），统一落到投资理财
  if (tab && INVESTMENT_MAJOR_KEYS.split(",").includes(tab)) {
    activeCategory.value = "investment";
  } else if (tab && INVENTORY_CATEGORIES.some(c => c.key === tab)) {
    activeCategory.value = tab;
  }
  fetchData();
});
</script>
