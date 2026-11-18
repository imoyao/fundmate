// frontend/src/store/modules/overview.ts
import { defineStore } from "pinia";
import { getSummary } from "@/api/summary";
// getSummary() 已带 ApiResponse<SummaryData>，响应无需再断言

export interface OverviewData {
  netAsset: number | null;
  netAssetCaption: string;
  todayProfit: number | null;
  todayProfitUnit: string;
  todayProfitLevel: "" | "rise" | "fall";
  todayProfitCaption: string;
  holdingReturn: number | null;
  holdingReturnLevel: "" | "rise" | "fall";
  availableCash: number | null;
  totalAsset: number | null;
  holdingsValue: number | null;
  holdingsCost: number | null;
  todayProfitAmount: number | null;
  positionCount: number | null;
  maxPosition: number | null;
  concentration: number | null;
  cashRatio: number | null;
  yearReturn: number | null;
  annualizedReturn: number | null;
  maxDrawdown: number | null;
  sharpe: number | null;
}

interface OverviewState {
  overview: OverviewData;
  loading: boolean;
}

const emptyOverview = (): OverviewData => ({
  netAsset: null,
  netAssetCaption: "",
  todayProfit: null,
  todayProfitUnit: "元",
  todayProfitLevel: "",
  todayProfitCaption: "",
  holdingReturn: null,
  holdingReturnLevel: "",
  availableCash: null,
  totalAsset: null,
  holdingsValue: null,
  holdingsCost: null,
  todayProfitAmount: null,
  positionCount: null,
  maxPosition: null,
  concentration: null,
  cashRatio: null,
  yearReturn: null,
  annualizedReturn: null,
  maxDrawdown: null,
  sharpe: null
});

export const useOverviewStore = defineStore("overview", {
  state: (): OverviewState => ({
    overview: emptyOverview(),
    loading: false
  }),
  actions: {
    async fetchOverview(force = false) {
      if (this.loading && !force) return;
      this.loading = true;
      try {
        const res = await getSummary();
        const d = res?.data;
        if (d) {
          const total = d.total_assets_cny ?? null;
          const pnl = d.total_pnl_cny ?? null;
          this.overview = {
            ...emptyOverview(),
            netAsset: total,
            netAssetCaption: "截至最新估值",
            availableCash:
              pnl != null && total != null ? Math.max(total - pnl, 0) : null,
            totalAsset: total,
            todayProfit: pnl,
            todayProfitUnit: "元",
            todayProfitLevel:
              pnl != null && pnl > 0
                ? "rise"
                : pnl != null && pnl < 0
                  ? "fall"
                  : "",
            todayProfitCaption:
              pnl != null ? (pnl >= 0 ? "较昨日" : "较昨日") : "",
            todayProfitAmount: pnl,
            holdingReturn:
              total != null && pnl != null
                ? safeDiv(pnl, total - pnl) * 100
                : null,
            holdingReturnLevel:
              pnl != null && pnl > 0
                ? "rise"
                : pnl != null && pnl < 0
                  ? "fall"
                  : "",
            cashRatio:
              total != null && pnl != null
                ? safeDiv(Math.max(total - pnl, 0), total) * 100
                : null
          };
        }
      } catch {
        // 保留占位结构，渲染空态
      } finally {
        this.loading = false;
      }
    }
  }
});

function safeDiv(a: number, b: number): number {
  if (!b) return 0;
  return a / b;
}

export function useOverviewStoreHook() {
  return useOverviewStore();
}
