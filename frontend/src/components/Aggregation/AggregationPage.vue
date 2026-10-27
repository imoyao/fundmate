<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import AggregationHero from "@/components/Aggregation/AggregationHero.vue";
import AggregationToolbar from "@/components/Aggregation/AggregationToolbar.vue";
import AggregationStateBlock from "@/components/Aggregation/AggregationStateBlock.vue";
import AggregationProductCard from "@/components/Aggregation/AggregationProductCard.vue";
import AggregationProductDetail from "@/components/Aggregation/AggregationProductDetail.vue";
import { buildTypeOptions } from "@/components/Aggregation/aggregationToolbarModel";
import {
  type AggregationDimension,
  type AggregationProductGroup,
  type AggregationSort,
  type AggregationSource
} from "@/api/ledger";
import {
  useAggregation,
  type AggregationFetcher
} from "@/composables/useAggregation";

/**
 * 持仓聚合下钻页共享组件（#1266 抽离）。
 *
 * /funds（场外基金）与 /stocks（场内证券）共用同一套英雄区 / 维度切换 / 产品卡 / 详情抽屉，
 * 差异收敛为配置项：fetcher（数据源）、title/subtitle、showTypeTab（类型筛选 Tab）、
 * typeTabLabel、typeFilterField（基金 fund_type / 证券 asset_type）、emptyTitle/emptyHint。
 * 共享逻辑只有一份实现，改一处两侧同步生效。
 *
 * 资产构成环形图由 AggregationHero 按 result.fund_type_breakdown 渲染；后端对该字段按
 * 品类维度聚类（基金侧 fund_type、证券侧 asset_type），两侧共用同一字段，天然对齐（#1264）。
 *
 * #980 拆分：工具条（维度/搜索/类型/排序）→ `AggregationToolbar`，错误/空态 →
 * `AggregationStateBlock`，选项常量与类型 Tab 派生 → `aggregationToolbarModel.ts`。
 * 本文件只保留取数编排、分页与详情抽屉。
 */
defineOptions({ name: "AggregationPage" });

const props = withDefaults(
  defineProps<{
    /** 聚合取数函数（场外基金 / 场内证券各传自己的 API） */
    fetcher: AggregationFetcher;
    /** 页面标题（如「基金」「股票」） */
    title: string;
    /** 副标题说明文案 */
    subtitle: string;
    /** 每页条数，默认 18（与卡片网格列数配合，避免末行缺卡） */
    pageSize?: number;
    /** 是否展示「类型筛选」胶囊 Tab（基金有，证券按需求可关） */
    showTypeTab?: boolean;
    /** 类型 Tab 的 aria 标签前缀（如「基金类型」「证券类型」） */
    typeTabLabel?: string;
    /** 类型 Tab 的筛选字段：'fund_type'（基金，默认）/ 'asset_type'（证券：股票/ETF/可转债） */
    typeFilterField?: "fund_type" | "asset_type";
    /** 空态标题 */
    emptyTitle?: string;
    /** 空态提示 */
    emptyHint?: string;
  }>(),
  {
    pageSize: 18,
    showTypeTab: false,
    typeTabLabel: "类型",
    emptyTitle: "还没有持仓",
    emptyHint: ""
  }
);

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
  fundType,
  result,
  load,
  setDimension,
  setPage,
  setSort,
  setKeyword,
  setFundType
} = useAggregation(props.fetcher, {
  pageSize: props.pageSize,
  typeFilterField: props.typeFilterField
});

const isEmpty = computed(() => total.value === 0);

/** 类型 Tab 选项：只列实际有产品的分类（动态生成，见 aggregationToolbarModel） */
const typeOptions = computed(() =>
  buildTypeOptions(result.value, props.typeFilterField)
);

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
  <div class="aggregation-page">
    <PageHeaderBar :title="title" :subtitle="subtitle" />

    <!-- 品牌色沉浸式 Hero（含资产构成环形图；两侧共用同一 breakdown 字段，天然对齐 #1264） -->
    <AggregationHero
      class="mb-6"
      :total-yuan="totalYuan"
      :snapshot-date="snapshotDate"
      :snapshot-date-latest="snapshotDateLatest"
      :has-snapshot-gap="hasSnapshotGap"
      :nav-date="navDate"
      :count="total"
      :type-breakdown="result?.fund_type_breakdown ?? null"
    />

    <!-- 检索区：维度切换 + 搜索 / 类型 Tab + 排序（吸顶常驻，见 AggregationToolbar） -->
    <AggregationToolbar
      :dimension="dimension"
      :keyword="keyword"
      :sort="sort"
      :order="order"
      :fund-type="fundType"
      :show-type-tab="showTypeTab"
      :type-tab-label="typeTabLabel"
      :type-options="typeOptions"
      @dimension-change="setDimension"
      @keyword-change="setKeyword"
      @sort-change="setSort"
      @order-toggle="toggleOrder"
      @fund-type-change="setFundType"
    />

    <!-- 骨架屏：统一尺寸的产品卡网格（消除之前三种尺寸不一致的骨架屏，#1266） -->
    <PageSkeleton
      v-if="loading && showSkeleton"
      :product-cards="pageSize"
      :cards="0"
      :chart-cols="0"
      :table-rows="0"
    />

    <!-- 错误态 -->
    <AggregationStateBlock
      v-else-if="errorMsg"
      kind="error"
      :message="errorMsg"
      @retry="() => load()"
    />

    <!-- 空态 -->
    <AggregationStateBlock
      v-else-if="!loading && isEmpty"
      kind="empty"
      :message="emptyTitle"
      :hint="emptyHint"
    />

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

    <!-- 按渠道：展平为「产品×渠道」卡片列表 -->
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

    <!-- 产品详情抽屉（分摊保存成功后刷新聚合数据，#1176） -->
    <AggregationProductDetail
      v-model="detailVisible"
      :group="selectedGroup"
      @saved="() => load()"
    />
  </div>
</template>

<style scoped>
.aggregation-page {
  min-height: 100%;
  padding: var(--space-5, 24px);
  font-variant-numeric: tabular-nums;
  background: var(--bg-page);
}

/* 自适应卡片网格：minmax 320px 保证笔记本 3 列、宽屏 4 列；
   配合每页 18 条（3 的倍数）从根上避免「末行缺卡」的怪异感 */
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--space-compact, 14px);
}

.pagination-bar {
  display: flex;
  justify-content: center;
  margin-top: var(--space-5, 24px);
}

@media (width <= 640px) {
  .aggregation-page {
    padding: var(--space-compact);
  }

  .card-grid {
    grid-template-columns: 1fr;
  }
}
</style>
