<template>
  <div class="inventory-home p-4 md:p-6 bg-[#f5f7fa] min-h-full">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h2 class="text-2xl font-bold text-gray-800">全面盘点</h2>
      <p class="text-gray-500 text-sm mt-1">选择资产大类，快速录入或导入</p>
    </div>

    <!-- 顶部资产分类标签栏（更大更突出） -->
    <div class="flex flex-wrap gap-3 mb-10">
      <div
        v-for="cat in categories"
        :key="cat.key"
        class="category-tab"
        :class="{ active: activeCategory === cat.key }"
        :style="activeCategory === cat.key ? { backgroundColor: cat.color + '20', borderColor: cat.color } : {}"
        @click="activeCategory = cat.key"
      >
        <span class="category-tab-label">{{ cat.label }}</span>
        <span class="category-tab-amount">{{ getCategoryAmount(cat.key) }}</span>
        <span v-if="activeCategory === cat.key" class="category-tab-arrow">▾</span>
      </div>
    </div>

    <!-- 下方内容区域 -->
    <div class="content-area">
      <!-- 分类标题与总金额 -->
      <div class="mb-8">
        <h3 class="text-2xl font-bold text-gray-800">{{ activeCategoryLabel }}</h3>
        <p
          :class="[
            'font-bold mt-3',
            categoryHasAmount ? 'text-5xl text-[#FF6B00]' : 'text-2xl text-gray-400'
          ]"
        >
          {{ categoryAmountText }}
        </p>
      </div>

      <!-- 投资理财：按大类聚合卡片，不列出全部持仓 -->
      <div v-if="activeCategory === 'investment' && investmentGroups.length > 0" class="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-5 mb-10">
        <div
          v-for="group in investmentGroups"
          :key="group.type"
          class="asset-card"
        >
          <div class="flex items-center gap-4">
            <div class="group-icon-wrapper" :style="{ backgroundColor: group.color + '20' }">
              <IconifyIconOffline :icon="group.icon" class="group-icon" :style="{ color: group.color }" />
            </div>
            <div>
              <p class="font-semibold text-gray-800 text-lg">{{ group.label }}</p>
              <p class="text-sm text-gray-400">{{ group.count }} 项 · ¥{{ group.total.toLocaleString() }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 其他大类：具体资产卡片（数据量少，保留原样） -->
      <div v-else-if="activeCategory !== 'investment' && activeItems.length > 0" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5 mb-10">
        <div
  v-for="item in activeItems"
  :key="item.id"
  class="asset-card"
  :class="{ selected: selectedItemId === item.id }"
  @click="selectedItemId = selectedItemId === item.id ? null : item.id"
>
  <div class="flex items-start gap-3">
    <IconifyIconOffline
      icon="ep:wallet"
      class="shrink-0 mt-0.5"
      :class="selectedItemId === item.id ? 'text-2xl text-[#FF6B00]' : 'text-xl text-gray-400'"
    />
    <div class="flex-1 min-w-0">
      <p class="font-semibold text-gray-800 text-lg truncate">{{ item.name }}</p>
      <p class="text-sm text-gray-500 mt-0.5">{{ item.account_name || '未指定账户' }}</p>
    </div>
  </div>
  <div class="mt-3 pl-9">
    <p class="text-base font-medium text-gray-700">¥{{ item.amount?.toLocaleString() || '0' }}</p>
    <p class="text-xs text-gray-400 mt-0.5">{{ item.updated_at?.slice(0, 10) || '' }}</p>
  </div>
</div>
      </div>

      <!-- 分类说明卡片 -->
      <div class="info-card mb-10">
        <div class="flex items-start gap-3">
          <IconifyIconOffline icon="ep:info-filled" class="text-[#a6a6d2] text-xl mt-0.5 shrink-0" />
          <p class="text-sm text-gray-600 leading-relaxed">{{ activeCategoryDesc }}</p>
        </div>
      </div>

      <!-- 可添加资产类型卡片网格 -->
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-5">
        <div
          v-for="type in activeAssetTypes"
          :key="type.key"
          class="add-type-card"
          @click="handleAddType(type.key)"
        >
          <div class="type-card-content">
            <div class="type-icon-wrapper" :style="{ backgroundColor: getTypeColor(type.key) + '20' }">
              <IconifyIconOffline :icon="type.icon" class="type-icon" :style="{ color: getTypeColor(type.key) }" />
            </div>
            <span class="type-label">{{ type.label }}</span>
          </div>
        </div>

        <!-- 投资理财专属：导入投资记账卡片 -->
        <div
          v-if="activeCategory === 'investment'"
          class="add-type-card primary-card"
          @click="$router.push('/inventory/investment/import')"
        >
          <div class="type-card-content">
            <div class="type-icon-wrapper" style="background-color: #E8D5C420">
              <IconifyIconOffline icon="ep:upload" class="type-icon" style="color: #E8A87C" />
            </div>
            <span class="type-label">导入投资记账</span>
          </div>
        </div>

        <!-- 自定义资产类型卡片 -->
        <div class="add-type-card" @click="handleCustomAdd">
          <div class="type-card-content">
            <div class="type-icon-wrapper" style="background-color: #f0f0f0">
              <IconifyIconOffline icon="ep:edit" class="type-icon" style="color: #999" />
            </div>
            <span class="type-label">自定义{{ activeCategoryLabel }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import { getAssets } from "@/api/assets";
import { getPositions } from "@/api/positions";

const router = useRouter();
const route = useRoute();   // 用于读取 query 参数

defineOptions({ name: "InventoryHome" });


// 资产大类定义
const categories = [
  { key: "cash", label: "流动资金", color: "#B5C4B1", desc: "可随用随取、即时变现的钱，大额存单、定期存单、基金、股票等流动性更低的资产推荐记入投资理财。" },
  { key: "fixed", label: "固定资产", color: "#A3B5C7", desc: "用于投资或自用的、流动性低的实物类资产。" },
  { key: "investment", label: "投资理财", color: "#9D81A9", desc: "投资于金融产品，追求保值增值的钱，投资于房产、收藏品等实物类投资资产推荐记入固定资产。" },
  { key: "receivable", label: "应收款", color: "#8E8B82", desc: "家庭资产中应收未收的款项，如借给他人的钱，为他人垫付的资金。" },
  { key: "liability", label: "负债", color: "#C4A0A8", desc: "家庭需偿还的债务，如信用卡、房贷、车贷、个人借款等。" },
  { key: "insurance", label: "保险项目", color: "#E8D5C4", desc: "家庭保障类资产，如寿险、健康险、年金险等。" },
];

// 可添加资产类型
const assetTypeMap: Record<string, { key: string; icon: string; label: string; color: string }[]> = {
  cash: [
    { key: "bank", icon: "ep:bank", label: "银行活期", color: "#B5C4B1" },
    { key: "money_fund", icon: "ep:money", label: "货币基金", color: "#9CAF88" },
    { key: "cash_other", icon: "ep:wallet", label: "其他现金", color: "#8DA3B8" },
  ],
  fixed: [
    { key: "house", icon: "ep:house", label: "房产", color: "#C4A0A8" },
    { key: "car", icon: "ep:van", label: "汽车", color: "#9B9EB0" },
    { key: "gold", icon: "ep:medal", label: "黄金", color: "#B6B09C" },
  ],
  investment: [
    { key: "stock", icon: "ep:trend-charts", label: "股票", color: "#9D81A9" },
    { key: "fund", icon: "ep:money", label: "基金", color: "#A3B5C7" },
    { key: "bond", icon: "ep:document", label: "可转债", color: "#8E8B82" },
  ],
  receivable: [
    { key: "personal_loan", icon: "ep:user", label: "个人借款", color: "#8E8B82" },
    { key: "prepaid", icon: "ep:credit-card", label: "预付款", color: "#A89F94" },
  ],
  liability: [
    { key: "credit_card", icon: "ep:credit-card", label: "信用卡", color: "#C4A0A8" },
    { key: "mortgage", icon: "ep:house", label: "房屋贷款", color: "#B5C4B1" },
    { key: "car_loan", icon: "ep:van", label: "汽车贷款", color: "#9B9EB0" },
  ],
  insurance: [
    { key: "life", icon: "ep:shield", label: "寿险", color: "#E8D5C4" },
    { key: "health", icon: "ep:first-aid-kit", label: "健康险", color: "#D4C5C7" },
    { key: "annuity", icon: "ep:document", label: "年金险", color: "#C4C8D0" },
  ],
};

const activeCategory = ref("cash");
const allAssets = ref<any[]>([]);
const allPositions = ref<any[]>([]);

const activeCategoryLabel = computed(() => categories.find(c => c.key === activeCategory.value)?.label || "");
const activeCategoryDesc = computed(() => categories.find(c => c.key === activeCategory.value)?.desc || "");
const activeAssetTypes = computed(() => assetTypeMap[activeCategory.value] || []);

// 普通大类（非投资理财）的资产列表
const activeItems = computed(() => {
  if (activeCategory.value === "investment") return [];
  return allAssets.value.filter(a => a.major_category === activeCategory.value);
});

const categoryAmountText = computed(() => getCategoryAmount(activeCategory.value));

const categoryHasAmount = computed(() => {
  const text = categoryAmountText.value;
  return text !== "无记录";
});

// 投资理财大类：按类型聚合持仓
const investmentGroups = computed(() => {
  if (activeCategory.value !== "investment") return [];

  // 类型图标与颜色映射
  const typeMeta: Record<string, { label: string; icon: string; color: string }> = {
    stock: { label: "股票", icon: "ep:trend-charts", color: "#9D81A9" },
    fund: { label: "场外基金", icon: "ep:money", color: "#A3B5C7" },
    bond: { label: "可转债", icon: "ep:document", color: "#8E8B82" },
    etf: { label: "ETF", icon: "ep:pie-chart", color: "#B5C4B1" },
    crypto: { label: "虚拟货币", icon: "ep:coin", color: "#C4A0A8" },
    saving: { label: "银行存款/理财", icon: "ep:bank", color: "#9CAF88" },
  };

  const groups: Record<string, { total: number; count: number }> = {};
  allPositions.value.forEach(p => {
    const t = p.type || "other";
    if (!groups[t]) groups[t] = { total: 0, count: 0 };
    groups[t].total += p.marketValue || 0;
    groups[t].count += 1;
  });

  return Object.entries(groups).map(([type, data]) => ({
    type,
    label: typeMeta[type]?.label || type,
    icon: typeMeta[type]?.icon || "ep:question",
    color: typeMeta[type]?.color || "#C5C9B8",
    ...data,
  }));
});

function getCategoryAmount(key: string): string {
  if (key === "investment") {
    const fromAssets = allAssets.value.filter(a => a.major_category === "investment").reduce((s, a) => s + (a.amount || 0), 0);
    const fromPositions = allPositions.value.reduce((s, p) => s + (p.marketValue || 0), 0);
    const total = fromAssets + fromPositions;
    return total > 0 ? `¥${total.toLocaleString()}` : "无记录";
  }
  const total = allAssets.value.filter(a => a.major_category === key).reduce((s, a) => s + (a.amount || 0), 0);
  return total > 0 ? `¥${total.toLocaleString()}` : "无记录";
}

function getTypeColor(key: string): string {
  const types = activeAssetTypes.value;
  const found = types.find(t => t.key === key);
  return found?.color || '#C5C9B8';
}

function handleAddType(typeKey: string) {
  router.push(`/asset/asset-entry?category=${activeCategory.value}&type=${typeKey}`);
}

function handleCustomAdd() {
  router.push(`/asset/asset-entry?category=${activeCategory.value}`);
}

async function fetchData() {
  try {
    const [assetsRes, posRes] = await Promise.all([
      getAssets({ per_page: 500 }),
      getPositions({ per_page: 500 }),
    ]);

    let assetsRaw: any[] = [];
    if (Array.isArray(assetsRes)) assetsRaw = assetsRes;
    else if (assetsRes && Array.isArray((assetsRes as any).data)) assetsRaw = (assetsRes as any).data;
    else if (assetsRes && (assetsRes as any).data && Array.isArray((assetsRes as any).data.data)) assetsRaw = (assetsRes as any).data.data;
    else {
      const maybe = (assetsRes as any)?.data ?? assetsRes ?? [];
      assetsRaw = Array.isArray(maybe) ? maybe : [];
    }
    allAssets.value = assetsRaw;

    let positionsRaw: any[] = [];
    if (Array.isArray(posRes)) positionsRaw = posRes;
    else if (posRes && Array.isArray((posRes as any).data)) positionsRaw = (posRes as any).data;
    else if (posRes && (posRes as any).data && Array.isArray((posRes as any).data.data)) positionsRaw = (posRes as any).data.data;
    else {
      const maybe = (posRes as any)?.data ?? posRes ?? [];
      positionsRaw = Array.isArray(maybe) ? maybe : [];
    }
    allPositions.value = positionsRaw.map((p: any) => ({
      ...p,
      marketValue: (p.quantity || 0) * (p.current_price || 0),
    }));
  } catch (e) {
    console.error(e);
  }
}

onMounted(() => {
  fetchData();
  const tab = route.query.tab as string;
  if (tab && categories.some(c => c.key === tab)) {
    activeCategory.value = tab;
  }
});
</script>

<style scoped>
/* 顶部标签（加大尺寸） */
.category-tab {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 24px;
  border-radius: 16px;
  border: 2px solid transparent;
  background: #fff;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 16px;
  font-weight: 500;
  color: #555;
}
.category-tab:hover {
  background: #f5f5f5;
}
.category-tab.active {
  font-weight: 700;
  color: #333;
}
.category-tab-arrow {
  font-size: 12px;
  margin-left: 4px;
}

/* 资产卡片 */
.asset-card {
  background: #fff;
  border-radius: 16px;
  padding: 20px;
  border: 1px solid #f0f0f0;
  transition: all 0.2s;
}
.asset-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
  transform: translateY(-2px);
}

/* 投资理财聚合卡片内的图标 */
.group-icon-wrapper {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.group-icon {
  font-size: 28px;
}

/* 说明卡片 */
.info-card {
  background: #f5f3ff;
  border-radius: 16px;
  padding: 18px 20px;
}

/* 添加类型卡片 */
.add-type-card {
  background: #fff;
  border-radius: 16px;
  padding: 24px 16px;
  border: 1px solid #f0f0f0;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
}
.add-type-card:hover {
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
  transform: translateY(-3px);
}
.add-type-card.primary-card {
  border-color: #E8D5C450;
}
.type-card-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.type-icon-wrapper {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.type-icon {
  font-size: 24px;
}
.type-label {
  font-size: 14px;
  font-weight: 500;
  color: #444;
}

.add-type-card:active .type-icon {
  transform: scale(1.15);
  color: inherit;
}
</style>
