<!--
  Watchlist · 自选页（完整管理）

  与探市页（/explore）的区别与关联：
  - 探市 = 引流沙盒（未登录用 localStorage 本地草稿，仅"看 + 轻收藏"，登录后隐藏添加并引导去自选页）；
    自选 = 权威管理（后端 watchlist API，分组/标签/批量/OCR/实时估值齐全）。
  - 两者表格刻意不共用：产品边界不同（观察 vs 管理）。共享的是底层 composable：
    useAssetSearch / useRealtimeQuotes / useAuthState（见 explore-watchlist-replan-2026-08-08 决策）。
  - 迁移桥：POST /api/watchlist/import/explore 将探市本地草稿导入自选。

  未来优化方向（见重构 issue #980 / 技术债 #981 / #982）：
  - 本页 8 大功能模块（分组/标签/批量/实时估值/搜索分页/导出/OCR/移除）可进一步按
    composable 抽取（如 useWatchlistGroups / useWatchlistTags）。
  - 顶部操作栏已抽取为 WatchlistToolbar，移除弹窗已抽取为 WatchlistRemoveDialog。
  - 标签管理 / 行内标签编辑已拆为共有组件 TagManagerDialog / TagEditorDialog
    （components/Watchlist/），未来其它页面需要标签能力可复用。
-->
<template>
  <div
    class="watchlist-page p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 顶部操作栏（已抽取为 WatchlistToolbar 组件） -->
    <WatchlistToolbar
      :toolbar="toolbar"
      :custom-groups="customGroups"
      :toggle-btn-text="toggleBtnText"
      @search-input="debounceSearch"
      @batch-move="handleBatchMoveToGroup"
      @batch-delete="handleBatchDelete"
      @exit-batch="toggleBatchMode"
      @add="openAddDialog"
      @refresh="fetchData"
      @export="exportData"
      @ocr="openOcrDialog"
      @toggle-realtime="realtime.toggle"
      @open-settings="openSettingsDrawer"
    />

    <!-- 主区域：单个工作区卡片（单行筛选条 + 单行估值数据条 + 表格，聚焦表格减少视线打断） -->
    <CardBlock class="watchlist-card">
      <!-- 单行筛选条：标签筛选 + 视图 segmented + 分组 tab 滚动（已抽离到 WatchlistFilterBar） -->
      <WatchlistFilterBar
        :groups="groups"
        :tags="tags"
        :toolbar="toolbar"
        :on-refresh="fetchData"
        @view-change="handleViewChange()"
        @tag-apply="tags.applyTagFilter()"
        @tag-clear="tags.clearTagFilter()"
        @manage-groups="groupManagerVisible = true"
      />

      <!-- 估值横幅与状态 -->
      <!-- ✅ 核心修复：用 template 包裹，加上 v-if 物理移除整个模块 -->
      <template v-if="realtimeEnabled">
        <RealtimeWarningBanner />
        <!-- 实时状态指示 + 刷新档位 + 汇总指标数据条（已抽离到 WatchlistSummaryBar） -->
        <WatchlistSummaryBar
          :realtime="realtime"
          :refreshing="refreshing"
          @interval-change="onRefreshIntervalChange"
          @manual-refresh="handleManualRefresh"
        />
      </template>

      <!-- 批量删除（batchMode 时显示；原筛选行已并入分组行，批量删除按钮移至表格上方） -->
      <div
        v-if="batchMode && selectedItems.length > 0"
        class="flex justify-end mb-2"
      >
        <el-button
          type="danger"
          plain
          size="small"
          class="!h-7 !px-3 !text-xs"
          @click="handleBatchDelete"
        >
          删除选中 ({{ selectedItems.length }})
        </el-button>
      </div>

      <!--
          表格视觉基线（边框/表头/hover/文字色）统一在 src/style/el-table.css 维护，
          勿在本页 :deep(.el-table) 覆盖视觉基线；本页保留的 :deep 仅限行内行为样式。
          行高例外（2026-08-15）：全局基线 44px 偏松，自选页信息密度优先，本页覆盖为 40px
          （EP 默认行高，tr height 为最小高度语义，两行式名称列自动撑高不裁切）；
          覆盖规则见本页 style 区「本页行高覆盖」注释。
        -->
      <el-table
        ref="tableRef"
        v-loading="loading"
        :data="items"
        stripe
        @selection-change="handleSelectionChange"
        @sort-change="handleSortChange"
        @cell-mouse-enter="handleCellMouseEnter"
        @cell-mouse-leave="handleCellMouseLeave"
      >
        <el-table-column
          v-if="batchMode"
          type="selection"
          width="50"
          align="center"
          :selectable="row => row.id != null"
        />
        <!-- #995 columnDefs 数据驱动：全量列（仅 selection 因 type="selection" 无法 renderer 化，保留模板）。
             product/marker/actions 均由 columnRenderers.tsx 渲染，详见 docs/spec/watchlist-column-defs.md。 -->
        <el-table-column
          v-for="def in dataColumns"
          :key="def.key"
          :prop="def.key"
          :label="def.label"
          :width="def.width"
          :min-width="def.minWidth"
          :align="def.align"
          :fixed="def.fixed"
          :sortable="def.sortable"
          :class-name="def.draggable ? undefined : 'col-no-drag'"
          :show-overflow-tooltip="def.showOverflowTooltip"
        >
          <template #default="{ row }">
            <component
              :is="resolveRenderer(def.renderer)"
              :row="row as WatchlistItem"
              :def="def"
              :ctx="renderCtx"
            />
          </template>
        </el-table-column>

        <!-- 空状态：区分「标签筛选导致为空」与「本就无任何自选」，避免干巴巴的默认占位。
             注：design.md 规划了鹦鹉螺简笔画空状态，现仓库无对应资产，先用文案版，待插画资产到位后替换。 -->
        <template #empty>
          <div class="watchlist-empty">
            <p class="watchlist-empty__title">
              {{
                selectedFilterTagIds.length > 0
                  ? "暂无匹配所选标签的持仓"
                  : "暂无自选资产"
              }}
            </p>
            <p
              v-if="selectedFilterTagIds.length > 0"
              class="watchlist-empty__hint"
            >
              试试调整或清空标签筛选条件
            </p>
          </div>
        </template>
      </el-table>

      <div class="flex justify-end mt-4">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="totalItems"
          layout="total, prev, pager, next"
          small
          background
          @current-change="fetchData"
        />
      </div>
    </CardBlock>

    <!-- 弹窗部分 -->
    <AddToWatchlistModal
      v-model="addDialogVisible"
      :initial-group-id="activeCustomGroupId"
      @submitted="onItemAdded"
      @catalog-changed="onCatalogChanged"
    />

    <OcrImportModal v-model="ocrDialogVisible" @imported="onOcrImported" />

    <!-- 移除自选弹窗（已抽取为 WatchlistRemoveDialog 组件） -->
    <WatchlistRemoveDialog
      v-model="removeDialogVisible"
      v-model:remove-scope="removeScope"
      :removing-item="removingItem"
      :current-is-custom="currentIsCustom"
      @confirm="executeRemove"
    />

    <!-- 标签管理弹窗（共有组件 TagManagerDialog，自本页拆出，见 docs/design/components.md） -->
    <TagManagerDialog
      v-model="tagManagerVisible"
      :all-tags="allTags"
      :tag-usage="tagUsage"
      @tags-changed="fetchTags"
    />

    <!-- 分组管理弹窗（GitHub Labels 风格，与标签同构，见 docs/design/components.md）。
         系统分组可见但不可编辑/删除（managerGroups 含系统分组虚拟行），自定义分组可管理。 -->
    <GroupManagerDialog
      v-model="groupManagerVisible"
      :all-groups="managerGroups"
      @groups-changed="fetchGroups"
    />

    <!-- 行内标签编辑弹窗（共有组件 TagEditorDialog） -->
    <TagEditorDialog
      v-model="showTagEditor"
      :item="editingItem"
      :all-tags="allTags"
      @saved="onTagEditorSaved"
    />

    <SettingsDrawer
      v-model="settingsDrawerVisible"
      :realtime-enabled="realtimeEnabled"
      :refresh-interval="realtime.refreshInterval.value"
      :column-settings="columnSettings"
      @refresh-interval-change="realtime.setRefreshInterval"
      @manage-groups="
        groupManagerVisible = true;
        settingsDrawerVisible = false;
      "
      @manage-tags="
        tagManagerVisible = true;
        settingsDrawerVisible = false;
      "
      @manage-batch="
        toggleBatchMode();
        settingsDrawerVisible = false;
      "
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import Sortable from "sortablejs";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";
import OcrImportModal from "@/components/QuickEntry/OcrImportModal.vue";
import SettingsDrawer from "@/components/Watchlist/SettingsDrawer.vue";
import TagManagerDialog from "@/components/Watchlist/TagManagerDialog.vue";
import GroupManagerDialog from "@/components/Watchlist/GroupManagerDialog.vue";
import TagEditorDialog from "@/components/Watchlist/TagEditorDialog.vue";
import { getWatchlistTrends, type WatchlistItem } from "@/api/watchlist";
import CardBlock from "@/components/CardBlock/index.vue";
// 金额/涨跌展示组件（MoneyDisplay/RiseFallText/MoneyWithRatio）已随 #995 列渲染器化
// 迁移至 columnRenderers.tsx，本页模板不再直接使用
import WatchlistToolbar from "@/views/asset/watchlist/components/WatchlistToolbar.vue";
import WatchlistRemoveDialog from "@/views/asset/watchlist/components/WatchlistRemoveDialog.vue";
import {
  useRealtimeQuotes,
  type RefreshInterval
} from "@/composables/useRealtimeQuotes";
import { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import { useWatchlistTags } from "@/composables/useWatchlistTags";
import { useWatchlistData } from "@/composables/useWatchlistData";
import { useWatchlistToolbar } from "@/composables/useWatchlistToolbar";
import { useWatchlistColumnVisibility } from "@/composables/useWatchlistColumnVisibility";
import WatchlistFilterBar from "@/views/asset/watchlist/WatchlistFilterBar.vue";
import WatchlistSummaryBar from "@/views/asset/watchlist/WatchlistSummaryBar.vue";
import RealtimeWarningBanner, {
  REALTIME_BANNER_DISMISS_KEY
} from "@/components/RealtimeWarningBanner/index.vue";
import type { Holding } from "@/utils/valuationEngine";
import { formatDateTime } from "@/utils/date";
// 列定义不再直接消费：dataColumns 经 useWatchlistColumnVisibility 的
// visibleColumns 过滤取得（#993），本页只保留 renderer 注册表依赖
import {
  resolveRenderer,
  type RenderCtx
} from "@/views/asset/watchlist/columnRenderers";

defineOptions({ name: "Watchlist" });

// 分组 / 标签 / 数据编排 / 工具栏 四类状态全部收敛到 composable（见 #980 拆分总纲）：
// - groups：分组 tab 派生 + fetchGroups
// - tags：标签列表 + 标签筛选面板（applyTagFilter 提交后由 useWatchlistData 内部 watch 自动刷新）
// - data：分页 / 筛选 / fetchData / 行操作 / 批量（依赖 groups + tags + toolbar）
// - toolbar：顶部搜索 / 批量模式 / 视图 segmented / 弹窗开关
const groups = useWatchlistGroups();
const tags = useWatchlistTags();
const toolbar = useWatchlistToolbar();
const data = useWatchlistData(groups, tags, toolbar);
// 列显隐偏好（#993）：localforage 本机持久化，SettingsDrawer 经 prop 共享同一实例
const columnSettings = useWatchlistColumnVisibility();

const {
  activeGroup,
  allGroups,
  customGroups,
  managerGroups,
  activeGroupLabel,
  currentIsCustom,
  activeCustomGroupId,
  fetchGroups
} = groups;
const { allTags, selectedFilterTagIds, fetchTags } = tags;
const {
  items,
  loading,
  currentPage,
  pageSize,
  totalItems,
  fetchData,
  handleSortChange,
  handleViewChange,
  debounceSearch,
  handleSelectionChange,
  handleBatchDelete,
  handleBatchMoveToGroup,
  handleTogglePin,
  handleToggleFavorite,
  confirmRemove,
  executeRemove,
  removingItem,
  removeScope,
  removeDialogVisible,
  editingItem,
  showTagEditor,
  openTagEditor,
  exportData,
  resetFilters
} = data;
const {
  searchKeyword,
  currentView,
  batchMode,
  selectedItems,
  batchMoveGroupId,
  addDialogVisible,
  ocrDialogVisible,
  groupManagerVisible,
  tagManagerVisible,
  settingsDrawerVisible,
  toggleBatchMode,
  openAddDialog,
  openOcrDialog,
  openGroupManager,
  openTagManager,
  openSettingsDrawer
} = toolbar;

// ── 估值相关 ──
const getValuationItem = (symbol: string) => {
  return realtime.items.value?.find(item => item.symbol === symbol);
};

// ── 行 hover 状态（供 fixed 列操作按钮淡入）──
// 操作列(_actions)/产品列(product) 均为 fixed 列，EP 固定列渲染为独立 DOM，
// CSS :hover 无法跨表同步，故由 JS 状态驱动（见 columnRenderers.tsx hoveredRowKey 注释）。
// leave 延迟 100ms 清除，避免鼠标在主体行 ↔ 固定列之间移动时按钮闪烁。
const hoveredRowKey = ref<string | number | null>(null);
let hoverClearTimer: ReturnType<typeof setTimeout> | undefined;

function handleCellMouseEnter(row: WatchlistItem) {
  if (hoverClearTimer) {
    clearTimeout(hoverClearTimer);
    hoverClearTimer = undefined;
  }
  hoveredRowKey.value = row.id ?? row.symbol;
}

function handleCellMouseLeave() {
  if (hoverClearTimer) clearTimeout(hoverClearTimer);
  hoverClearTimer = setTimeout(() => {
    hoveredRowKey.value = null;
    hoverClearTimer = undefined;
  }, 100);
}

/** 添加后涨幅（%）=（当前价 - 添加日价格）/ 添加日价格 */
function addedReturnPct(row: {
  symbol?: string;
  current_price?: number | null;
  holding_quantity?: number | null;
  price_at_added?: number | null;
}): number | null {
  const added = row.price_at_added;
  if (!added) return null;
  const cur = (getValuationItem(row.symbol ?? "")?.currentPrice ??
    row.current_price) as number;
  if (!cur) return null;
  return ((cur - added) / added) * 100;
}

/** 添加后收益（元）=（当前价 - 添加日价格）× 持有数量，仅持有时有意义 */
function addedReturnAmount(row: {
  symbol?: string;
  current_price?: number | null;
  holding_quantity?: number | null;
  price_at_added?: number | null;
}): number | null {
  if (!row.holding_quantity || row.holding_quantity <= 0) return null;
  if (addedReturnPct(row) === null) return null;
  const cur = (getValuationItem(row.symbol ?? "")?.currentPrice ??
    row.current_price) as number;
  return (cur - (row.price_at_added as number)) * row.holding_quantity;
}

/** 持仓市值占总市值的比例（%）；无总市值或无市值时返回 null（组件仅显示金额） */
function marketValueRatio(row: {
  position_market_value?: number | null;
}): number | null {
  const total = realtime.summary.value?.totalMarketValue;
  if (!total || total <= 0 || row.position_market_value == null) return null;
  return (row.position_market_value / total) * 100;
}

const getHoldings = (): Holding[] => {
  return items.value
    .filter(item => item.symbol)
    .map(item => ({
      symbol: item.symbol,
      type:
        item.asset_type === "fund" || item.venue === "OTC" ? "fund" : "stock",
      // 使用真实持仓数量与成本价，使汇总卡与逐行盈亏正确
      quantity:
        item.status === "HOLDING" && (item.holding_quantity ?? 0) > 0
          ? (item.holding_quantity as number)
          : 0,
      costPrice:
        item.status === "HOLDING" && (item.holding_quantity ?? 0) > 0
          ? (item.holding_cost_price as number)
          : 0
    }));
};

const getStaticPrice = (symbol: string) => {
  const item = items.value.find(i => i.symbol === symbol);
  return item
    ? { currentPrice: item.current_price, changePct: item.change_pct }
    : undefined;
};

const realtime = useRealtimeQuotes(getHoldings, getStaticPrice);

// ✅ 1. 新增：一个专门控制按钮文字的 computed，解决文字不更新的脏数据问题
const toggleBtnText = computed(() => {
  return realtime.enabled.value ? "关闭实时估值" : "开启实时估值";
});

// ✅ 2. 修复：原 watch 导致的死循环/卡顿，重构为更稳定的版本
watch(
  () => items.value,
  () => {
    if (realtime.enabled.value) {
      try {
        realtime.manualRefresh();
      } catch (e) {
        console.warn("手动刷新失败", e);
      }
    }
  }
);

// ✅ 3. 修改：监听实时行情数据，更新绿灯和时间
watch(
  () => realtime.items.value,
  newItems => {
    if (newItems && newItems.length > 0) {
      const hasValidPrice = newItems.some(item => item.currentPrice > 0);
      if (hasValidPrice) {
        realtime.status.value = "trading";
        realtime.lastUpdateTime.value = formatDateTime(new Date());
      }
    }
  },
  { deep: true }
);

// 实时估值功能被「关闭→重新开启」时，清除横幅关闭标记，让提示横幅重新出现
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

// 标签使用统计：供 TagManagerDialog 显示每个标签被多少自选使用
const tagUsage = computed(() => {
  const usage = new Map<number, number>();
  if (!Array.isArray(items.value)) return usage;
  items.value.forEach(item => {
    const tagIds = item?.tag_ids;
    if (Array.isArray(tagIds)) {
      tagIds.forEach(id => {
        if (typeof id === "number" && !isNaN(id)) {
          usage.set(id, (usage.get(id) || 0) + 1);
        }
      });
    }
  });
  return usage;
});

/** 手动刷新估值：旋转图标至请求完成 */
const refreshing = ref(false);
async function handleManualRefresh() {
  if (refreshing.value) return;
  refreshing.value = true;
  try {
    await realtime.manualRefresh();
  } finally {
    refreshing.value = false;
  }
}

// ── 迷你走势图数据（#990）：price_history 后端批量序列，随列表行变化拉取 ──
const trendMap = ref<Record<string, number[]>>({});
async function fetchTrends() {
  const symbols = [...new Set(items.value.map(i => i.symbol).filter(Boolean))];
  if (symbols.length === 0) {
    trendMap.value = {};
    return;
  }
  try {
    const res = await getWatchlistTrends(symbols);
    trendMap.value = res.data ?? {};
  } catch {
    // 走势获取失败静默降级为 --（列渲染器对缺失数据的处理），不打断列表
  }
}
watch(items, () => {
  void fetchTrends();
});

/** 切换刷新档位：转发给 realtime（负责持久化 + 盘中重启定时器） */
const onRefreshIntervalChange = (value: string | number | boolean) => {
  realtime.setRefreshInterval(value as RefreshInterval);
};

function onItemAdded() {
  addDialogVisible.value = false;
  fetchData();
  fetchTags();
}

// 弹窗内新建/编辑了标签或分组，立即刷新页面目录，避免页面不更新的问题
function onCatalogChanged() {
  groups.fetchGroups();
  tags.fetchTags();
}

function onOcrImported() {
  ocrDialogVisible.value = false;
  fetchData();
  fetchTags();
}

/** 标签保存成功（含弹窗内新建标签）后：刷新列表与标签 */
const onTagEditorSaved = () => {
  fetchData();
  fetchTags();
};

// ─────────────────────────────────────────────
// 生命周期
// ─────────────────────────────────────────────
onMounted(() => {
  fetchGroups();
  fetchTags();
  fetchData();
  watch(activeGroup, () => {
    currentPage.value = 1;
    fetchData();
  });
  initHeaderDrag();
});

// ── #992 表头列拖拽：sortablejs 复用（RePureTableBar 同款方案）──
const tableRef = ref();

/** 给可拖拽中段列提交新顺序（固定列/内置列不参与，见 columnDefs.draggable） */
function initHeaderDrag() {
  const el = (tableRef.value?.$el ?? null) as HTMLElement | null;
  const headerRow = el?.querySelector<HTMLElement>(
    ".el-table__header-wrapper tr"
  );
  if (!headerRow) return;
  Sortable.create(headerRow, {
    animation: 300,
    filter: ".col-no-drag",
    preventOnFilter: false,
    onMove(evt) {
      // 目标位置落在固定列上时拒绝放置（固定列左右包夹中段拖拽区）
      const related = evt.related as HTMLElement | undefined;
      return !related?.classList.contains("col-no-drag");
    },
    onEnd({ oldIndex, newIndex }) {
      if (oldIndex == null || newIndex == null || oldIndex === newIndex) return;
      // th 序列与渲染列一一对应：[selection(batchMode)] + dataColumns
      const keys = [
        ...(batchMode.value ? ["_selection"] : []),
        ...dataColumns.value.map(d => d.key)
      ];
      if (oldIndex >= keys.length || newIndex >= keys.length) return;
      const moved = keys.splice(oldIndex, 1)[0];
      keys.splice(newIndex, 0, moved);
      // 只持久化可拖拽中段列的相对顺序（内置 _ 前缀列不进偏好存储）
      columnSettings.applyOrder(keys.filter(k => !k.startsWith("_")));
    }
  });
}

const realtimeEnabled = computed(() => realtime.enabled.value);

// ── #995 columnDefs 数据驱动 + #993 列显隐：visibleColumns 已按用户隐藏集过滤
//（仅 selection 因 type="selection" 无法 renderer 化，保留模板）──
const dataColumns = computed(() =>
  columnSettings.visibleColumns.value.filter(
    d => d.key !== "_selection" && d.key !== "_marker"
  )
);

// 渲染上下文：把页面级状态/方法注入 renderer 注册表，renderer 不耦合本组件
const renderCtx = computed<RenderCtx>(() => ({
  realtimeEnabled: realtimeEnabled.value,
  getValuationItem,
  allTags: allTags.value,
  derived: (kind, row) => {
    if (kind === "addedReturn") {
      return {
        value: addedReturnAmount(row as WatchlistItem) ?? 0,
        ratio: addedReturnPct(row as WatchlistItem) ?? 0
      };
    }
    // marketValue
    return {
      value: (row.position_market_value as number) ?? 0,
      ratio: marketValueRatio(row as WatchlistItem) ?? 0
    };
  },
  openTagEditor,
  batchMode: batchMode.value,
  hoveredRowKey: hoveredRowKey.value,
  setHoveredRowKey: (key: string | number | null) => {
    hoveredRowKey.value = key;
  },
  actions: {
    togglePin: handleTogglePin,
    toggleFavorite: handleToggleFavorite,
    remove: confirmRemove
  },
  trends: trendMap.value
}));
</script>

<style scoped>
/* 旧刷新频率下拉（.refresh-interval-select/.is-spinning）样式已随 el-segmented 化删除 */

/* ======================================
   基础输入框/下拉框样式
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
   ✅ 已移除强制 32px 高度逻辑，按钮和输入框默认跟随 Element Plus 尺寸
   ====================================== */

/* 标签筛选面板已抽离到 WatchlistFilterBar（2026-08-21 胶囊化重构），
   原 tag-filter-trigger / tag-filter-item / tag-filter-panel 等 checkbox 时代样式已随组件迁移移除。 */

/* 表格空状态：区分标签筛选为空与无自选（鹦鹉螺插画资产到位后可在文案前补简笔画） */
.watchlist-empty {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
  padding: 32px 0;
}

.watchlist-empty__title {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.watchlist-empty__hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* ======================================
   view-segmented / refresh-segmented 样式已收口到使用组件：
   - 视图 segmented（全部/场内/场外）→ WatchlistFilterBar.vue
   - 刷新频率 segmented（15s/30s/60s/90s）→ WatchlistSummaryBar.vue
   （2026-08-21 组件抽取时样式遗留在本页 scoped 中无法作用到子组件内部元素，已迁移；SettingsDrawer 自带同款）
   ====================================== */

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

.tag-fade-enter-active,
.tag-fade-leave-active {
  transition: all 0.2s ease;
}

.tag-fade-enter-from,
.tag-fade-leave-to {
  opacity: 0;
  transform: scale(0.8);
}

/* 标签管理弹窗样式已随组件抽取迁入 TagManagerDialog.vue（本页 scoped 无法作用到弹层） */

/* 操作列按钮默认弱化可见，行悬停时全亮（150ms ease）。
   说明：不采用 opacity:0 完全隐藏——操作列/产品列是 fixed 列，EP 固定列独立 DOM，
   JS 状态驱动（is-row-hovered）依赖单元格重渲染，在 EP 中不可靠会致按钮"完全不可见"，
   故改为默认 45% 弱化可见 + hover 全亮，保证可发现性同时保留行内操作弱化原则。 */
:deep(.el-table__row .el-button) {
  opacity: 0.45;
  transition: opacity 150ms ease;
}

:deep(.el-table__row:hover .el-button),
:deep(.el-table__row .is-row-hovered .el-button),
:deep(.el-table__fixed-right .el-table__row:hover .el-button),
:deep(.el-table__fixed-left .el-table__row:hover .el-button) {
  opacity: 1;
}

/* 操作列 3 个 circle 按钮：flex 容器内归零 EP 相邻 margin，间距统一由 gap 控制，保证一行排布 */
:deep(.el-table__row .el-button + .el-button) {
  margin-left: 0;
}

/* 本页行高覆盖：全局基线 44px（el-table.css）偏松，自选页信息密度优先，降为 40px（EP 默认行高）。
   覆盖理由：全局 44px 为 2026-08-14 基线，影响探市/温度计等页面，不宜全局下调；
   本页名称列为两行式（名称+标签），tr height 为最小高度语义，40px 下多行内容仍自动撑高不裁切。 */
:deep(.el-table .el-table__row) {
  height: 40px;
}

/* 表头不换行：保证排序图标(.caret-wrapper)与表头文字始终同一行，
   修复 5 字表头（添加自选日 / 添加后涨幅）加排序按钮后换行错位的问题。
   各列 width 已预留足够空间容纳文字+图标，此处仅作双保险防止意外折行。 */
:deep(.el-table__header th.el-table__cell .cell) {
  white-space: nowrap;
}

/* 分组胶囊 Tab / 新建分组按钮样式已迁移至 components/Watchlist/WatchlistFilterBar.vue（方案 B，2026-08-14） */

/* 置顶/关注标记图标与标签 chips（.marker-icon/.tag-chip/.add-tag-btn）样式已迁移至
   columnRenderers.css——列 renderer 化后这些 DOM 由 tsx 产生，不携带本页 scoped 属性，
   留在本页的规则会静默失效（#995 迁移遗留，2026-08-22 清理） */
</style>
