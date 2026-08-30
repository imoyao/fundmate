<!--
  未竟之蹊 · /the-road-not-taken（路由名 Favourites）

  与普通自选页（/watchlist）的分工（docs/features/watchlist.md §1.5.7）：
  自选页看「实时数据」，本页看「私有思考 + 资产变迁」——卡片流而非表格行，
  排序与筛选围绕「最近动了哪张卡 / 该复盘哪张卡」，而不是涨跌幅。

  设计落点：
  - 两级胶囊筛选（design.md「Filter & Selection」，严禁左侧边栏）
  - Masonry 三列不等高瀑布流 + 封面走势图（小红书式封面，但用真实曲线代替照片）
  - 暖奶油底 + 珊瑚红强调，圆角 16px、胶囊标签、底部互动图标
  - 让用户慢下来：一张卡只讲一件事——你为什么在意它，以及下次什么时候回看
-->
<template>
  <div class="road-page">
    <RoadPoemBanner />

    <RoadFilterBar
      :entity-filter="entityFilter"
      :status-filter="statusFilter"
      :entity-counts="entityCounts"
      :status-counts="statusCounts"
      :keyword="keyword"
      :sort-by="sortBy"
      :manage-mode="manageMode"
      :preview-mode="previewMode"
      @update:entity-filter="setEntityFilter"
      @update:status-filter="setStatusFilter"
      @update:keyword="onKeywordChange"
      @update:sort-by="onSortChange"
      @update:preview-mode="previewMode = $event"
      @toggle-manage="toggleManage"
    />

    <RoadBatchToolbar
      v-if="manageMode"
      :selected-count="selectedIds.length"
      @select-all="selectAllOnPage"
      @clear="clearSelection"
      @batch-pin="batchPin"
      @batch-remove="batchRemove"
    />

    <div ref="listHostRef" v-loading="loading" class="road-waterfall">
      <template v-if="pagedItems.length">
        <V3Waterfall
          :key="breakpoint"
          :list="pagedItems"
          :col-width="colWidth"
          :gap="GAP"
          :is-over="isLastPage"
          :over-text="overText"
          over-color="var(--text-tertiary)"
        >
          <template #default="{ item }">
            <RoadCard
              :item="item"
              :tags="tags"
              :selected="isSelected(item)"
              :editing="editingId === item.id"
              :manage-mode="manageMode"
              @toggle-select="toggleSelect"
              @start-edit="startEdit"
              @cancel-edit="cancelEdit"
              @save="onSave"
              @pin="togglePin"
              @remove="confirmRemove"
            />
          </template>
        </V3Waterfall>

        <div v-if="pageCount > 1" class="road-pagination">
          <el-pagination
            v-model:current-page="page"
            :page-size="PAGE_SIZE"
            :total="total"
            layout="total, prev, pager, next"
            small
            background
          />
        </div>
      </template>

      <RoadEmptyState
        v-else
        :filtered="hasFilter"
        :preview-mode="previewMode"
        @go-watchlist="$router.push('/watchlist')"
        @toggle-preview="previewMode = !previewMode"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessageBox } from "element-plus";
import { V3waterfall as V3Waterfall } from "v3-waterfall";
import "v3-waterfall/dist/style.css";
import RoadPoemBanner from "./components/RoadPoemBanner.vue";
import RoadFilterBar from "./components/RoadFilterBar.vue";
import RoadBatchToolbar from "./components/RoadBatchToolbar.vue";
import RoadCard from "./components/RoadCard.vue";
import RoadEmptyState from "./components/RoadEmptyState.vue";
import { useRoadNotTaken } from "./composables/useRoadNotTaken";
import { PAGE_SIZE } from "./constants";
import type { RoadItem } from "@/types/favorites";

// 路由名必须与 defineOptions.name 一致，否则 keep-alive 失效（AGENTS.md 前端约束）
defineOptions({ name: "Favourites" });

const GAP = 20;

const {
  tags,
  loading,
  entityFilter,
  statusFilter,
  keyword,
  sortBy,
  page,
  manageMode,
  selectedIds,
  editingId,
  previewMode,
  entityCounts,
  statusCounts,
  pagedItems,
  total,
  pageCount,
  isLastPage,
  load,
  setEntityFilter,
  setStatusFilter,
  resetPage,
  toggleManage,
  toggleSelect,
  clearSelection,
  batchPin,
  batchRemove,
  togglePin,
  removeFavorite,
  startEdit,
  cancelEdit,
  saveCard
} = useRoadNotTaken();

const listHostRef = ref<HTMLElement | null>(null);

/**
 * 列宽随容器实宽响应式计算：保证桌面下严格三列且铺满（v3-waterfall 只按
 * colWidth 切列、不拉伸，故不能用固定值，否则右侧会留空隙）。
 * 用 hostWidth + ResizeObserver 跟踪容器尺寸（侧栏收起、分屏等），并在容器
 * 变化时主动派发 window resize 让 v3-waterfall 重算列数——否则容器变窄时
 * 卡片会停留在旧列宽，看起来像挤在一列（所谓"堆叠"）。
 */
const hostWidth = ref<number>(listHostRef.value?.clientWidth ?? 1120);
const colWidth = computed(() => {
  const width = hostWidth.value;
  const columns = width >= 1180 ? 3 : width >= 760 ? 2 : 1;
  return Math.max(240, Math.floor((width - GAP * (columns - 1)) / columns));
});

/**
 * 列数断点：容器宽度跨断点（侧栏收起 / 分屏 / 窗口缩放）时换 key 让
 * V3Waterfall 重挂载，从而按新宽度重新计算列数——这是容器尺寸变化的唯一
 * 可靠触发方式（库本身只在 window resize 时重算）。
 */
const breakpoint = computed(() =>
  hostWidth.value >= 1180 ? 3 : hostWidth.value >= 760 ? 2 : 1
);

const overText = computed(() => `已到蹊径尽头 · 共 ${total.value} 段未竟`);

const hasFilter = computed(
  () =>
    entityFilter.value !== "all" ||
    statusFilter.value !== "all" ||
    Boolean(keyword.value.trim())
);

const isSelected = (item: RoadItem) =>
  item.id != null && selectedIds.value.includes(item.id);

function onKeywordChange(value: string) {
  keyword.value = value;
  resetPage();
}

function onSortChange(value: string) {
  sortBy.value = value;
  resetPage();
}

/** 全选/全不选本页（示例卡 id 为空，天然被跳过） */
function selectAllOnPage() {
  const ids = pagedItems.value
    .map(i => i.id)
    .filter((id): id is number => id != null);
  const allSelected =
    ids.length > 0 && ids.every(id => selectedIds.value.includes(id));
  selectedIds.value = allSelected
    ? selectedIds.value.filter(id => !ids.includes(id))
    : [...new Set([...selectedIds.value, ...ids])];
}

async function confirmRemove(item: RoadItem) {
  try {
    await ElMessageBox.confirm(
      `把「${item.display_name}」移回普通自选？写过的笔记会保留。`,
      "移出特别关注",
      { type: "warning", confirmButtonText: "移出", cancelButtonText: "再想想" }
    );
  } catch {
    return;
  }
  await removeFavorite(item);
}

function onSave(payload: {
  item: RoadItem;
  draft: { notes: string; next_review_date: string | null; tagIds: number[] };
}) {
  void saveCard(payload.item, payload.draft);
}

let resizeObserver: ResizeObserver | null = null;
// 只在「容器宽度」真正变化时更新 hostWidth：避免 v3-waterfall 重排导致高度变化
// 又触发 ResizeObserver，形成「resize → 重排 → 高度变 → 再 resize」的死循环
// （会把主线程占满、页面卡死、点哪都没反应）。
function syncHostWidth() {
  if (!listHostRef.value) return;
  const w = listHostRef.value.clientWidth;
  if (w !== hostWidth.value) hostWidth.value = w;
}
onMounted(() => {
  syncHostWidth();
  if (listHostRef.value) {
    resizeObserver = new ResizeObserver(syncHostWidth);
    resizeObserver.observe(listHostRef.value);
  }
  void load();
});
onBeforeUnmount(() => resizeObserver?.disconnect());
</script>

<style scoped>
.road-page {
  padding: 4px 4px 32px;
  background: var(--bg-page);
}

.road-waterfall {
  min-height: 240px;
}

.road-pagination {
  display: flex;
  justify-content: flex-end;
  padding-top: 20px;
}
</style>
