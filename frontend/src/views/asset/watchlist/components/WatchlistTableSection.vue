<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Plus } from "@element-plus/icons-vue";
import type { WatchlistItem } from "@/api/watchlist";
import type { ColumnDef } from "@/views/asset/watchlist/columnDefs";
import WatchlistTableSkeleton from "@/views/asset/watchlist/WatchlistTableSkeleton.vue";
import {
  resolveRenderer,
  type RenderCtx
} from "@/views/asset/watchlist/columnRenderers";

/**
 * 自选表格区（#980 P0-b 拆分自 index.vue，零行为变更）：
 * 表格容器 + el-table（列渲染/排序/hover/行点击）+ 空态覆盖层 + 骨架屏。
 * 页面级状态经 ctx（RenderCtx）注入，事件经 emit 上抛由 index.vue 编排。
 */
const props = defineProps<{
  loading: boolean;
  items: WatchlistItem[];
  batchMode: boolean;
  /** 实际渲染列（visibleColumns 过滤掉 _selection，由 index 计算后注入） */
  columns: ColumnDef[];
  /** 列渲染器注册表上下文（index 组装，见 columnRenderers.RenderCtx） */
  ctx: RenderCtx;
  /** 空态是否落在「空白自定义分组」（虚线快捷入口，#987） */
  isEmptyCustomGroup: boolean;
  activeGroupLabel: string;
  /** 是否叠加了标签筛选（空态文案分支） */
  hasTagFilter: boolean;
}>();

const emit = defineEmits<{
  (e: "sort-change", payload: SortPayload): void;
  (e: "selection-change", selection: WatchlistItem[]): void;
  (e: "cell-mouse-enter", row: WatchlistItem): void;
  (e: "cell-mouse-leave"): void;
  (e: "row-click", row: WatchlistItem, column: unknown, event: Event): void;
  /** el-table 实例上抛（表头列拖拽用，见 useWatchlistStickyLayout） */
  (e: "table-ready", instance: unknown): void;
  (e: "open-group-items"): void;
}>();

type SortPayload = {
  prop?: string | number;
  order: "ascending" | "descending" | null;
};

const tableRef = ref();

/**
 * 置顶行的视觉区分（#1281 第四轮）。
 * 置顶项由后端默认排序（is_pinned + 更新时间）自然落在最前，这里再给整行一层
 * 极淡品牌底，扫一眼即可看出「上面这一块是置顶的」；置顶图标本身则内联在
 * 产品列名称前（columnRenderers.tsx renderRowMarks），不再占用独立列宽。
 */
function rowClassName({ row }: { row: WatchlistItem }): string {
  return row.is_pinned ? "is-pinned-row" : "";
}

function onSortChange(payload: SortPayload) {
  emit("sort-change", payload);
}
function onSelectionChange(selection: WatchlistItem[]) {
  emit("selection-change", selection);
}
function onCellMouseEnter(row: WatchlistItem) {
  emit("cell-mouse-enter", row);
}
function onCellMouseLeave() {
  emit("cell-mouse-leave");
}
function onRowClick(row: WatchlistItem, column: unknown, event: Event) {
  emit("row-click", row, column, event);
}
function openGroupItems() {
  emit("open-group-items");
}

// 子组件 mounted 早于页面 mounted，index 的 onMounted 调 initHeaderDrag 前
// 实例已上抛（与拆分前模板 ref 在渲染期赋值的可见性等价）。
onMounted(() => {
  emit("table-ready", tableRef.value);
});
</script>

<template>
  <!--
    表格视觉基线（边框/表头/hover/文字色）统一在 src/style/el-table.css 维护，
    勿在本组件 :deep(.el-table) 覆盖视觉基线；本组件保留的 :deep 仅限行内行为样式。
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
    <!-- 表格宽度铁律（#1285 / #1341 / #1421 / #1425，改这里前先读 design.md
         「冻结列与横向滚动规范」§4/§5）：
         ① 默认可见列总宽 ≤ 1040px —— 列集在 columnDefs.ts，「加一列必须减一列」；
         ② 横向滚动**只允许发生在表格内部**：页面级横向滚动条由本页 flex
            min-width:0 链（.watchlist-page / .watchlist-scroll / .watchlist-card /
            本容器）禁止（#1341），**不要摘掉任何一层 min-width:0**；
         ③ 两端必须冻结：product 左冻结 + _actions 右冻结（defs 里的 fixed），
            中间列才滚动 —— 用户滑动时始终能看到「哪只标的」与「能做什么」。
         三者同时成立才符合设计；只满足其一（如为铺满而不守预算）会立刻退回
         「整表溢出」状态（该问题已三次回归）。 -->
    <el-table
      ref="tableRef"
      :data="loading ? [] : items"
      empty-text=""
      :row-class-name="rowClassName"
      stripe
      @selection-change="onSelectionChange"
      @sort-change="onSortChange"
      @cell-mouse-enter="onCellMouseEnter"
      @cell-mouse-leave="onCellMouseLeave"
      @row-click="onRowClick"
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
        v-for="def in columns"
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
            :ctx="ctx"
          />
        </template>
      </el-table-column>
    </el-table>
    <!-- 空态覆盖层：表格无数据且非加载时，以绝对定位铺满「表头之下」的表格区
         并垂直居中（问题 1：空分组时表格占满页面，而非文案悬在卡片中部）。
         不复用 el-table #empty（其 empty-block 高度由 EP 撑到 280px 封顶，
         无法在整段空表格区内垂直居中）；隐藏 el-table 自带空态文字
         （empty-text=""）避免穿透。表头吸顶保留（30px，见 overlay top）。 -->
    <div v-if="!loading && items.length === 0" class="watchlist-empty-overlay">
      <!-- 空白自定义分组：虚线「+ 从全部自选添加」快捷入口（#987）。
           空白组是可填充的占位区，给可点入口而非阻断性文案；系统分组为空、
           以及标签筛选无匹配的场景，仍走下方纯文案空态。 -->
      <template v-if="isEmptyCustomGroup">
        <button type="button" class="empty-add-btn" @click="openGroupItems">
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
    <!-- 骨架屏覆盖层：仅数据加载期间渲染（分组切换/首屏/搜索/翻页），
         随 .watchlist-table-wrap 定位，top 对齐表头底部。 -->
    <WatchlistTableSkeleton v-if="loading" />
  </div>
</template>

<style scoped>
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

  /* 纵向 visible：表头 sticky 的必要条件——overflow:hidden 会让 el-table 成为
     header-wrapper 的「最近滚动祖先」，sticky 相对表格自身而不随页面滚，吸顶失效
     （见上方长注释）。
     **横向必须 clip**：列总宽 > 容器宽时表格内部会出现横向滚动（见 columnDefs 的
     minWidth 机制）。若横向也 visible，超宽的表体会直接溢出卡片、把整页顶出横向
     滚动条——这正是 #1341 已修、2026-09-12 又复现的形态。
     `overflow-x: clip` 与 `overflow-y: visible` 可以共存（clip 不会像 hidden 那样
     把另一轴强制成 auto），于是「纵向照常吸顶 + 横向永不溢出页面」同时成立。
     ⚠️ 不要把这里改回 `overflow: visible` 或整段删掉：会同时让吸顶失效 / 页面横滚。 */
  overflow: clip visible;
}

.watchlist-table-wrap :deep(.el-table__header-wrapper) {
  position: sticky;
  top: var(--watchlist-sticky-top, 0);
  z-index: 3;
  background: var(--bg-card);
}

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
</style>
