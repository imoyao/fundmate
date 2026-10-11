import {
  ref,
  watch,
  nextTick,
  onActivated,
  onBeforeUnmount,
  type ComputedRef
} from "vue";
import Sortable from "sortablejs";
import type { ColumnDef } from "@/views/asset/watchlist/columnDefs";
import type { WatchlistColumnVisibility } from "@/composables/useWatchlistColumnVisibility";
import type { useWatchlistData } from "@/composables/useWatchlistData";
import type { useWatchlistToolbar } from "@/composables/useWatchlistToolbar";

interface StickyLayoutOptions {
  data: ReturnType<typeof useWatchlistData>;
  toolbar: ReturnType<typeof useWatchlistToolbar>;
  columnSettings: WatchlistColumnVisibility;
  dataColumns: ComputedRef<ColumnDef[]>;
  realtimeEnabled: ComputedRef<boolean>;
}

/**
 * 自选页布局域（#980 P0-b 拆分自 index.vue，零行为变更）：
 * 页面根 ref、表头吸顶偏移实测、页面 min-height 同步、表头列拖拽（#992）。
 *
 * 吸顶链（外层滚动版，2026-09-05 根因修复）：
 *   1. .filter-bar（分组 Tab 行）CSS position:sticky top:0 → 相对外层滚动容器吸顶；
 *   2. .el-table__header-wrapper（表头）position:sticky，top 取 CSS 变量
 *      --watchlist-sticky-top = .filter-bar 实际高度（脚本实测写入，见 syncStickyOffset），
 *      使表头正好吸在分组条下方，形成「分组条 + 表头」连续固定区；
 *   3. .head-primary（搜索行）不吸顶，作为滚动内容的正常首行——下滚时自然滚出视口，
 *      即「搜索框自动隐藏」。
 * 关键前置：.watchlist-page/.watchlist-scroll/.el-scrollbar__view 均不得有
 * overflow:hidden/auto（否则会截断 sticky 上溯，见 index.vue 样式注释与 lay-content）。
 *
 * 呼吸感（2026-09-05）：filter-bar 自身 padding-top = STICKY_TOP_GAP（12px），
 * 白背景覆盖到 padding 区——吸顶时 filter-bar 从容器顶 0 贴住、整体 offsetHeight
 * 增大，胶囊内容相对顶部下移，与面包屑间形成白条带。故表头吸顶偏移只需 =
 * offsetHeight（含 padding-top），不要再叠加 gap，否则表头会比 filter-bar 底多
 * 悬空 gap 像素、露出滚动行。
 */
export function useWatchlistStickyLayout(options: StickyLayoutOptions) {
  const { data, toolbar, columnSettings, dataColumns, realtimeEnabled } =
    options;

  // ── #992 表头列拖拽：sortablejs 复用（RePureTableBar 同款方案）──
  // el-table 实例由 TableSection 经 @table-ready 上抛（其 mounted 早于页面 mounted，
  // 故 onMounted 里调用 initHeaderDrag 时实例已就绪，与拆分前模板 ref 时序等价）。
  const tableRef = ref();
  function onTableReady(instance: unknown) {
    tableRef.value = instance;
  }

  const pageRef = ref<HTMLElement>();
  let stickyObserver: ResizeObserver | null = null;

  /** 实测分组条 .filter-bar 高度，写入吸顶偏移 CSS 变量。
   *  分组条是正常流元素，批量模式/视图 segmented/标签数量变化都可能改变其换行高度，
   *  故用 ResizeObserver 监听其几何变化，实时重算吸顶位置。
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
  /** 键盘重排结果播报（#1852）：列顺序变了但视觉上只是表头换位，
   *  不播报则屏幕阅读器用户完全感知不到。role=status + aria-live=polite。 */
  const announce = ref("");

  /** 表头列序（th 序列 → 持久化 key），与 onEnd 的算法保持一致。 */
  function headerKeys(): string[] {
    return [
      ...(toolbar.batchMode.value ? ["_selection"] : []),
      ...dataColumns.value.map(d => d.key)
    ];
  }

  /** 目标位置是否落在固定列上——键盘路径必须复刻 Sortable 的 onMove 约束，
   *  否则会出现「键盘能排出一个拖拽排不出的顺序」，那比不做更糟。 */
  function isFixedAt(headerRow: HTMLElement, index: number): boolean {
    const th = headerRow.children[index] as HTMLElement | undefined;
    return th?.classList.contains("col-no-drag") ?? true;
  }

  /** 给表头列挂键盘等价物（#1852）。 */
  function bindHeaderKeyboard(headerRow: HTMLElement) {
    const ths = Array.from(headerRow.children) as HTMLElement[];
    ths.forEach((th, i) => {
      // 只加 tabindex，**不加 role="button"**——th 的 columnheader 语义要留住，
      // 改成 button 会破坏表格语义（读表头会当成一排按钮）。
      th.tabIndex = 0;
      th.dataset.colIndex = String(i);
      th.setAttribute("aria-describedby", "watchlist-col-hint");
      // 焦点跟随：移动后焦点必须跟到新位置的列上，否则键盘用户会「丢失」当前列。
      th.addEventListener("keydown", e => onHeaderKeydown(e, headerRow, i));
    });
  }

  function onHeaderKeydown(
    e: KeyboardEvent,
    headerRow: HTMLElement,
    index: number
  ) {
    // Ctrl+←/→ 移动列。用 Ctrl 而非 Alt：Alt 在部分浏览器/系统是全局快捷键。
    if (!e.ctrlKey) return;
    const dir = e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : 0;
    if (dir === 0) return;
    e.preventDefault();
    e.stopPropagation();

    const keys = headerKeys();
    const to = index + dir;
    if (to < 0 || to >= keys.length) return;
    // 复刻 onMove：目标落在固定列上就拒绝
    if (isFixedAt(headerRow, to)) {
      announce.value = "该方向相邻列是固定列，不能移过去";
      return;
    }
    // 起点本身是固定列也不该移动
    if (isFixedAt(headerRow, index)) {
      announce.value = "固定列不能移动";
      return;
    }

    const moved = keys.splice(index, 1)[0];
    keys.splice(to, 0, moved);
    columnSettings.applyOrder(keys.filter(k => !k.startsWith("_")));

    // 落库后 DOM 会重渲染，等下一帧再把焦点跟过去
    void nextTick(() => {
      const fresh = headerRow.children[to] as HTMLElement | undefined;
      fresh?.focus();
      announce.value = `「${moved}」移到第 ${to + 1} 列，共 ${keys.length} 列`;
    });
  }

  // 键盘操作提示，配合表头的 aria-describedby
  const COL_HINT = "可用 Ctrl 加左右方向键调整该列顺序";

  function initHeaderDrag() {
    const el = (tableRef.value?.$el ?? null) as HTMLElement | null;
    const headerRow = el?.querySelector<HTMLElement>(
      ".el-table__header-wrapper tr"
    );
    if (!headerRow) return;
    bindHeaderKeyboard(headerRow);
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
        if (oldIndex == null || newIndex == null || oldIndex === newIndex)
          return;
        // th 序列与渲染列一一对应：[selection(batchMode)] + dataColumns
        const keys = [
          ...(toolbar.batchMode.value ? ["_selection"] : []),
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

  // keep-alive 切回时重绑分组条高度观察（filter-bar 可能已重新渲染）；
  // 批量/估值条/加载态变化也会引起分组条换行高度变化，实时重算表头吸顶偏移。
  onActivated(() => {
    bindStickyObserver();
    bindPageMinHObserver();
  });
  watch([realtimeEnabled, toolbar.batchMode, data.loading], () => {
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

  return {
    pageRef,
    onTableReady,
    initHeaderDrag,
    bindStickyObserver,
    bindPageMinHObserver,
    // 键盘重排的播报文本与操作提示，供页面渲染 aria-live 与 aria-describedby 目标
    announce,
    COL_HINT
  };
}
