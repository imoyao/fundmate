import type { Ref } from "vue";
import { getFundFeeRates } from "@/api/funds";
import type { useSecurityPriceRange } from "@/composables/useSecurityPrice";
import type { SecurityOption } from "./useSecuritySearch";

type RefreshRange = ReturnType<typeof useSecurityPriceRange>["refresh"];

interface SelectionForm {
  symbol: string;
  name: string;
  market: string;
  type: string;
  price: number | undefined;
  buyAmount: number | undefined;
  shares: number | undefined;
}

/**
 * 选中 / 清空买入标的后的连带动作（#980 从 BuyForm 拆出）：
 * - 股票：拉当日价格区间并回填收盘价（用户可改）；
 * - 基金：拉申购费明细回填 subscription_rate，供手续费预设使用；
 * - 最后统一触发一次手续费预设。
 *
 * 清空时把标的相关字段与 navMissing 一起复位 —— 之前漏掉 navMissing 会让
 * 「先选基金（净值缺失）再清空」停留在「可留空份额」的状态。
 */
export function useBuySecuritySelection(deps: {
  form: SelectionForm;
  selectedSecurityOption: Ref<SecurityOption | null>;
  navMissing: Ref<boolean>;
  applyFeePreset: () => void;
  refreshStockRange: RefreshRange;
}) {
  const { form, selectedSecurityOption, navMissing, applyFeePreset } = deps;

  async function onSecuritySelected(option: SecurityOption | null) {
    if (!option) {
      form.symbol = "";
      form.name = "";
      form.market = "CN_A";
      form.type = "stock";
      selectedSecurityOption.value = null;
      form.buyAmount = undefined;
      form.shares = undefined;
      navMissing.value = false;
      return;
    }
    form.symbol = option.symbol;
    form.name = option.name;
    form.market = option.market || "CN_A";
    form.type = option.type;
    selectedSecurityOption.value = option;

    // 股票：拉取价格区间并回填默认价（#948；基金净值由净值同步链路处理）
    if (option.type === "stock") {
      const range = await deps.refreshStockRange(option.symbol);
      if (!form.price && range?.close) {
        form.price = range.close; // 默认填收盘价，用户可改
      }
    }

    // 基金：拉取详细费率更新 subscription_rate（applyFeePreset 之后要读它）
    if (option.type === "fund") {
      try {
        const res = await getFundFeeRates(option.symbol);
        const data = res.data;
        if (data && data.purchase && data.purchase.length > 0) {
          // 取第一条费率作为默认预设（通常是无门槛或最低门槛的费率）
          const defaultRate = data.purchase[0].rate;
          // 回填到 option 上，这样 applyFeePreset 在之后触发时能拿到正确的 0.0 或 0.15%
          option.subscription_rate = defaultRate;
        }
      } catch (e) {
        console.warn("拉取详细费率失败", e);
      }
    }

    applyFeePreset(); // 最终触发预设
  }

  return { onSecuritySelected };
}
