// frontend/src/constants/assetType.ts
// 资产类型（asset_type）/ 资产大类（major_category）中文标签的前端镜像。
//
// 单一真相源在后端：app/core/asset_types（经 GET /api/utils/enums 的 asset_type / asset_category 下发）。
// 本文件是前端镜像，仅供「后端枚举未拉取时」的同步回退使用，确保任何情况下都不显示英文原键。
// 新增 / 修改类型或大类标签请改后端 asset_types，勿在此手抄第二份（#1171 枚举一致性）。
// 组件优先用 useEnumLabels.assetTypeLabel / assetCategoryLabel（后端实时来源），本文件作兜底。

/** 资产类型中文标签（镜像后端 ASSET_TYPE_LABELS；bond=可转债 为后端定调的权威值） */
export const ASSET_TYPE_LABELS: Record<string, string> = {
  stock: "股票",
  etf: "ETF",
  fund: "基金",
  bond: "可转债",
  index: "指数",
  crypto: "加密货币",
  saving: "存款",
  cash: "现金",
  static: "其他",
  money_fund: "货币基金",
  reverse_repo: "逆回购",
  bank: "银行",
  real_estate: "房产",
  insurance: "保险",
  precious_metal: "贵金属",
  liability: "负债"
};

/** 资产大类中文标签（镜像后端 ASSET_CATEGORY_LABELS） */
export const ASSET_CATEGORY_LABELS: Record<string, string> = {
  cash: "流动资金",
  fixed: "固定资产",
  investment: "投资理财",
  receivable: "应收款",
  liability: "负债",
  insurance: "保险",
  real_estate: "房产",
  precious_metal: "贵金属",
  custom: "自定义"
};

/** 资产类型 → 中文标签；未知类型回退镜像/原值 */
export function getTypeLabel(type: string): string {
  return ASSET_TYPE_LABELS[type] ?? type;
}

/** 资产大类 → 中文标签；未知大类回退镜像/原值 */
export function getCategoryLabel(category: string): string {
  return ASSET_CATEGORY_LABELS[category] ?? category;
}
