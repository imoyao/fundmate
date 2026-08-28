import { ref } from "vue";
import { calcFundConfirmDate } from "@/api/utils";
import { fetchFundNav } from "@/api/fundNav";

interface CalcOptions {
  /** 交易日期 YYYY-MM-DD */
  tradeDate: string;
  /** 基金代码（传入则自动拉取净值） */
  symbol?: string;
  /** 是否 15:00 后下单 */
  isAfter15?: boolean;
}

interface CalcResult {
  /** 实际净值日（后端返回，用于拉净值） */
  actualNavDate: string;
  /** 确认日期 */
  confirmDate: string;
  /** 拉取到的净值（symbol 传入时才有值） */
  nav?: number;
}

/**
 * 基金交易日期联动 composable
 *
 * 统一封装：交易日期 → calcFundConfirmDate → 确认日期 + 实际净值日 → fetchFundNav
 *
 * 被 BuyForm / SellForm / TransactionEditDialog 共用，
 * 消除三处重复的 calcFundConfirmDate + fetchFundNav 调用链。
 */
export function useFundTradeDate() {
  const navLoading = ref(false);
  const actualNavDate = ref("");
  const confirmDate = ref("");

  /**
   * 根据交易日期计算确认日期 + 实际净值日，可选拉取净值
   *
   * 仅对基金有效（调用方自行判断 isFund 后决定是否调用）。
   * 传入 symbol 则自动用 actualNavDate 拉净值。
   */
  async function calcConfirmAndNav(
    options: CalcOptions
  ): Promise<CalcResult | null> {
    const { tradeDate, symbol, isAfter15 = false } = options;

    if (!tradeDate) {
      actualNavDate.value = "";
      confirmDate.value = "";
      return null;
    }

    navLoading.value = true;
    try {
      const res = await calcFundConfirmDate({
        trade_date: tradeDate,
        fund_type: "domestic",
        is_after_15: isAfter15
      });
      const data = (
        res as unknown as {
          data?: { actual_trade_date?: string; confirm_date?: string };
        }
      )?.data;
      if (!data) return null;

      actualNavDate.value = data.actual_trade_date ?? tradeDate;
      confirmDate.value = data.confirm_date ?? tradeDate;

      // 可选：用实际净值日拉净值（不是 confirm_date）
      let nav: number | undefined;
      if (symbol && actualNavDate.value) {
        try {
          const result = await fetchFundNav(symbol, actualNavDate.value);
          if (result) {
            nav = result.unit_nav;
          }
        } catch (e) {
          console.warn("[useFundTradeDate] 净值拉取失败:", e);
        }
      }

      return {
        actualNavDate: actualNavDate.value,
        confirmDate: confirmDate.value,
        nav
      };
    } catch (e) {
      console.warn("[useFundTradeDate] 确认日期计算失败:", e);
      actualNavDate.value = "";
      confirmDate.value = "";
      return null;
    } finally {
      navLoading.value = false;
    }
  }

  /** 重置所有状态 */
  function reset() {
    actualNavDate.value = "";
    confirmDate.value = "";
    navLoading.value = false;
  }

  return {
    navLoading,
    actualNavDate,
    confirmDate,
    calcConfirmAndNav,
    reset
  };
}
