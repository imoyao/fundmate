import { watch, type Ref } from "vue";
import { useFundTradeDate } from "@/composables/useFundTradeDate";

interface SellNavForm {
  trade_date: string;
  isAfter15: boolean;
  type: string;
  price: number | undefined;
}

/**
 * 卖出侧的净值回填（#980 从 SellForm 拆出）。
 *
 * 交易日期 / 15:00 时点 / 选中持仓任一变化 → 基金按确认日（15:00 后顺延 T+1）拉净值
 * 回填到 `form.price`；股票不处理（价格区间由 useSecurityPriceRange 自己刷新）。
 *
 * 监听刻意**不依赖** `form.price`：把 price 放进依赖列表会让净值回填触发自身，
 * 既可能循环，也可能覆盖用户手改的成交价。
 */
export function useSellNavSync(deps: {
  form: SellNavForm;
  selectedPosition: Ref<any>;
}) {
  const { form, selectedPosition } = deps;
  const {
    confirmDate,
    actualNavDate,
    calcConfirmAndNav,
    reset: resetTradeDate
  } = useFundTradeDate();

  watch(
    [() => form.trade_date, () => form.isAfter15, () => selectedPosition.value],
    async () => {
      if (!selectedPosition.value) return;
      if (form.type === "fund" && form.trade_date) {
        const pos = selectedPosition.value;
        const result = await calcConfirmAndNav({
          tradeDate: form.trade_date,
          symbol: pos.symbol,
          isAfter15: form.isAfter15
        });
        if (result?.nav != null) {
          form.price = result.nav;
        }
      }
      // 股票价格区间由 useSecurityPriceRange 随持仓/交易日自动刷新（#948 统一约束）
    }
  );

  return { confirmDate, actualNavDate, calcConfirmAndNav, resetTradeDate };
}
