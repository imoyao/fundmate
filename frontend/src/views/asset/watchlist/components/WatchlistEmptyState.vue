<script setup lang="ts">
import { Plus } from "@element-plus/icons-vue";

/**
 * 自选表格空态覆盖层（2026-10-30 从 WatchlistTableSection 原样抽出）。
 *
 * WHY 独立：表格区已贴着 `.vue` 行数门禁（issue #980，阈值 400），加「当日盈亏口径
 * 下拉」后越过阈值。空态是**纯展示 + 一个事件**、与表格渲染零耦合，是最干净的可拆件
 * （门禁的两条修法之一就是「拆子组件，让文件回到基线内」）。
 *
 * 行为零变更，两条设计原样保留：
 * 1. 覆盖整张 el-table（含表头）并用卡片色遮挡——空态时没有数据行，列名与表头底边框
 *    会在文案上方形成一条怪异分割线；overlay 从 full 铺满、文案在整卡区内垂直居中。
 *    不复用 el-table 的 `#empty`：它的 empty-block 高度被 EP 撑到 280px 封顶，
 *    无法在整段空表格区内居中。
 * 2. 空白自定义分组给虚线「+ 从全部自选添加」入口（#987，与表格内「＋ 标签」虚线按钮
 *    同一视觉语言）；系统分组为空 / 标签筛选无匹配仍走纯文案。
 */
defineProps<{
  /** 空态是否落在「空白自定义分组」（虚线快捷入口） */
  isEmptyCustomGroup: boolean;
  activeGroupLabel: string;
  /** 是否叠加了标签筛选（空态文案分支） */
  hasTagFilter: boolean;
}>();

const emit = defineEmits<{
  (e: "open-group-items"): void;
}>();
</script>

<template>
  <div class="watchlist-empty-overlay">
    <!-- 空白自定义分组：虚线「+ 从全部自选添加」快捷入口（#987） -->
    <template v-if="isEmptyCustomGroup">
      <button
        type="button"
        class="empty-add-btn"
        @click="emit('open-group-items')"
      >
        <el-icon><Plus /></el-icon>
        从全部自选添加
      </button>
      <p class="watchlist-empty__hint">
        把已有自选归入「{{ activeGroupLabel }}」
      </p>
    </template>
    <template v-else>
      <p class="watchlist-empty__title">
        {{ hasTagFilter ? "暂无匹配所选标签的持仓" : "暂无自选资产" }}
      </p>
      <p v-if="hasTagFilter" class="watchlist-empty__hint">
        试试调整或清空标签筛选条件
      </p>
    </template>
  </div>
</template>

<style scoped>
/* 覆盖在 .watchlist-table-wrap 上、铺满表格区并让文案垂直居中：
   空态时表格仍渲染表头（吸顶正常），数据行为 0，下方整段区域由本层占住——
   视觉上「暂无自选资产」位于卡片中部，footer 经 .watchlist-card flex:1 +
   margin-top:auto 沉到视口底，不再出现「文案靠上 + footer 悬在中间」的观感。 */
.watchlist-empty-overlay {
  /* 覆盖整张 el-table（含表头）：空态时没有数据行，列名与表头底边框没有意义，
     反而会在文案上方形成一条「怪异分割线」。overlay 从 top:0 铺满并用卡片色背景
     盖住表头/空体。z-index 需高于表头（header z-index:3）才能盖住其底边线。 */
  position: absolute;
  inset: 0;
  z-index: 6;
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
  justify-content: center;
  padding: 32px 0;
  background-color: var(--bg-card);
}

.watchlist-empty__title {
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-secondary);
}

.watchlist-empty__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 空白自定义分组的虚线「+ 从全部自选添加」入口（issue #987）。
   虚线框表达「可填充的占位区」而非阻断性空态，与表格内「＋ 标签」
   虚线按钮（columnRenderers.css .add-tag-btn）同一视觉语言。
   选中态/hover 转为品牌色实线，明确可点。 */
.empty-add-btn {
  display: inline-flex;
  gap: var(--space-2);
  align-items: center;
  padding: 8px 16px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  cursor: pointer;
  background-color: transparent;
  border: 1px dashed var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.empty-add-btn:hover {
  color: var(--brand-700);
  background-color: var(--brand-100);
  border-color: var(--brand-400);
  border-style: solid;
}

.empty-add-btn:focus-visible {
  outline: 1px solid var(--brand-400);
  outline-offset: 2px;
}
</style>
