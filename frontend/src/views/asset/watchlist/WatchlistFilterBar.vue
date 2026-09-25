<script setup lang="ts">
/* eslint-disable vue/no-mutating-props -- 状态注入模式：groups/tags/toolbar 为 composable 实例 prop，
   经 computed get/set 桥接修改其内部 ref 属有意设计（与 WatchlistToolbar 同模式） */
import { computed, ref } from "vue";
import { Files, Folder, Plus } from "@element-plus/icons-vue";
import GroupFormDialog from "@/components/Watchlist/GroupFormDialog.vue";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import type { useWatchlistTags } from "@/composables/useWatchlistTags";
import type { WatchlistToolbarState } from "@/composables/useWatchlistData";
import { assetTypeLabel } from "@/composables/useEnumLabels";
import FilterGroupTabs from "@/views/asset/watchlist/components/FilterGroupTabs.vue";
import FilterPanelPopover from "@/views/asset/watchlist/components/FilterPanelPopover.vue";

/**
 * 自选筛选条（分组胶囊 Tab + 标签筛选 + 视图 Segmented），从 index.vue 顶部区块抽出（2026-08-20）。
 * 2026-08-21 重构：分组 Tab 与标签筛选 / 视图 segmented 合并为单行三段式
 * （左固定筛选 + 中段 tab 横向滚动 + 右固定「+」），与 design.md 分组胶囊 Tab
 * 「tab 左对齐 + 右侧 segmented」布局规范一致（规范 414），省去独立筛选行。
 * 2026-09-05 修订：原 #actions 快捷图标组（刷新/导出/AI导入/实时估值）上移至
 * index.vue 第一行 .head-primary，本行收窄为纯筛选职责，不再拥挤。
 * 2026-09-24 拆分（#980 P0-b）：分组 Tab 横滑区 → FilterGroupTabs，
 * 「筛选」Popover 弹层（含两组草稿状态）→ FilterPanelPopover，本组件只做编排。
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
  /**
   * 「筛选」面板确定（由 FilterPanelPopover 上抛）：仅在「标签未变化、只有类型变化」
   * 时触发——标签变化由 useWatchlistData 的 watch(selectedFilterTagIds) 自动刷新，
   * 两者同时触发会打两次请求。
   */
  (e: "filter-apply"): void;
  /** 管理分组本身（新建/改名/删除）→ GroupManagerDialog */
  (e: "manage-groups"): void;
  /** #987：管理当前自定义分组「里有哪些产品」→ GroupItemsDialog */
  (e: "manage-group-items"): void;
}>();

// 状态注入模式：selectedAssetTypes 为 composable 内部 ref，
// 双向绑定经 computed get/set 桥接其内部 ref（避免 vue/no-mutating-props）
const selectedAssetTypesModel = computed({
  get: () => props.toolbar.selectedAssetTypes.value,
  set: (value: string[]) => {
    props.toolbar.selectedAssetTypes.value = value;
  }
});

// ── 类型快捷 segmented（主界面单选快捷；弹层多选在 FilterPanelPopover）──
// 主界面「类型快捷 segmented」（全部/股票/基金/ETF/可转债）为单维度快速切换（单选覆盖式）；
// 与「筛选」Popover 的多选正交：组合筛选仍走 Popover。
// venue（场内/场外）维度 2026-09-12 已从主界面移除：普通用户对场内/场外心智门槛高，
// 且与类型维度重叠；当前 toolbar.currentView 恒为 'all'，后端不过滤 venue（见 useWatchlistData）。
// 中文 label 走 assetTypeLabel（后端 /enums/asset_type 唯一真相源，禁止手抄映射），
// 「可转债」对应资产类型 bond（useEnumLabels 已映射）。
const QUICK_TYPES = [
  { label: assetTypeLabel("stock"), value: "stock" },
  { label: assetTypeLabel("fund"), value: "fund" },
  { label: assetTypeLabel("etf"), value: "etf" },
  { label: assetTypeLabel("bond"), value: "bond" }
] as const;

// segmented 选项含「全部」（清除类型筛选），其余为高频类型。
const TYPE_SEGMENTED_OPTIONS = [
  { label: "全部", value: "all" },
  ...QUICK_TYPES
] as const;

/**
 * 当前单选激活项派生：
 * - 无类型筛选 → 'all'（高亮「全部」）；
 * - 恰好单选一个高频类型 → 该类型；
 * - 多选 / 选了 Popover 里的其它类型 → ''（无高亮，组合态，看「筛选」角标）。
 */
const quickActive = computed<string>(() => {
  const t = selectedAssetTypesModel.value;
  if (t.length === 0) return "all";
  if (t.length === 1 && QUICK_TYPES.some(q => q.value === t[0])) return t[0];
  return "";
});

/**
 * 主界面类型快捷入口（单选覆盖式）：点击即设置该类型为唯一生效筛选并刷新列表；
 * 再次点击当前项 → 取消回「全部」；「全部」→ 清空类型筛选。
 * 与 Popover 内多选正交：此处只能单维度，复杂组合进 Popover。
 *
 * 注（#980 P0-b 拆分等价性）：原实现此处还会把类型草稿 draftAssetTypes 同步为新值，
 * 拆分后草稿状态内聚在 FilterPanelPopover——点击 segmented 属「点击弹层外部」，
 * EP（trigger=click）会收起弹层，草稿于下次打开时由 watch 重置为已提交筛选，
 * 可见行为与原先一致，故不再跨组件写草稿。
 */
function selectQuickType(value: string) {
  if (value === "all") {
    if (selectedAssetTypesModel.value.length === 0) return;
    selectedAssetTypesModel.value = [];
  } else if (
    selectedAssetTypesModel.value.length === 1 &&
    selectedAssetTypesModel.value[0] === value
  ) {
    selectedAssetTypesModel.value = [];
  } else {
    selectedAssetTypesModel.value = [value];
  }
  emit("filter-apply");
}

const addDialogVisible = ref(false);
</script>

<template>
  <div class="filter-bar">
    <!-- 筛选行（双行分区布局的「第二行」，见 index.vue head-primary 注释）：
         分组 Tab（主导航，弹性横向滚动，永远最左）
         + 次级操作（新建分组 / 管理分组 / 标签筛选 / 视图 segmented）
         （#actions 快捷图标组已于 2026-09-05 上移第一行 head-primary，本行保持纯筛选）

         批量模式（batchMode）：分组与筛选整体隐藏（批量工具条占用第一行），
         避免表格上方出现两排状态不同的操作。 -->
    <div v-if="!toolbar.batchMode.value" class="filter-row">
      <!-- 左段（弹性）：分组胶囊 Tab（拆分见 FilterGroupTabs） -->
      <FilterGroupTabs :groups="groups" />

      <!-- 右段（固定）：分组操作 + 类型快捷 + 复杂筛选入口，不随分组 tab 滚动 -->
      <div class="filter-bar__right">
        <!-- 新建分组「+」+ 管理分组「📁」：固定展示，避免分组过多时被挤进滚动区 -->
        <el-button
          class="group-tab-add"
          circle
          aria-label="新建分组"
          @click="addDialogVisible = true"
        >
          <el-icon><Plus /></el-icon>
        </el-button>
        <el-tooltip content="管理分组" placement="bottom">
          <el-button
            class="manage-groups-btn"
            circle
            aria-label="管理分组"
            @click="emit('manage-groups')"
          >
            <el-icon><Folder /></el-icon>
          </el-button>
        </el-tooltip>
        <!-- 「管理本组产品」：仅当前选中自定义分组时出现（issue #987）。
             与上方「管理分组」（管分组本身的新建/改名/删除）是两件事——本入口
             管「这个组里有哪些产品」，系统分组由后端规律维护故不展示。 -->
        <el-tooltip
          v-if="groups.currentIsCustom.value"
          content="管理本组产品"
          placement="bottom"
        >
          <el-button
            class="manage-group-items-btn"
            circle
            aria-label="管理本组产品"
            @click="emit('manage-group-items')"
          >
            <el-icon><Files /></el-icon>
          </el-button>
        </el-tooltip>
        <div class="right-divider" />

        <!-- 类型快捷 segmented：全部 / 股票 / 基金 / ETF / 可转债（单选覆盖式）。
             手写分段控制器（弃用 el-segmented：JS 绝对定位滑块与自定义尺寸错位，
             见 OcrImportModal 同款决策）；选中态仅浅红底 + 深红字。
             与「筛选」Popover 多选正交：此处单维度快速切换，组合仍走 Popover。 -->
        <div class="type-segmented" role="tablist" aria-label="类型快捷筛选">
          <button
            v-for="opt in TYPE_SEGMENTED_OPTIONS"
            :key="opt.value"
            type="button"
            role="tab"
            class="type-segmented__item"
            :class="{ 'is-active': quickActive === opt.value }"
            :aria-selected="quickActive === opt.value"
            @click="selectQuickType(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>

        <!-- 复杂筛选入口 + 弹层（拆分见 FilterPanelPopover） -->
        <FilterPanelPopover
          :groups="groups"
          :tags="tags"
          :toolbar="toolbar"
          @filter-apply="emit('filter-apply')"
        />
      </div>
    </div>

    <!-- 新建分组弹窗 -->
    <GroupFormDialog v-model="addDialogVisible" @saved="onRefresh" />
  </div>
</template>

<style scoped>
.filter-bar {
  /* design.md「表格/列表/筛选栏：--space-compact(16px)」在卡片外层生效；
     此处为卡内子区块间距，取 12px（--space-3）。
     （2026-09-06 呼吸感回调：曾收紧到 6px 为表格让首屏行数，实测与上方搜索行、
     下方表头三带贴合成一条、分区层级丢失；回到 12px 后筛选带与表格区边界清晰。
     注意：margin 不计入 offsetHeight，故表头吸顶偏移 --watchlist-sticky-top
     仍等于本元素 offsetHeight，吸顶无缝衔接不受本值影响。） */
  margin-bottom: var(--space-3);
}

/* 行布局：分组 tab（弹性滚动）+ 次级操作 + #actions 快捷图标组
   （design.md 分组胶囊 Tab 布局，规范 414）
   flex-wrap: wrap 兜底：窄屏（<1280）放不下时自动换行，宁可高一点也不挤压溢出。 */
.filter-row {
  display: flex;
  flex-wrap: wrap;
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

/* 右段分隔线：分组操作 与 标签/视图 之间的视觉分隔 */
.right-divider {
  width: 1px;
  height: 20px;
  margin: 0 4px;
  background-color: var(--border-default);
}

.filter-bar__right :deep(.el-popover__reference),
.filter-bar__right :deep(.el-popover) {
  display: inline-flex;
  align-items: center;
}

/* 新建分组按钮：原文字按钮简化为「+」图标（2026-08-21）。
   尺寸规范（2026-09-05）：纯图标按钮统一 28×28，与文字按钮（32）区分层级 */
.group-tab-add {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-tertiary-ink);
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

/* 管理分组按钮：文件夹图标 = 分组管理语义（非通用齿轮）。
   尺寸规范（2026-09-05）：纯图标按钮统一 28×28 */
.manage-groups-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-tertiary-ink);
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

/* 管理本组产品按钮（#987）：与「管理分组」同尺寸同语言（28×28 圆形线框），
   仅图标不同（多文件 = 组内产品清单，文件夹 = 分组本身），避免两个入口混淆 */
.manage-group-items-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-tertiary-ink);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  transition:
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease;
}

.manage-group-items-btn:hover {
  color: var(--brand-700);
  background-color: var(--bg-hover);
  border-color: var(--brand-400);
}

/* ===== 类型快捷分段控制器（全部/股票/基金/ETF/可转债）：手写，弃用 el-segmented =====
   与分组 tab 同高（轨道 32px）；item 统一几何尺寸，hover/选中仅底色深浅递进，
   文字 flex 居中；选中态仅浅红底 + 深红字，无边框 */
.type-segmented {
  display: flex;
  gap: 2px;
  height: 32px;
  padding: 3px;
  background-color: var(--bg-soft);

  /* 轨道补 1px 描边：与筛选入口按钮、面板内胶囊统一「构件边界」语言，
     避免一整条筛选带里只有分段控制器没有边界、显得糊在卡片底色上（2026-09-11）。
     注意：只在**轨道**上加描边；选中项仍保持「浅红软底 + 深红字、无边框」不变。 */
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
}

.type-segmented__item {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 26px;
  padding: 0 14px;
  font-size: var(--text-label);
  line-height: 1;
  color: var(--text-secondary);
  cursor: pointer;
  background-color: transparent;
  border: none;
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease;
}

/* 原生 button 点击后收掉浏览器默认 focus 外框；键盘导航保留细描边兜底 */
.type-segmented__item:focus {
  outline: none;
}

.type-segmented__item:focus-visible {
  outline: 1px solid var(--brand-400);
  outline-offset: 1px;
}

.type-segmented__item:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

.type-segmented__item.is-active {
  font-weight: 600;
  color: var(--brand-700);
  background-color: var(--brand-100);
}
</style>
