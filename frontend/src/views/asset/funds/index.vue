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
  getFundAggregation,
  type AggregationDimension,
  type AggregationInstitutionGroup,
  type AggregationProductGroup,
  type AggregationSource
} from "@/api/ledger";
import { useAggregation } from "@/composables/useAggregation";

/**
 * 场外基金（含 E 账户）聚合下钻页（#1101 / #1133）。
 *
 * 对齐参考截图的设计范式：
 * - 品牌色沉浸式 Hero（红底白字总资产）
 * - 果冻胶囊切换「按产品展示」/「按账户展示」
 * - 两种视图共享同一套产品卡片，「按账户」仅多一行销售机构副标题
 * - 点击产品 → 右侧抽屉展开完整详情（四格信息 + 管理人 + 分渠道持仓）
 *
 * 本文件只做编排，符合 docs/spec/frontend-ui.md §3 的页面规模规范。
 */
defineOptions({ name: "AssetFunds" });

const DIMENSION_OPTIONS: { label: string; value: AggregationDimension }[] = [
  { label: "按产品展示", value: "product" },
  { label: "按账户展示", value: "institution" }
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
} = useAggregation(getFundAggregation, { pageSize: 20 });

const isEmpty = computed(() => total.value === 0);

// ── 产品详情抽屉 ──
const detailVisible = ref(false);
const selectedGroup = ref<AggregationProductGroup | null>(null);

/** 打开详情 */
function openDetail(payload: AggregationProductGroup | AggregationSource) {
  if ("ledger_id" in payload) {
    // 渠道模式：从单条 source 构造虚拟 product group（含该渠道的完整信息）
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

// ── 渠道模式：将 institutionGroups 展平为「产品×渠道」卡片列表 ──
/**
 * 「按账户展示」的核心变换：
 *
 * 后端在 dimension=institution 时返回 AggregationInstitutionGroup[]，
 * 每个分组含 .items[]（AggregationSource）。
 * 将其展平为扁平列表，每条对应一张带机构副标题的产品卡（对齐截图2）。
 */
interface FlattenedSource {
  /** 单条来源记录（提供产品名、代码、份额、市值、机构名等全部字段） */
  source: AggregationSource;
  /** 所属机构组名（用于副标题展示） */
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
  <div class="funds-page">
    <PageHeaderBar
      title="基金"
      subtitle="跨账本聚合的全部场外基金持仓，含基金 E 账户份额"
    />

    <!-- 品牌色沉浸式 Hero -->
    <AggregationHero
      class="mb-6"
      :total-yuan="totalYuan"
      :snapshot-date="snapshotDate"
      :snapshot-date-latest="snapshotDateLatest"
      :has-snapshot-gap="hasSnapshotGap"
      :nav-date="navDate"
      :count="total"
    />

    <!-- 果冻胶囊维度切换 + 排序 -->
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

    <!-- 骨架屏 -->
    <PageSkeleton v-if="loading && showSkeleton" :cards="3" :table-rows="6" />

    <!-- 错误态 -->
    <div v-else-if="errorMsg" class="state-block">
      <IconifyIconOffline icon="ep:warning" class="state-icon" />
      <p class="state-text">{{ errorMsg }}</p>
      <el-button type="primary" plain @click="() => load()">重试</el-button>
    </div>

    <!-- 空态 -->
    <div v-else-if="!loading && isEmpty" class="state-block">
      <IconifyIconOffline icon="ep:box" class="state-icon" />
      <p class="state-text">还没有基金持仓</p>
      <p class="state-hint">
        导入基金账户对账单或手动记一笔后，这里会展示全部基金
      </p>
    </div>

    <!-- 按产品：产品级卡片网格 -->
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

    <!-- 按账户：展平为「产品×渠道」卡片列表（对齐截图2） -->
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

    <!-- 分页 -->
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

    <!-- 产品详情抽屉（对齐截图3/4） -->
    <AggregationProductDetail v-model="detailVisible" :group="selectedGroup" />
  </div>
</template>

<style scoped>
@media (width <= 640px) {
  .funds-page {
    padding: var(--space-4, 16px);
  }

  .control-bar {
    align-items: flex-start;
  }

  .card-grid {
    grid-template-columns: 1fr;
  }
}

.funds-page {
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

/* 自适应卡片网格：minmax 缩小以支持 4 列（20 条 / 4 = 5 行整除，消除末行空白） */
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
</style>
