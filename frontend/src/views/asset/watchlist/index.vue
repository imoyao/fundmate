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
    改为卡内「双行分区」，2026-09-05 微调行内职责：第一行 .head-primary 承载搜索 +
    快捷工具图标（刷新/导出/AI 导入/实时）+ 核心操作（管理/添加自选），第二行
    WatchlistFilterBar 承载分组 Tab（最左）+ 次级筛选，功能全保留
    （原独立 WatchlistToolbar.vue 组件已废弃）。移除弹窗已抽取为 WatchlistRemoveDialog。
  - 标签管理 / 行内标签编辑已拆为共有组件 TagManagerDialog / TagEditorDialog
    （components/Watchlist/），未来其它页面需要标签能力可复用。
-->
<template>
  <div
    ref="pageRef"
    class="watchlist-page"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 本页单滚动容器语义（2026-09-05 根因修复）：本页不再自造滚动容器，
         页面滚动全部由布局层的 .el-scrollbar__wrap 承担。.watchlist-scroll 只是
         一个无 overflow 的普通包裹层（其类名保留便于定位/测试），保证 CSS sticky
         链不被内部 overflow 截断（见本文件底部样式注释）。 -->
    <div class="watchlist-scroll">
      <!-- 主区域：单个工作区卡片。顶部按「双行分区」布局（#1281 第四轮修订，2026-09-05）：
         第一行 .head-primary 承载「全局搜索 + 快捷工具图标 + 核心操作」——搜索自动隐藏
         与工具常驻同排，第二行 WatchlistFilterBar 承载「分组 Tab（最左）+ 次级筛选」
         纯筛选职责（两组元素互不挤占、层级分明）。
         滚动吸顶分工：head-primary 不吸顶，下滚自然滚出视口（搜索框「自动隐藏」）；
         WatchlistFilterBar 的 .filter-bar 与表格表头经 position:sticky 连续吸顶。 -->
      <CardBlock class="watchlist-card">
        <!-- 第一行：搜索 + 核心操作（不吸顶；作为滚动内容首行，下滚时自然滚出视口） -->
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

          <!-- 正常模式：搜索占左、核心操作 + 快捷工具居右，中间留白呼吸。
               布局修订（2026-09-05）：原第二行的「刷新/导出/AI 导入/实时估值」图标组
               并入本行（用户反馈第二行因分组 Tab + 筛选 + 图标组共挤一行显拥挤、
               本行反而空），行内从左到右为「图标组(次级工具) | 管理(次级) | 添加自选
               (主 CTA 最右)」，图标组前不再加 divider（其左侧本就是行间留白）。 -->
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
              <!-- 快捷工具图标组（原 WatchlistFilterBar #actions，2026-09-05 上移本行）：
                   刷新 / 导出 / AI 导入 / 实时估值开关。实时开启态品牌色高亮见 .icon-tool-btn.is-active -->
              <div v-if="!batchMode" class="header-actions">
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
                  <el-button
                    circle
                    class="icon-tool-btn"
                    @click="openOcrDialog"
                  >
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
              <!-- 图标组与核心操作之间的细分隔线（design.md 卡片内分割线） -->
              <div class="head-divider" aria-hidden="true" />
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

        <!-- 第二行（WatchlistFilterBar）：分组 Tab 最左 + 标签筛选/视图/新建分组，
             纯筛选职责（2026-09-05：快捷图标组刷新/导出/AI导入/实时估值已上移第一行，
             见 head-primary__actions，本行不再拥挤；批量模式下整行由组件内部隐藏） -->
        <WatchlistFilterBar
          :groups="groups"
          :tags="tags"
          :toolbar="toolbar"
          :on-refresh="onCatalogChanged"
          @view-change="handleViewChange()"
          @tag-apply="tags.applyTagFilter()"
          @tag-clear="tags.clearTagFilter()"
          @manage-groups="groupManagerVisible = true"
          @manage-group-items="groupItemsVisible = true"
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
        <!-- 表格容器（外层滚动 + 表头吸顶，2026-09-05 根因修复）：
           el-table 不设固定 height，直接按内容高度展开所有行；整页由外层布局
           el-scrollbar 滚动（无内部滚动条 → 无双滚动条、无每帧测量开销）。
           表头经 CSS position:sticky 吸顶（见本文件底部样式）；向下滚动时：
           .head-primary（搜索行）作为滚动首行自然滚出视口 = 搜索框自动隐藏；
           分组条 .filter-bar 与表头 sticky 连续吸顶。 -->
        <div class="watchlist-table-wrap">
          <!-- 表格本体：数据/行操作渲染。loading 期间不显示 EP 全表遮罩（spinner），
               改由下方 WatchlistTableSkeleton 覆盖「表头之下」区域做行级骨架占位。
               :data 在 loading 时置空：分组切换/搜索等加载中，让表格回到表头 + 空体
               的高度（整页收缩为一屏），骨架屏得以完整覆盖可视区——若保留旧行，
               旧行高度会把页面撑长，滚到底部时骨架只盖到 wrap 高度、下方露出大片空白。 -->
          <el-table
            ref="tableRef"
            :data="loading ? [] : items"
            empty-text=""
            :row-class-name="rowClassName"
            stripe
            @selection-change="handleSelectionChange"
            @sort-change="onSortChange"
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
          </el-table>
          <!-- 空态覆盖层：表格无数据且非加载时，以绝对定位铺满「表头之下」的表格区
               并垂直居中（问题 1：空分组时表格占满页面，而非文案悬在卡片中部）。
               不复用 el-table #empty（其 empty-block 高度由 EP 撑到 280px 封顶，
               无法在整段空表格区内垂直居中）；隐藏 el-table 自带空态文字
               （empty-text=""）避免穿透。表头吸顶保留（30px，见 overlay top）。 -->
          <div
            v-if="!loading && items.length === 0"
            class="watchlist-empty-overlay"
          >
            <!-- 空白自定义分组：虚线「+ 从全部自选添加」快捷入口（#987）。
                 空白组是可填充的占位区，给可点入口而非阻断性文案；系统分组为空、
                 以及标签筛选无匹配的场景，仍走下方纯文案空态。 -->
            <template v-if="isEmptyCustomGroup">
              <button
                type="button"
                class="empty-add-btn"
                @click="openGroupItemsDialog"
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
            </template>
          </div>
          <!-- 骨架屏覆盖层：仅数据加载期间渲染（分组切换/首屏/搜索/翻页），
               随 .watchlist-table-wrap 定位，top 对齐表头底部。 -->
          <WatchlistTableSkeleton v-if="loading" />
        </div>

        <!-- 表格底栏：左侧总数 + 右侧翻页。
           合规文案不放在本行（用户反馈放表格里很怪异），
           改由页面底部 .watchlist-footer 承担（见 CardBlock 之后）。 -->
        <div class="table-footer">
          <span class="table-footer__total">共 {{ totalItems }} 条</span>
          <div class="table-footer__right">
            <!-- 每页条数选择（#1335）：纯本地记忆（localforage），不落数据库 -->
            <div class="page-size-select">
              <span class="page-size-select__label">每页</span>
              <el-select
                :model-value="pageSize"
                size="small"
                class="page-size-select__control"
                @change="setPageSize"
              >
                <el-option
                  v-for="opt in pageSizeOptions"
                  :key="opt"
                  :label="opt"
                  :value="opt"
                />
              </el-select>
            </div>
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

    <!-- 分组内产品增删弹窗（#987）：管理「某个自定义分组里有哪些产品」，
         与上方 GroupManagerDialog（管理分组本身）分工互补。系统分组不提供该能力
         （activeCustomGroup 为 null 时弹窗不展示内容）。 -->
    <GroupItemsDialog
      v-model="groupItemsVisible"
      :group="activeCustomGroup"
      @changed="onGroupItemsChanged"
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
import { Search, Plus } from "@element-plus/icons-vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import Sortable from "sortablejs";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";
import OcrImportModal from "@/components/QuickEntry/OcrImportModal.vue";
import SettingsDrawer from "@/components/Watchlist/SettingsDrawer.vue";
import TagManagerDialog from "@/components/Watchlist/TagManagerDialog.vue";
import GroupManagerDialog from "@/components/Watchlist/GroupManagerDialog.vue";
// #987：组内产品增删（与 GroupManagerDialog 管「分组本身」分工不同）
import GroupItemsDialog from "@/components/Watchlist/GroupItemsDialog.vue";
import TagEditorDialog from "@/components/Watchlist/TagEditorDialog.vue";
import {
  getWatchlistTrends,
  type WatchlistItem,
  type WatchlistGroup
} from "@/api/watchlist";
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
import WatchlistTableSkeleton from "@/views/asset/watchlist/WatchlistTableSkeleton.vue";
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
  pageSizeOptions,
  initPageSize,
  setPageSize,
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

// ── #987：自定义分组「组内产品增删」──
// 与「管理分组」（GroupManagerDialog，管理分组本身的新建/改名/删除）分工不同：
// 本弹窗只管「某个自定义分组里有哪些产品」，对应空白组快捷添加 + 常规组内增删。
// 系统分组由后端规律方法维护，不提供组内增删（activeCustomGroup 为 null 即不生效）。
const groupItemsVisible = ref(false);
/** 当前选中的自定义分组对象；系统分组或未选中时为 null */
const activeCustomGroup = computed<WatchlistGroup | null>(() => {
  const gid = activeCustomGroupId.value;
  if (gid == null) return null;
  return customGroups.value.find(g => g.id === gid) ?? null;
});
/** 空态是否落在「空白自定义分组」：需为自定义分组且未叠加标签筛选
    （叠加了标签筛选时的空结果是筛选无匹配，不应引导去加产品） */
const isEmptyCustomGroup = computed(
  () =>
    currentIsCustom.value &&
    selectedFilterTagIds.value.length === 0 &&
    !searchKeyword.value
);

function openGroupItemsDialog(): void {
  groupItemsVisible.value = true;
}

/** 组内增删成功后：分组计数与列表都需刷新（#987 验收标准：计数与列表实时生效） */
function onGroupItemsChanged(): void {
  void fetchGroups();
  void fetchData();
}

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

/**
 * 表头排序分发（issue #1333 修正）。
 * 带 realtimeField 的列（change_pct 涨跌幅 / current_price 最新价）其「有意义的值」来自
 * 前端实时行情引擎，后端只有 None / positions 静态快照——若走后端 sort_by 会按错值排，
 * 故这两列改为前端按实时估值项做客户端排序。
 * 限制：后端无实时值，跨页一致排序本就不成立，因此只排当前页（items）；
 * 其余列维持原 handleSortChange → 后端 sort_by/sort_order（跨页一致）。
 */
function onSortChange({
  prop,
  order
}: {
  prop?: string | number;
  order: "ascending" | "descending" | null;
}) {
  const def = prop
    ? columnSettings.visibleColumns.value.find(d => d.key === String(prop))
    : undefined;
  if (def?.realtimeField && order) {
    const field = def.realtimeField; // "currentPrice" | "changePct"
    const dir = order === "descending" ? -1 : 1;
    const rtMap = new Map<string, number>();
    for (const it of realtime.items.value ?? []) {
      const v = it[field];
      if (typeof v === "number") rtMap.set(it.symbol, v);
    }
    const sortVal = (row: (typeof items.value)[number]): number => {
      const rv = rtMap.get(row.symbol);
      if (typeof rv === "number") return rv;
      const sv = (row as Record<string, unknown>)[def.key];
      return typeof sv === "number" ? sv : 0;
    };
    items.value = [...items.value].sort(
      (a, b) => (sortVal(a) - sortVal(b)) * dir
    );
    return;
  }
  handleSortChange({ prop, order });
}

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
onMounted(async () => {
  // 先恢复本地记忆的每页条数，确保首屏 fetch 即使用户上次的选择（#1335）
  await initPageSize();
  fetchGroups();
  fetchTags();
  fetchData();
  watch(activeGroup, () => {
    currentPage.value = 1;
    fetchData();
  });
  initHeaderDrag();
  bindStickyObserver();
  bindPageMinHObserver();
});

// ── #992 表头列拖拽：sortablejs 复用（RePureTableBar 同款方案）──
const tableRef = ref();

// ── 表头吸顶（外层滚动版，2026-09-05 根因修复）──
// 本页不再自造滚动容器：滚动全部交给布局层的 .el-scrollbar__wrap（fixedHeader 模式
// 布局唯一的滚动容器）。el-table 不设固定 height，按内容高度展开所有行。
// 吸顶链：
//   1. .filter-bar（分组 Tab 行）CSS position:sticky top:0 → 相对外层滚动容器吸顶；
//   2. .el-table__header-wrapper（表头）position:sticky，top 取 CSS 变量
//      --watchlist-sticky-top = .filter-bar 实际高度（脚本实测写入，见 syncStickyOffset），
//      使表头正好吸在分组条下方，形成「分组条 + 表头」连续固定区；
//   3. .head-primary（搜索行）不吸顶，作为滚动内容的正常首行——下滚时自然滚出视口，
//      即「搜索框自动隐藏」。
// 关键前置：.watchlist-page/.watchlist-scroll/.el-scrollbar__view 均不得有
// overflow:hidden/auto（否则会截断 sticky 上溯，见上方样式注释与 lay-content）。
const pageRef = ref<HTMLElement>();
let stickyObserver: ResizeObserver | null = null;

/** 实测分组条 .filter-bar 高度，写入吸顶偏移 CSS 变量。
 *  分组条是正常流元素，批量模式/视图 segmented/标签数量变化都可能改变其换行高度，
 *  故用 ResizeObserver 监听其几何变化，实时重算吸顶位置。
 *  - 呼吸感（2026-09-05）：已内化为 .filter-bar 的 padding-top（CSS 变量
 *    --watchlist-sticky-gap = STICKY_TOP_GAP），白背景覆盖到 padding 区——吸顶时
 *    filter-bar 从容器顶 0 贴住、整体 offsetHeight 增大，胶囊内容相对顶部下移，
 *    与面包屑间形成白条带。故表头吸顶偏移只需 = offsetHeight（含 padding-top），
 *    不要再叠加 gap，否则表头会比 filter-bar 底多悬空 gap 像素、露出滚动行。
 *  - offsetHeight 不含分组条底部 margin：若把 margin 算进偏移会留 6px 透缝。 */
const STICKY_TOP_GAP = 12;
function syncStickyOffset() {
  const page = pageRef.value;
  const bar = page?.querySelector<HTMLElement>(".filter-bar");
  if (!bar) return;
  page?.style.setProperty("--watchlist-sticky-gap", `${STICKY_TOP_GAP}px`);
  page?.style.setProperty("--watchlist-sticky-top", `${bar.offsetHeight}px`);
}

function bindStickyObserver() {
  const page = pageRef.value;
  const bar = page?.querySelector<HTMLElement>(".filter-bar");
  if (!bar || stickyObserver) return;
  stickyObserver = new ResizeObserver(() => syncStickyOffset());
  stickyObserver.observe(bar);
  syncStickyOffset();
}

/** 把 .watchlist-page 的 min-height 设为外层滚动容器的可视高度。
 *  滚动发生在布局层 .el-scrollbar__wrap（fixedHeader 模式唯一），其 clientHeight
 *  等于「视口高度 - 顶部 header 高度」。本函数把此高度直接写到 .watchlist-page 的
 *  min-height：内容少时（空态）撑满可视区、让 footer 贴底；内容多时由 max(content, h)
 *  自然增长、超出后由外层 wrap 滚动，无需手动处理。
 *  ResizeObserver 监听 wrap 尺寸变化（浏览器缩放/侧栏展开）实时同步。 */
let pageMinHObserver: ResizeObserver | null = null;
function findScrollWrap(): HTMLElement | null {
  return pageRef.value?.closest(".el-scrollbar__wrap") as HTMLElement | null;
}
function syncPageMinHeight() {
  const page = pageRef.value;
  if (!page) return;
  const wrap = findScrollWrap();
  const h = wrap?.clientHeight || window.innerHeight;
  page.style.minHeight = `${h}px`;
}
function bindPageMinHObserver() {
  const wrap = findScrollWrap();
  if (!wrap) {
    syncPageMinHeight();
    return;
  }
  if (pageMinHObserver) return;
  pageMinHObserver = new ResizeObserver(() => syncPageMinHeight());
  pageMinHObserver.observe(wrap);
  syncPageMinHeight();
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

// keep-alive 切回时重绑分组条高度观察（filter-bar 可能已重新渲染）；
// 批量/估值条/加载态变化也会引起分组条换行高度变化，实时重算表头吸顶偏移。
onActivated(() => {
  bindStickyObserver();
  bindPageMinHObserver();
});
watch([realtimeEnabled, batchMode, loading], () => {
  nextTick(() => {
    bindStickyObserver();
    bindPageMinHObserver();
  });
});
// 切走本页（keep-alive 缓存但不可见）时断开 ResizeObserver
onBeforeUnmount(() => {
  stickyObserver?.disconnect();
  stickyObserver = null;
  pageMinHObserver?.disconnect();
  pageMinHObserver = null;
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
  // #993「所属分组」列：group_ids → 分组名映射。
  // 只需自定义分组——系统分组（持仓/观察等）由后端规律方法派生，不写进 group_ids。
  groupNames: Object.fromEntries(
    customGroups.value.map(g => [g.id, g.name])
  ) as Record<string, string>,
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

/* 自选页容器（外层滚动 + 头部 sticky 版，2026-09-05 根因修复）：
   - 真正滚动的是「布局层的 .el-scrollbar__wrap」（fixedHeader 模式布局把整页裹进
     el-scrollbar 后只有它一个滚动容器）；此前本页又自造 .watchlist-scroll
     （overflow-y:auto）去截断 position:sticky，而它自身高度被内容撑到与内容等高、
     从不滚动，sticky 的「最近滚动祖先」被它吞掉 → 分组条/表头跟随整页滚走。
   - 现改为：本页不再创建任何滚动容器（.watchlist-page/.watchlist-scroll 均
     overflow:visible，默认），让布局 el-scrollbar__wrap 成为唯一滚动容器；
     .filter-bar（分组 Tab 行）用 position:sticky top:0 吸顶，表头
     .el-table__header-wrapper 用 sticky top:var(--watchlist-sticky-top) 吸在分组条
     下方（偏移由脚本实测 .filter-bar 高度写入，见 syncStickyOffset）。
   - .head-primary（搜索 + 核心操作行）不 sticky：它是滚动内容的正常首行，下滚时
     自然滚出视口 = 「自动隐藏」，无需 JS 收起动画。
   - 配套：布局组件 lay-content 的 el-scrollbar view 由 overflow:hidden 改为 clip，
     避免把 sticky 上溯到 wrap 的路截断（见 lay-content/index.vue）。 */
.watchlist-page {
  /* 整页高度由内容决定（行多则高、由外层布局 el-scrollbar 滚动），同时设
     min-height 为外层滚动容器可视高度（JS 实测写入，见 syncPageMinHeight）：
     空态/内容不足时页面至少一屏高，配合下方 flex 链让卡片撑满、footer 贴底。
     关键：任何祖先/自身都不设 overflow:hidden/auto，否则会创建新的滚动容器、
     截断 .filter-bar / 表头的 position:sticky 上溯到布局滚动容器。
     min-width:0：本页是 flex column，子项默认 min-width:auto 不会收缩到内容宽度
     以下；若某层不放开，列总宽超过视口时 el-table 会把整条 flex 链撑宽、产生
     页面级横向滚动条（#1341）。放开后列宽溢出由 el-table 内部横向滚动承载。 */
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

/* 高密度列表页：取消全局 .main-content 的 48px 边距，避免上下白边吞掉表格行数。 */
.watchlist-page.main-content {
  padding: 0;
}

.watchlist-scroll {
  /* 外层滚动容器（布局 el-scrollbar__wrap）的唯一内容，普通流即可；el-table 按
     内容高度展开所有行。display:flex column + flex-grow 让它至少吃满 .watchlist-page
     的 min-height（空态时 footer 由此贴底，见 .watchlist-card flex:1 与下方 app-footer）。
     min-width:0：配合 .watchlist-page / .el-table 同款约束，防止列宽溢出撑出页面横向
     滚动条（#1341）。 */
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.watchlist-card {
  display: flex;

  /* flex:1 撑满 .watchlist-scroll 剩余高度：空态（无自选）时卡片拉伸到一屏，
     表格区 .watchlist-table-wrap flex:1 再撑满卡片，配合「暂无自选资产」空态垂直
     居中——不再出现卡片只占半屏、footer 悬在中间的观感。有数据时行内容自然增高，
     卡片随内容增高（flex-grow 仅在容器有空余时才作用，不会压缩真实行）。 */
  flex: 1 1 auto;
  flex-direction: column;

  /* 防止列宽溢出撑出页面横向滚动条（#1341） */
  min-width: 0;
  min-height: 0;
  padding: var(--space-compact);
}

/* 表格容器：flex:1 让 el-table 撑满卡片剩余空间（内容不足时表格区占满、空态居中；
   内容超高时表格按行高自然展开，外层滚动接管，此处的 grow 不会约束真实行高）。
   position:relative 是 WatchlistTableSkeleton 覆盖层的定位锚点（loading 期间骨架
   absolute 覆盖表头之下的行区）。表头吸顶见下方 :deep(.el-table__header-wrapper)。 */
.watchlist-table-wrap {
  /* 提供给 WatchlistTableSkeleton 覆盖层的表头高度锚点（#1324 review）：
     与真实表头高度保持一致，骨架屏 top 即对齐表头底边。
     2026-09-06：表头 th padding 3px→6px（≈30px→≈36px）后同步本值，
     否则骨架屏会与真实表头底边错位、露出 6px 空白条。 */
  --watchlist-header-h: 36px;

  position: relative;
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;

  /* 防止列宽溢出撑出页面横向滚动条（#1341）：el-table 是其 flex 子项，
     自身 min-width:0 见下方 :deep(.el-table)。 */
  min-width: 0;
  min-height: 0;
}

/* 合规页脚贴底：位于 .watchlist-scroll（flex column）末尾，margin-top:auto 把空余
   空间全部让给上方 .watchlist-card（空态一屏高），footer 自然沉到可视区底部。 */
:deep(.app-footer) {
  margin-top: auto;
}

/* 表头吸顶：滚动容器是外层布局的 .el-scrollbar__wrap（唯一），表头随其滚动到顶后
   固定在 .filter-bar（分组 Tab 行，同样 sticky）正下方——top 偏移由脚本实测分组条
   高度写入 CSS 变量 --watchlist-sticky-top（仅 offsetHeight 不含 margin，让 filter 与
   header 背景无缝拼接形成连续白色遮罩，避免 6px 透缝造成"悬浮按钮"观感）。
   z-index 高于行，背景用卡片色（--bg-card，亮色纯白/暗色 #242120）遮住下方滚动行，
   避免穿透重影。
   关键：el-table 默认 overflow:hidden 会成为 header-wrapper 的「最近滚动祖先」，
   导致 sticky 相对表格自身（不随页面滚）而非布局滚动容器——这是吸顶反复失效的根因。
   本页表格无内部滚动，改为 overflow:visible 让 sticky 正确吸附到布局滚动容器。
   （el-table 不需要 flex 拉伸：空态文案已由 .watchlist-empty-overlay 覆盖层承载，
   见下；有数据时表格按内容高度自然展开，外层滚动接管。） */
.watchlist-table-wrap :deep(.el-table) {
  min-width: 0;

  /* 吸顶需要：overflow:visible 让表头 sticky 上溯到布局滚动容器（见上方长注释）。
     配套 min-width:0：el-table 是 .watchlist-table-wrap 的 flex 子项，默认 min-width:auto
     会被列总宽撑开、把整页顶出横向滚动条（#1341）。放开后 el-table 约束到容器宽度，
     多出的列宽由 .el-table__body-wrapper 内部横向滚动承载，页面不再溢出。
     此约束是通用防护：今后新增可排序列（见 columnDefs.ts）只要总宽超视口，
     都只会在表格内出现横向滚动，不会再撑宽页面。 */
  overflow: visible;
}

.watchlist-table-wrap :deep(.el-table__header-wrapper) {
  position: sticky;
  top: var(--watchlist-sticky-top, 0);
  z-index: 3;
  background: var(--bg-card);
}

/* ======================================
   双行分区头部（#1281 第四轮修订，2026-09-05）
   —— 第一行 .head-primary：搜索框 + 快捷工具图标（刷新/导出/AI导入/实时估值，
      2026-09-05 从第二行上移）+ 核心操作（管理 / 添加自选，主 CTA 最右）；
      第二行由 WatchlistFilterBar 承载「分组 Tab（最左）+ 标签筛选/视图/新建」，
      纯筛选职责（用户反馈：图标组挤在第二行显拥挤、第一行留白过空）。
   两行各自 justify-between / 左紧右松，主次分离；控件统一 32px 高、
   同一垂直基线。
   ====================================== */

/* 搜索 + 核心操作区：固定高度由内容撑出，与下方筛选行间距 12px（--space-3）。
   （2026-09-06 呼吸感回调：原 6px 使「搜索行 / 分组筛选行 / 表头」三带几乎贴合成
   一条，缺少分区层级；回到规范间距后各带边界可辨，代价约 6px 首屏高度。）
   不吸顶：作为滚动内容首行，页面下滚时自然滚出视口（即「搜索框自动隐藏」），
   无需 JS 收起动画。max-height 40px 上限防止内容意外溢出（原紧凑态折叠机制
   已于 2026-09-05 根因修复时随外层滚动架构废弃）。 */
.head-primary {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  max-height: 40px;
  margin-bottom: var(--space-3);
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

/* 快捷工具图标组（原 FilterBar #actions，2026-09-05 上移 head-primary）：等距排布 */
.header-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

.header-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

/* 快捷图标组与核心操作（管理/添加自选）之间的细分隔线 */
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

/* 表格底栏：左侧总数 + 右侧翻页，与表格之间用细分割线分区
   （design.md「卡片内分割线使用 --border-subtle 降低视觉权重」） */

/* 表格底栏：2026-09-06 呼吸感回调。
   曾收紧到 padding-top 8 / margin-top 4 为表格让出首屏高度，结果「共 N 条」与
   翻页码紧贴分割线，底栏不像独立信息带而像表格长出的一条边。
   回到 padding-top 12（--space-3）/ margin-top 8（--space-2）：分割线上方留白
   足够，底栏与表格成为两个可分辨的区域。 */
.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-3);
  margin-top: var(--space-2);
  border-top: 1px solid var(--border-light);
}

/* 底栏右侧：每页条数选择 + 翻页 成组右对齐 */
.table-footer__right {
  display: flex;
  gap: var(--space-3);
  align-items: center;
}

/* 每页条数选择器（#1335）：与翻页器同高对齐，标签用次级/三级文字色 */
.page-size-select {
  display: flex;
  gap: 6px;
  align-items: center;
}

.page-size-select__label {
  font-size: 13px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.page-size-select__control {
  width: 88px;
}

.table-footer__total {
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

/* 估值条（实时开启时显示）：不吸顶，作为分组条与表格之间的普通流内容，
   滚动时自然滚出视口（分组条吸顶后其会被盖住消失）。上限防内容溢出。 */
:deep(.summary-bar) {
  max-height: 48px;
  overflow: hidden;
}

:deep(.filter-bar) {
  /* 分组 Tab 行吸顶：相对外层布局滚动容器 .el-scrollbar__wrap sticky 贴顶（top:0），
     完整白遮罩从滚动容器顶 0 开始覆盖——确保滚动行从下方进入时被白底遮住，不会
     从顶部「穿透」出去（2026-09-05 第三轮反馈：上一版 top:gap 让上方 12px 无遮罩、
     行滚过该缝隙时在面包屑底与分组条之间漏出顶部 12px 文字）。
     呼吸感实现：filter-bar 自身 padding-top = STICKY_TOP_GAP（12px），白背景覆盖到
     padding 区，吸顶后从 y=0 到 y=offsetHeight 整段白——胶囊内容相对容器顶向下 12px，
     与上方面包屑底之间呈现 12px 白条带（视觉分层，不贴），同时白色遮罩不间断。
     表头吸顶 top = --watchlist-sticky-top = filter-bar.offsetHeight（offsetHeight 已含
     padding-top），与 filter-bar 底部无缝衔接。
     注意：.filter-bar 祖先链上的 .watchlist-page/.watchlist-scroll/.el-scrollbar__view
     都不能有 overflow:hidden/auto，否则会截断 sticky 上溯（2026-09-05 根因修复）。 */
  position: sticky;
  top: 0;
  z-index: 4;
  padding-top: var(--watchlist-sticky-gap, 12px);
  background: var(--bg-card);
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

/* 表格空状态覆盖层（2026-09-05 问题 1 修复）：
   覆盖在 .watchlist-table-wrap 上、表头（约 30px）之下，铺满表格剩余区并让文案垂直
   居中。空态时表格仍渲染表头（吸顶正常），数据行为 0，下方整段区域由本层占住——
   视觉上"暂无自选资产"位于卡片中部，footer 经 .watchlist-card flex:1 + margin-top:auto
   沉到视口底，不再出现"文案靠上 + footer 悬在中间"的空分组观感。
   注：不再使用 el-table #empty（empty-text="" 已隐藏 EP 默认占位）。 */
.watchlist-empty-overlay {
  /* 覆盖整张 el-table（含表头）：空态时没有数据行，列名与表头底边框没有意义，
     反而会在文案上方形成一条"怪异分割线"。overlay 从 top:0 铺满并用卡片色背景
     盖住表头/空体，文案在整卡区内垂直居中，视觉干净。
     注意 z-index 需高于表头（header z-index:3）才能盖住其底边线。 */
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
  font-size: 14px;
  color: var(--text-secondary);
}

.watchlist-empty__hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary);
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
  font-size: 13px;
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

/* 表头行高 ≈36px（EP 默认 th padding 8px ≈ 40px 高）。
   #1281 第四轮曾收到 3px（≈30px）为数据行让出高度，实测表头过薄：与下方 52px
   数据行比例失衡，5 字表头（添加自选日 / 添加后涨幅）贴着上下边线显廉价。
   2026-09-06 回调到 6px（≈36px）：表头获得与数据行协调的纵向呼吸，可点区域
   反而更充裕（30px 对触控偏小），代价约 6px 首屏高度。 */
:deep(.el-table__header th.el-table__cell) {
  padding: 6px 0;
}

/* 分组胶囊 Tab / 新建分组按钮样式已迁移至 components/Watchlist/WatchlistFilterBar.vue（方案 B，2026-08-14） */

/* 置顶/关注标记图标与标签 chips（.marker-icon/.tag-chip/.add-tag-btn）样式已迁移至
   columnRenderers.css——列 renderer 化后这些 DOM 由 tsx 产生，不携带本页 scoped 属性，
   留在本页的规则会静默失效（#995 迁移遗留，2026-08-22 清理） */
</style>
