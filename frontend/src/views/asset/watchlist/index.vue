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
    class="watchlist-page p-4 min-h-full"
    :class="{ 'is-condensed': condensed }"
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
        :on-refresh="onCatalogChanged"
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
          行高例外：全局基线 44px，本页为 56px——自选行承载「名称 / 代码+标签」与
          「金额 / 比例」两组双行信息，压到 44px 以下必然牺牲可读性（#1281 已验证一轮：
          单行压扁到 40px 后名称只剩两三个字，被判定为不可用）。56px 是三行式（约 78px）
          与压扁式（40px）之间的平衡点，rows per screen 约为三行式的 1.4 倍。
          滚动条：EP 覆盖式滚动条保持默认 hover 显现（不常驻，避免横向+纵向两条常亮
          造成「双滚动条」观感），配色在 el-table.css 统一为 --border-default。
        -->
      <el-table
        ref="tableRef"
        v-loading="loading"
        :data="items"
        :max-height="tableMaxHeight"
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

      <!-- 表格底栏：左侧总数（分页器的 total 单独拎出来，避免与右侧翻页挤成一团），
           右侧翻页；与表格之间用 --border-light 细分割线分区（design.md「卡片内分割线」） -->
      <div ref="footerRef" class="table-footer">
        <span class="table-footer__total">共 {{ totalItems }} 条</span>
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="totalItems"
          layout="prev, pager, next"
          small
          background
          @current-change="() => fetchData(false)"
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
import {
  ref,
  computed,
  onMounted,
  onActivated,
  onBeforeUnmount,
  watch,
  nextTick
} from "vue";
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
  allItems,
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
  // 估值汇总必须基于全量过滤结果（allItems），而非当前页（items），
  // 否则翻页时总市值/总成本/总盈亏会随当前页跳变（#1245）。
  return allItems.value
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
  const item = allItems.value.find(i => i.symbol === symbol);
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
  recalcTableMaxHeight();
  observeHeaderResize();
  bindTableScroll();
});

// ── #992 表头列拖拽：sortablejs 复用（RePureTableBar 同款方案）──
const tableRef = ref();

// 表格内部滚动：动态计算可用高度，使卡片占满视口、页面不滚动，
// 表头固定、工具栏/筛选条常驻可见（keep-alive 切回 / 窗口缩放 / 估值条或批量条显隐后需重算）
//
// 为什么重写计算（issue #1281「滚动条异常」）：
// 旧实现把页脚（分页器 + 卡片内边距）写成固定 reserve=96，与真实高度常有几十像素误差；
// 误差为正 → 表格偏高 → 页面溢出 → **页面滚动条与表格滚动条同时出现**（双滚动条的怪异感）；
// 误差为负 → 底部留一大块空白。
// 现改为：① 实测底栏高度；② 以「滚动量归零」的坐标系计算，避免页面一旦滚动就越算越高
// （旧公式直接用 viewport 相对位置，页面滚了 50px 就会把表格再放高 50px，形成雪崩）。
const tableMaxHeight = ref(520);
const footerRef = ref<HTMLElement>();

/** 找到真正承载页面纵向滚动的容器（本项目是布局里的 el-scrollbar__wrap，不是 window） */
function findScrollContainer(el: HTMLElement): HTMLElement {
  let node: HTMLElement | null = el.parentElement;
  while (node) {
    const oy = getComputedStyle(node).overflowY;
    if (oy === "auto" || oy === "scroll" || oy === "overlay") return node;
    node = node.parentElement;
  }
  return document.documentElement;
}

function recalcTableMaxHeight() {
  nextTick(() => {
    const el = tableRef.value?.$el as HTMLElement | null;
    if (!el) return;
    const sp = findScrollContainer(el);
    const isDocument = sp === document.documentElement || sp === document.body;
    const spRect = sp.getBoundingClientRect();
    const rect = el.getBoundingClientRect();
    // 表格顶部在「滚动内容坐标系」中的位置（与当前滚动量无关）：
    // 普通容器要补回 scrollTop；documentElement 自身的 rect 已经随滚动上移，不能再补
    const offsetTop = rect.top - spRect.top + (isDocument ? 0 : sp.scrollTop);
    const viewportH = isDocument
      ? document.documentElement.clientHeight
      : sp.clientHeight;
    // 底部预留 = 底栏高度 + 卡片下内边距(16) + 页面下内边距(16) + 安全余量(4)
    const footerH = footerRef.value?.offsetHeight ?? 40;
    const next = Math.max(
      240,
      Math.floor(viewportH - offsetTop - footerH - 36)
    );
    // 只在变化超过 2px 时赋值：ResizeObserver 回调里避免抖动与无谓重排
    if (Math.abs(next - tableMaxHeight.value) > 2) {
      tableMaxHeight.value = next;
    }
  });
}

// 上方区块（估值条显隐、批量条、筛选条换行、窗口缩放）高度变化时自动重算。
// 用 ResizeObserver 而非逐个 watch，覆盖所有「高度变了但状态没变」的场景。
let headerResizeObserver: ResizeObserver | undefined;
function observeHeaderResize() {
  const el = (tableRef.value?.$el ?? null) as HTMLElement | null;
  const parent = el?.parentElement;
  if (!parent || typeof ResizeObserver === "undefined") return;
  headerResizeObserver?.disconnect();
  headerResizeObserver = new ResizeObserver(() => recalcTableMaxHeight());
  headerResizeObserver.observe(parent);
}

// ── 向下滚动表格时收起顶部区块（估值条 + 工具条留白），把高度让给表格 ──
// 用户原话：「向下拉的时候，能不能把这些收缩了」。
// 表格是内部滚动（页面本身不滚），所以监听表格滚动容器的 scrollTop：
// 下滚超过 64px 进入紧凑态，回到 20px 以内恢复；两个阈值形成滞回区间，避免临界抖动。
const condensed = ref(false);
let bodyScrollEl: HTMLElement | null = null;
let recalcTimer: ReturnType<typeof setTimeout> | undefined;

/** 顶部区块收起/展开是 200ms 过渡，等过渡结束再重算表格高度 */
function scheduleRecalc(delay = 240) {
  if (recalcTimer) clearTimeout(recalcTimer);
  recalcTimer = setTimeout(() => {
    recalcTimer = undefined;
    recalcTableMaxHeight();
  }, delay);
}

function onTableBodyScroll() {
  const top = bodyScrollEl?.scrollTop ?? 0;
  if (!condensed.value && top > 64) {
    condensed.value = true;
    scheduleRecalc();
  } else if (condensed.value && top < 20) {
    condensed.value = false;
    scheduleRecalc();
  }
}

/** 绑定表格滚动容器：无数据时 EP 不渲染滚动容器，故每次加载完成后重绑一次 */
function bindTableScroll() {
  nextTick(() => {
    const el = (tableRef.value?.$el ?? null) as HTMLElement | null;
    const wrap = el?.querySelector<HTMLElement>(
      ".el-table__body-wrapper .el-scrollbar__wrap"
    );
    if (!wrap || wrap === bodyScrollEl) return;
    if (bodyScrollEl) {
      bodyScrollEl.removeEventListener("scroll", onTableBodyScroll);
    }
    bodyScrollEl = wrap;
    wrap.addEventListener("scroll", onTableBodyScroll, { passive: true });
  });
}

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

// 自适应高度：keep-alive 切回 / 窗口缩放 / 估值条或批量条显隐 / 数据加载完成时重算。
// keep-alive 从缓存切回时 EP 可能重建滚动容器，需同时重绑表格滚动监听。
onActivated(() => {
  recalcTableMaxHeight();
  bindTableScroll();
});
watch([realtimeEnabled, batchMode, loading], () => {
  recalcTableMaxHeight();
  bindTableScroll();
});
window.addEventListener("resize", recalcTableMaxHeight);
onBeforeUnmount(() => {
  window.removeEventListener("resize", recalcTableMaxHeight);
  headerResizeObserver?.disconnect();
  if (bodyScrollEl)
    bodyScrollEl.removeEventListener("scroll", onTableBodyScroll);
  if (recalcTimer) clearTimeout(recalcTimer);
});

// ── #995 columnDefs 数据驱动 + #993 列显隐：visibleColumns 已按用户隐藏集过滤
//（仅 selection 因 type="selection" 无法 renderer 化，保留模板由 batchMode 注入；
//  marker 列同理由 defs 自带，正常参与 v-for 渲染——此前误把它一并过滤掉，
//  导致「置顶/关注」状态图标整列消失，2026-09-03 修复）──
const dataColumns = computed(() =>
  columnSettings.visibleColumns.value.filter(d => d.key !== "_selection")
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
   自选卡片沿用 design.md「表格/列表/筛选栏：--space-compact(16px)」
   （CardBlock 默认 --space-standard(24)），仅本页生效，其它页面不受影响。
   #1281 第一轮曾一路压到 8/4px 级留白，结果整页「贴脸」没有呼吸感，已回调：
   留白回到规范值，可见行数靠「行高 52px + 滚动时收起顶部区块」去换，不再靠挤压留白。
   ====================================== */
.watchlist-card {
  padding: var(--space-compact);
}

/* 表格底栏：左侧总数 + 右侧翻页，与表格之间用细分割线分区
   （design.md「卡片内分割线使用 --border-subtle 降低视觉权重」） */
.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-3);
  margin-top: var(--space-2);
  border-top: 1px solid var(--border-light);
}

.table-footer__total {
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

/* ======================================
   向下滚动表格 → 紧凑态（is-condensed）：收起估值条、收紧筛选条留白、淡出说明图标，
   把约 40px 高度还给表格。过渡 200ms（design.md Motion 区间），
   收起/展开后由 index.vue 的 scheduleRecalc 重算表格高度。
   ====================================== */

/* 展开态：估值条有明确高度上限，配合 overflow 才能做 max-height 过渡 */
:deep(.summary-bar) {
  max-height: 48px;
  overflow: hidden;
  transition:
    max-height 200ms ease,
    margin-bottom 200ms ease,
    opacity 150ms ease;
}

:deep(.filter-bar) {
  transition: margin-bottom 200ms ease;
}

.watchlist-page.is-condensed :deep(.summary-bar) {
  max-height: 0;
  margin-bottom: 0;
  opacity: 0;
}

.watchlist-page.is-condensed :deep(.filter-bar) {
  margin-bottom: var(--space-1);
}

.watchlist-page.is-condensed :deep(.search-hint) {
  opacity: 0;
}

/* 尊重系统「减少动效」偏好（design.md Motion） */
@media (prefers-reduced-motion: reduce) {
  :deep(.summary-bar),
  :deep(.filter-bar) {
    transition: none;
  }
}

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

/* 本页行高覆盖：全局基线 44px（el-table.css），本页 56px。
   覆盖理由：自选行承载两组双行信息（「名称 / 代码+标签 chips」与「金额 / 比例」），
   产品列行内容 42px（名称 20 + gap 2 + 元信息 20），加单元格 6px×2 padding 共 54px，
   行高取 56px 留 2px 余量避免内容贴边/裁切。
   #1281 第一轮为压行高把产品列压成单行（40px），实测名称只剩两三个字、被判定不可用；
   第二轮曾用 6px 色点省宽度，用户反馈「标签看不到字」，第三轮改为文字 chip 见下——
   行高 56px 是「三行式 78px」与「压扁式 40px」之间的平衡点：行数约为三行式的 1.4 倍，
   名称、标签文字、金额都完整可读。例外已登记在 design.md「Table · 行高例外」。 */
:deep(.el-table .el-table__row) {
  height: 56px;
}

/* 单元格上下 padding 8px → 6px：与上面 56px 行高自洽（产品列内容 42 + 12 = 54），
   同时让两行信息之间留出呼吸，不再像 40px 那版那样「贴脸」 */
:deep(.el-table .el-table__cell) {
  padding: 6px 0;
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
