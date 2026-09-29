<!--
  Watchlist · 自选页（完整管理）

  与探市页（/explore）的区别与关联：
  - 探市 = 引流沙盒（未登录用 localStorage 本地草稿，仅"看 + 轻收藏"，登录后隐藏添加并引导去自选页）；
    自选 = 权威管理（后端 watchlist API，分组/标签/批量/OCR/实时估值齐全）。
  - 两者表格刻意不共用：产品边界不同（观察 vs 管理）。共享的是底层 composable：
    useAssetSearch / useRealtimeQuotes / useAuthState（见 explore-watchlist-replan-2026-08-08 决策）。
  - 迁移桥：POST /api/watchlist/import/explore 将探市本地草稿导入自选。

  #980 P0-b 拆分（2026-09-24，纯结构拆分、零视觉/行为变更）：
  - 状态域：useWatchlist{Groups,Tags,Data,Toolbar,ColumnVisibility}（已有）+
    本目录 composables/ 的 useWatchlistValuation（估值）/ useWatchlistStickyLayout
    （吸顶与列拖拽）/ useWatchlistPageActions（缺口补齐、组内/多分组、速览、弹窗回调）。
  - 展示层：components/ 的 WatchlistHeadPrimary（头部第一行）、WatchlistFilterBar
    （筛选行，其内部再拆 FilterGroupTabs/FilterPanelPopover/FilterPanelBody）、
    WatchlistTableSection（表格区）、WatchlistTableFooter（底栏）、WatchlistDialogs（弹窗集合）。
  - 本文件只保留：composable 装配、renderCtx 注入、排序/hover 分发与生命周期编排。
-->
<template>
  <div
    ref="pageRef"
    class="watchlist-page"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 单滚动容器语义（2026-09-05 根因修复）：本页不自造滚动容器，页面滚动
         全由布局层 .el-scrollbar__wrap 承担；.watchlist-scroll 只是无 overflow
         的普通包裹层（类名保留便于定位/测试），保证 CSS sticky 链不被截断。 -->
    <div class="watchlist-scroll">
      <!-- 主区域：单个工作区卡片，双行分区头部（#1281 第四轮）——
           第一行 head-primary 不吸顶（搜索框下滚自动隐藏），第二行
           WatchlistFilterBar 的 .filter-bar 与表格表头经 position:sticky 连续吸顶。 -->
      <CardBlock class="watchlist-card">
        <WatchlistHeadPrimary
          :toolbar="toolbar"
          :data="data"
          :groups="groups"
          :toggle-btn-text="toggleBtnText"
          @toggle-realtime="realtime.toggle"
        />

        <WatchlistFilterBar
          :groups="groups"
          :tags="tags"
          :toolbar="toolbar"
          :on-refresh="actions.onCatalogChanged"
          @view-change="data.handleViewChange"
          @filter-apply="data.handleViewChange"
          @manage-groups="groupManagerVisible = true"
          @manage-group-items="actions.onManageGroupItems"
        />

        <!-- 持仓未入自选提示（#1458 后续：持仓即自选）：缺口可一键补齐 -->
        <el-alert
          v-if="holdingGaps.length > 0"
          type="warning"
          :closable="false"
          show-icon
          class="holding-gap-banner"
        >
          <template #title>
            <span
              >有 {{ holdingGaps.length }} 个持仓产品尚未加入自选，暂无法打标签
              / 写备注。</span
            >
          </template>
          <template #default>
            <span
              >持仓即自选：补齐后即可像普通自选一样管理，卖出后也不会被删除。</span
            >
            <el-button
              type="warning"
              size="small"
              plain
              class="ml-2"
              :loading="reconciling"
              @click="handleAddAllToWatchlist"
            >
              一键加入自选
            </el-button>
          </template>
        </el-alert>

        <!-- 合规横幅：仅在开启实时时出现（未开启实时时它没有意义） -->
        <RealtimeWarningBanner v-if="realtimeEnabled" />
        <!-- 状态 + 汇总数据条：**常驻**（不再 v-if realtimeEnabled）。
             未开实时时用静态价（最近交易日收盘价 / 确认净值）汇总兜底（#1245 /
             2026-09-22 用户反馈），数据与事件由 useWatchlistValuation 注入。 -->
        <WatchlistSummaryBar
          :realtime="realtime"
          :refreshing="refreshing"
          :fallback-summary="staticSummary"
          @interval-change="onRefreshIntervalChange"
          @manual-refresh="handleManualRefresh"
        />

        <WatchlistTableSection
          :loading="loading"
          :items="items"
          :batch-mode="batchMode"
          :columns="dataColumns"
          :ctx="renderCtx"
          :is-empty-custom-group="isEmptyCustomGroup"
          :active-group-label="activeGroupLabel"
          :has-tag-filter="selectedFilterTagIds.length > 0"
          @sort-change="onSortChange"
          @selection-change="data.handleSelectionChange"
          @cell-mouse-enter="handleCellMouseEnter"
          @cell-mouse-leave="handleCellMouseLeave"
          @row-click="actions.onRowClick"
          @open-group-items="actions.openGroupItemsDialog"
          @table-ready="onTableReady"
        />

        <WatchlistTableFooter :data="data" />
      </CardBlock>

      <!-- 合规页脚：常驻页面底部，随页面滚动至最底部时自然显现（仅本页自绘，
         全局布局级页脚已通过路由 meta.hideFooter 隐藏，避免重复）。 -->
      <LayFooter />
    </div>

    <!-- 弹窗集合（添加/OCR/移除/标签/分组/组内/多分组/速览/设置，#980 拆分） -->
    <WatchlistDialogs
      :toolbar="toolbar"
      :data="data"
      :groups="groups"
      :tags="tags"
      :valuation="valuation"
      :actions="actions"
      :column-settings="columnSettings"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import LayFooter from "@/layout/components/lay-footer/index.vue";
import RealtimeWarningBanner, {
  REALTIME_BANNER_DISMISS_KEY
} from "@/components/RealtimeWarningBanner/index.vue";
import WatchlistFilterBar from "@/views/asset/watchlist/WatchlistFilterBar.vue";
import WatchlistSummaryBar from "@/views/asset/watchlist/WatchlistSummaryBar.vue";
import WatchlistHeadPrimary from "@/views/asset/watchlist/components/WatchlistHeadPrimary.vue";
import WatchlistTableSection from "@/views/asset/watchlist/components/WatchlistTableSection.vue";
import WatchlistTableFooter from "@/views/asset/watchlist/components/WatchlistTableFooter.vue";
import WatchlistDialogs from "@/views/asset/watchlist/components/WatchlistDialogs.vue";
import { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import { useWatchlistTags } from "@/composables/useWatchlistTags";
import { useWatchlistData } from "@/composables/useWatchlistData";
import { useWatchlistToolbar } from "@/composables/useWatchlistToolbar";
import { useWatchlistColumnVisibility } from "@/composables/useWatchlistColumnVisibility";
import { useWatchlistValuation } from "@/views/asset/watchlist/composables/useWatchlistValuation";
import { useWatchlistStickyLayout } from "@/views/asset/watchlist/composables/useWatchlistStickyLayout";
import { useWatchlistPageActions } from "@/views/asset/watchlist/composables/useWatchlistPageActions";
import { useWatchlistTable } from "@/views/asset/watchlist/composables/useWatchlistTable";

defineOptions({ name: "Watchlist" });

// 状态域装配（#980 拆分总纲）：分组 / 标签 / 数据 / 工具栏四类已有 composable
// + 估值 / 布局吸顶 / 页面动作三个新 composable，本文件只做编排。
const groups = useWatchlistGroups();
const tags = useWatchlistTags();
const toolbar = useWatchlistToolbar();
const data = useWatchlistData(groups, tags, toolbar);

// 当前品类（类型筛选命中单一品类时为其 asset_type；否则 null＝混合视图）。
// 供列显隐在「混合视图通用列 / 品类视图专属列」间切换（#1285）。
const activeCategory = computed<string | null>(() =>
  toolbar.selectedAssetTypes.value.length === 1
    ? toolbar.selectedAssetTypes.value[0]
    : null
);
// 列显隐偏好（#993）：localforage 本机持久化，SettingsDrawer 经 prop 共享同一实例
const columnSettings = useWatchlistColumnVisibility(activeCategory);

const valuation = useWatchlistValuation(data);
const actions = useWatchlistPageActions({ groups, tags, toolbar, data });

// #995 columnDefs 数据驱动 + #993 列显隐：visibleColumns 已按用户隐藏集过滤
//（仅 selection 因 type="selection" 无法 renderer 化，保留模板由 batchMode 注入；
//  原 marker 列已于 #1281 第四轮删除：置顶/关注状态改为产品列名称前内联渲染）──
const dataColumns = computed(() =>
  columnSettings.visibleColumns.value.filter(d => d.key !== "_selection")
);

const sticky = useWatchlistStickyLayout({
  data,
  toolbar,
  columnSettings,
  dataColumns,
  realtimeEnabled: valuation.realtimeEnabled
});
const { pageRef, onTableReady, initHeaderDrag, bindStickyObserver } = sticky;

// 表格渲染域（renderCtx 组装 / 行 hover / 排序分发），见 useWatchlistTable
const table = useWatchlistTable({
  groups,
  tags,
  toolbar,
  data,
  valuation,
  actions,
  activeCategory,
  columnSettings
});
const { renderCtx, onSortChange, handleCellMouseEnter, handleCellMouseLeave } =
  table;

const { activeGroupLabel } = groups;
const { selectedFilterTagIds } = tags;
const { items, loading } = data;
const { batchMode, groupManagerVisible } = toolbar;
const {
  realtime,
  realtimeEnabled,
  toggleBtnText,
  refreshing,
  staticSummary,
  handleManualRefresh,
  onRefreshIntervalChange
} = valuation;
const {
  holdingGaps,
  reconciling,
  handleAddAllToWatchlist,
  isEmptyCustomGroup
} = actions;

// 实时估值功能被「关闭→重新开启」时，清除横幅关闭标记，让提示横幅重新出现。
// （key 只能从 RealtimeWarningBanner.vue 的具名导出引用，故本条 watch 留在
//  页面 .vue 内，其余估值 watch 见 composables/useWatchlistValuation.ts）
watch(
  () => realtime.enabled.value,
  (now, prev) => {
    if (prev === false && now === true) {
      try {
        localStorage.removeItem(REALTIME_BANNER_DISMISS_KEY);
      } catch {
        /* 隐私模式下忽略存储异常 */
      }
    }
  }
);

// ─────────────────────────────────────────────
// 生命周期：首屏取数 + 分组切换刷新 + 吸顶/拖拽接线
// ─────────────────────────────────────────────
onMounted(async () => {
  // 先恢复本地记忆的每页条数，确保首屏 fetch 即使用户上次的选择（#1335）
  await data.initPageSize();
  groups.fetchGroups();
  tags.fetchTags();
  data.fetchData();
  actions.fetchHoldingGaps();
  watch(groups.activeGroup, () => {
    // 持仓分组只含真实持仓（stock/fund/etf/bond/index/convertible），
    // 不含「经理」等非持仓类型——切到持仓分组时仅清掉非持仓类型，
    // 其余持仓类型一律保留并生效（#1449：此前整体清空非 stock/fund 类型，
    // 导致 ETF/可转债等持仓类型筛选在持仓分组下形同虚设）。
    if (groups.activeGroup.value === "holding") {
      const holdingTypes = new Set([
        "stock",
        "fund",
        "etf",
        "bond",
        "index",
        "convertible"
      ]);
      toolbar.selectedAssetTypes.value =
        toolbar.selectedAssetTypes.value.filter(t => holdingTypes.has(t));
    }
    data.currentPage.value = 1;
    data.fetchData();
  });
  initHeaderDrag();
  bindStickyObserver();
  sticky.bindPageMinHObserver();
});
</script>

<style scoped>
/* #1458 后续：持仓未入自选的引导 banner（warning 级） */
.holding-gap-banner {
  margin: 12px 0;
}

.holding-gap-banner .ml-2 {
  margin-left: 8px;
}

/* 自选卡片沿用 design.md「表格/列表/筛选栏：--space-compact(16px)」，
   仅本页生效。留白规范与吸顶/min-height 的机制说明见
   composables/useWatchlistStickyLayout.ts（#980 P0-b 拆分）。 */

/* 自选页容器：任何祖先/自身都不设 overflow:hidden/auto，否则会创建新的滚动
   容器、截断 .filter-bar / 表头的 sticky 上溯到布局滚动容器。
   min-width:0：列总宽超视口时防止 el-table 把整条 flex 链撑宽、产生页面级
   横向滚动条（#1341）；min-height 由脚本实测外层可视高度写入（空态时
   撑满一屏、footer 贴底）。 */
.watchlist-page {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

/* 高密度列表页：取消全局 .main-content 的 48px 边距，避免上下白边吞掉表格行数。 */
.watchlist-page.main-content {
  padding: 0;
}

/* 无 overflow 的普通流包裹层（唯一滚动容器是布局 el-scrollbar__wrap）；
   flex column + flex-grow 吃满 .watchlist-page 的 min-height（footer 由此贴底）。 */
.watchlist-scroll {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

/* 卡片 flex:1 撑满剩余高度：空态时卡片拉伸到一屏、表格区居中、footer 沉底；
   有数据时随内容增高（flex-grow 仅在有空余时作用，不压缩真实行）。 */
.watchlist-card {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: var(--space-compact);
}

/* 合规页脚贴底：margin-top:auto 把空余空间让给上方卡片，footer 沉到可视区底部。 */
:deep(.app-footer) {
  margin-top: auto;
}

/* 估值条（实时开启时显示）：不吸顶，滚动时自然滚出视口；上限防内容溢出。 */
:deep(.summary-bar) {
  max-height: 48px;
  overflow: hidden;
}

/* 分组 Tab 行吸顶：相对外层布局滚动容器 sticky 贴顶（top:0），白遮罩从
   滚动容器顶开始覆盖（避免行从顶部穿透）；padding-top = --watchlist-sticky-gap
   （12px 呼吸感，脚本实测写入），表头吸顶偏移 = 其 offsetHeight 无缝衔接。
   祖先链（本页各层）不得有 overflow:hidden/auto，否则截断 sticky 上溯。 */
:deep(.filter-bar) {
  position: sticky;
  top: 0;
  z-index: 4;
  padding-top: var(--watchlist-sticky-gap, 12px);
  background: var(--bg-card);
}

/* ======================================
   基础输入框/下拉框样式（作用于本页树内全部子组件的控件）
   ====================================== */
:deep(.el-input__wrapper) {
  --el-input-border-color: var(--border-default);
  --el-input-hover-border-color: var(--brand-500);
  --el-input-focus-border-color: var(--brand-700);
  --el-input-focus-shadow:
    inset 0 0 0 1px var(--brand-700), 0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);

  border-radius: var(--radius-sm);
}

:deep(.el-select .el-input__wrapper) {
  --el-input-border-color: var(--border-default);
  --el-input-hover-border-color: var(--brand-500);
  --el-input-focus-border-color: var(--brand-700);
  --el-input-focus-shadow:
    inset 0 0 0 1px var(--brand-700), 0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);

  border-radius: var(--radius-sm);
}

/* ======================================
   按钮物理反馈（去除缩放，仅保留符合规范的 translateY）
   ====================================== */
:deep(.el-button--primary:active) {
  box-shadow: none !important;
  transform: translateY(1px);
}

/* 规范要求：软按钮/其他按钮点击不进行缩放位移，仅背景加深 */
:deep(.el-button.is-text:active) {
  transform: none;
}
</style>
