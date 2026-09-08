// frontend/src/constants/market.ts
// 市场 / 交易场所 中文标签与工具函数。
// 收口自 AddToWatchlistModal.vue 与 AccountOverview.vue 的重复实现（#1053）。

/** 市场中文标签：CN_A=沪深A股、CN_HK=港股、US=美股、CRYPTO=虚拟币 */
export const MARKET_LABELS: Record<string, string> = {
  CN_A: "A股",
  CN_HK: "港股",
  HK: "港股",
  SH: "沪市",
  SZ: "深市",
  US: "美股",
  CRYPTO: "虚拟币",
  crypto: "虚拟币",
  COMMODITY: "大宗商品",
  // #1286：无市场实体（基金经理/投顾组合）约定存空串
  "": "通用"
};

/** 市场 → 中文标签；未知市场原样返回 */
export function getMarketLabel(market: string): string {
  return MARKET_LABELS[market] || market;
}

/** 交易场所中文标签：EXCHANGE=场内、OTC=场外 */
export const VENUE_LABELS: Record<string, string> = {
  EXCHANGE: "场内",
  OTC: "场外"
};

/** 交易场所 → 中文标签；未知场所原样返回 */
export function getVenueLabel(venue: string): string {
  return VENUE_LABELS[venue] || venue;
}
