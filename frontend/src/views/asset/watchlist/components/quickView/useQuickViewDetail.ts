import { ref, watch } from "vue";
import {
  getAdvisorAdjusts,
  getAdvisorHoldings,
  type AdvisorAdjustGroup,
  type AdvisorAdjustsResult,
  type AdvisorHoldingsResult
} from "@/api/funds";
import { unwrap } from "./quickViewModel";

/**
 * #1468 成分与调仓：抽屉打开时**按需**拉取。
 *
 * 不进列表主请求——只有点开速览的组合才需要，上百只组合全量带明细会拖慢列表。
 * 三个触发条件（打开 / 换标的 / 品类是投顾组合）缺一不拉，与原先的 watch 源一致。
 */
export function useQuickViewDetail(opts: {
  open: () => boolean;
  symbol: () => string | undefined;
  isPortfolio: () => boolean;
}) {
  const detailLoading = ref(false);
  const detailError = ref("");
  const holdingsCount = ref(0);
  const missingCount = ref(0);
  const adjustGroups = ref<AdvisorAdjustGroup[]>([]);

  async function loadDetail(symbol: string) {
    detailLoading.value = true;
    detailError.value = "";
    holdingsCount.value = 0;
    missingCount.value = 0;
    adjustGroups.value = [];
    try {
      const [hRes, aRes] = await Promise.all([
        getAdvisorHoldings(symbol),
        getAdvisorAdjusts(symbol, 3)
      ]);
      const h = unwrap<AdvisorHoldingsResult>(hRes);
      const holdings = h?.holdings ?? [];
      holdingsCount.value = holdings.length;
      missingCount.value = holdings.filter(x => !x.in_local_db).length;

      const a = unwrap<AdvisorAdjustsResult>(aRes);
      adjustGroups.value = a?.adjusts ?? [];
    } catch {
      detailError.value = "明细加载失败";
    } finally {
      detailLoading.value = false;
    }
  }

  watch(
    () => [opts.open(), opts.symbol(), opts.isPortfolio()] as const,
    ([open, symbol, isPf]) => {
      if (!open || !isPf || !symbol) return;
      void loadDetail(String(symbol));
    },
    { immediate: true }
  );

  return {
    detailLoading,
    detailError,
    holdingsCount,
    missingCount,
    adjustGroups
  };
}
