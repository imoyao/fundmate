import { ref, computed, watch } from "vue";
import { getWatchlistTrends } from "@/api/watchlist";
import {
  useRealtimeQuotes,
  type RefreshInterval
} from "@/composables/useRealtimeQuotes";
import type { useWatchlistData } from "@/composables/useWatchlistData";
import { formatDateTime } from "@/utils/date";
import type { Holding, ValuationSummary } from "@/utils/valuationEngine";

type WatchlistData = ReturnType<typeof useWatchlistData>;

/**
 * 自选页估值域（#980 P0-b 拆分自 index.vue，零行为变更）：
 * 实时行情接线（useRealtimeQuotes 取数回调 + 三条状态 watch）、静态价汇总、
 * 持仓市值占比、添加后收益派生、手动刷新与迷你走势数据。
 *
 * 所有 watch 在本 composable 内注册（随组件 setup 自动绑定），与原 index.vue
 * 内联注册等价；调用方须在 setup 顶层同步调用。
 * （「关闭→重开实时」清横幅标记的那条 watch 留在 index.vue——其 key 由
 * RealtimeWarningBanner.vue 导出，.ts 模块无法引用 .vue 的具名导出。）
 */
export function useWatchlistValuation(data: WatchlistData) {
  const { items, allItems } = data;

  // ── 估值相关 ──
  const getValuationItem = (symbol: string) => {
    return realtime.items.value?.find(item => item.symbol === symbol);
  };

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

  /** 全量标的的持仓市值合计（静态价口径），作为占比分母的兜底 */
  const staticTotalMarketValue = computed(() =>
    allItems.value.reduce(
      (sum, item) => sum + Number(item.position_market_value ?? 0),
      0
    )
  );

  /**
   * 静态价汇总（未开实时时的展示口径，2026-09-22 用户反馈修复）。
   *
   * 口径与实时汇总（utils/valuationEngine）严格对齐：只统计**真实持仓行**
   * （有持仓数量与成本价），总市值取后端 position_market_value
   * （= 数量 × 最近交易日收盘价 / 确认净值），总成本 = Σ 成本价 × 数量。
   *
   * 为什么需要它：汇总条原先整块挂在 `v-if="realtimeEnabled"` 上，未开实时时
   * 「总市值 / 总成本 / 总盈亏」直接消失——而这三项在后端已有权威的静态口径数据，
   * 不该依赖实时通道是否开启。
   */
  const staticSummary = computed<ValuationSummary | null>(() => {
    let totalMarketValue = 0;
    let totalCost = 0;
    for (const item of allItems.value) {
      const quantity = Number(item.holding_quantity ?? 0);
      if (!(quantity > 0)) continue;
      totalMarketValue += Number(item.position_market_value ?? 0);
      totalCost += Number(item.holding_cost_price ?? 0) * quantity;
    }
    if (totalMarketValue <= 0 && totalCost <= 0) return null;
    const totalPnl = totalMarketValue - totalCost;
    return {
      totalMarketValue,
      totalCost,
      totalPnl,
      totalPnlPercent: totalCost > 0 ? (totalPnl / totalCost) * 100 : 0,
      updateTime: "",
      source: "static"
    };
  });

  /**
   * 持仓市值占总市值的比例（%）。
   *
   * 分母优先取实时汇总（实时开启时是「盘中最新价」口径的总市值），未开实时 /
   * 汇总未产出时回退静态价合计——两者都是**全量标的**口径（不是当前页合计，
   * 翻页不会跳变，#1245）。
   *
   * 仍算不出（无持仓 / 无市值）返回 null，由 MoneyWithRatio 隐藏比例行：
   * 原先调用处兜底成 0，把「没有数据」显示成了「占比 0.00%」。
   */
  function marketValueRatio(row: {
    position_market_value?: number | null;
  }): number | null {
    const realtimeTotal = realtime.summary.value?.totalMarketValue ?? 0;
    const total =
      realtimeTotal > 0 ? realtimeTotal : staticTotalMarketValue.value;
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
  const realtimeEnabled = computed(() => realtime.enabled.value);

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
    const symbols = [
      ...new Set(items.value.map(i => i.symbol).filter(Boolean))
    ];
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

  return {
    realtime,
    realtimeEnabled,
    getValuationItem,
    addedReturnPct,
    addedReturnAmount,
    staticSummary,
    marketValueRatio,
    toggleBtnText,
    refreshing,
    handleManualRefresh,
    trendMap,
    onRefreshIntervalChange
  };
}
