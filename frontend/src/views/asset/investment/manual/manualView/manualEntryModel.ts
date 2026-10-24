/**
 * 完整记账页的纯函数层（#980 拆分）。
 *
 * 抽出来的都是「同一份判定在模板和脚本里各写一遍」的东西：
 * 模板用它们决定渲染哪个表单分支，脚本用它们决定「确认记账」走买入还是卖出提交。
 * 两边一旦写歪（比如模板加了 `drip` 分支而脚本没跟上），表现是点了没反应或提交错通道——
 * 比报错更难发现，所以收成一处、由单测钉住。
 *
 * 这里不 import 任何组件 / 路由 / 请求，保证可在 node 环境直接跑。
 */

/** 证券账户可用的操作 */
export type StockOpType = "buy" | "sell" | "dividend" | "split";

/** 基金 / 银行（类现金）账户可用的操作 */
export type FundOpType =
  "subscribe" | "redeem" | "dividend_reinvest" | "split" | "convert" | "drip";

/** 提交通道：`useQuickEntrySubmit` 只认这三个 */
export type SubmitOpType = "buy" | "sell" | "dividend";

/** 账户 `ledger_type`，只关心本页会分流到的几种 */
export type LedgerType = string | null | undefined;

/** 基金组（fund / bank）才有的操作，判定里反复出现 */
const FUND_LIKE = ["fund", "bank"];

export function isFundLike(type: LedgerType): boolean {
  return FUND_LIKE.includes(type ?? "");
}

/**
 * 是否「卖出类」操作：证券卖出 / 基金赎回。
 * 影响账户下拉的可选项（只留可卖出的）和是否显示「新建账户」。
 */
export function isSellLikeOf(
  ledgerType: LedgerType,
  stockOpType: StockOpType,
  fundOpType: FundOpType
): boolean {
  if (ledgerType === "stock") return stockOpType === "sell";
  if (isFundLike(ledgerType)) return fundOpType === "redeem";
  return false;
}

/** 分红 / 红利再投：复用同一张 DividendForm，按操作类型切子模式 */
export function isDividendLikeOf(
  ledgerType: LedgerType,
  stockOpType: StockOpType,
  fundOpType: FundOpType
): boolean {
  if (ledgerType === "stock") return stockOpType === "dividend";
  if (isFundLike(ledgerType)) return fundOpType === "dividend_reinvest";
  return false;
}

/** 送股 / 拆分：同样复用 DividendForm */
export function isSplitOf(
  ledgerType: LedgerType,
  stockOpType: StockOpType,
  fundOpType: FundOpType
): boolean {
  if (ledgerType === "stock") return stockOpType === "split";
  if (isFundLike(ledgerType)) return fundOpType === "split";
  return false;
}

/**
 * DividendForm 的 mode 入参。
 * 原写法是模板里的三元套三元，搬到函数里是为了让「split 优先于 dividend」这条
 * 优先级有名字——两个标志位不会同时为真，但阅读顺序曾经暗示它们会。
 */
export function dividendModeOf(
  isSplit: boolean,
  ledgerType: LedgerType,
  stockOpType: StockOpType
): "split" | "dividend" | "dividend_reinvest" {
  if (isSplit) return "split";
  return stockOpType === "dividend" ? "dividend" : "dividend_reinvest";
}

/**
 * 「确认记账」实际走哪条提交通道。
 * 分红类（含拆分）归 dividend，卖出 / 赎回归 sell，其余（买入 / 申购 / 定投）归 buy。
 */
export function submitOpTypeOf(
  isDividendLike: boolean,
  isSplit: boolean,
  stockOpType: StockOpType,
  fundOpType: FundOpType
): SubmitOpType {
  if (isDividendLike || isSplit) return "dividend";
  return stockOpType === "sell" || fundOpType === "redeem" ? "sell" : "buy";
}

/** 未实现分支的占位文案：把枚举值翻成中文，翻不出来就原样显示 */
export function getFundOpLabel(type: string): string {
  const map: Record<string, string> = {
    dividend_reinvest: "红利再投",
    split: "送股/拆分",
    convert: "转换",
    drip: "定投"
  };
  return map[type] || type;
}

/**
 * 极简建账时随渠道下发的费率初值，与账户页 `CreateAccountDialog` 保持一致：
 * 场外基金申购费 1 折，证券佣金万 2.5（免五）。
 *
 * 这里只给这两类渠道配初值——其余渠道后端有自己的默认值，前端不越权写死。
 */
export function quickAddFeeConfig(
  channel: string
): Record<string, unknown> | undefined {
  if (channel === "fund_platform") return { subscription_discount: 0.1 };
  if (channel === "securities")
    return { commission: { rate: 0.00025, min: null } };
  return undefined;
}
