<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import AggregationHero from "@/components/Aggregation/AggregationHero.vue";
import AggregationDimensionTabs from "@/components/Aggregation/AggregationDimensionTabs.vue";
import AggregationProductCard from "@/components/Aggregation/AggregationProductCard.vue";
import AggregationInstitutionCard from "@/components/Aggregation/AggregationInstitutionCard.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  getSecuritiesAggregation,
  type AggregationDimension,
  type AggregationProductGroup
} from "@/api/ledger";
import { useAggregation } from "@/composables/useAggregation";

/**
 * 场内证券（股票 / ETF / 可转债）聚合下钻页（#1132 / #1133）。
 *
 * #1133 路由归并：本页取代原隐藏页 /asset/securities-aggregation，成为「股票」品类的**唯一**落地页。
 * 与 /funds 完全同构：共用 useAggregation 取数与 Aggregation* 展示组件，仅品类口径不同，
 * 差异全部收敛在本文件的编排配置里。
 */
// keep-alive 依赖：组件 name 须与路由 name 一致
defineOptions({ name: "AssetStocks" });

const DIMENSION_OPTIONS: { label: string; value: AggregationDimension }[] = [
  { label: "按产品", value: "product" },
  { label: "按机构", value: "institution" }
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
  productGroups,
  institutionGroups,
  total,
  totalPages,
  loading,
  errorMsg,
  load,
  setPage,
  setSort
} = useAggregation(getSecuritiesAggregation, { pageSize: 20 });

const isEmpty = computed(() => total.value === 0);

/** 骨架屏阈值控制：请求 ≤200ms 返回时不展示，避免闪屏 */
const showSkeleton = ref(false);
let skeletonTimer: ReturnType<typeof setTimeout> | null = null;
watch(loading, isLoading => {
  if (isLoading) {
    skeletonTimer = setTimeout(() => {
      showSkeleton.value = true;
    }, 200);
  } else {
    if (skeletonTimer) clearTimeout(skeletonTimer);
    skeletonTimer = null;
    showSkeleton.value = false;
  }
});

function toggleOrder() {
  setSort(sort.value);
}

/** 产品详情下钻：暂缓，与自选产品详情通篇设计后统一落地（#1133） */
function handleSelectProduct(group: AggregationProductGroup) {
  ElMessage.info(`「${group.name || group.symbol}」详情页规划中，敬请期待`);
}

onMounted(load);
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
      :count="total"
    />

    <div class="control-bar mb-5">
      <AggregationDimensionTabs
        v-model="dimension"
        :options="DIMENSION_OPTIONS"
      />
      <div class="sort-control">
        <el-select
          :model-value="sort"
          class="sort-select"
          placeholder="排序"
          @change="setSort"
        >
          <el-option label="按资产金额" value="market_value" />
          <el-option label="按持有份额" value="quantity" />
          <el-option label="按名称" value="name" />
        </el-select>
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
      <el-button type="primary" plain @click="load">重试</el-button>
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
        @select="handleSelectProduct"
      />
    </div>

    <div
      v-else-if="!loading && dimension === 'institution'"
      class="institution-list"
    >
      <AggregationInstitutionCard
        v-for="g in institutionGroups"
        :key="String(g.key)"
        :group="g"
      />
    </div>

    <div v-if="totalPages > 1" class="pagination-bar">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        background
        @current-change="setPage"
      />
    </div>
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
  flex-wrap: wrap;
  gap: var(--space-4, 16px);
  align-items: center;
  justify-content: space-between;
}

.sort-control {
  display: flex;
  gap: 8px;
  align-items: center;
}

.sort-select {
  width: 140px;
}

.order-btn {
  padding: 6px 10px;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--space-compact, 16px);
}

.institution-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact, 16px);
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

  .control-bar {
    align-items: flex-start;
  }
}
</style>
