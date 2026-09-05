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
  - 顶部操作栏（搜索 / 批量 / 添加 / 刷新 / 导出 / OCR / 实时 / 管理）已于 #1281 第四轮
    改为卡内「双行分区」：第一行 .head-primary 承载搜索 + 核心操作，第二行
    WatchlistFilterBar 承载分组 Tab（最左）+ 次级筛选 + 快捷图标组，功能全保留
    （原独立 WatchlistToolbar.vue 组件已废弃）。移除弹窗已抽取为 WatchlistRemoveDialog。
  - 标签管理 / 行内标签编辑已拆为共有组件 TagManagerDialog / TagEditorDialog
    （components/Watchlist/），未来其它页面需要标签能力可复用。
-->
<template>
  <div
    ref="pageRef"
    class="watchlist-page"
    :class="{ 'is-condensed': condensed && !batchMode }"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 本页自有原生滚动容器：让布局 el-scrollbar 的内容正好撑满视口、自身不再滚动，
         从而消除 el-scrollbar 每帧测量 scrollHeight/clientHeight 引发的 Forced reflow
         与 requestAnimationFrame 耗时（控制台 [Violation]）。表头 position:sticky 吸顶
         改为相对本容器（原生、平滑），搜索行收起也监听本容器滚动。 -->
    <div class="watchlist-scroll">
      <!-- 主区域：单个工作区卡片。顶部按「双行分区」布局（#1281 第四轮修订，2026-09-05）：
         第一行 .head-primary 承载「全局搜索 + 核心操作」，第二行 WatchlistFilterBar
         承载「分组 Tab（最左）+ 次级筛选 + 快捷图标」，两组元素互不挤占、层级分明；
         所有功能原样保留，滚动进入紧凑态时收起第一行把高度让给表格。 -->
      <CardBlock class="watchlist-card">
        <!-- 第一行：搜索 + 核心操作（滚动紧凑态收起，见下方 is-condensed 规则） -->
        <div class="head-primary">
          <!-- 批量模式：第一行整行切换为批量工具条 -->
          <template v-if="batchMode">
            <span
              class="text-sm font-medium shrink-0"
              :style="{ color: 'var(--text-primary)' }"
            >
              已选 {{ selectedItems.length }} 项
            </span>
            <el-select
              v-model="batchMoveGroupId"
              placeholder="移动到分组"
              class="batch-move-select"
              clearable
              @change="handleBatchMoveToGroup"
            >
              <el-option
                v-for="group in customGroups"
                :key="group.id"
                :label="group.name"
                :value="group.id"
              >
                <div class="flex items-center gap-2">
                  <!-- 数据色例外：分组色为用户数据（非设计令牌），缺失时回退中性 token -->
                  <span
                    class="w-2.5 h-2.5 rounded-full"
                    :style="{
                      backgroundColor: group.color || 'var(--text-tertiary)'
                    }"
                  />
                  <span>{{ group.name }}</span>
                </div>
              </el-option>
            </el-select>
            <el-button
              class="batch-delete-btn"
              :disabled="selectedItems.length === 0"
              @click="handleBatchDelete"
            >
              <IconifyIconOffline icon="ep:delete" class="mr-1" />
              删除选中
            </el-button>
            <el-button type="primary" @click="toggleBatchMode">
              退出批量模式
            </el-button>
          </template>

          <!-- 正常模式：搜索占左、核心操作居右，中间留白呼吸 -->
          <template v-else>
            <div class="head-primary__search">
              <el-input
                v-model="searchKeyword"
                placeholder="搜索自选..."
                clearable
                :prefix-icon="Search"
                class="watchlist-search"
                @input="debounceSearch"
              />
              <el-tooltip
                content="在当前自选列表中按代码或名称过滤"
                placement="bottom-start"
                :offset="8"
              >
                <IconifyIconOffline
                  icon="ep:info-filled"
                  class="search-hint text-sm cursor-help transition-opacity"
                  :style="{ color: 'var(--text-tertiary)' }"
                />
              </el-tooltip>
            </div>
            <div class="head-primary__actions">
              <el-button plain @click="openSettingsDrawer">
                <IconifyIconOffline icon="ep:setting" class="mr-1" />
                管理
              </el-button>
              <el-button type="primary" @click="openAddDialog">
                <IconifyIconOffline icon="ep:plus" class="mr-1" />
                添加自选
              </el-button>
            </div>
          </template>
        </div>

        <!-- 第二行（WatchlistFilterBar）：分组 Tab 最左 + 标签筛选/视图/新建 + 快捷图标 -->
        <WatchlistFilterBar
          :groups="groups"
          :tags="tags"
          :toolbar="toolbar"
          :on-refresh="onCatalogChanged"
          @view-change="handleViewChange()"
          @tag-apply="tags.applyTagFilter()"
          @tag-clear="tags.clearTagFilter()"
          @manage-groups="groupManagerVisible = true"
        >
          <!-- 快捷图标组（#actions）：刷新/导出/AI 导入/实时估值开关，常驻本行最右；
             与第一行的「管理 / 添加自选」主按钮分开，避免整排按钮挤在一起 -->
          <template #actions>
            <div v-if="!batchMode" class="header-actions">
              <!-- 快捷图标组与筛选区之间的细分隔线（design.md 卡片内分割线） -->
              <div class="head-divider" aria-hidden="true" />
              <el-tooltip content="刷新" placement="bottom">
                <el-button circle class="icon-tool-btn" @click="fetchData()">
                  <IconifyIconOffline icon="ep:refresh" />
                </el-button>
              </el-tooltip>

              <el-tooltip content="导出" placement="bottom">
                <el-button circle class="icon-tool-btn" @click="exportData">
                  <IconifyIconOffline icon="ep:download" />
                </el-button>
              </el-tooltip>

              <el-tooltip content="AI 导入" placement="bottom">
                <el-button circle class="icon-tool-btn" @click="openOcrDialog">
                  <IconifyIconOffline icon="ep:magic-stick" />
                </el-button>
              </el-tooltip>

              <!-- 实时估值开关：开启 = 品牌色高亮（tooltip「关闭实时估值」），关闭 = 中性弱化 -->
              <el-tooltip :content="toggleBtnText" placement="bottom">
                <el-button
                  circle
                  class="icon-tool-btn"
                  :class="{ 'is-active': toggleBtnText.includes('关闭') }"
                  @click="realtime.toggle()"
                >
                  <IconifyIconOffline icon="ep:lightning" />
                </el-button>
              </el-tooltip>
            </div>
          </template>
        </WatchlistFilterBar>

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

        <!-- 批量操作的「删除选中」已并入头部行 #actions（#1281 第四轮），
           不再单独占一行，避免批量模式下顶部又多出一块 -->

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
        <!-- 表格容器：本页为「单滚动容器（页面滚动）」架构——el-table 不设固定 height，
           直接按内容高度展开所有行，页面随布局 el-scrollbar 整体滚动（只有一条滚动条）。
           表头经 CSS position:sticky 吸顶（见本文件底部样式）；向下滚动时第一行搜索区
           与估值条收起（is-condensed）把高度让给表格。 -->
        <div class="watchlist-table-wrap">
          <el-table
            ref="tableRef"
            v-loading="loading"
            :data="items"
            :row-class-name="rowClassName"
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
        </div>

        <!-- 表格底栏：左侧总数 + 右侧翻页。
           合规文案不放在本行（用户反馈放表格里很怪异），
           改由页面底部 .watchlist-footer 承担（见 CardBlock 之后）。 -->
        <div class="table-footer">
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

      <!-- 合规页脚：常驻页面底部，随页面滚动至最底部时自然显现（仅本页自绘，
         全局布局级页脚已通过路由 meta.hideFooter 隐藏，避免重复）。表头吸顶 +
         页脚置底，单滚动容器（页面滚动）承载，无双滚动条观感。 -->
      <LayFooter />
    </div>
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
import { Search } from "@element-plus/icons-vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import Sortable from "sortablejs";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";
import OcrImportModal from "@/components/QuickEntry/OcrImportModal.vue";
import SettingsDrawer from "@/components/Watchlist/SettingsDrawer.vue";
import TagManagerDialog from "@/components/Watchlist/TagManagerDialog.vue";
import GroupManagerDialog from "@/components/Watchlist/GroupManagerDialog.vue";
import TagEditorDialog from "@/components/Watchlist/TagEditorDialog.vue";
import { getWatchlistTrends, type WatchlistItem } from "@/api/watchlist";
import CardBlock from "@/components/CardBlock/index.vue";
import LayFooter from "@/layout/components/lay-footer/index.vue";
// 金额/涨跌展示组件（MoneyDisplay/RiseFallText/MoneyWithRatio）已随 #995 列渲染器化
// 迁移至 columnRenderers.tsx，本页模板不再直接使用
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

/**
 * 置顶行的视觉区分（#1281 第四轮）。
 * 置顶项由后端默认排序（is_pinned + 更新时间）自然落在最前，这里再给整行一层
 * 极淡品牌底，扫一眼即可看出「上面这一块是置顶的」；置顶图标本身则内联在
 * 产品列名称前（columnRenderers.tsx renderRowMarks），不再占用独立列宽。
 */
function rowClassName({ row }: { row: WatchlistItem }): string {
  return row.is_pinned ? "is-pinned-row" : "";
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
  bindPageScroll();
});

// ── #992 表头列拖拽：sortablejs 复用（RePureTableBar 同款方案）──
const tableRef = ref();

// ── 单滚动容器（页面滚动）+ 表头吸顶 + 底部页脚置底 ──
// 用户原话：「向下拉的时候，能不能把这些收缩了」+「表头需要固定 + 拉到底展示 footer」。
// 本页改为页面级滚动：el-table 不再设固定 height（因此没有内部滚动条），
// 整页随布局 el-scrollbar 滚动；表头用 CSS position:sticky 吸顶（见下方样式），
// 页脚作为页面底部正常流元素，滚动到最底部时自然显现。这样整页只有一个滚动条，
// 彻底消除此前「外层布局滚动 + 内层表格滚动」双滚动条、且外层滚动把表头带跑的毛病。
const condensed = ref(false);
let pageScrollEl: EventTarget | null = null;
let scrollGetTop: (() => number) | null = null;
const pageRef = ref<HTMLElement>();

/** 找到本页真正的滚动容器：
   - 优先用本页自有原生滚动容器 .watchlist-scroll（承担全部纵向滚动），
     这样布局 el-scrollbar 内容满高、自身不滚动，彻底消除其 onScroll 每帧
     读取 scrollHeight/clientHeight 引发的 Forced reflow 与慢 rAF（控制台 [Violation]）；
   - 兜底（异常路径）：回退到布局 .el-scrollbar__wrap / 窗口。 */
function findScrollContainer(): {
  el: EventTarget;
  getTop: () => number;
} | null {
  const page = pageRef.value;
  const sc = page?.querySelector(".watchlist-scroll") as HTMLElement | null;
  if (sc) return { el: sc, getTop: () => sc.scrollTop };
  if (page) {
    const wrap = page.closest(".el-scrollbar__wrap") as HTMLElement | null;
    if (wrap) return { el: wrap, getTop: () => wrap.scrollTop };
  }
  const se = document.scrollingElement;
  if (se && se.scrollHeight > se.clientHeight) {
    return { el: window, getTop: () => se.scrollTop };
  }
  return null;
}

function onPageScroll() {
  const el = pageScrollEl;
  const getTop = scrollGetTop;
  if (!el || !getTop || batchMode.value) return; // 批量工具条也在第一行，批量期间保持可见
  // 下滚超过 64px 收起第一行搜索区（.head-primary），把高度让给表格多看近一行；
  // 回到 20px 以内恢复；20~64 为滞回区，维持当前状态。务必用「保持」而非翻转，
  // 否则一旦收起，下一帧只要 top>20 又会被算成展开，导致每帧反复重渲染（强制重排、
  // el-scrollbar 每帧重测、表头抖动）。
  const top = getTop();
  let next = condensed.value;
  if (top > 64) next = true;
  else if (top <= 20) next = false;
  if (next !== condensed.value) condensed.value = next;
}

/** 绑定页面滚动容器：数据加载完成 / keep-alive 切回后重绑一次 */
function bindPageScroll() {
  nextTick(() => {
    const sc = findScrollContainer();
    if (!sc) return;
    if (sc.el !== pageScrollEl) {
      if (pageScrollEl)
        pageScrollEl.removeEventListener("scroll", onPageScroll);
      pageScrollEl = sc.el;
      scrollGetTop = sc.getTop;
      pageScrollEl.addEventListener("scroll", onPageScroll, { passive: true });
    }
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

// 页面滚动容器绑定：keep-alive 切回 / 估值条或批量条显隐 / 数据加载完成时重绑。
onActivated(() => {
  bindPageScroll();
});
watch([realtimeEnabled, batchMode, loading], () => {
  bindPageScroll();
});
// 切走本页（keep-alive 缓存但不可见）时移除滚动监听
onBeforeUnmount(() => {
  if (pageScrollEl) pageScrollEl.removeEventListener("scroll", onPageScroll);
});

// ── #995 columnDefs 数据驱动 + #993 列显隐：visibleColumns 已按用户隐藏集过滤
//（仅 selection 因 type="selection" 无法 renderer 化，保留模板由 batchMode 注入。
//  原 marker 列已于 #1281 第四轮删除：置顶/关注状态改为产品列名称前内联渲染，
//  不再作为独立列参与 v-for）──
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

/* 自选页容器（单滚动容器版）：
   - 本页改用「页面滚动」承载（而非表格内部滚动）：el-table 不设固定 height，
     按内容高度展开所有行，整页随布局 el-scrollbar 滚动——整页只有一条滚动条，
     彻底消除此前 fixedHeader 下「外层布局滚动 + 内层表格滚动」双滚动条、且外层滚动
     把表头带跑（吸顶失效）的毛病；
   - .watchlist-page 仅 min-height:100% 让短内容页也撑满视口、页脚贴底，
     内容超过视口时自然增高由布局滚动——不再用 calc(100vh - 86px) 这种硬编码头部高度
     （此前误把头部高度写死导致页面溢出布局、双滚动条）；
   - 同时释放 .main-content 默认的 48px 大边距，把空间还给表格。 */
.watchlist-page {
  display: flex;
  flex-direction: column;
  /* 撑满布局 el-scrollbar 分配给本页的高度（fixedHeader 下 .grow 为确定高度），
     使外层 el-scrollbar 内容正好满视口、自身不滚动——这是消除其每帧测量引发的
     Forced reflow / 慢 rAF 的关键。 */
  height: 100%;
  overflow: hidden;
}

/* 本页自有原生滚动容器：承担全部纵向滚动（head/筛选/表格/页脚），
   表头 position:sticky 相对它吸顶（原生、平滑）。外层 el-scrollbar 因内容满高
   不再滚动，故不产生测量开销，控制台 [Violation] 消失。 */
.watchlist-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

/* 高密度列表页：取消全局 .main-content 的 48px 边距，避免上下白边吞掉表格行数。 */
.watchlist-page.main-content {
  padding: 0;
}

.watchlist-card {
  display: flex;
  flex-direction: column;
  /* 卡片随内容自然增高；padding 沿用 design.md 的 --space-compact(16px)。
     不再设 flex:1/min-height:0（那是「表格内部滚动撑满」时代的写法，已废弃）。 */
  padding: var(--space-compact);
}

/* 表格容器：随内容自然增高（el-table 不设固定 height，无内部滚动条）。
   表头吸顶见下方 :deep(.el-table__header-wrapper)。 */
.watchlist-table-wrap {
  display: flex;
  flex-direction: column;
}

/* 表头吸顶：本页为单滚动容器（页面滚动），表头随页面滚动时固定在滚动视口顶部；
   z-index 高于行，背景用卡片色遮住下方滚动行，避免穿透。top:0 即贴滚动容器顶
   （布局已用 padding 把导航/页签让出来，无需额外偏移）。
   关键：el-table 默认 overflow:hidden，会成为 header-wrapper 的「最近滚动祖先」，
   导致 sticky 相对表格自身（不随页面滚）而非页面滚动容器 .el-scrollbar__wrap，
   表头会随页面一起滚走——这正是此前吸顶反复失效的根因。本页表格无内部滚动，
   改为 overflow:visible 让 sticky 正确吸附到布局滚动容器。（无横向滚动，
   横向溢出由 .watchlist-page 的 overflow-x:clip 裁切，不会外溢）。 */
.watchlist-table-wrap :deep(.el-table) {
  overflow: visible;
}
.watchlist-table-wrap :deep(.el-table__header-wrapper) {
  position: sticky;
  top: 0;
  z-index: 3;
  background: var(--bg-card);
}

/* ======================================
   双行分区头部（#1281 第四轮修订，2026-09-05）
   —— 第一行 .head-primary：搜索框 + 核心操作（管理 / 添加自选）；
      第二行由 WatchlistFilterBar 承载「分组 Tab（最左）+ 标签筛选/视图/新建」，
      其 #actions 注入快捷图标组（刷新/导出/AI导入/实时估值）。
   两行各自 justify-between / 左紧右松，主次分离；控件统一 32px 高、
   同一垂直基线，滚动进入紧凑态时收起第一行（下方 is-condensed 规则）。
   ====================================== */

/* 搜索 + 核心操作区：固定高度由内容撑出，与下方筛选行间距 6px。
   展开态设 max-height（内容实际约 36px）+ overflow hidden，配合过渡实现
   表格滚动时的紧凑态收起（下方 is-condensed 规则），上限留余量防误裁。 */
.head-primary {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  max-height: 40px;
  margin-bottom: 6px;
  overflow: hidden;
  transition:
    max-height 200ms ease,
    margin-bottom 200ms ease,
    opacity 150ms ease;
}

/* 搜索区：固定 240px（2026-09-05 修订）。
   此前设为 flex:1 + max-width 560，输入框被拉得过长、与右侧按钮组失衡，
   且「搜索自选」只是 4~6 字提示，240px 已足够容纳代码/名称输入。 */
.head-primary__search {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

.watchlist-search {
  width: 240px;
}

/* 核心操作按钮组：次级（管理）32px + 主按钮（添加自选）36px，同一垂直基线居中。
   尺寸规范（2026-09-05）：主按钮 36 / 次级文字按钮 32 / 纯图标按钮 28。 */
.head-primary__actions {
  display: flex;
  flex-shrink: 0;
  gap: var(--space-2);
  align-items: center;
}

.head-primary__actions :deep(.el-button--primary) {
  height: 36px;
}

/* 第二行快捷图标组（FilterBar #actions）：固定居右、等距排布 */
.header-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

.header-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

/* 快捷图标组前的细分隔线：与左侧筛选区建立视觉边界 */
.head-divider {
  flex-shrink: 0;
  width: 1px;
  height: 20px;
  margin: 0 2px;
  background-color: var(--border-light);
}

/* 轻量图标操作按钮（刷新/导出/AI导入/实时估值）
   尺寸规范：纯图标按钮统一 28×28（与主按钮 36、次级按钮 32 形成三级梯度）；
   默认中性弱化线框，hover 提亮；实时开关开启态填品牌实底 */
.icon-tool-btn {
  width: 28px;
  height: 28px;
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

.icon-tool-btn:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

/* 实时开启态：品牌色实底高亮——开关在图标组里是否可见/是否已开，一眼可辨 */
.icon-tool-btn.is-active {
  color: var(--brand-100);
  background-color: var(--brand-700);
  border-color: var(--brand-700);
}

.icon-tool-btn.is-active:hover {
  background-color: var(--brand-800);
  border-color: var(--brand-800);
}

/* 批量模式：移动到分组下拉 */
.batch-move-select {
  width: 160px;
}

.batch-move-select :deep(.el-input__wrapper) {
  padding-top: 0;
  padding-bottom: 0;
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  box-shadow: none;
  transition: all 0.2s ease;
}

.batch-move-select :deep(.el-input__wrapper:hover) {
  border-color: var(--brand-500);
}

.batch-move-select :deep(.el-input__wrapper.is-focus) {
  border-color: var(--brand-700);
  box-shadow: var(--focus-ring);
}

/* 批量模式：删除选中（幽灵危险按钮） */
.batch-delete-btn {
  color: var(--color-danger);
  background-color: transparent;
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
  transition: all 0.2s ease;
}

.batch-delete-btn:hover {
  color: #fff;
  background-color: var(--color-danger);
  border-color: var(--color-danger);
}

.batch-delete-btn:active {
  transform: translateY(1px);
}

.batch-delete-btn:disabled {
  color: var(--text-disabled);
  cursor: not-allowed;
  border-color: var(--text-disabled);
  opacity: 0.5;
}

.batch-delete-btn:disabled:hover {
  color: var(--text-disabled);
  background-color: transparent;
}

/* 说明图标：默认可见，滚动进入紧凑态时淡出（规则见下「紧凑态」） */
.search-hint {
  opacity: 1;
  transition: opacity 150ms ease;
}

/* ======================================
   向下滚动页面 → 紧凑态（is-condensed）：
   仅折叠第一行搜索区 .head-primary（全局搜索 + 核心操作），把高度让给表格多看近一行；
   分组 Tab 行与实时估值条 .summary-bar 保持可见，表头经 CSS position:sticky 吸顶。
   过渡 200ms（design.md Motion 区间）。本页为单滚动容器（页面滚动），
   紧凑态由监听「页面滚动容器 scrollTop」触发（见脚本 bindPageScroll），不再依赖
   表格内部滚动；页脚作为页面底部正常流元素常驻，滚动到最底部时自然显现。
   ====================================== */
.watchlist-page.is-condensed .head-primary {
  max-height: 0;
  margin-bottom: 0;
  opacity: 0;
  pointer-events: none;
}

.watchlist-page.is-condensed .search-hint {
  opacity: 0;
}

/* 表格底栏：左侧总数 + 右侧翻页，与表格之间用细分割线分区
   （design.md「卡片内分割线使用 --border-subtle 降低视觉权重」） */

/* 表格底栏：2026-09-05 收紧 padding-top(12→8) 与 margin-top(8→4)，省下约 8px 首屏高度。
   左侧总数 + 右侧翻页，与表格之间用细分割线分区。 */
.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-2);
  margin-top: var(--space-1);
  border-top: 1px solid var(--border-light);
}

.table-footer__total {
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

/* 估值条（实时开启时显示）：展开态有明确高度上限 + overflow，配合 max-height 折叠；
   进入紧凑态（.watchlist-page.is-condensed）时收起，把高度让给表格。 */
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

/* 尊重系统「减少动效」偏好（design.md Motion） */
@media (prefers-reduced-motion: reduce) {
  .head-primary,
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

/* 表格空状态：撑满 body wrapper（#1281 第五轮，2026-09-05）。
   没有数据时卡片高度由 .watchlist-table-wrap flex:1 撑满，但 EP 默认的 empty 占位
   很小、靠上居中，导致"几行字 + 下方大片空白"的难看观感；
   给 .watchlist-empty height:100% + flex column justify center，让文案垂直居中、占满 body。 */
.watchlist-empty {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
  justify-content: center;
  height: 100%;
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
  height: 52px;
}

/* ── 置顶行：极淡品牌底，让「置顶区」一眼可辨（#1281 第四轮）──
   置顶项由后端默认排序落在最前，加这层底色后即使与后续行混排也能分组识别。
   必须打到 td 上：EP 的斑马纹（--el-table-tr-bg-color）与 hover 底色都在 td 层级，
   只写 tr 会被覆盖；置顶 + hover 再递进一档，避免 hover 反馈丢失。
   底色用 --brand-100（亮色近白粉 / 暗色深棕红），明暗模式自动适配。 */
:deep(.el-table__row.is-pinned-row > td.el-table__cell) {
  background-color: var(--brand-100);
}

:deep(.el-table__row.is-pinned-row:hover > td.el-table__cell) {
  background-color: var(--brand-200);
}

/* 单元格上下 padding 8px → 6px：与上面 56px 行高自洽（产品列内容 42 + 12 = 54），
   同时让两行信息之间留出呼吸，不再像 40px 那版那样「贴脸」 */
:deep(.el-table .el-table__cell) {
  padding: 4px 0;
}

/* 表头不换行：保证排序图标(.caret-wrapper)与表头文字始终同一行，
   修复 5 字表头（添加自选日 / 添加后涨幅）加排序按钮后换行错位的问题。
   各列 width 已预留足够空间容纳文字+图标，此处仅作双保险防止意外折行。 */
:deep(.el-table__header th.el-table__cell .cell) {
  white-space: nowrap;
}

/* 表头行高压到约 34px（EP 默认 th padding 8px ≈ 40px 高，此处收到 5px）。
   与「顶部区块压缩」同批（#1281 第四轮）：表头只承载列标题与排序图标，
   5px 上下留白仍满足可点区域，省下的约 10px 让给数据行。 */
:deep(.el-table__header th.el-table__cell) {
  padding: 3px 0;
}

/* 分组胶囊 Tab / 新建分组按钮样式已迁移至 components/Watchlist/WatchlistFilterBar.vue（方案 B，2026-08-14） */

/* 置顶/关注标记图标与标签 chips（.marker-icon/.tag-chip/.add-tag-btn）样式已迁移至
   columnRenderers.css——列 renderer 化后这些 DOM 由 tsx 产生，不携带本页 scoped 属性，
   留在本页的规则会静默失效（#995 迁移遗留，2026-08-22 清理） */
</style>
