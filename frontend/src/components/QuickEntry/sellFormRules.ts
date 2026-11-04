import type { FormRules } from "element-plus";
import {
  createStockPriceValidator,
  type useSecurityPriceRange
} from "@/composables/useSecurityPrice";

type StockPriceRange = ReturnType<typeof useSecurityPriceRange>["priceRange"];

/**
 * 卖出表单校验规则（#980 从 SellForm 拆出）。
 *
 * - 份额必填，文案随品类变（基金「份额」/ 股票「数量」）；
 * - 价格只在股票生效，走 useSecurityPrice 的区间校验（#948 统一约束）；
 * - 账户/持仓/日期只判必填。
 */
export function createSellRules(deps: {
  /** 当前品类（决定份额文案与价格校验是否生效） */
  getType: () => string;
  stockPriceRange: StockPriceRange;
}): FormRules {
  const validateQuantity = (_rule: any, value: any, callback: any) => {
    if (value === undefined || value === null || value === "") {
      callback(
        new Error(
          deps.getType() === "fund" ? "请输入卖出份额" : "请输入卖出数量"
        )
      );
    } else {
      callback();
    }
  };

  return {
    ledger_id: [{ required: true, message: "请选择账户", trigger: "change" }],
    positionId: [
      { required: true, message: "请选择持仓产品", trigger: "change" }
    ],
    quantity: [{ validator: validateQuantity, trigger: "blur" }],
    price: [
      {
        validator: createStockPriceValidator(
          () => deps.stockPriceRange.value,
          () => deps.getType() === "stock"
        ),
        trigger: "blur"
      }
    ],
    trade_date: [{ required: true, message: "请选择日期", trigger: "change" }]
  };
}
