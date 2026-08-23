<script setup lang="ts">
import { ref, reactive } from "vue";
import { ElMessage } from "element-plus";
import { useAssetSearch } from "@/composables/useAssetSearch";
import { getTypeLabel } from "@/constants/assetType";

/**
 * 探市·添加观察栏（#984 explore/index.vue 拆分）。
 * 仅未登录时渲染（登录后隐藏，引导去自选页管理）。
 * 从 index.vue 原样迁移：搜索建议 / 类型与成本份额输入 / 热门资产一键添加。
 * 写入经 props.addHolding（useLocalHoldings 的方法）落到本地观察列表。
 */
const props = defineProps<{
  /** useLocalHoldings.addHolding：父页面注入，避免重复初始化 composable */
  addHolding: (h: {
    symbol: string;
    name: string;
    type: string;
    costPrice: number | null;
    quantity: number | null;
  }) => { success: boolean; message: string };
  /** 实时行情映射：选中建议后用现价预填成本 */
  quotesMap: Record<string, any>;
}>();

// ================================================================
// 搜索（复用 useAssetSearch）
// ================================================================
const {
  loading: searchLoading,
  results: searchResults,
  search
} = useAssetSearch();

const querySearch = (queryString: string, cb: (results: any[]) => void) => {
  search(queryString, cb);
};

// ================================================================
// 新资产表单
// ================================================================
const adding = ref(false);
const selectedAssetInfo = ref<any>(null);

const newAsset = reactive({
  symbol: "",
  type: "stock" as "stock" | "fund" | "etf",
  costPriceInput: "",
  quantityInput: ""
});

const handleSelect = (item: any) => {
  if (!item || !item.code) return;
  newAsset.symbol = item.code;
  newAsset.type = item.type || "stock";
  selectedAssetInfo.value = item;
  const quote = props.quotesMap?.[item.code];
  if (quote?.currentPrice) {
    newAsset.costPriceInput = String(quote.currentPrice);
  }
  if (!newAsset.quantityInput) {
    newAsset.quantityInput = "1";
  }
};

const handleAdd = async () => {
  const symbol = newAsset.symbol.trim();
  if (!symbol) {
    ElMessage.warning("请输入资产代码");
    return;
  }

  const costPrice = newAsset.costPriceInput
    ? parseFloat(newAsset.costPriceInput)
    : null;
  const quantity = newAsset.quantityInput
    ? parseFloat(newAsset.quantityInput)
    : null;

  if (costPrice !== null && isNaN(costPrice)) {
    ElMessage.warning("请输入有效的成本价");
    return;
  }
  if (quantity !== null && isNaN(quantity)) {
    ElMessage.warning("请输入有效的份额");
    return;
  }

  let name = selectedAssetInfo.value?.name;
  if (!name) {
    const found = searchResults.value.find(item => item.code === symbol);
    name = found?.name || symbol;
  }

  adding.value = true;
  try {
    const result = props.addHolding({
      symbol,
      name,
      type: newAsset.type,
      costPrice: costPrice ?? null,
      quantity: quantity ?? null
    });
    if (!result.success) {
      ElMessage.warning(result.message);
    } else {
      ElMessage.success(`已添加「${name}」到观察列表`);
      newAsset.symbol = "";
      newAsset.type = "stock";
      newAsset.costPriceInput = "";
      newAsset.quantityInput = "";
      selectedAssetInfo.value = null;
    }
  } catch (e) {
    console.error("添加失败:", e);
    ElMessage.error("添加失败，请重试");
  } finally {
    adding.value = false;
  }
};

// ================================================================
// 热门预置
// ================================================================
// 热门预置只提供「标的 + 类型」，不预填成本价/份额。
// 传 null 即进入纯观察模式（useLocalHoldings 约定：costPrice/quantity 为 null = 未填），
// 由系统按当前价取成本、份额 1，盈亏恒为 0，避免展示编造的持仓收益（原 P0-2 硬编码假数据）。
const hotAssets = [
  { symbol: "510300", name: "沪深300ETF", type: "etf" as const },
  { symbol: "513100", name: "纳指ETF", type: "etf" as const },
  { symbol: "600036", name: "招商银行", type: "stock" as const },
  { symbol: "588000", name: "科创50ETF", type: "etf" as const }
];

const addHotAsset = (item: (typeof hotAssets)[0]) => {
  try {
    const result = props.addHolding({
      symbol: item.symbol,
      name: item.name,
      type: item.type,
      costPrice: null,
      quantity: null
    });
    if (!result.success) {
      ElMessage.warning(result.message);
    } else {
      ElMessage.success(`已添加「${item.name}」到观察列表（纯观察，未填成本）`);
    }
  } catch (e) {
    console.error(e);
    ElMessage.error("添加失败");
  }
};
</script>

<template>
  <div class="add-card">
    <div class="add-form-row">
      <div class="input-wrapper">
        <el-autocomplete
          v-model="newAsset.symbol"
          :fetch-suggestions="querySearch"
          placeholder="输入代码或名称搜索（如 510300）"
          size="large"
          clearable
          :trigger-on-focus="false"
          class="symbol-input"
          @select="handleSelect"
          @input="() => {}"
          @keyup.enter="handleAdd"
        >
          <template #prefix>
            <span class="input-prefix">搜索</span>
          </template>
          <template #default="{ item }">
            <div class="suggestion-item">
              <span class="suggestion-code">{{ item.code }}</span>
              <span class="suggestion-name">{{ item.name }}</span>
              <el-tag size="small" class="suggestion-tag">{{
                getTypeLabel(item.type)
              }}</el-tag>
            </div>
          </template>
        </el-autocomplete>
      </div>

      <el-select
        v-model="newAsset.type"
        placeholder="类型"
        size="large"
        class="type-select"
      >
        <el-option label="股票" value="stock" />
        <el-option label="基金" value="fund" />
        <el-option label="ETF" value="etf" />
      </el-select>

      <el-input
        v-model="newAsset.costPriceInput"
        placeholder="成本价（选填）"
        size="large"
        class="price-input"
        clearable
      >
        <template #prepend>¥</template>
      </el-input>

      <el-input
        v-model="newAsset.quantityInput"
        placeholder="份额（选填）"
        size="large"
        class="qty-input"
        clearable
      />

      <el-button
        type="primary"
        size="large"
        :loading="adding"
        @click="handleAdd"
        >添加观察</el-button
      >
    </div>

    <div class="hot-section">
      <span class="hot-label">热门资产</span>
      <div class="hot-cards">
        <div
          v-for="item in hotAssets"
          :key="item.symbol"
          class="hot-card"
          @click="addHotAsset(item)"
        >
          <span class="hot-name">{{ item.name }}</span>
          <span class="hot-code">{{ item.symbol }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.add-section {
  max-width: 1280px;
  padding: 16px 24px 8px;
  margin: 0 auto;
}

/* 5.1 登录态引导卡（登录后替代添加栏） */
.auth-guide {
  max-width: 1280px;
  padding: 16px 24px 8px;
  margin: 0 auto;

  &__inner {
    display: flex;
    gap: 20px;
    align-items: center;
    justify-content: space-between;
    padding: 20px 24px;
    background: var(--bg-card);
    border: 1px solid var(--brand-400);
    border-radius: 12px;
    box-shadow: var(--shadow-raised);
  }

  &__title {
    font-size: 15px;
    font-weight: 600;
    color: var(--text-primary);
  }

  &__desc {
    margin-top: 4px;
    font-size: 13px;
    color: var(--text-secondary);
  }
}

.add-card {
  padding: 20px 24px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  box-shadow: var(--shadow-raised);
}

.add-form-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-start;

  .input-wrapper {
    flex: 2;
    min-width: 200px;
  }

  .symbol-input {
    width: 100%;
  }

  .type-select {
    flex-shrink: 0;
    width: 120px;
  }

  .price-input {
    flex-shrink: 0;
    width: 140px;
  }

  .qty-input {
    flex-shrink: 0;
    width: 120px;
  }
}

.input-prefix {
  font-size: 13px;
  color: var(--text-tertiary);
}

.suggestion-item {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 4px 0;

  .suggestion-code {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .suggestion-name {
    font-size: 14px;
    color: var(--text-secondary);
  }

  .suggestion-tag {
    margin-left: auto;
    font-size: 11px;
  }
}

.hot-section {
  display: flex;
  gap: 12px;
  align-items: center;
  padding-top: 14px;
  margin-top: 14px;
  border-top: 1px solid var(--border-light);

  .hot-label {
    font-size: 13px;
    color: var(--text-tertiary);
    white-space: nowrap;
  }

  .hot-cards {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .hot-card {
    display: flex;
    gap: 6px;
    align-items: center;
    padding: 4px 14px;
    font-size: 13px;
    cursor: pointer;
    background: var(--bg-soft);
    border: 1px solid var(--border-light);
    border-radius: 20px;
    transition: all 0.2s;

    &:hover {
      background: var(--brand-100);
      border-color: var(--brand-400);
      transform: translateY(-1px);
    }

    .hot-name {
      color: var(--text-primary);
    }

    .hot-code {
      font-size: 11px;
      color: var(--text-tertiary);
    }
  }
}
</style>
