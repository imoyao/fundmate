<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import AggregationHero from "@/components/Aggregation/AggregationHero.vue";
import AggregationDimensionTabs from "@/components/Aggregation/AggregationDimensionTabs.vue";
import AggregationProductCard from "@/components/Aggregation/AggregationProductCard.vue";
import AggregationProductDetail from "@/components/Aggregation/AggregationProductDetail.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  getSecuritiesAggregation,
  type AggregationDimension,
  type AggregationInstitutionGroup,
  type AggregationProductGroup,
  type AggregationSort,
  type AggregationSource
} from "@/api/ledger";
import { useAggregation } from "@/composables/useAggregation";

/**
 * 场内证券（股票 / ETF / 可转债）聚合下钻页（#1132 / #1133）。
 *
 * 与 /funds 完全同构：共用 Hero / 维度切换 / 产品卡 / 详情抽屉，
 * 差异全部收敛在本文件的编排配置里。
 */
defineOptions({ name: "AssetStocks" });

const DIMENSION_OPTIONS: { label: string; value: AggregationDimension }[] = [
  { label: "按产品展示", value: "product" },
  // 分组键是 institution_id（销售机构/购买渠道），非 Ledger（账本），文案用「渠道」（#1185）
  { label: "按渠道展示", value: "institution" }
];

/** 常驻排序快捷按钮：点击即切换字段，同一字段再点反转升降序 */
const SORT_OPTIONS: { label: string; value: AggregationSort }[] = [
  { label: "市值", value: "market_value" },
  { label: "份额", value: "quantity" },
  { label: "收益率", value: "return_pct" },
  { label: "名称", value: "name" }
];

const {
  dimension,
  sort,
  order,
  page,
  pageSize,
  totalYuan,
  snapshotDate,
  snapshotDateLatest,
  hasSnapshotGap,
  navDate,
  productGroups,
  institutionGroups,
  total,
  totalPages,
  loading,
  showSkeleton,
  errorMsg,
  keyword,
  load,
  setDimension,
  setPage,
  setSort,
  setKeyword
} = useAggregation(getSecuritiesAggregation, { pageSize: 18 });

const isEmpty = computed(() => total.value === 0);

// ── 产品详情抽屉 ──
const detailVisible = ref(false);
const selectedGroup = ref<AggregationProductGroup | null>(null);

function openDetail(payload: AggregationProductGroup | AggregationSource) {
  if ("ledger_id" in payload) {
    const src = payload as AggregationSource;
    selectedGroup.value = {
      symbol: src.symbol || "",
      name: src.name || null,
      quantity: src.quantity,
      market_value_cents: src.market_value_cents,
      nav_yuan: src.nav_yuan ?? null,
      snapshot_date: src.snapshot_date ?? null,
      fund_manager: src.fund_manager ?? null,
      dividend_preference: src.dividend_preference ?? null,
      fund_account: src.fund_account ?? null,
      trade_account: src.trade_account ?? null,
      sources: [src]
    } as AggregationProductGroup;
  } else {
    selectedGroup.value = payload as AggregationProductGroup;
  }
  detailVisible.value = true;
}

// ── 渠道模式展平 ──
interface FlattenedSource {
  source: AggregationSource;
  institutionName: string;
}

const flattenedSources = computed<FlattenedSource[]>(() => {
  if (dimension.value !== "institution") return [];
  const result: FlattenedSource[] = [];
  for (const grp of institutionGroups.value) {
    for (const item of grp.items) {
      result.push({
        source: { ...item, institution_name: grp.institution_name },
        institutionName: grp.institution_name
      });
    }
  }
  return result;
});

function toggleOrder() {
  setSort(sort.value);
}

// 骨架屏与维度切换/排序/分页的加载态统一由 useAggregation 管理
onMounted(() => load());
</script>

<template>
  <div class="stocks-page">
    <PageHeaderBar
      title="股票"
      subtitle="跨账本聚合的全部场内证券持仓，含股票、ETF 与可转债"
    />

    <AggregationHero
      class="mb-6"
      :total-yuan="totalYuan"
      :snapshot-date="snapshotDate"
      :snapshot-date-latest="snapshotDateLatest"
      :has-snapshot-gap="hasSnapshotGap"
      :nav-date="navDate"
      :count="total"
    />

    <!-- 检索区：维度切换 + 搜索 / 排序快捷按钮（与 /funds 同构，无基金类型 Tab） -->
    <div class="control-bar mb-5">
      <div class="control-row">
        <AggregationDimensionTabs
          :model-value="dimension"
          :options="DIMENSION_OPTIONS"
          @update:model-value="setDimension"
        />
        <el-input
          :model-value="keyword"
          class="search-input"
          placeholder="搜索名称 / 代码"
          clearable
          @update:model-value="setKeyword"
        >
          <template #prefix>
            <IconifyIconOffline icon="ep:search" class="search-icon" />
          </template>
        </el-input>
      </div>
      <div class="control-row control-row--sub">
        <div class="sort-pills" role="tablist" aria-label="排序方式">
          <button
            v-for="opt in SORT_OPTIONS"
            :key="opt.value"
            type="button"
            role="tab"
            class="sort-pill"
            :class="{ active: sort === opt.value }"
            :aria-selected="sort === opt.value"
            @click="setSort(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
        <el-button class="order-btn" text @click="toggleOrder">
          <IconifyIconOffline
            :icon="order === 'desc' ? 'ep:sort-down' : 'ep:sort-up'"
          />
        </el-button>
      </div>
    </div>

    <PageSkeleton v-if="loading && showSkeleton" :cards="3" :table-rows="6" />

    <div v-else-if="errorMsg" class="state-block">
      <IconifyIconOffline icon="ep:warning" class="state-icon" />
      <p class="state-text">{{ errorMsg }}</p>
      <el-button type="primary" plain @click="() => load()">重试</el-button>
    </div>

    <div v-else-if="!loading && isEmpty" class="state-block">
      <IconifyIconOffline icon="ep:box" class="state-icon" />
      <p class="state-text">还没有场内证券持仓</p>
      <p class="state-hint">
        导入券商对账单或手动记一笔后，这里会展示全部股票、ETF 与可转债
      </p>
    </div>

    <div v-else-if="!loading && dimension === 'product'" class="card-grid">
      <AggregationProductCard
        v-for="g in productGroups"
        :key="g.symbol"
        :group="g"
        :total-yuan="totalYuan"
        mode="product"
        @select="openDetail"
      />
    </div>

    <div v-else-if="!loading && dimension === 'institution'" class="card-grid">
      <AggregationProductCard
        v-for="(item, idx) in flattenedSources"
        :key="`${item.source.ledger_id}-${item.source.symbol || 'unk'}-${idx}`"
        :source="item.source"
        :nav-yuan="item.source.nav_yuan"
        :snapshot-date="item.source.snapshot_date"
        :total-yuan="totalYuan"
        mode="institution"
        @select="openDetail"
      />
    </div>

    <div v-if="totalPages > 1" class="pagination-bar">
      <el-pagination
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        background
        @current-change="setPage"
      />
    </div>

    <AggregationProductDetail v-model="detailVisible" :group="selectedGroup" />
  </div>
</template>

<style scoped>
.stocks-page {
  min-height: 100%;
  padding: var(--space-5, 24px);
  font-variant-numeric: tabular-nums;
  background: var(--bg-page);
}

.control-bar {
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 8px);
}

.control-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3, 12px);
  align-items: center;
  justify-content: space-between;
}

/* 次级行：与上一行用细分隔线区隔（对齐 design.md 分组胶囊 Tab 规范） */
.control-row--sub {
  padding-top: var(--space-2, 8px);
  border-top: 1px solid var(--border-subtle, var(--border-light));
}

.search-input {
  width: 240px;
}

.search-icon {
  font-size: 14px;
  color: var(--text-tertiary);
}

.sort-pills {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* 排序胶囊：选中态走软按钮规范（brand-100 底 + brand-700 字） */
.sort-pill {
  padding: 5px 14px;
  font-family: var(--font-ui);
  font-size: 13px;
  line-height: 1.2;
  color: var(--text-secondary);
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    color 0.15s ease,
    background-color 0.15s ease,
    border-color 0.15s ease;
}

.sort-pill:hover {
  color: var(--text-primary);
  border-color: var(--brand-400);
}

.sort-pill.active {
  color: var(--brand-700);
  background: var(--brand-100);
  border-color: var(--brand-400);
}

.order-btn {
  padding: 6px 10px;
}

/* 自适应卡片网格：minmax 320px 保证笔记本 3 列、宽屏 4 列；
   配合每页 18 条（3 的倍数）从根上避免「末行缺卡」的怪异感 */
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--space-compact, 14px);
}

.state-block {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  padding: 60px 20px;
  text-align: center;
}

.state-icon {
  font-size: 48px;
  opacity: 0.3;
}

.state-text {
  font-size: 16px;
  color: var(--text-secondary);
}

.state-hint {
  font-size: 13px;
  color: var(--text-tertiary);
}

.pagination-bar {
  display: flex;
  justify-content: center;
  margin-top: var(--space-5, 24px);
}

@media (width <= 640px) {
  .stocks-page {
    padding: var(--space-4, 16px);
  }

  .card-grid {
    grid-template-columns: 1fr;
  }

  .search-input {
    width: 100%;
  }
}
</style>
