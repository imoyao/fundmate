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
  // #1365：指数名录三源合并，中证/国证专属代码的命名空间前缀
  CSI: "中证",
  CNI: "国证",
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

/** 交易场所取值（与后端 app/core/venues.py 的 VENUE_VALUES 对齐，#1662） */
export const VENUE_EXCHANGE = "EXCHANGE";
export const VENUE_OTC = "OTC";

/**
 * 资产类型 → 交易场所的**缺省**推断（#1662）。
 *
 * 与后端 core/venues.venue_of_asset_type 同一张表：股票 / ETF / 债券 / 逆回购 → 场内，
 * 基金 / 货基 → 场外，经理 / 组合 / 指数等无场所实体 → 空串。
 *
 * ⚠️ 这张表**不是全函数**：场内货基（代码段 ^97\d{4}$，如 970164）与场内 LOF 的场所
 * 与缺省相反，必须由调用方显式传 venue。前端只把它当作手动记账的缺省值，
 * 最终形态仍以后端归一结果为准。
 */
export function venueOfAssetType(assetType?: string | null): string {
  const t = (assetType || "").trim().toLowerCase();
  if (t === "fund" || t === "money_fund") return VENUE_OTC;
  if (t === "stock" || t === "etf" || t === "bond" || t === "reverse_repo")
    return VENUE_EXCHANGE;
  return "";
}
