import { ref, computed, type ComputedRef } from "vue";
import type { WatchlistItem } from "@/api/watchlist";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import type { useWatchlistTags } from "@/composables/useWatchlistTags";
import type { useWatchlistData } from "@/composables/useWatchlistData";
import type { WatchlistToolbarState } from "@/composables/useWatchlistData";
import type { WatchlistColumnVisibility } from "@/composables/useWatchlistColumnVisibility";
import type { useWatchlistValuation } from "@/views/asset/watchlist/composables/useWatchlistValuation";
import type { useWatchlistPageActions } from "@/views/asset/watchlist/composables/useWatchlistPageActions";
import type { RenderCtx } from "@/views/asset/watchlist/columnRenderers";

interface TableRenderOptions {
  groups: ReturnType<typeof useWatchlistGroups>;
  tags: ReturnType<typeof useWatchlistTags>;
  toolbar: WatchlistToolbarState;
  data: ReturnType<typeof useWatchlistData>;
  valuation: ReturnType<typeof useWatchlistValuation>;
  actions: ReturnType<typeof useWatchlistPageActions>;
  activeCategory: ComputedRef<string | null>;
  columnSettings: WatchlistColumnVisibility;
}

/**
 * 自选页表格渲染域（#980 P0-b 拆分自 index.vue，零行为变更）：
 * renderCtx 组装（把页面级状态/方法注入 renderer 注册表）、行 hover 状态
 * （fixed 列操作按钮淡入用）、表头排序分发（#1333 实时列客户端排序）。
 */
export function useWatchlistTable(options: TableRenderOptions) {
  const { groups, tags, toolbar, data, valuation, actions } = options;
  const { items } = data;
  const { batchMode } = toolbar;
  const {
    realtime,
    realtimeEnabled,
    getValuationItem,
    addedReturnPct,
    addedReturnAmount,
    marketValueRatio,
    trendMap
  } = valuation;

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
      ? options.columnSettings.visibleColumns.value.find(
          d => d.key === String(prop)
        )
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
    data.handleSortChange({ prop, order });
  }

  // 渲染上下文：把页面级状态/方法注入 renderer 注册表，renderer 不耦合本组件
  const renderCtx = computed<RenderCtx>(() => ({
    realtimeEnabled: realtimeEnabled.value,
    getValuationItem,
    allTags: tags.allTags.value,
    // #993「所属分组」列：group_ids → 分组名映射。
    // 只需自定义分组——系统分组（持仓/观察等）由后端规律方法派生，不写进 group_ids。
    groupNames: Object.fromEntries(
      groups.customGroups.value.map(g => [g.id, g.name])
    ) as Record<string, string>,
    derived: (kind, row) => {
      if (kind === "addedReturn") {
        // 无数据一律给 null：由 MoneyWithRatio 显示占位符 / 隐藏比例行，
        // 不再兜底 0（0 会被读成「收益 0」或「涨幅 0%」）
        return {
          value: addedReturnAmount(row as WatchlistItem),
          ratio: addedReturnPct(row as WatchlistItem)
        };
      }
      // marketValue
      return {
        value: (row.position_market_value as number | null) ?? null,
        ratio: marketValueRatio(row as WatchlistItem)
      };
    },
    openTagEditor: data.openTagEditor,
    batchMode: batchMode.value,
    // 品类视图（类型筛选命中单一品类）：供产品列与品类专属列去重（#1425）
    categoryView: options.activeCategory.value !== null,
    hoveredRowKey: hoveredRowKey.value,
    setHoveredRowKey: (key: string | number | null) => {
      hoveredRowKey.value = key;
    },
    actions: {
      togglePin: data.handleTogglePin,
      toggleFavorite: data.handleToggleFavorite,
      remove: data.confirmRemove,
      openNotesEditor: data.openNotesEditor,
      addToGroup: actions.openMultiGroupDialog
    },
    trends: trendMap.value
  }));

  return {
    renderCtx,
    onSortChange,
    handleCellMouseEnter,
    handleCellMouseLeave
  };
}
