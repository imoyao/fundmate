<script setup lang="ts">
/**
 * E账户对账面板（筛选 + 明细表 + 分页），2026-10-28 新建。
 *
 * 为什么把它做成组件：同一种数据（`GET /api/e-account/reconciliation/`）在两个地方
 * 出现——独立对账页（老入口，`showLink:false`，隐藏路由）和对账中心域 A（侧边栏
 * 正门）。此前工作台是手抄一份，抄丢了三样东西（系统份额字段名、差异列、分页）外加
 * 一个更危险的：**「归因覆盖」不弹确认框就删渠道原记录**。两份实现并存 ⇒ 一定会有
 * 第三次漂移，故收敛成一份，两处只传数据与回调。
 *
 * 职责边界：本组件只负责「看」，不负责「改」。归因 / 忽略的请求与确认框在
 * `useEaccountActions`（容器各持一个实例），行内按钮经 emit 上抛。
 *
 * 筛选与分页留在本层而不是表格层：它们共同回答「这一屏看哪一段」，
 * 拆开就会出现「顶部共 N 条」与「分页器 total」两个口径。
 */
import { computed, ref, watch } from "vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import type { ReconciliationItem } from "@/api/eaccount";

import ReconcileTable from "./ReconcileTable.vue";
import {
  STATUS_OPTIONS,
  filterByStatus,
  slicePage,
  type Acting
} from "./model";

const props = withDefaults(
  defineProps<{
    items: ReconciliationItem[];
    loading: boolean;
    acting: Acting;
    /**
     * 是否自带卡片外框。独立对账中心直接挂在页面上，需要外框；
     * 工作台域 A 已经在 `CardBlock` 里，再套一层就是双框（表格浮在卡片中间）。
     */
    framed?: boolean;
  }>(),
  { framed: true }
);

const emit = defineEmits<{
  (e: "cover", row: ReconciliationItem): void;
  (e: "ignore", row: ReconciliationItem): void;
}>();

/** 一级状态筛选（客户端过滤：数据量小，切换即时，四态计数保持全量口径） */
const statusFilter = ref<string>("all");
/** 客户端分页：当前页码 + 每页条数（默认 50；E账户快照实测 90+ 条、域 B 160+ 条） */
const page = ref(1);
const pageSize = ref(50);

const filteredItems = computed(() =>
  filterByStatus(props.items, statusFilter.value)
);

/** 客户端分页：在筛选结果上按当前页码切片（顶部「共 N 条」保持全量口径） */
const pagedItems = computed(() =>
  slicePage(filteredItems.value, page.value, pageSize.value)
);

/** 筛选切换时回到第一页，避免停留在旧筛选的高页码 */
watch(statusFilter, () => {
  page.value = 1;
});

/** 数据重载后回到第一页（对账操作会改变行状态，停在旧页码会看到空页） */
watch(
  () => props.items,
  () => {
    page.value = 1;
  }
);
</script>

<template>
  <div class="eaccount-panel" :class="{ 'eaccount-panel--framed': framed }">
    <!-- 状态筛选：一级胶囊分段（design.md「Filter & Selection」；收敛到 SegmentedControl） -->
    <div class="eaccount-panel__bar">
      <SegmentedControl
        v-model="statusFilter"
        :options="STATUS_OPTIONS"
        aria-label="对账状态筛选"
      />
      <!-- 类名 filter-bar__count 是 e2e 锚点（frontend/e2e/reconcile.spec.ts），改名须同步 spec -->
      <span class="filter-bar__count">共 {{ filteredItems.length }} 条</span>
    </div>

    <ReconcileTable
      :items="pagedItems"
      :loading="loading"
      :status-filter="statusFilter"
      :acting="acting"
      @cover="emit('cover', $event)"
      @ignore="emit('ignore', $event)"
    />

    <!-- 一页装得下就不出翻页器：6 行的表底下挂一排灰掉的页码是纯噪音 -->
    <el-pagination
      v-if="filteredItems.length > pageSize"
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="filteredItems.length"
      :page-sizes="[50, 100, 200]"
      layout="total, prev, pager, next, sizes"
      small
      background
      class="eaccount-panel__pagination"
    />
  </div>
</template>

<style scoped>
/* 卡片外框：仅独立对账中心使用（工作台域 A 由 CardBlock 提供外框） */
.eaccount-panel--framed {
  padding: var(--space-compact);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

/* 筛选栏：与表格之间留一口气，右侧「共 N 条」与分页 total 同口径 */
.eaccount-panel__bar {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-compact);
}

.filter-bar__count {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

/* 分页条：表格底部右对齐，Element Plus 默认视觉 */
.eaccount-panel__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--space-compact);
}
</style>
