/**
 * 买入表单的默认值（#980 拆分时留在 BuyForm.vue）。
 *
 * 之所以搬出来：买入手续费对股票/ETF 也开放后，页面逼近 400 行门禁，
 * 而「默认值」与「重记一笔」「载荷组装」一样，属于不依赖组件状态的可搬迁数据。
 * 每次调用都返回新对象 —— 若共享同一个对象，`Object.assign(form, default)` 之外的
 * 任何就地修改都会污染下一次重置。
 */
export function createBuyFormDefaults() {
  return {
    ledger_id: null as number | null,
    symbol: "",
    name: "",
    market: "CN_A",
    type: "stock",
    price: undefined as number | undefined,
    trade_date: new Date().toISOString().slice(0, 10),
    confirm_date: "",
    fee: 0 as number | undefined,
    allocation: "longterm",
    notes: "",
    isAfter15: false,
    currency: "CNY",
    buyAmount: undefined as number | undefined,
    shares: undefined as number | undefined
  };
}
