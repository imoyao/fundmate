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
  load,
  setDimension,
  setPage,
  setSort
} = useAggregation(getSecuritiesAggregation, { pageSize: 20 });

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

    <div class="control-bar mb-5">
      <AggregationDimensionTabs
        :model-value="dimension"
        :options="DIMENSION_OPTIONS"
        @update:model-value="setDimension"
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
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
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

  .control-bar {
    align-items: flex-start;
  }

  .card-grid {
    grid-template-columns: 1fr;
  }
}
</style>
