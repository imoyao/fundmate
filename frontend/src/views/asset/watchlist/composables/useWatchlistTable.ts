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
import {
  CLIENT_SORT_KEYS,
  type ClientSortKey
} from "@/views/asset/watchlist/clientSort";
import { pickSortMetric } from "@/views/asset/watchlist/sortMetric";

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
 * （fixed 列操作按钮淡入用）、表头排序分发（吃实时价的列走客户端**整组**排序，
 * 见 `views/asset/watchlist/clientSort.ts`）。
 */
export function useWatchlistTable(options: TableRenderOptions) {
  const { groups, tags, toolbar, data, valuation, actions } = options;
  const router = useRouter(); // 「问这个」跳转用（#1764）
  const { batchMode } = toolbar;
  const {
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

  /** 最新价取值：真拿到行情才用实时价，否则回落后端静态价（同 money renderer 口径） */
  function livePriceOf(row: WatchlistItem): number | null {
    const quote = getValuationItem(row.symbol ?? "");
    const live =
      quote && quote.source === "realtime" ? quote.currentPrice : null;
    const value = live ?? row.current_price;
    return typeof value === "number" && value > 0 ? value : null;
  }

  /**
   * 当日盈亏取值：按当前口径选「金额」或「涨幅」——复合列两行数各有各的排序。
   *
   * 口径在**调用时**读（`data.sortMetricOf`），所以表头切口径后，客户端整组排序
   * （`clientSortedItems` 是 computed）会立刻重算，不需要再手动触发一次排序。
   */
  function dayPnlSortValueOf(): (row: WatchlistItem) => number | null {
    return row => pickSortMetric(dayPnlOf(row), data.sortMetricOf("day_pnl"));
  }

  /** 该列是否走客户端整组排序（名单只在 `clientSort.ts` 维护，不在此另立一份） */
  function isClientSortKey(key: string): key is ClientSortKey {
    return (CLIENT_SORT_KEYS as readonly string[]).includes(key);
  }

  /**
   * 表头排序分发（#1333 → #2641 → 2026-10-30 整组化 → 2026-10-30 复合列口径）。
   *
   * | 列 | 走哪 | 为什么 |
   * |---|---|---|
   * | 当日盈亏 / 最新价 | **客户端整组排序**（`data.setClientSort`，对全量 allItems 排 + 本地分页） | 这两列吃实时价，后端只有上一交易日收盘（job 17:30 跑）⇒ 按 `sort_by` 排等于「按昨天的涨幅排」，与列里显示的今日值不是同一个数 |
   * | 持仓市值 / 持仓收益 | `handleSortChange` → 后端 `sort_by/sort_order`，**字段随口径切换** | 两列主行取自 positions 快照 + 库内行情，后端排的就是列里显示的数；「金额 / 比例」是库里两个不同的排序键（`position_market_value` / `holding_pnl` / `holding_pnl_percent`，均在后端白名单内） |
   * | 其余列 | `handleSortChange` → 后端 `sort_by/sort_order` | 这些列的值后端就有，跨页一致由后端保证 |
   *
   * ⚠️ 旧实现（含 #2641 版）在实时开启时**只排当前页**——第 2 页重新从最大/最小开始，
   * 用户看到的就是「点了排序但顺序很乱」（2026-10-30 用户实测反馈）。现在要么整组排
   * （客户端），要么整组排（后端），没有「页内排」这一档。
   *
   * ⚠️ 复合列（`ColumnDef.sortMetrics`）的排序指标由表头徽标决定，**不再拿一个口径
   * 代理另一个**：#2641 把当日盈亏代理到 `change_pct`，于是「按金额排序」这个诉求
   * 在实现上根本不存在。
   */
  function onSortChange({
    prop,
    order
  }: {
    prop?: string | number;
    order: "ascending" | "descending" | null;
  }) {
    const key = prop ? String(prop) : "";
    const def = key
      ? options.columnSettings.visibleColumns.value.find(d => d.key === key)
      : undefined;

    // 取消排序（普通列的第三档；复合列只有两档，不会走到这里）：先退出客户端模式
    // 再让后端回默认序。只清本地状态的话，items 会停在上一轮本地切片上（表格「卡住」）。
    if (!order) {
      data.clearClientSort();
      data.handleSortChange({ prop: def?.sortBy ?? key, order });
      return;
    }

    const dir = order === "descending" ? "desc" : "asc";

    // ① 客户端整组排序：吃实时价的两列（当日盈亏还要看口径）
    if (isClientSortKey(key)) {
      data.setClientSort(
        key,
        dir,
        key === "current_price" ? livePriceOf : dayPnlSortValueOf()
      );
      return;
    }

    // ② 复合列走后端时，排序字段随口径切换：金额 / 比例在库里是两个不同的列。
    //    只认列定义声明的 `ratioSortBy`（当日盈亏没声明 → 两种口径都走客户端，见 ①）。
    const ratioField = def?.sortMetrics?.ratioSortBy;
    const field =
      ratioField && data.sortMetricOf(key) === "ratio"
        ? ratioField
        : (def?.sortBy ?? key);

    data.clearClientSort();
    data.handleSortChange({ prop: field, order });
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
