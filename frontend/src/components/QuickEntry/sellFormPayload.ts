import type { PositionCreate } from "@/api/types";
import type { SellFormModel } from "./sellFormModel";

/** 卖出提交载荷：PositionCreate + 几个一直随 body 发送、但未在后端模型声明的兼容字段 */
export interface SellPositionPayload extends PositionCreate {
  position_id?: number | null;
  /** 卖出金额（元）= 数量 × 成交价，后端据此记账 */
  amount?: number;
  allocation?: string | null;
  isAfter15?: boolean;
}

/**
 * 组装卖出 body（#980 从 SellForm.handleSubmit 抽出，纯函数可单测）。
 *
 * 口径：确认日只有基金留空（T+1 由后端按净值链路算），股票/ETF 当日确认；
 * 金额按「数量 × 成交价」原样提交，不扣手续费（手续费单列，后端算净额）。
 */
export function buildSellPayload(input: {
  form: SellFormModel;
  accountName: string;
  quantity: number;
}): SellPositionPayload {
  const { form, quantity } = input;
  return {
    symbol: form.symbol,
    name: form.name,
    op_type: "sell",
    position_id: form.positionId,
    market: form.market || "CN_A",
    type: form.type,
    ledger_id: form.ledger_id,
    account_name: input.accountName,
    quantity,
    avg_price: form.price,
    amount: quantity * form.price,
    currency: form.currency,
    trade_date: form.trade_date,
    confirm_date: form.type === "fund" ? null : form.trade_date,
    fee: form.fee || 0,
    notes: form.notes,
    allocation: null,
    isAfter15: form.isAfter15
  };
}
