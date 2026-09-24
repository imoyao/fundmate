<template>
  <!-- 复杂筛选入口：合并「类型 / 标签」多选，以 500px 左右分栏 Popover 展示。
       按钮角标表达已生效条件数（0 时不显示）。
       trigger="click" + v-model:visible：EP 原生接管「点击外部 / Esc 自动收起」；
       点外部关闭不丢草稿：草稿仅在重新打开时由 watch 重置为已提交筛选。 -->
  <el-popover
    v-model:visible="visibleModel"
    trigger="click"
    placement="bottom-start"
    :width="500"
    popper-class="watchlist-filter-popper"
  >
    <template #reference>
      <el-button
        class="filter-entry-btn"
        :class="{ 'is-active': activeFilterCount > 0 }"
        aria-label="筛选自选列表"
      >
        <el-icon class="filter-entry-btn__icon"><Filter /></el-icon>
        筛选
        <span v-if="activeFilterCount" class="filter-entry-btn__count">
          {{ activeFilterCount }}
        </span>
      </el-button>
    </template>

    <!-- 面板主体（左导航 + 类型/标签草稿区）：拆分见 FilterPanelBody；
         底部操作栏经 #footer slot 嵌入其 .filter-panel__main 内（DOM 结构与原版一致） -->
    <FilterPanelBody
      :groups="groups"
      :tags="tags"
      :active-panel="activePanel"
      :draft-types="draftAssetTypes"
      :draft-tag-ids="draftFilterTagIdsModel"
      @update:active-panel="activePanel = $event"
      @toggle-type="toggleDraftType"
      @toggle-tag="toggleDraftTag"
    >
      <template #footer>
        <!-- 底部固定操作栏：重置 / 已选计数 / 取消 / 确定 永远可见 -->
        <div class="filter-panel__footer">
          <el-button
            size="small"
            text
            type="primary"
            :disabled="!hasAnyFilter"
            @click="resetAllFilters"
          >
            重置
          </el-button>
          <span class="filter-panel__count">
            已选 {{ draftFilterCount }} 项
          </span>
          <div class="flex gap-2">
            <el-button size="small" @click="visibleModel = false">
              取消
            </el-button>
            <!-- 确定：一次性提交「类型 + 标签」两组草稿；刷新只走一条路径，
                 避免标签 watch 与类型刷新叠加成两次请求（见 applyFilters 注释） -->
            <el-button size="small" type="primary" @click="applyFilters">
              确定
            </el-button>
          </div>
        </div>
      </template>
    </FilterPanelBody>
  </el-popover>
</template>

<script setup lang="ts">
/* eslint-disable vue/no-mutating-props -- 状态注入模式：groups/tags/toolbar 为 composable 实例 prop，
   经 computed get/set 桥接修改其内部 ref 属有意设计（与 WatchlistToolbar 同模式） */
import { computed, ref, watch } from "vue";
import { Filter } from "@element-plus/icons-vue";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import type { useWatchlistTags } from "@/composables/useWatchlistTags";
import type { WatchlistToolbarState } from "@/composables/useWatchlistData";
import FilterPanelBody from "@/views/asset/watchlist/components/FilterPanelBody.vue";

/**
 * 「筛选」弹层（#980 P0-b 拆分自 WatchlistFilterBar，零行为变更）：
 * 类型 + 标签两组多选草稿，打开时同步已生效筛选，点「确定」一次性提交。
 * 草稿真源与提交逻辑（applyFilters 单路径）内聚在本组件；面板展示区拆至
 * FilterPanelBody。状态经 groups / tags / toolbar 三个 composable 实例注入。
 */
const props = defineProps<{
  groups: ReturnType<typeof useWatchlistGroups>;
  tags: ReturnType<typeof useWatchlistTags>;
  toolbar: WatchlistToolbarState;
}>();

const emit = defineEmits<{
  /**
   * 「筛选」面板确定：类型 + 标签两组草稿均已提交，请父页面按新条件刷新列表。
   * 仅在「标签未变化、只有类型变化」时触发——标签变化由 useWatchlistData 的
   * watch(selectedFilterTagIds) 自动置第 1 页并刷新，两者同时触发会打两次请求。
   */
  (e: "filter-apply"): void;
}>();

// 状态注入模式：tags/toolbar 内部 ref 经 computed get/set 桥接（避免 vue/no-mutating-props）
const visibleModel = computed({
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
const selectedTagCount = computed(
  () => props.tags.selectedFilterTagIds.value.length
);
const selectedAssetTypesModel = computed({
  get: () => props.toolbar.selectedAssetTypes.value,
  set: (value: string[]) => {
    props.toolbar.selectedAssetTypes.value = value;
  }
});

// Popover 内当前激活的分类面板：产品类型 / 资产标签
const activePanel = ref<"type" | "tag">("type");

// 类型草稿。与标签草稿同一节奏：打开「筛选」面板时同步已生效筛选，点「确定」才提交。
// 面板开合统一由 visibleModel 承担（类型与标签本就是同一个面板，见下方 watch）。
const draftAssetTypes = ref<string[]>([]);

function toggleDraftType(type: string) {
  const idx = draftAssetTypes.value.indexOf(type);
  if (idx >= 0) draftAssetTypes.value.splice(idx, 1);
  else draftAssetTypes.value.push(type);
}

// 标签筛选胶囊：点击切换草稿选中态（与「管理标签」的颜色胶囊同语言）
function toggleDraftTag(id: number) {
  const idx = draftFilterTagIdsModel.value.indexOf(id);
  if (idx >= 0) draftFilterTagIdsModel.value.splice(idx, 1);
  else draftFilterTagIdsModel.value.push(id);
}

/** 已生效的筛选条件数（类型 + 标签）：用于筛选入口按钮的角标 */
const activeFilterCount = computed(
  () => selectedAssetTypesModel.value.length + selectedTagCount.value
);

/** Popover 内草稿状态的已选计数：用于底部操作栏实时反馈 */
const draftFilterCount = computed(
  () => draftAssetTypes.value.length + draftFilterTagIdsModel.value.length
);

/** 是否有「已生效」或「草稿中」的条件：决定面板内「重置」是否可用 */
const hasAnyFilter = computed(
  () =>
    activeFilterCount.value > 0 ||
    draftAssetTypes.value.length > 0 ||
    draftFilterTagIdsModel.value.length > 0
);

// 打开「筛选」面板时把已生效筛选同步到两组草稿（类型 + 标签）。
// 原触发按钮 @click 内的 onTagFilterShow 迁移至此：trigger="click" 后开合由 EP 接管，
// 组件不再经手打开动作。
watch(visibleModel, visible => {
  if (!visible) return;
  activePanel.value = "type";
  props.tags.onTagFilterShow();
  draftAssetTypes.value = [...selectedAssetTypesModel.value];
});

/**
 * 「确定」：一次性提交类型 + 标签两组草稿并关闭面板。
 *
 * 刷新只走**一条**路径，避免重复请求：
 * - 标签有变化 → useWatchlistData 内部 `watch(selectedFilterTagIds)` 会自动置第 1 页并刷新
 *   （类型已先写入，刷出来的就是新条件）；
 * - 只有类型变化 → 标签 watch 不触发，补发 `filter-apply` 让页面刷新；
 * - 两者都没变 → 只关面板，不打请求。
 */
function applyFilters() {
  const beforeTags = [...props.tags.selectedFilterTagIds.value]
    .sort()
    .join(",");
  const beforeTypes = [...selectedAssetTypesModel.value].sort().join(",");

  selectedAssetTypesModel.value = [...draftAssetTypes.value];
  props.tags.selectedFilterTagIds.value = [...draftFilterTagIdsModel.value];
  visibleModel.value = false;

  const tagsChanged =
    [...props.tags.selectedFilterTagIds.value].sort().join(",") !== beforeTags;
  const typesChanged =
    [...selectedAssetTypesModel.value].sort().join(",") !== beforeTypes;
  if (!tagsChanged && typesChanged) emit("filter-apply");
}

/** 一键重置：清空两组草稿后走同一条提交路径（清空即清除筛选），并关闭面板 */
function resetAllFilters() {
  draftAssetTypes.value = [];
  draftFilterTagIdsModel.value = [];
  applyFilters();
}
</script>

<style scoped>
/* 筛选入口按钮：32px 胶囊，与分组 tab / segmented 同高。
   默认 1px 描边（--border-default）把控件从卡片底色里「立」起来；
   有生效条件时转品牌软底 + 品牌描边 + 数字角标（见 .is-active）。
   关于描边/阴影的取舍（2026-09-11 用户提问）：**只加描边，不加带色阴影**——
   design.md 的阴影是「层级浮起」语义（card / popover / modal），把彩色阴影挂到胶囊上
   属装饰性阴影，与「克制」冲突；描边则是设计语言里既有的构件边界
   （Input / 软按钮 / ProductDisplay 的类型胶囊都在用）。 */
.filter-entry-btn {
  display: inline-flex;
  gap: 4px;
  align-items: center;
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

.filter-entry-btn:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

.filter-entry-btn.is-active {
  font-weight: 500;
  color: var(--brand-700);
  background-color: var(--brand-100);
  border-color: var(--brand-400);
}

.filter-entry-btn__icon {
  font-size: 14px;
}

/* 条件数角标：品牌实底 + 卡片色字，16px 胶囊（与分组 tab 的数量徽章同为「数字角标」语言） */
.filter-entry-btn__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  color: var(--text-inverse);
  background-color: var(--brand-solid);
  border-radius: var(--radius-pill);
}

/* 底部固定操作栏：重置 / 已选计数 / 取消 / 确定 永远可见
   （样式随模板自 FilterPanelBody 原样迁回此处，保持 scoped 作用域不变，零视觉变更） */
.filter-panel__footer {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-top: 1px solid var(--border-light);
}

.filter-panel__count {
  flex: 1;
  padding: 0 12px;
  font-size: 13px;
  color: var(--text-secondary);
  text-align: center;
}
</style>
