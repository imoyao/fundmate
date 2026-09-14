// frontend/src/views/explore/composables/useExploreWatchlist.ts
/**
 * 探市页「观察列表」区块的数据与行为（2026-09-12 从 explore/index.vue 抽出，见 #980
 * 「第三步：抽自定义 Hook」）。
 *
 * 抽取原因：index.vue 曾把「本地持仓 + 实时估值 + 表格派生 + 状态指示 + 收藏/移除」
 * 全部内联，主文件 618 行远超 #980 建议的 200~300 行上限，且页面无法回归「只做编排」。
 *
 * 边界：本 composable 只管**数据与列表行为**；页面级导航（去自选页 / 去登录）
 * 仍留在 index.vue，因为它属于页面编排职责。
 */
import { ref, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import { useLocalHoldings } from "@/composables/useLocalHoldings";
import { useRealtimeQuotes } from "@/composables/useRealtimeQuotes";
import { useAuthState } from "@/composables/useAuthState";
import { createWatchlistItem } from "@/api/watchlist";
import {
  buildExternalQuoteUrl,
  type ExternalLinkCommand
} from "@/utils/externalQuoteLinks";
import type { Router } from "vue-router";

/** 观察列表行（本地持仓 + 实时行情合并后的展示模型） */
export interface ExploreWatchlistRow {
  symbol: string;
  type: string;
  name: string;
  [key: string]: unknown;
}

/**
 * @param router 由调用方注入，避免 composable 内部重复 useRouter（便于测试）
 */
export function useExploreWatchlist(router: Router) {
  const { isAuthenticated } = useAuthState();

  // ================================================================
  // 本地持仓（useLocalHoldings 初始化失败时降级为空实现，保证页面不白屏）
  // ================================================================
  let localHoldings;
  try {
    localHoldings = useLocalHoldings();
  } catch (e) {
    console.error("useLocalHoldings 初始化失败:", e);
    localHoldings = {
      holdings: ref([]),
      addHolding: () => ({ success: false, message: "初始化失败" }),
      removeHolding: () => {},
      updateHolding: () => {},
      clearAll: () => {},
      getHoldingsForQuotes: () => [],
      isPureObservationMode: computed(() => false),
      totalCount: computed(() => 0)
    };
  }

  const holdings = localHoldings.holdings;
  const addHolding = localHoldings.addHolding;
  const removeHolding = localHoldings.removeHolding;
  const getHoldingsForQuotes = localHoldings.getHoldingsForQuotes;
  const totalCount = localHoldings.totalCount;
  const isPureObservationMode = localHoldings.isPureObservationMode;

  // ================================================================
  // 实时估值
  // ================================================================
  const {
    items,
    summary,
    enabled,
    toggle,
    status,
    lastUpdateTime,
    refreshInterval,
    setRefreshInterval,
    manualRefresh
  } = useRealtimeQuotes(
    () => {
      try {
        return getHoldingsForQuotes();
      } catch {
        return [];
      }
    },
    () => undefined
  );

  const quotesMap = computed(() => {
    const map: Record<string, any> = {};
    if (!items || !items.value) return map;
    items.value.forEach((item: any) => {
      if (item.symbol) {
        map[item.symbol] = item;
      }
    });
    return map;
  });

  watch(
    () => holdings.value,
    newHoldings => {
      if (enabled.value && newHoldings && newHoldings.length > 0) {
        manualRefresh();
      }
    },
    { deep: true }
  );

  /** 页面挂载后开启实时刷新（幂等） */
  const startRealtime = () => {
    if (!enabled.value) {
      toggle(true);
    }
  };

  // ================================================================
  // 表格数据：本地持仓 × 实时行情
  // ================================================================
  const loading = ref(false);

  const tableData = computed(() => {
    try {
      let hold: any[] = [];
      if (
        localHoldings &&
        typeof localHoldings.holdings === "object" &&
        "value" in localHoldings.holdings
      ) {
        const h = localHoldings.holdings.value;
        if (Array.isArray(h)) {
          hold = h;
        }
      }
      if (hold.length === 0) return [];

      const map = quotesMap.value;
      return hold.map(h => {
        const quote = map[h.symbol] || null;
        const price = quote?.currentPrice ?? 0;
        const changePct = quote?.changePct ?? 0;
        const cost = h.costPrice ?? 0;
        const qty = h.quantity ?? 0;
        const prevClose = quote?.prevClose ?? price;
        const pnl = (price - prevClose) * qty;
        // 行情缺失时不能把 price 当 0 代入持仓收益：否则 (0 - cost) * qty
        // 会显示成巨额虚假亏损；无行情应视为「无盈亏」。
        const positionPnl = quote ? (price - cost) * qty : 0;
        return {
          ...h,
          quote,
          price,
          changePct,
          pnl,
          positionPnl
        };
      });
    } catch {
      return [];
    }
  });

  // ================================================================
  // 状态指示器
  // ================================================================
  const statusClass = computed(() => {
    switch (status.value) {
      case "trading":
        return "status-trading";
      case "closed":
        return "status-closed";
      case "error":
        return "status-error";
      default:
        return "status-idle";
    }
  });

  const statusText = computed(() => {
    switch (status.value) {
      case "trading":
        return "实时更新";
      case "closed":
        return "休市中";
      case "error":
        return "连接异常";
      default:
        return "等待中";
    }
  });

  // ================================================================
  // 列表行为
  // ================================================================
  /** 移除（确认框在子组件内，这里只负责真正移除） */
  const handleRemove = (id: string) => {
    removeHolding(id);
    ElMessage.success("已移除");
  };

  /** 深度分析跳转（外部工具） */
  const handleJump = (row: ExploreWatchlistRow, command: string) => {
    const url = buildExternalQuoteUrl(
      row.symbol,
      command as ExternalLinkCommand
    );
    if (url) {
      window.open(url, "_blank");
    }
  };

  /**
   * 收藏到自选（#822 todo2）：已登录 → 写入后端 watchlist；未登录 → 引导注册。
   */
  const handleFavorite = async (row: ExploreWatchlistRow) => {
    if (!isAuthenticated.value) {
      ElMessage.warning("登录后可收藏到自选，立即注册解锁跨设备同步");
      router.push("/login");
      return;
    }
    try {
      await createWatchlistItem({
        symbol: row.symbol,
        asset_type: row.type,
        // venue 必传：后端 normalize_and_infer_venue 对非 fund 且无 venue 的标的
        // 直接 ValueError('缺少 asset_type 或 venue') → 400「收藏失败」。
        // 场外基金 OTC，其余（股票/ETF/指数等场内标的）EXCHANGE，与后端口径一致
        venue: row.type === "fund" ? "OTC" : "EXCHANGE"
      });
      ElMessage.success(`已收藏「${row.name}」到自选`);
    } catch (e: unknown) {
      // 409 = 后端查重命中「该资产已在自选列表中」：是预期结果不是故障，
      // 用 warning 提示而非 error（否则用户重复点击会看到一串红色报错）
      const status = (e as { response?: { status?: number } })?.response
        ?.status;
      if (status === 409) {
        ElMessage.warning(`「${row.name}」已在自选中，无需重复收藏`);
        return;
      }
      const msg = e instanceof Error ? e.message : String(e);
      ElMessage.error(msg || "收藏失败，请重试");
    }
  };

  return {
    // 数据
    addHolding,
    quotesMap,
    tableData,
    loading,
    totalCount,
    isPureObservationMode,
    summary,
    // 状态
    statusClass,
    statusText,
    refreshInterval,
    lastUpdateTime,
    setRefreshInterval,
    manualRefresh,
    // 行为
    startRealtime,
    handleRemove,
    handleJump,
    handleFavorite
  };
}
