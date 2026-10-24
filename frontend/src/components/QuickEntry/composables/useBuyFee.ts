import { ref, type ComputedRef, type Ref } from "vue";
import type { LedgerItem } from "@/api/ledger";
import { DEFAULT_SUB_RATE } from "@/utils/trading";
import type { SecurityOption } from "./useSecuritySearch";

/** 账户 fee_config 的形状（后端 JSON：申购折扣 / 佣金费率与最低） */
export interface FeeConfig {
  subscription_discount?: number;
  commission?: { rate: number; min: number | null };
}

/** 手续费输入模式：金额（元）或费率（%）——两种模式共用同一个 form.fee */
export type FeeMode = "amount" | "rate";

export function parseFeeConfig(raw: unknown): FeeConfig | null {
  if (!raw) return null;
  try {
    return typeof raw === "string"
      ? (JSON.parse(raw) as FeeConfig)
      : (raw as FeeConfig);
  } catch {
    return null;
  }
}

/** 折扣档位：与份额档位同语言（SegmentedControl），值是折扣系数本身 */
export const FEE_DISCOUNT_OPTIONS = [
  { label: "原价", value: 1 },
  { label: "1折", value: 0.1 },
  { label: "0.1折", value: 0.01 },
  { label: "免申购费", value: 0 }
];

/**
 * 金额 ⇄ 费率换算：金额模式存元、费率模式存百分比（%）。
 * 金额算不出来（未填金额 / 手续费为 0）时返回 undefined —— 与旧行为一致：
 * 切模式时清空输入，而不是留个 0 让用户以为已经算过。
 */
export function convertFeeValue(
  targetMode: FeeMode,
  fee: number | undefined,
  amount: number
): number | undefined {
  if (amount > 0 && fee && fee > 0) {
    return targetMode === "rate"
      ? parseFloat(((fee / amount) * 100).toFixed(4))
      : parseFloat((amount * (fee / 100)).toFixed(2));
  }
  return undefined;
}

/** 快捷折扣档位 → 手续费（按当前模式返回元或百分比） */
export function feeFromDiscount(input: {
  subscriptionRate: number;
  discount: number;
  amount: number;
  mode: FeeMode;
}): number {
  const rate = input.subscriptionRate * input.discount;
  return input.mode === "rate"
    ? parseFloat((rate * 100).toFixed(4))
    : parseFloat((input.amount * rate).toFixed(2));
}

interface BuyFeeForm {
  fee: number | undefined;
  buyAmount: number | undefined;
}

/**
 * 买入手续费：账户预设 + 模式切换 + 折扣档位。
 *
 * 全表单只有 form.fee 一个真源（历史教训：曾另设 feeRateValue，两套状态互不同步，
 * 导致「切到费率模式改数字、金额模式算出 0」）。所有写入都落在 form.fee 上。
 */
export function useBuyFee(deps: {
  form: BuyFeeForm;
  currentLedger: ComputedRef<LedgerItem | null>;
  selectedSecurityOption: Ref<SecurityOption | null>;
}) {
  const feeMode = ref<FeeMode>("amount");
  /** 基金手续费折扣（账户 preset 可覆盖） */
  const fundFeeDiscount = ref(0.1);

  /** 按账户类型回填预设手续费：股票按佣金率，基金/银行按申购费 × 折扣 */
  function applyFeePreset() {
    const ledger = deps.currentLedger.value;
    if (!ledger) {
      deps.form.fee = 0;
      return;
    }
    const config = parseFeeConfig(ledger.fee_config);
    const safeAmount = deps.form.buyAmount || 0;
    if (ledger.ledger_type === "stock") {
      deps.form.fee = safeAmount * (config?.commission?.rate ?? 0.00025);
    } else if (ledger.ledger_type === "fund" || ledger.ledger_type === "bank") {
      fundFeeDiscount.value = config?.subscription_discount ?? 0.1;
      const fundRate =
        deps.selectedSecurityOption.value?.subscription_rate ??
        DEFAULT_SUB_RATE;
      deps.form.fee = safeAmount * fundRate * fundFeeDiscount.value;
    } else {
      deps.form.fee = 0;
    }
  }

  function onFeeModeChange() {
    deps.form.fee = convertFeeValue(
      feeMode.value,
      deps.form.fee,
      deps.form.buyAmount || 0
    );
  }

  function onFundFeeDiscountChange() {
    deps.form.fee = feeFromDiscount({
      subscriptionRate:
        deps.selectedSecurityOption.value?.subscription_rate ??
        DEFAULT_SUB_RATE,
      discount: fundFeeDiscount.value,
      amount: deps.form.buyAmount || 0,
      mode: feeMode.value
    });
  }

  return {
    feeMode,
    fundFeeDiscount,
    FEE_DISCOUNT_OPTIONS,
    applyFeePreset,
    onFeeModeChange,
    onFundFeeDiscountChange
  };
}
