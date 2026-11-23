/**
 * 账户详情页「区块可见性」派生（#3222）。
 *
 * 从 `LedgerDetailOverview.vue` 下沉：区块清单（`ledgerDetailSections`）是
 * 单一真相源，这里把它翻译成页面可直接绑定的几个 `computed`。独立成
 * composable 的原因同 `overviewMetrics`——那页受页面规模门禁（400 行，
 * 只减不增）约束，而「某类型显示哪些区块」这组派生逻辑本身是纯读、无副作用，
 * 放页面里只会把它顶破阈值。
 */
import { computed } from "vue";
import type { ComputedRef, Ref } from "vue";
import {
  isInvestmentLedger,
  isSectionVisible
} from "@/composables/ledger/ledgerDetailSections";

export interface LedgerSectionsApi {
  /** 是否投资类账户（净值 + 盈亏口径），概览区的盈亏指标格只对它显示。 */
  isInvestment: ComputedRef<boolean>;
  /** 是否展示资产明细（property 专属）。 */
  showAssetList: ComputedRef<boolean>;
  /** 是否展示类现金卡（资金账户概念）。 */
  showCashLike: ComputedRef<boolean>;
  /** 是否展示收益日历 / 收益归因（净值型投资账户专属）。 */
  showPnlSections: ComputedRef<boolean>;
}

/**
 * 注意：`showDepthAnalysis` 不在本 composable 内——它额外带「ledgerIdNum 可解析」
 * 这条页面特有的口径前提（#2739，守卫 ledgerDepthAnalysisGuard 钉住），由
 * `LedgerDetailOverview.vue` 就地 computed，不下沉以免判据与页面脱钩。
 *
 * @param summaryData 账户概览（区块可见性只看它的 ledger_type）。
 */
export function useLedgerSections(
  summaryData: Ref<{ ledger_type?: string | null } | null>
): LedgerSectionsApi {
  const ledgerType = computed(() => summaryData.value?.ledger_type);

  const isInvestment = computed(() => isInvestmentLedger(ledgerType.value));

  const showAssetList = computed(() =>
    isSectionVisible("assetList", ledgerType.value)
  );

  const showCashLike = computed(() =>
    isSectionVisible("cashLike", ledgerType.value)
  );

  const showPnlSections = computed(() =>
    isSectionVisible("calendar", ledgerType.value)
  );

  return {
    isInvestment,
    showAssetList,
    showCashLike,
    showPnlSections
  };
}
