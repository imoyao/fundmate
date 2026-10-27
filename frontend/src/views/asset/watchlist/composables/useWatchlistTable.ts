import { ref, computed, type ComputedRef } from "vue";
import { useRouter } from "vue-router";
import type { WatchlistItem } from "@/api/watchlist";
import { agentAskQuery } from "@/utils/agentAsk";
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
  const router = useRouter(); // 「问这个」跳转用（#1764）
  const { items } = data;
  const { batchMode } = toolbar;
  const {
    realtime,
    realtimeEnabled,
    getValuationItem,
    addedReturnPct,
    addedReturnAmount,
    dayPnlOf,
    marketValueRatio,
    trendMap,
    intradayMap
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
   * 表头排序分发（issue #1333 修正，#2641 扩展）。
   *
   * 两个维度各管一段：
   *
   * | 状态 | 走哪 | 为什么 |
   * |---|---|---|
   * | **实时开启**（`realtimeEnabled`）且列带 `realtimeField` | 客户端排序，**仅当前页** | 后端只有 None / positions 静态快照，按 `sort_by` 会按**错值**排（#1333）；而实时值不进后端，跨页一致本就不成立 |
   * | **其余情况**（含实时关闭时点这两列） | `handleSortChange` → 后端 `sort_by/sort_order`，**跨页一致** | 实时关闭时列里显示的就是后端静态值，交给后端按同一值排即可，没有理由退化成只排当前页 |
   *
   * ⚠️ #2641 前这里是 `if (def?.realtimeField && order)`——**不看实时开关**，
   * 于是「实时关闭」时点「最新价 / 涨跌幅」也只排当前页，后端一次都没被调用。
   * 这与「排序调后端接口」的预期不符，且用户看不出差别（顺序看着对，翻页即错）。
   * 判据见 `__tests__/sortDispatch.spec.ts`。
   *
   * 派生列（`day_pnl`）不靠 `realtimeField` 渲染也不在 `row` 上，故两处都要用它的
   * **排序代理**：实时分支的兜底值读 `sortBy`（`change_pct`），落后端时把 `sortBy`
   * 当作 `sort_by` 发出去。缺省仍是列 `key` 本身。
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
    // 排序代理：派生列（day_pnl）在 row 上没有同名字段，后端白名单里也没有它，
    // 必须代理到语义对应的行字段（change_pct），否则 sort_by=day_pnl 会静默失效（#1331）。
    const sortKey = def?.sortBy ?? (prop ? String(prop) : undefined);
    if (def?.realtimeField && order && realtimeEnabled.value) {
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
        const sv = sortKey
          ? (row as Record<string, unknown>)[sortKey]
          : undefined;
        return typeof sv === "number" ? sv : 0;
      };
      items.value = [...items.value].sort(
        (a, b) => (sortVal(a) - sortVal(b)) * dir
      );
      return;
    }
    data.handleSortChange({ prop: sortKey, order });
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
      if (kind === "dayPnl") {
        // 当日盈亏（#2640）：口径与汇总条同源（dayPnl.ts），缺失同样是 null 而非 0
        return dayPnlOf(row);
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
    // 行 hover 状态经**稳定 getter** 注入（不能直接写 hoveredRowKey.value：
    // 那会把 hover 烧进 renderCtx 对象身份，每次 mouseenter/leave 让全表单元格
    // 重渲染——悬停操作列时的整表抖动/滚动条闪烁即源于此。getter 身份恒定，
    // 仅产品列渲染时读取并订阅，见 columnRenderers.RenderCtx.getHoveredRowKey）。
    getHoveredRowKey: () => hoveredRowKey.value,
    setHoveredRowKey: (key: string | number | null) => {
      hoveredRowKey.value = key;
    },
    // 是否处于自定义分组视图：操作列「移除」按钮据此区分语义——
    // 自定义分组内移除 = 从当前分组移除（持仓资产也允许）；
    // 系统分组/全部视图内移除 = 彻底删除自选（持仓资产禁用 + 提示）。
    currentIsCustom: groups.currentIsCustom.value,
    actions: {
      togglePin: data.handleTogglePin,
      toggleFavorite: data.handleToggleFavorite,
      remove: data.confirmRemove,
      openNotesEditor: data.openNotesEditor,
      addToGroup: actions.openMultiGroupDialog,
      // 「问这个」（#1764）：带行上下文跳账本精灵页；query 由 router 编码，
      // 接收端 parseAgentAskQuery 消费即摘除（刷新无残留）
      askAbout: row => {
        router.push({
          name: "AgentChat",
          query: agentAskQuery({
            symbol: row.symbol,
            name: row.display_name || row.symbol,
            from: "watchlist"
          })
        });
      }
    },
    trends: trendMap.value,
    // 当日分时（#2640）：走势列盘中态的唯一数据源；缺省 → 回落 trends
    intraday: intradayMap.value
  }));

  return {
    renderCtx,
    onSortChange,
    handleCellMouseEnter,
    handleCellMouseLeave
  };
}
