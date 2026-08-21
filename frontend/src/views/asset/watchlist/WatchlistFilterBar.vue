<script setup lang="ts">
/* eslint-disable vue/no-mutating-props -- 状态注入模式：groups/tags/toolbar 为 composable 实例 prop，
   经 computed get/set 桥接修改其内部 ref 属有意设计（与 WatchlistToolbar 同模式） */
import { computed, ref } from "vue";
import { Folder, Plus } from "@element-plus/icons-vue";
import GroupFormDialog from "@/components/Watchlist/GroupFormDialog.vue";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import type { useWatchlistTags } from "@/composables/useWatchlistTags";
import type { WatchlistToolbarState } from "@/composables/useWatchlistData";
import type { WatchlistTag } from "@/api/watchlist";
import { DEFAULT_TAG_COLOR } from "@/constants/watchlist";

/**
 * 自选筛选条（分组胶囊 Tab + 标签筛选 + 视图 Segmented），从 index.vue 顶部区块抽出（2026-08-20）。
 * 2026-08-21 重构：分组 Tab 与标签筛选 / 视图 segmented 合并为单行三段式
 * （左固定筛选 + 中段 tab 横向滚动 + 右固定「+」），与 design.md 分组胶囊 Tab
 * 「tab 左对齐 + 右侧 segmented」布局规范一致（规范 414），省去独立筛选行。
 * 纯展示 + 事件转发：状态全部在 groups / tags / toolbar 三个 composable，本组件不持有业务状态。
 */
const props = defineProps<{
  groups: ReturnType<typeof useWatchlistGroups>;
  tags: ReturnType<typeof useWatchlistTags>;
  toolbar: WatchlistToolbarState;
  onRefresh: () => void;
}>();

const emit = defineEmits<{
  (e: "view-change"): void;
  (e: "tag-apply"): void;
  (e: "tag-clear"): void;
  (e: "manage-groups"): void;
}>();

// 状态注入模式：groups / tags / toolbar 为 composable 实例 prop，
// 双向绑定经 computed get/set 桥接其内部 ref（避免 vue/no-mutating-props）
const activeGroupModel = computed({
  get: () => props.groups.activeGroup.value,
  set: (value: string) => {
    props.groups.activeGroup.value = value;
  }
});
const allGroups = computed(() => props.groups.allGroups.value);
const tagFilterVisibleModel = computed({
  get: () => props.tags.tagFilterVisible.value,
  set: (value: boolean) => {
    props.tags.tagFilterVisible.value = value;
  }
});
const draftFilterTagIdsModel = computed({
  get: () => props.tags.draftFilterTagIds.value,
  set: (value: number[]) => {
    props.tags.draftFilterTagIds.value = value;
  }
});
const allTags = computed(() => props.tags.allTags.value);
const currentViewModel = computed({
  get: () => props.toolbar.currentView.value,
  set: (value: "all" | "exchange" | "otc") => {
    props.toolbar.currentView.value = value;
  }
});
const selectedTagCount = computed(
  () => props.tags.selectedFilterTagIds.value.length
);

const addDialogVisible = ref(false);

// 标签筛选胶囊：点击切换草稿选中态（与「管理标签」的颜色胶囊同语言）
function toggleDraftTag(id: number) {
  const idx = draftFilterTagIdsModel.value.indexOf(id);
  if (idx >= 0) draftFilterTagIdsModel.value.splice(idx, 1);
  else draftFilterTagIdsModel.value.push(id);
}

// 一键重置：清空草稿并提交（applyTagFilter 提交空数组即清除标签筛选），关闭面板
function resetFilter() {
  draftFilterTagIdsModel.value = [];
  emit("tag-apply");
  tagFilterVisibleModel.value = false;
}

/** 胶囊颜色：标签色为底（12% 透明度）+ 同色字 + 同色边框（数据色例外，缺失回退 DEFAULT_TAG_COLOR）。
 *  与 TagManagerDialog.pillStyle 保持同一套颜色语言。 */
function chipStyle(tag: WatchlistTag) {
  const c = tag.color || DEFAULT_TAG_COLOR;
  return {
    "--chip-color": c,
    "--chip-bg": `${c}1f`,
    "--chip-border": c
  } as Record<string, string>;
}
</script>

<template>
  <div class="filter-bar">
    <!-- 单行布局：分组 Tab（主导航，弹性横向滚动）居左 + 次级操作（标签筛选 / 视图 segmented / 新建）固定居右 -->
    <div class="filter-row">
      <!-- 左段（弹性）：分组胶囊 Tab（design.md「分组胶囊 Tab · 方案 B」，水平滑动、数量徽章 tabular-nums） -->
      <div class="group-tabs-scroll">
        <button
          v-for="g in allGroups"
          :key="g.key"
          type="button"
          class="group-tab"
          :class="{ 'is-active': g.key === activeGroupModel }"
          :title="g.label"
          @click="activeGroupModel = g.key"
        >
          <!-- 分组色点：用户数据色（非设计令牌），缺失回退中性 token（数据色例外） -->
          <span
            v-if="g.color"
            class="group-tab-dot"
            :style="{ backgroundColor: g.color }"
          />
          <span class="group-tab-label">{{ g.label }}</span>
          <span
            v-if="g.count > 0"
            class="group-tab-count"
            :style="{
              /* 分组/标签色为用户数据（非设计令牌），缺失回退中性 token（数据色例外） */
              color: g.color ? g.color : undefined
            }"
          >
            {{ g.count }}
          </span>
        </button>

        <!-- 新建分组「+」+ 管理分组「📁」：紧跟所有分组名末尾，分组操作聚在一起（随分组一起滚动） -->
        <el-button
          v-if="!toolbar.batchMode.value"
          class="group-tab-add"
          circle
          aria-label="新建分组"
          @click="addDialogVisible = true"
        >
          <el-icon><Plus /></el-icon>
        </el-button>
        <el-tooltip
          v-if="!toolbar.batchMode.value"
          content="管理分组"
          placement="bottom"
        >
          <el-button
            class="manage-groups-btn"
            circle
            aria-label="管理分组"
            @click="emit('manage-groups')"
          >
            <el-icon><Folder /></el-icon>
          </el-button>
        </el-tooltip>
      </div>

      <!-- 右段（固定）：标签筛选 + 视图 segmented，不随分组 tab 滚动 -->
      <div class="filter-bar__right">
        <!-- 标签筛选（bottom-start 左对齐触发按钮，减少浮层错位感） -->
        <el-popover
          :visible="tagFilterVisibleModel"
          placement="bottom-start"
          :width="260"
          title="按标签筛选"
        >
          <template #reference>
            <el-button
              class="tag-filter-btn"
              @click="
                tags.onTagFilterShow();
                tagFilterVisibleModel = true;
              "
            >
              标签筛选<template v-if="selectedTagCount">
                ({{ selectedTagCount }})
              </template>
            </el-button>
          </template>
          <div class="tag-filter-panel">
            <!-- 标签筛选胶囊（多选）：标签色为底 + 色点 + 名称，与「管理标签」/表格内标签胶囊同一颜色语言 -->
            <div class="tag-filter-chips">
              <button
                v-for="t in allTags"
                :key="t.id"
                type="button"
                class="tag-filter-chip"
                :class="{
                  'is-selected': draftFilterTagIdsModel.includes(t.id)
                }"
                :style="chipStyle(t)"
                @click="toggleDraftTag(t.id)"
              >
                <span
                  class="tag-filter-chip__dot"
                  :style="{
                    backgroundColor: t.color || undefined
                  }"
                />
                {{ t.name }}
              </button>
              <p v-if="allTags.length === 0" class="tag-filter-empty">
                暂无标签，可在「管理」中新建
              </p>
            </div>
            <div class="flex items-center justify-between mt-3">
              <el-button size="small" text type="primary" @click="resetFilter">
                重置筛选
              </el-button>
              <div class="flex gap-2">
                <el-button size="small" @click="tagFilterVisibleModel = false">
                  取消
                </el-button>
                <el-button
                  size="small"
                  type="primary"
                  @click="emit('tag-apply')"
                >
                  确定
                </el-button>
              </div>
            </div>
          </div>
        </el-popover>

        <!-- 视图 segmented：全部 / 场内 / 场外（venue 维度，一级筛选胶囊） -->
        <el-segmented
          v-model="currentViewModel"
          class="view-segmented"
          :options="[
            { label: '全部', value: 'all' },
            { label: '场内', value: 'exchange' },
            { label: '场外', value: 'otc' }
          ]"
          @change="emit('view-change')"
        />
      </div>
    </div>

    <!-- 新建分组弹窗 -->
    <GroupFormDialog v-model="addDialogVisible" @saved="onRefresh" />
  </div>
</template>

<style scoped>
.filter-bar {
  margin-bottom: 12px;
}

/* 单行布局：左段分组 tab 弹性滚动 + 右段次级操作固定（design.md 分组胶囊 Tab 布局，规范 414） */
.filter-row {
  display: flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

/* 右段：标签筛选 + 视图 segmented + 新建分组，固定不参与 tab 滚动；
   子项统一 32px 高并垂直居中，保证下拉浮层弹出前后行内元素始终同一条直线 */
.filter-bar__right {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

.filter-bar__right > * {
  flex-shrink: 0;
}

.filter-bar__right :deep(.el-popover__reference),
.filter-bar__right :deep(.el-popover) {
  display: inline-flex;
  align-items: center;
}

/* 标签筛选按钮：32px 胶囊，与分组 tab / segmented 同高（浅色 soft 按钮，未选中 --text-secondary） */
.tag-filter-btn {
  height: 32px;
  padding: 0 12px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease,
    border-color 150ms ease;
}

.tag-filter-btn:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

/* ===== 分组胶囊 Tab（design.md「分组胶囊 Tab · 方案 B」2026-08-14，数值与 index.vue 原实现逐值对齐） ===== */

/* 横向滚动条细化为 --border-light 色 */
.group-tabs-scroll {
  display: flex;
  flex: 1;
  gap: 4px;
  align-items: center;
  min-width: 0;
  overflow-x: auto;
  scrollbar-color: var(--border-light) transparent;
  scrollbar-width: thin;
}

.group-tabs-scroll::-webkit-scrollbar {
  height: 4px;
}

.group-tabs-scroll::-webkit-scrollbar-thumb {
  background-color: var(--border-light);
  border-radius: var(--radius-pill);
}

.group-tabs-scroll::-webkit-scrollbar-track {
  background: transparent;
}

/* tab 项：32px 胶囊；选中态软按钮（--brand-100/--brand-700/--brand-400），未选中 --text-secondary + hover --bg-hover */
.group-tab {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 32px;
  padding: 0 12px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  white-space: nowrap;
  cursor: pointer;
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease,
    border-color 150ms ease;
}

.group-tab:hover {
  background-color: var(--bg-hover);
}

.group-tab.is-active {
  color: var(--brand-700);
  background-color: var(--brand-100);
  border-color: var(--brand-400);
}

.group-tab.is-active:hover {
  background-color: var(--brand-200);
}

/* 分组色点：用户数据色常驻可见（数据色例外），选中态软按钮品牌色不受影响 */
.group-tab-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* 分组名：展示截断 8 汉字（8em），全名由 title 提示 */
.group-tab-label {
  max-width: 8em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-tab-count {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
}

.group-tab.is-active .group-tab-count {
  color: var(--brand-700);
}

/* 新建分组按钮：与分组 tab 同高 32px 的圆形（原文字按钮，2026-08-21 简化为「+」图标） */
.group-tab-add {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  padding: 0;
  color: var(--text-tertiary);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: 50%;
  transition:
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.group-tab-add:hover {
  color: var(--text-secondary);
  background-color: var(--bg-hover);
}

/* 管理分组按钮：32px 圆角胶囊图标，与标签筛选/分组 tab 同高（文件夹图标 = 分组管理语义，非通用齿轮） */
.manage-groups-btn {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  padding: 0;
  color: var(--text-tertiary);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.manage-groups-btn:hover {
  color: var(--brand-700);
  background-color: var(--bg-hover);
}

/* ===== 视图 segmented（全部/场内/场外）：一级筛选胶囊，与分组 tab 同高 32px（design.md「Filter & Selection」） ===== */
.view-segmented :deep(.el-segmented) {
  height: 32px;
  padding: 2px;
  background-color: var(--bg-muted);
  border-radius: var(--radius-pill);
  box-shadow: none;
}

/* item 均分铺满 + 文字居中：EP 选中背景是 JS 绝对定位块，item 不 flex 会错位（胖/偏左） */
.view-segmented :deep(.el-segmented__group) {
  display: flex;
  width: 100%;
}

.view-segmented :deep(.el-segmented__item) {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  height: 28px;
  padding: 0 14px;
  font-size: var(--text-label);
  line-height: 28px;
  color: var(--text-secondary);
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease;
}

.view-segmented :deep(.el-segmented__item:hover) {
  color: var(--text-primary);
}

.view-segmented :deep(.el-segmented__item.is-selected) {
  color: var(--brand-700);
  background-color: var(--brand-100);
  box-shadow: none;
}

.view-segmented :deep(.el-segmented__item.is-selected:hover) {
  background-color: var(--brand-200);
}

/* EP 选中态背景是独立子元素（默认白底+阴影），一并覆盖为品牌软按钮色 */
.view-segmented :deep(.el-segmented__item-selected) {
  background-color: var(--brand-100);
  border-radius: var(--radius-pill);
  box-shadow: none;
}

.view-segmented
  :deep(.el-segmented__item.is-selected:hover .el-segmented__item-selected) {
  background-color: var(--brand-200);
}

.tag-filter-panel {
  max-height: 240px;
  overflow-y: auto;
}

/* 标签筛选胶囊组：flex 换行，多选胶囊（与「管理标签」颜色胶囊同语言） */
.tag-filter-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* 胶囊：默认中性（--bg-muted + 灰点），选中态以标签色为底（--chip-bg/--chip-color/--chip-border 由 chipStyle 注入） */
.tag-filter-chip {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 28px;
  padding: 0 12px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  background-color: var(--bg-muted);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease,
    border-color 150ms ease;
}

.tag-filter-chip:hover {
  background-color: var(--bg-hover);
}

.tag-filter-chip.is-selected {
  color: var(--chip-color);
  background-color: var(--chip-bg);
  border-color: var(--chip-border);
}

.tag-filter-chip__dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  background-color: var(--text-tertiary);
  border-radius: 50%;
}

.tag-filter-empty {
  margin: 4px 0;
  font-size: 12px;
  color: var(--text-tertiary);
}
</style>
