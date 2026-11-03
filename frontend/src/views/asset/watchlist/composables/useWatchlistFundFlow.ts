/**
 * 自选页资金面数据域（#watchlist 资金面卡 + 个股主力净流入 / 所属板块两列）。
 *
 * 数据来自东财资金流（`realtimeDataSources.fetchStockFundFlow` /
 * `fetchSectorFundFlow`），与现有东财分时同源——纯前端 JSONP，无新后端依赖。
 *
 * 职责边界（与探市页划清）：
 * - 本 composable 只负责「个股级资金面」（主力净流入 + 所属板块）与「板块资金流排名」；
 * - 探市页（`explore`）承担全市场温度 / 行业情绪 / 拥挤度，**不做个股级资金面**，避免重复。
 *
 * 行补字段：个股资金流直接写回 `WatchlistItem.main_inflow` / `.sector`
 * （renderer 经 `field(row, key)` 读取，与 text/money 同机制；`clientSortedItems`
 * 返回的是原行对象引用，补字段会透传到表格单元格）。
 */
import { onMounted, ref, watch, type Ref } from "vue";
import type { WatchlistItem } from "@/api/types";
import {
  fetchSectorFundFlow,
  fetchStockFundFlow,
  type SectorFundFlow
} from "@/utils/realtimeDataSources";

export function useWatchlistFundFlow() {
  /** 个股资金流：symbol → { 主力净流入, 所属板块 }（供测试 / 外部读取，表格实际读 row 字段） */
  const stockFlow = ref<
    Record<string, { mainInflow: number | null; sector: string | null }>
  >({});
  /** 板块资金流（流入 / 流出两端各一批，按主力净流入降序） */
  const sectorFlow = ref<SectorFundFlow[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  // 避免「排序 / 分页」等非数据变更触发的重复拉取：仅当标的集合变化时再请求
  let lastSymbolSig = "";

  /**
   * 拉取并写回个股资金流。传入全量行（`data.allItems`），过滤股票/ETF 后批量查询，
   * 再补字段到每个行对象。标的集合不变时直接跳过。
   */
  async function loadStockFlow(items: WatchlistItem[]): Promise<void> {
    const targets = items.filter(it =>
      /^(stock|etf)$/.test((it.asset_type || "").toLowerCase())
    );
    const sig = targets
      .map(i => i.symbol)
      .slice()
      .sort()
      .join(",");
    if (sig === lastSymbolSig) return;
    lastSymbolSig = sig;

    if (targets.length === 0) {
      stockFlow.value = {};
      return;
    }

    try {
      const map = await fetchStockFundFlow(targets);
      const next: Record<
        string,
        { mainInflow: number | null; sector: string | null }
      > = {};
      for (const it of targets) {
        const f = map.get(it.symbol);
        const mainInflow = f?.mainInflow ?? null;
        const sector = f?.sector ?? null;
        next[it.symbol] = { mainInflow, sector };
        // 直接写回行对象（renderer 读 row[key]，与 text/money 同机制）
        it.main_inflow = mainInflow;
        it.sector = sector;
      }
      stockFlow.value = next;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    }
  }

  /** 拉取板块资金流（盘前资金面卡用）：两端一起取，由卡内取头尾。 */
  async function loadSectorFlow(): Promise<void> {
    loading.value = true;
    try {
      sectorFlow.value = await fetchSectorFundFlow();
    } catch (e) {
      sectorFlow.value = [];
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      loading.value = false;
    }
  }

  /**
   * 绑定到全量行：行集合变化（加载 / 刷新）时重新拉取个股资金流。
   * 用 `allItems` 而非 `items`——`items` 是 `allItems` 的切片，补字段到 allItems
   * 即透传到当前页（clientSortedItems 返回原行引用）。
   */
  function bindAllItems(allItems: Ref<WatchlistItem[]>): void {
    watch(
      allItems,
      rows => {
        void loadStockFlow(rows);
      },
      { immediate: true }
    );
  }

  onMounted(() => {
    void loadSectorFlow();
  });

  return {
    stockFlow,
    sectorFlow,
    loading,
    error,
    loadStockFlow,
    loadSectorFlow,
    bindAllItems
  };
}
