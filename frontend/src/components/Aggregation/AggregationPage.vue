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
  type AggregationDimension,
  type AggregationInstitutionGroup,
  type AggregationProductGroup,
  type AggregationSort,
  type AggregationSource
} from "@/api/ledger";
import {
  useAggregation,
  type AggregationFetcher
} from "@/composables/useAggregation";
import { ASSET_TYPE_LABELS } from "@/constants/assetType";

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

const DIMENSION_OPTIONS: { label: string; value: AggregationDimension }[] = [
  { label: "按产品展示", value: "product" },
  // 该维度的分组键是 institution_id（销售机构/购买渠道），不是 Ledger（账本），
  // 故文案用「渠道」而非「账户」，避免与账本概念混淆（#1185）
  { label: "按渠道展示", value: "institution" }
];

/** 常驻排序快捷按钮：点击即切换字段，同一字段再点反转升降序 */
const SORT_OPTIONS: { label: string; value: AggregationSort }[] = [
  { label: "市值", value: "market_value" },
  { label: "份额", value: "quantity" },
  { label: "收益率", value: "return_pct" },
  { label: "名称", value: "name" }
];

/**
 * 类型筛选 Tab：动态生成，只显示实际有产品的分类（#1224 反馈）。
 * 「全部」常驻；基金侧中间分类来自后端 fund_type_counts（有产品才显示）+「未分类」；
 * 证券侧从 fund_type_breakdown（已按 asset_type 聚类的中文标签）反查原始 asset_type 值。
 * 仅当 showTypeTab 时渲染。
 */
// asset_type 中文标签 → 原始值 的反查表（复用前端镜像，禁止手抄第二份）
const ASSET_TYPE_VALUE_BY_LABEL: Record<string, string> = Object.fromEntries(
  Object.entries(ASSET_TYPE_LABELS).map(([value, label]) => [label, value])
);
const typeOptions = computed<{ label: string; value: string }[]>(() => {
  const opts: { label: string; value: string }[] = [
    { label: "全部", value: "" }
  ];
  if (props.typeFilterField === "asset_type") {
    for (const b of result.value?.fund_type_breakdown ?? []) {
      const raw = ASSET_TYPE_VALUE_BY_LABEL[b.name];
      if (raw) opts.push({ label: b.name, value: raw });
    }
    return opts;
  }
  const counts = result.value?.fund_type_counts ?? {};
  for (const [name, count] of Object.entries(counts)) {
    if (count > 0) opts.push({ label: name, value: name });
  }
  if ((result.value?.fund_type_unclassified_count ?? 0) > 0) {
    opts.push({ label: "未分类", value: "__none__" });
  }
  return opts;
});

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

    <!-- 检索区：第一行 = 维度切换 + 搜索；第二行 = 类型 Tab + 排序快捷按钮 -->
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
        <div
          v-if="showTypeTab"
          class="type-tabs"
          role="tablist"
          :aria-label="`${typeTabLabel}筛选`"
        >
          <button
            v-for="opt in typeOptions"
            :key="opt.value"
            type="button"
            role="tab"
            class="type-pill"
            :class="{ active: fundType === opt.value }"
            :aria-selected="fundType === opt.value"
            @click="setFundType(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
        <div class="sort-control">
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
    </div>

    <!-- 骨架屏：统一尺寸的产品卡网格（消除之前三种尺寸不一致的骨架屏，#1266） -->
    <PageSkeleton
      v-if="loading && showSkeleton"
      :product-cards="pageSize"
      :cards="0"
      :chart-cols="0"
      :table-rows="0"
    />

    <!-- 错误态 -->
    <div v-else-if="errorMsg" class="state-block">
      <IconifyIconOffline icon="ep:warning" class="state-icon" />
      <p class="state-text">{{ errorMsg }}</p>
      <el-button type="primary" plain @click="() => load()">重试</el-button>
    </div>

    <!-- 空态 -->
    <div v-else-if="!loading && isEmpty" class="state-block">
      <IconifyIconOffline icon="ep:box" class="state-icon" />
      <p class="state-text">{{ emptyTitle }}</p>
      <p v-if="emptyHint" class="state-hint">{{ emptyHint }}</p>
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

/* 吸顶常驻：滚动时品牌色 Hero 自然滚走，但维度切换 + 搜索 + 排序（核心操作）始终可见。
   背景与页面底一致避免下方卡片穿透；略微向下延伸遮住滚到其下方的卡片边缘。
   与 WatchlistToolbar 的 .top-bar 同款处理（#1267）。 */
.control-bar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  gap: var(--space-2, 8px);
  padding-bottom: var(--space-2, 8px);
  background: var(--bg-page);
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

.type-tabs,
.sort-pills {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* 类型/排序胶囊：选中态走软按钮规范（brand-100 底 + brand-700 字） */
.type-pill,
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

.type-pill:hover,
.sort-pill:hover {
  color: var(--text-primary);
  border-color: var(--brand-400);
}

.type-pill.active,
.sort-pill.active {
  color: var(--brand-700);
  background: var(--brand-100);
  border-color: var(--brand-400);
}

.sort-control {
  display: flex;
  gap: 8px;
  align-items: center;
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
  .aggregation-page {
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
