/** 卖出表单的数据模型（#980 拆分时从 SellForm.vue 的局部 defaultForm 抽出，供父组件与
 *  「账户/持仓切换」「重置」两处共用同一份默认值）。 */
export interface SellFormModel {
  ledger_id: number | null;
  positionId: number | null;
  symbol: string;
  name: string;
  market: string;
  type: string;
  quantity: number | undefined;
  price: number | undefined;
  trade_date: string;
  isAfter15: boolean;
  notes: string;
  currency: string;
  fee: number | undefined;
}

export function defaultSellForm(): SellFormModel {
  return {
    ledger_id: null as number | null,
    positionId: null as number | null,
    symbol: "",
    name: "",
    market: "CN_A",
    type: "stock",
    quantity: undefined as number | undefined,
    price: undefined as number | undefined,
    trade_date: new Date().toISOString().slice(0, 10),
    isAfter15: false,
    notes: "",
    currency: "CNY",
    fee: 0 as number | undefined
  };
}
