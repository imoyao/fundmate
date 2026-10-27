<script setup lang="ts">
/* eslint-disable vue/no-mutating-props -- 状态注入模式：groups/tags/toolbar 为 composable 实例 prop，
   经 computed get/set 桥接修改其内部 ref 属有意设计（与 WatchlistToolbar 同模式） */
import { computed, ref } from "vue";
import { Close } from "@element-plus/icons-vue";
import GroupFormDialog from "@/components/Watchlist/GroupFormDialog.vue";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import type { useWatchlistTags } from "@/composables/useWatchlistTags";
import type { WatchlistToolbarState } from "@/composables/useWatchlistData";
import { assetTypeLabel } from "@/composables/useEnumLabels";
import { useWatchlistQuickFilters } from "@/composables/useWatchlistQuickFilters";
import {
  buildQuickTypeOptions,
  nextQuickSelection,
  resolveQuickActiveValue,
  QUICK_TYPE_ALL
} from "@/views/asset/watchlist/quickTypeModel";
import FilterGroupTabs from "@/views/asset/watchlist/components/FilterGroupTabs.vue";
import FilterGroupActions from "@/views/asset/watchlist/components/FilterGroupActions.vue";
import QuickTypePills from "@/views/asset/watchlist/components/QuickTypePills.vue";
import FilterPanelPopover from "@/views/asset/watchlist/components/FilterPanelPopover.vue";
import QuickFilterConfigDialog from "@/views/asset/watchlist/components/QuickFilterConfigDialog.vue";

/**
 * 自选筛选条（分组胶囊 Tab + 类型快捷胶囊 + 标签筛选），从 index.vue 顶部区块抽出（2026-08-20）。
 * 2026-08-21 重构：分组 Tab 与标签筛选 / 视图 segmented 合并为单行三段式
 * （左固定筛选 + 中段 tab 横向滚动 + 右固定「+」），与 design.md 分组胶囊 Tab
 * 「tab 左对齐 + 右侧 segmented」布局规范一致（规范 414），省去独立筛选行。
 * 2026-09-05 修订：原 #actions 快捷图标组（刷新/导出/AI导入/实时估值）上移至
 * index.vue 第一行 .head-primary，本行收窄为纯筛选职责，不再拥挤。
 * 2026-09-24 拆分（#980 P0-b）：分组 Tab 横滑区 → FilterGroupTabs，
 * 「筛选」Popover 弹层（含两组草稿状态）→ FilterPanelPopover，本组件只做编排。
 * #2199 修订：类型快捷由 SegmentedControl 胶囊化为 QuickTypePills（选项用户
 * 自定义外显后可达 11 项，超分段器适用域，见 design.md「Filter & Selection」），
 * 并从右段抽出与分组区并列为两个弹性区（各限 max-width 50%，打架各自横滑兜底）。
 * 2026-10 拆分（#980 批 B2）：分组操作三按钮 → FilterGroupActions；类型快捷的
 * 两条派生规则（持仓收窄 / 单选覆盖式切换）→ quickTypeModel.ts 纯函数。
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
  /**
   * 「清除筛选」被点（#2199 ⑥）：清空类型 + 标签、分组切回「全部」并刷新，
   * 由 index.vue 接到 data.clearAllFilters（本组件不持有数据层，只转发意图）。
   */
  (e: "clear-filters"): void;
}>();

// 状态注入模式：selectedAssetTypes 为 composable 内部 ref，
// 双向绑定经 computed get/set 桥接其内部 ref（避免 vue/no-mutating-props）
const selectedAssetTypesModel = computed({
  get: () => props.toolbar.selectedAssetTypes.value,
  set: (value: string[]) => {
    props.toolbar.selectedAssetTypes.value = value;
  }
});

// ── 类型快捷胶囊栏（主界面单选快捷；弹层多选在 FilterPanelPopover）──
// 主界面「类型快捷胶囊栏」为单维度快速切换（单选覆盖式）；
// 外露哪些类型由用户偏好决定（#1449，user_preferences.watchlist_quick_filters 跨设备同步，
// 默认 stock/fund/etf/bond；股票、基金为 PINNED 常驻外显，#2199），「全部」恒为首项。
// #2199 胶囊化：用户自定义后选项可达 11 项（全部 + 10 类型），超出分段器
// 「选项少（2–6）、平铺」适用域，按 design.md「Filter & Selection」分水岭
// 切换为水平滑动胶囊栏（QuickTypePills），不再用 SegmentedControl。
// 与「筛选」Popover 的多选正交：组合筛选仍走 Popover。
// venue（场内/场外）维度 2026-09-12 已从主界面移除：普通用户对场内/场外心智门槛高，
// 且与类型维度重叠；当前 toolbar.currentView 恒为 'all'，后端不过滤 venue（见 useWatchlistData）。
// 中文 label 走 assetTypeLabel（后端 /enums/asset_type 唯一真相源，禁止手抄映射），
// 「可转债」对应资产类型 bond（useEnumLabels 已映射）。
const { quickFilters } = useWatchlistQuickFilters();

/**
 * 快捷胶囊选项：**持仓分组下收窄一层**（#2329）+「全部」恒为首项。
 * 收窄口径与「为什么收窄」的完整来龙去脉见 quickTypeModel.buildQuickTypeOptions
 * 与本目录 watchlistAssetTypes.ts 的 HOLDING_ASSET_TYPES。
 * 分工不变：本处只收窄可见选项，不改已生效的筛选状态（唯一写入点是 index.vue
 * 的 applyHoldingTypeConstraint）。
 */
const QUICK_TYPE_OPTIONS = computed(() =>
  buildQuickTypeOptions(
    quickFilters.value,
    props.groups.activeGroup.value === "holding",
    assetTypeLabel
  )
);

/** 当前单选激活项派生（多选 / 选了不可见类型 → '' 无高亮，见模型层注释） */
const quickActive = computed(() =>
  resolveQuickActiveValue(
    selectedAssetTypesModel.value,
    QUICK_TYPE_OPTIONS.value
  )
);

/**
 * 主界面类型快捷入口（单选覆盖式）：点击即设置该类型为唯一生效筛选并刷新列表；
 * 再次点击当前项 → 取消回「全部」；「全部」→ 清空类型筛选。
 * 与 Popover 内多选正交：此处只能单维度，复杂组合进 Popover。
 *
 * 注（#980 P0-b 拆分等价性）：原实现此处还会把类型草稿 draftAssetTypes 同步为新值，
 * 拆分后草稿状态内聚在 FilterPanelPopover——点击胶囊属「点击弹层外部」，
 * EP（trigger=click）会收起弹层，草稿于下次打开时由 watch 重置为已提交筛选，
 * 可见行为与原先一致，故不再跨组件写草稿。
 */
function selectQuickType(value: string) {
  // 「全部」在已无类型筛选时是空操作：不写状态也不刷新（原实现的早退，勿删）
  if (value === QUICK_TYPE_ALL && selectedAssetTypesModel.value.length === 0) {
    return;
  }
  selectedAssetTypesModel.value = nextQuickSelection(
    selectedAssetTypesModel.value,
    value
  );
  emit("filter-apply");
}

const addDialogVisible = ref(false);
/** 「自定义快捷筛选」弹窗（#1449，入口在「筛选」Popover 底部链接） */
const quickFilterDialogVisible = ref(false);

/**
 * 「清除筛选」显隐（#2199 ⑥）：类型或标签任一生效才显示（与「筛选」入口角标
 * activeFilterCount 同源，见 FilterPanelPopover）；分组切换不参与显隐——
 * 分组 Tab 高亮本身就是其状态提示，且「全部」也是可点的 Tab。
 *
 * 显隐方式（本版布局修复）：按钮**常驻 DOM**，仅切 .is-hidden（opacity/visibility），
 * 宽度槽位始终占据——出现/消失不再改变右段总宽，flex-wrap 换行只由容器宽度决定，
 * 施加/清除筛选时整行零重排（此前 v-if 条件渲染会把右段挤宽、触发弹性区换行，
 * 右段整体掉到第二行，即用户反馈的「施加筛选一瞬间页面跳动」）。
 */
const hasActiveQuickFilters = computed(
  () =>
    props.toolbar.selectedAssetTypes.value.length > 0 ||
    props.tags.selectedFilterTagIds.value.length > 0
);
</script>

<template>
  <div class="filter-bar">
    <!-- 筛选行（双行分区布局的「第二行」，见 index.vue head-primary 注释）：
         分组 Tab（主导航，弹性横向滚动，永远最左）
         + 分组操作（新建分组 / 管理分组）
         + 分区分隔线
         + 类型快捷胶囊栏（#2199 第二弹性区）
         + 复杂筛选入口（「筛选」Popover）
         （#actions 快捷图标组已于 2026-09-05 上移第一行 head-primary，本行保持纯筛选）

         批量模式（batchMode）：分组与筛选整体隐藏（批量工具条占用第一行），
         避免表格上方出现两排状态不同的操作。 -->
    <div v-if="!toolbar.batchMode.value" class="filter-row">
      <!-- 第一段（弹性）：分组胶囊 Tab（拆分见 FilterGroupTabs）。
           flex 参数内聚在 FilterGroupTabs 的 .group-tabs-wrap（min-width 120px 保底
           #1281 + max-width 50% 上限 #2199），此处不重复声明。 -->
      <FilterGroupTabs :groups="groups" />

      <!-- 分组操作三按钮（新建 / 管理分组 / 管理本组产品，拆分见 FilterGroupActions）：
           三个入口管的都是「分组」，同区同规格，紧接分组列表之后（#2354）。 -->
      <FilterGroupActions
        :can-manage-items="groups.currentIsCustom.value"
        @add="addDialogVisible = true"
        @manage-groups="emit('manage-groups')"
        @manage-group-items="emit('manage-group-items')"
      />

      <!-- 分区分隔线：分组导航（主导航）与类型快捷（筛选维度）之间的分区语言
           （design.md 分组胶囊 Tab「与筛选行用分割线分区」同款处理） -->
      <div class="zone-divider" aria-hidden="true" />

      <!-- 第二段（弹性）：类型快捷胶囊栏（#2199 胶囊化，「全部」+ 用户自定义外露类型，
           默认 全部/股票/基金/ETF/可转债；股票、基金为 PINNED 常驻外显）。
           与「筛选」Popover 多选正交：此处单维度快速切换，组合仍走 Popover。
           flex 参数内聚在 QuickTypePills 的 .quick-pills-wrap（与分组区同规格）。 -->
      <QuickTypePills
        :options="QUICK_TYPE_OPTIONS"
        :active-value="quickActive"
        @select="selectQuickType"
      />

      <!-- 第三段（固定）：清除筛选 + 复杂筛选入口，不随左侧两区滚动。
           （#2354：「管理本组产品」已按语义归入上一段分组操作区，本段只剩筛选维度，
           原先隔在它与清除筛选之间的 .right-divider 随之删除——无对象可隔的孤立竖线。） -->
      <div class="filter-bar__right">
        <!-- 清除筛选（#2199 ⑥ + 本版跳动修复）：类型 / 标签任一生效时才「可见」。
             用户实测痛点：面板勾了条件 + 点过分组 Tab 后无快捷清除入口，且分组
             切换不清类型条件（胶囊持续高亮）造成「条件残留」错觉。点击清空
             类型 + 标签、分组切回「全部」并刷新（接线见 index.vue → data.clearAllFilters）。

             形态改 28×28 正圆 × 图标（与 + / 📁 同规格）：design.md 尺寸梯度里
             纯图标按钮本就比 32px 文字按钮低一级，次级层级更清晰，不与「筛选」
             入口（描边胶囊 + 角标）抢层级；语义由 tooltip + aria-label 补足。
             关键约束：按钮**常驻 DOM**，无筛选时仅 .is-hidden 隐藏（只隐不撤）——
             槽位宽度恒占，出现/消失零宽度变化，右段不再因它变宽触发整行重排。 -->
        <el-tooltip content="清除筛选" placement="bottom">
          <el-button
            class="clear-filters-btn"
            :class="{ 'is-hidden': !hasActiveQuickFilters }"
            aria-label="清除筛选"
            @click="emit('clear-filters')"
          >
            <el-icon><Close /></el-icon>
          </el-button>
        </el-tooltip>

        <!-- 复杂筛选入口 + 弹层（拆分见 FilterPanelPopover）；
             底部「自定义快捷筛选」链接打开外露类型管理弹窗（#1449） -->
        <FilterPanelPopover
          :groups="groups"
          :tags="tags"
          :toolbar="toolbar"
          @filter-apply="emit('filter-apply')"
          @manage-quick-filters="quickFilterDialogVisible = true"
        />
      </div>
    </div>

    <!-- 新建分组弹窗 -->
    <GroupFormDialog v-model="addDialogVisible" @saved="onRefresh" />
    <!-- 快捷筛选外露类型管理（#1449）：与上方筛选条共享 useWatchlistQuickFilters 单例 -->
    <QuickFilterConfigDialog v-model="quickFilterDialogVisible" />
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

/* 行布局：分组胶囊 Tab（弹性滚动）+ 分组操作 + 类型快捷胶囊栏（弹性滚动）+ 筛选入口
   （design.md 分组胶囊 Tab 布局，规范 414；#2199 布局争夺方案；#2354 调整顺序）
   两个弹性区的 flex 参数内聚在各自组件根（.group-tabs-wrap / .quick-pills-wrap）：
   min-width 120px 保底（#1281：极端窄屏宁可换行也不挤没分组）+
   max-width 50% 上限（#2199：打架时两区各限约一半，各自横滑兜底）。
   flex-wrap: wrap 兜底：窄屏（<1280）放不下时自动换行，宁可高一点也不挤压溢出。 */
.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

/* 右段：清除筛选 / 「筛选」入口，固定不参与左侧两区滚动；
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

/* 分区分隔线（#2199）：分组导航 与 类型快捷胶囊栏 之间的视觉分隔，
   与右段分隔线同尺寸同色，保证行内两道分隔语言一致 */
.zone-divider {
  flex-shrink: 0;
  width: 1px;
  height: 20px;
  background-color: var(--border-default);
}

.filter-bar__right :deep(.el-popover__reference),
.filter-bar__right :deep(.el-popover) {
  display: inline-flex;
  align-items: center;
}

/* 「清除筛选」（#2199 ⑥ + 本版跳动修复）：次级 × 图标按钮（28×28 正圆，
   与 + / 📁 同规格；design.md 尺寸梯度：纯图标按钮 28×28 低于 32px 文字按钮一级，
   次级层级不与「筛选」入口抢层级）。颜色语言沿用原文字版：次要色起步、
   悬停升主文字色（与「筛选」Popover 底栏「重置」同层级），行内 align-items 与相邻控件共线。

   恒定槽位（跳动修复核心）：本按钮常驻 DOM，无筛选时进 .is-hidden（只隐不撤）——
   若沿用 v-if 条件渲染，按钮出现的瞬间右段变宽、超过容器余量，
   flex-wrap 会把整个右段（清除 / 筛选）甩到第二行，
   用户施加筛选的一瞬间页面跳动。占位恒定后，换行与否只取决于容器宽度，与筛选状态无关。 */
.clear-filters-btn {
  position: relative; /* ::after 热区的定位锚点（同 WatchlistHeadPrimary 的 icon-tool-btn） */
  box-sizing: border-box;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--text-secondary);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);

  /* visibility「0s 延迟 0」：恢复可见时立即参与渲染，opacity 负责淡入；
     淡出侧的延迟见下方 .is-hidden 的 transition（进入哪态用哪态的 transition） */
  transition:
    opacity 150ms ease,
    color 150ms ease,
    background-color 150ms ease,
    border-color 150ms ease,
    visibility 0s linear 0s;
}

/* 命中区补偿：28 + 6×2 = 40×40（2026-10-09 定案，同 WatchlistHeadPrimary——
   伪元素不参与布局、不画背景，视觉仍是 28px 正圆） */
.clear-filters-btn::after {
  position: absolute;
  inset: -6px;
  content: "";
}

.clear-filters-btn:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

/* 无筛选时的隐藏态：opacity 淡出 150ms，visibility 延迟到淡出结束才切
   （否则先隐再淡、过渡不可见）；pointer-events 立即断开，淡出期间也不可误点。
   visibility:hidden 同时把它移出焦点序列与无障碍树，键盘不会聚焦到隐形按钮。
   ⚠️ 禁止改回 v-if / display:none——那会让槽位宽度塌缩，正是要修的整行重排。 */
.clear-filters-btn.is-hidden {
  visibility: hidden;
  pointer-events: none;
  opacity: 0;
  transition:
    opacity 150ms ease,
    visibility 0s linear 150ms;
}
</style>
