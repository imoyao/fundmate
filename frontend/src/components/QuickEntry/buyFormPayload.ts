import type { PositionCreate } from "@/api/types";
import type { FeeMode } from "./composables/useBuyFee";

/** 买入提交载荷：PositionCreate + 三个一直随 body 发送、但未在后端模型声明的兼容字段 */
export interface BuyPositionPayload extends PositionCreate {
  /** 买入金额（元）：后端按 amount 与 fee 反推份额，历史字段 */
  amount?: number;
  /** 配置目标（longterm 等），后端按需消费 */
  allocation?: string | null;
  /** 15:00 后下单标记，后端据此顺延净值日 */
  isAfter15?: boolean;
}

export interface BuyPayloadForm {
  symbol: string;
  name: string;
  market: string;
  type: string;
  ledger_id: number | null;
  price: number | undefined;
  buyAmount: number | undefined;
  fee: number | undefined;
  currency: string;
  trade_date: string;
  notes: string;
  allocation: string;
  isAfter15: boolean;
}

/**
 * 组装买入 body（#980 从 BuyForm.handleSubmit 抽出，纯函数可单测）。
 *
 * 三个口径点，拆出来才容易被测住：
 * 1. 确认日：基金取净值链路的 confirmDate（空串视同缺失 → null，后端自行按 T+1 算），
 *    股票/ETF 直接等于交易日；
 * 2. 手续费：费率模式下用户填的是百分比，必须换算成元再提交；
 * 3. 净值缺失先记账三件套：nav_pending + nav_date + shares_manual。
 *    nav_date 优先取 actualNavDate（15:00 后下单顺延一天），缺省回退 trade_date；
 *    份额手填过（quantity > 0）才标 shares_manual —— 回填时只校正净值不覆盖份额。
 */
export function buildBuyPayload(input: {
  form: BuyPayloadForm;
  accountName: string;
  quantity: number;
  /** 净值链路的确认日（useFundTradeDate.confirmDate） */
  confirmDate: string;
  navPending: boolean;
  /** 净值链路的实际净值日（useFundTradeDate.actualNavDate） */
  navDate: string;
  feeMode: FeeMode;
}): BuyPositionPayload {
  const { form } = input;

  const confirm_date =
    form.type === "fund"
      ? input.confirmDate && input.confirmDate.trim() !== ""
        ? input.confirmDate
        : null
      : form.trade_date;

  // 统一计算实际手续费，确保传给后端的是金额（元）
  let fee = form.fee || 0;
  if (input.feeMode === "rate") {
    fee = (form.buyAmount || 0) * (form.fee / 100);
  }

  return {
    symbol: form.symbol,
    name: form.name,
    op_type: "buy",
    market: form.market || "CN_A",
    type: form.type,
    ledger_id: form.ledger_id,
    account_name: input.accountName,
    quantity: input.quantity,
    avg_price: form.price || 0,
    amount: form.buyAmount || 0,
    currency: form.currency,
    trade_date: form.trade_date,
    confirm_date,
    fee,
    notes: form.notes,
    allocation: form.allocation,
    isAfter15: form.isAfter15,
    ...(input.navPending
      ? {
          nav_pending: true,
          nav_date: input.navDate || form.trade_date,
          shares_manual: input.quantity > 0
        }
      : {})
  };
}
