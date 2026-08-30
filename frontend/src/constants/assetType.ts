// frontend/src/constants/assetType.ts
// 资产类型（type）相关常量与工具函数。
// 收口自 explore/index.vue 与 AddToWatchlistModal.vue 的重复实现（#980）。

/** 资产类型中文标签，与后端 app/core/constants.TYPE_LABELS 对齐补齐（#1171 枚举一致性） */
export const ASSET_TYPE_LABELS: Record<string, string> = {
  stock: "股票",
  etf: "ETF",
  fund: "基金",
  bond: "可转债",
  index: "指数",
  crypto: "虚拟币",
  saving: "存款",
  cash: "现金",
  static: "其他",
  // 以下为后端已定义、前端原缺失的类型；补齐后 getTypeLabel 不再 fallback 显示原始英文键
  money_fund: "货币基金",
  reverse_repo: "逆回购",
  bank: "银行",
  real_estate: "房产",
  insurance: "保险",
  precious_metal: "贵金属",
  liability: "负债"
};

/** 资产类型 → 中文标签；未知类型原样返回 */
export function getTypeLabel(type: string): string {
  return ASSET_TYPE_LABELS[type] || type;
}
