<script setup lang="ts">
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  DIMENSION_OPTIONS,
  SORT_OPTIONS
} from "@/components/Aggregation/aggregationToolbarModel";
import type { AggregationDimension, AggregationSort } from "@/api/ledger";

/**
 * 聚合视图工具条（#980 拆分自 `AggregationPage.vue`）。
 *
 * 两行结构完全沿用原实现：
 *   行一 = 维度切换 + 搜索；行二 = 类型 Tab + 排序档位 + 升降序开关。
 * 吸顶（`position: sticky` + `--bg-page` 底）与 `WatchlistToolbar` 的 `.top-bar` 同款，
 * 滚动时品牌色 Hero 自然滚走，核心操作始终可见（#1267）。
 *
 * 组件自身不持有任何状态，全部交互抛给页面（页面仍由 `useAggregation` 统一管理），
 * 因此拆分不改变请求时序与缓存行为。
 */
defineOptions({ name: "AggregationToolbar" });

const props = withDefaults(
  defineProps<{
    dimension: AggregationDimension;
    keyword: string;
    sort: AggregationSort;
    order: "asc" | "desc";
    /** 类型筛选当前值（''=全部，'__none__'=未分类） */
    fundType: string;
    /** 是否展示「类型筛选」胶囊 Tab（基金有，证券按需求可关） */
    showTypeTab?: boolean;
    /** 类型 Tab 的 aria 标签前缀（如「基金类型」「证券类型」） */
    typeTabLabel?: string;
    /** 类型 Tab 选项（由页面按 result 派生，只列有产品的分类） */
    typeOptions?: { label: string; value: string }[];
  }>(),
  {
    showTypeTab: false,
    typeTabLabel: "类型",
    typeOptions: () => []
  }
);

const emit = defineEmits<{
  "dimension-change": [value: AggregationDimension];
  "keyword-change": [value: string];
  "sort-change": [value: AggregationSort];
  "order-toggle": [];
  "fund-type-change": [value: string];
}>();

function onDimensionChange(value: string | number) {
  emit("dimension-change", value as AggregationDimension);
}

function onSortChange(value: string | number) {
  emit("sort-change", value as AggregationSort);
}

function onFundTypeChange(value: string | number) {
  emit("fund-type-change", String(value));
}
</script>

<template>
  <!-- 检索区：第一行 = 维度切换 + 搜索；第二行 = 类型 Tab + 排序快捷按钮 -->
  <div class="control-bar mb-5">
    <div class="control-row">
      <!-- 维度切换（#1731 收敛）：原 `AggregationDimensionTabs` 包装组件自称「D13 果冻胶囊」，
           实现却是 --brand-600 实底 + --text-inverse 白字（实测 3.02:1 不达 AA）。该包装只此一处
           调用，其 select 去重守卫与 SegmentedControl 完全重复，故直接删除、改用唯一实现。 -->
      <SegmentedControl
        :model-value="dimension"
        :options="DIMENSION_OPTIONS"
        aria-label="聚合维度"
        @change="onDimensionChange"
      />
      <el-input
        :model-value="keyword"
        class="search-input"
        aria-label="搜索名称或代码"
        placeholder="搜索名称 / 代码"
        clearable
        @update:model-value="emit('keyword-change', $event)"
      >
        <template #prefix>
          <IconifyIconOffline icon="ep:search" class="search-icon" />
        </template>
      </el-input>
    </div>
    <div class="control-row control-row--sub">
      <!-- 类型筛选（#1731 收敛）：原手写 `.type-pill`（白卡底 + 1px 边框）→ SegmentedControl。
           与自选页 `WatchlistFilterBar` 的「类型快捷筛选」是同一语义（单维度快速切换），
           两处现用同一实现。 -->
      <SegmentedControl
        v-if="showTypeTab"
        :model-value="fundType"
        :options="typeOptions"
        :aria-label="`${typeTabLabel}筛选`"
        @change="onFundTypeChange"
      />
      <div class="sort-control">
        <!-- 排序档位（#1731 收敛）：原手写 `.sort-pill` 与类型筛选共用一份 CSS 块，
             迁移时一并改掉——否则同一控制行里会出现两种外观。 -->
        <SegmentedControl
          :model-value="sort"
          :options="SORT_OPTIONS"
          aria-label="排序方式"
          @change="onSortChange"
        />
        <el-button
          class="order-btn"
          text
          :aria-label="
            order === 'desc'
              ? '当前降序，点击切换为升序'
              : '当前升序，点击切换为降序'
          "
          @click="emit('order-toggle')"
        >
          <IconifyIconOffline
            :icon="order === 'desc' ? 'ep:sort-down' : 'ep:sort-up'"
          />
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 吸顶常驻：滚动时品牌色 Hero 自然滚走，但维度切换 + 搜索 + 排序（核心操作）始终可见。
   背景与页面底一致避免下方卡片穿透；略微向下延伸遮住滚到其下方的卡片边缘。 */
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
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
}

/* 类型筛选 / 排序档位的外观已全部移交 SegmentedControl（#1731 收敛）：
   原先这里有两份手写胶囊样式块（`.type-tabs`/`.type-pill` 与重复的 `.sort-pills`/`.sort-pill`，
   白卡底 + 1px 边框 + 选中 `--brand-100`/`--brand-700`/`--brand-400`）。现不再保留任何视觉声明——
   手写分段控制器样式是 #1717 / #1731 反复回潮的起点，守卫 `scripts/guard_segmented.py` 会在 CI 拦下。 */

.sort-control {
  display: flex;
  gap: 8px;
  align-items: center;
}

.order-btn {
  padding: 6px 10px;
}

@media (width <= 640px) {
  .search-input {
    width: 100%;
  }
}
</style>
