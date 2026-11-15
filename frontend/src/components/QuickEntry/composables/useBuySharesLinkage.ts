import type { Ref } from "vue";
import { useSharesLinkage } from "@/composables/useSharesLinkage";

interface SharesLinkageForm {
  buyAmount: number | undefined;
  shares: number | undefined;
  fee: number | undefined;
  price: number | undefined;
}

/**
 * 记一笔（`BuyForm`）的「金额 / 手续费 / 份额 / 净值」联动。
 *
 * 实现已上提为通用 composable `@/composables/useSharesLinkage`（2026-11-15）：
 * 对账工作台的补录弹窗也要同一份口径（owner 指出「基金买入按金额自动算份额，
 * 补录却不遵守」），而两边字段名不同（这边是 `buyAmount / shares / price`，
 * 那边是 `quantity / avg_price`），用访问器适配即可共用，不必改任何一侧的载荷。
 *
 * 这里保留原签名与单测（`__tests__/useBuySharesLinkage.spec.ts`）：
 * 行为逐字不变，测试同时钉住「共用后记一笔没被改坏」。
 */
export function useBuySharesLinkage(deps: {
  form: SharesLinkageForm;
  navMissing: Ref<boolean>;
}) {
  const { form, navMissing } = deps;
  return useSharesLinkage({
    navMissing,
    fields: {
      amount: () => form.buyAmount,
      setAmount: value => {
        form.buyAmount = value;
      },
      shares: () => form.shares,
      setShares: value => {
        form.shares = value;
      },
      price: () => form.price,
      fee: () => form.fee
    }
  });
}
