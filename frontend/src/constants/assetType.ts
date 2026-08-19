// frontend/src/constants/assetType.ts
// 资产类型（type）相关常量与工具函数。
// 收口自 explore/index.vue 与 AddToWatchlistModal.vue 的重复实现（#980）。

/** 资产类型中文标签（stock/etf/fund/bond/index） */
export const ASSET_TYPE_LABELS: Record<string, string> = {
  stock: "股票",
  etf: "ETF",
  fund: "场外基金",
  bond: "可转债",
  index: "指数"
};

/** 资产类型 → 中文标签；未知类型原样返回 */
export function getTypeLabel(type: string): string {
  return ASSET_TYPE_LABELS[type] || type;
}
