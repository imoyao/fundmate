<template>
  <div class="inventory-home p-4 md:p-6 bg-[#f5f7fa] min-h-full">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h2 class="text-2xl font-bold text-gray-800">全面盘点</h2>
      <p class="text-gray-500 text-sm mt-1">选择资产大类，快速录入或导入</p>
    </div>

    <!-- 顶部资产分类标签栏 -->
    <div class="flex flex-wrap gap-3 mb-10">
      <div
        v-for="cat in categories"
        :key="cat.key"
        class="category-tab"
        :class="{
          active: activeCategory === cat.key,
          'no-data': getCategoryAmount(cat.key) === '无记录'
        }"
        :style="activeCategory === cat.key ? { backgroundColor: `var(--category-${cat.key}-bg)`, borderColor: `var(--category-${cat.key})` } : {}"
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

      <!-- 投资理财：按大类聚合卡片 -->
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

      <!-- 其他大类：具体资产卡片 -->
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
            <div class="type-icon-wrapper" :style="{ backgroundColor: type.color + '20' }">
              <IconifyIconOffline :icon="type.icon" class="type-icon" :style="{ color: type.color }" />
            </div>
            <span class="type-label">{{ type.label }}</span>
          </div>
        </div>

        <!-- 投资理财导入记账卡片 -->
        <div
          v-if="activeCategory === 'investment'"
          class="add-type-card primary-card"
          @click="$router.push('/inventory/investment/import')"
        >
          <div class="type-card-content">
            <div class="type-icon-wrapper" style="background-color: var(--import-card-bg)">
              <IconifyIconOffline icon="ep:upload" class="type-icon" style="color: var(--import-card-icon)" />
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
const route = useRoute();

defineOptions({ name: "InventoryHome" });

// ---------- 汇率常量 ----------
const EXCHANGE_RATES: Record<string, number> = {
  CNY: 1,
  USD: 7.25,
  HKD: 0.92,
};

// ---------- 资产大类定义（颜色全部使用 CSS 变量）----------
const categories = [
  { key: "investment", label: "投资理财", color: "var(--category-investment)", desc: "追求保值增值的钱。股票、基金、可转债、银行定期存款、大额存单、银行理财、国债等。这些钱牺牲了部分流动性以换取更高收益。" },
  { key: "cash", label: "流动资金", color: "var(--category-cash)", desc: "用于日常消费和应急的活钱。银行卡活期、微信/支付宝余额、余额宝等随时可取的货币基金请放这里。如果这笔钱3个月内肯定不用，建议记入投资理财。" },
  { key: "fixed", label: "固定资产", color: "var(--category-fixed)", desc: "用于投资或自用的、流动性低的实物类资产。" },
  { key: "liability", label: "负债", color: "var(--category-liability)", desc: "家庭需偿还的债务，如信用卡、房贷、车贷、个人借款等。" },
  { key: "receivable", label: "应收款", color: "var(--category-receivable)", desc: "家庭资产中应收未收的款项，如借给他人的钱，为他人垫付的资金。" },
  { key: "insurance", label: "保险项目", color: "var(--category-insurance)", desc: "家庭保障类资产，如寿险、健康险、年金险等。" },
];

// ---------- 可添加资产类型（颜色全部使用 CSS 变量）----------
const assetTypeMap: Record<string, { key: string; icon: string; label: string; color: string }[]> = {
  cash: [
    { key: "bank", icon: "ep:bank", label: "活期/余额宝", color: "var(--add-type-cash)" },
    { key: "money_fund", icon: "ep:money", label: "货币基金", color: "var(--add-type-money-fund)" },
    { key: "cash_other", icon: "ep:wallet", label: "其他现金", color: "var(--add-type-cash-other)" },
  ],
  investment: [
    { key: "stock", icon: "ep:trend-charts", label: "股票", color: "var(--invest-stock)" },
    { key: "fund", icon: "ep:money", label: "场外基金", color: "var(--invest-fund)" },
    { key: "bond", icon: "ep:document", label: "可转债", color: "var(--invest-bond)" },
    { key: "etf", icon: "ep:pie-chart", label: "ETF", color: "var(--invest-etf)" },
    { key: "crypto", icon: "ep:coin", label: "虚拟货币", color: "var(--invest-crypto)" },
    { key: "saving", icon: "ep:bank", label: "定期/理财", color: "var(--invest-saving)" },
  ],
  fixed: [
    { key: "house", icon: "ep:house", label: "房产", color: "var(--add-type-house)" },
    { key: "car", icon: "ep:van", label: "汽车", color: "var(--add-type-car)" },
    { key: "gold", icon: "ep:medal", label: "黄金", color: "var(--add-type-gold)" },
  ],
  receivable: [
    { key: "personal_loan", icon: "ep:user", label: "个人借款", color: "var(--add-type-personal-loan)" },
    { key: "prepaid", icon: "ep:credit-card", label: "预付款", color: "var(--add-type-prepaid)" },
  ],
  liability: [
    { key: "credit_card", icon: "ep:credit-card", label: "信用卡", color: "var(--add-type-credit-card)" },
    { key: "mortgage", icon: "ep:house", label: "房屋贷款", color: "var(--add-type-mortgage)" },
    { key: "car_loan", icon: "ep:van", label: "汽车贷款", color: "var(--add-type-car-loan)" },
  ],
  insurance: [
    { key: "life", icon: "ep:shield", label: "寿险", color: "var(--add-type-life)" },
    { key: "health", icon: "ep:first-aid-kit", label: "健康险", color: "var(--add-type-health)" },
    { key: "annuity", icon: "ep:document", label: "年金险", color: "var(--add-type-annuity)" },
  ],
};

// ---------- 响应式数据 ----------
const activeCategory = ref("investment");
const allAssets = ref<any[]>([]);
const allPositions = ref<any[]>([]);
const selectedItemId = ref<number | string | null>(null);
const loading = ref(false);

// ---------- 计算属性 ----------
const activeCategoryLabel = computed(() => categories.find(c => c.key === activeCategory.value)?.label || "");
const activeCategoryDesc = computed(() => categories.find(c => c.key === activeCategory.value)?.desc || "");
const activeAssetTypes = computed(() => assetTypeMap[activeCategory.value] || []);

const activeItems = computed(() => {
  if (activeCategory.value === "investment") return [];
  return allAssets.value.filter(a => a.major_category === activeCategory.value);
});

const categoryAmountText = computed(() => getCategoryAmount(activeCategory.value));
const categoryHasAmount = computed(() => categoryAmountText.value !== "无记录");

// 投资理财聚合卡片
const investmentGroups = computed(() => {
  if (activeCategory.value !== "investment") return [];

  const typeMetaMap = Object.fromEntries(
    assetTypeMap.investment.map(item => [item.key, item])
  );

  const groups: Record<string, { total: number; count: number }> = {};
  allPositions.value.forEach(p => {
    const t = p.type || "other";
    if (!groups[t]) groups[t] = { total: 0, count: 0 };
    groups[t].total += p.marketValue || 0;
    groups[t].count += 1;
  });

  return Object.entries(groups).map(([type, data]) => {
    const meta = typeMetaMap[type];
    return {
      type,
      label: meta?.label || type,
      icon: meta?.icon || "ep:question",
      color: meta?.color || "var(--color-neutral)",
      ...data,
    };
  });
});

// ---------- 方法 ----------
function getCategoryAmount(key: string): string {
  if (key === "investment") {
    const fromAssets = allAssets.value
      .filter(a => a.major_category === "investment")
      .reduce((s, a) => s + (a.marketValue || 0), 0);
    const fromPositions = allPositions.value.reduce((s, p) => s + (p.marketValue || 0), 0);
    const total = fromAssets + fromPositions;
    return total > 0 ? `¥${total.toLocaleString()}` : "无记录";
  }
  const total = allAssets.value
    .filter(a => a.major_category === key)
    .reduce((s, a) => s + (a.marketValue || 0), 0);
  return total > 0 ? `¥${total.toLocaleString()}` : "无记录";
}

function getTypeColor(key: string): string {
  const types = activeAssetTypes.value;
  const found = types.find(t => t.key === key);
  return found?.color || "var(--color-neutral)";
}

function handleAddType(typeKey: string) {
  router.push(`/asset/asset-entry?category=${activeCategory.value}&type=${typeKey}`);
}

function handleCustomAdd() {
  router.push(`/asset/asset-entry?category=${activeCategory.value}`);
}

// ---------- 数据获取 ----------
async function fetchData() {
  loading.value = true;
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

    let positionsRaw: any[] = [];
    if (Array.isArray(posRes)) positionsRaw = posRes;
    else if (posRes && Array.isArray((posRes as any).data)) positionsRaw = (posRes as any).data;
    else if (posRes && (posRes as any).data && Array.isArray((posRes as any).data.data)) positionsRaw = (posRes as any).data.data;
    else {
      const maybe = (posRes as any)?.data ?? posRes ?? [];
      positionsRaw = Array.isArray(maybe) ? maybe : [];
    }

    allAssets.value = assetsRaw.map((a: any) => {
      const rate = EXCHANGE_RATES[a.currency || "CNY"] || 1;
      return { ...a, marketValue: (a.amount || 0) * rate };
    });

    allPositions.value = positionsRaw.map((p: any) => {
      const rate = EXCHANGE_RATES[p.currency || "CNY"] || 1;
      return {
        ...p,
        marketValue: (p.quantity || 0) * (p.current_price || 0) * rate,
      };
    });
  } catch (e) {
    console.error(e);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  const tab = route.query.tab as string;
  if (tab && categories.some(c => c.key === tab)) {
    activeCategory.value = tab;
  }
  fetchData();
});
</script>

<style scoped>
/* 顶部标签 */
.category-tab {
  display: flex;
  flex-direction: column;          /* 改为垂直布局 */
  align-items: center;
  gap: 4px;                        /* 缩小间距 */
  padding: 18px 24px;
  border-radius: 16px;
  border: 2px solid transparent;
  background: #fff;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 16px;
  font-weight: 500;
  color: #555;
  min-width: 180px;                /* 保证宽度一致 */
}
.category-tab-label {
  font-size: 14px;
  color: inherit;
}
.category-tab-amount {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-primary);
}
.category-tab.active .category-tab-amount {
  color: inherit;
}
.category-tab-arrow {
  font-size: 12px;
  line-height: 1;
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
.asset-card.selected {
  background-color: #FFF7F0;
  border-color: #FF6B00;
}

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

.info-card {
  background: #f5f3ff;
  border-radius: 16px;
  padding: 18px 20px;
}

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
