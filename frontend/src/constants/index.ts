// src/constants/index.ts
// 全局业务常量，与后端 app/core/constants.py 保持一致

/** 持仓数据来源枚举值（与后端 app.core.constants.PositionSource 对齐）。
 * 注意：中文 label 不在此处手抄，统一从 GET /api/utils/enums 的 position_source 下发，
 * 前端用 useEnumLabels 获取，避免前后端各维护一套导致漂移。 */
export const POSITION_SOURCE = {
  MANUAL: 'manual',
  E_ACCOUNT: 'e_account_holding',
  BROKER_TIANTIAN: 'tiantian_fund',
  BROKER_THS: 'ths_stock',
  BROKER_STD_FUND: 'standard_fund',
  BROKER_STD_STOCK: 'standard_stock',
  BROKER_ALIPAY: 'alipay_fund',
  BROKER_ALIPAY_PDF: 'alipay_pdf',
  BROKER_STD_TEMPLATE: 'standard_template',
  AI_TXN: 'ai_txn',
  AI_HOLDING: 'ai_holding',
  EXPLORE: 'explore'
} as const;

/** 账户类型 */
export const LEDGER_TYPE_OPTIONS = [
  { value: "bank", label: "银行账户" },
  { value: "stock", label: "证券账户" },
  { value: "fund", label: "基金平台" },
  { value: "property", label: "实物资产" }
] as const;

export const LEDGER_TYPE_LABELS: Record<string, string> = {
  bank: "银行账户",
  stock: "证券账户",
  fund: "基金平台",
  property: "实物资产"
};

/** 五笔钱配置目标 */
export const ALLOCATION_OPTIONS = [
  { value: "liquid", label: "活钱" },
  { value: "stable", label: "稳健底仓" },
  { value: "longterm", label: "长期增值" },
  { value: "speculative", label: "高风险博弈" },
  { value: "security", label: "保险保障" }
] as const;

export const ALLOCATION_LABELS: Record<string, string> = {
  liquid: "活钱",
  stable: "稳健底仓",
  longterm: "长期增值",
  speculative: "高风险博弈",
  security: "保险保障"
};

/** 账户类型单字缩写 */
export const LEDGER_TYPE_SHORT: Record<string, string> = {
  bank: "银",
  stock: "股",
  fund: "基",
  property: "物",
  deleted: "已删"
};

/** 资产大类标签（与后端 app/core/constants.py ASSET_CATEGORY_LABELS 对齐） */
export const MAJOR_CATEGORY_LABELS: Record<string, string> = {
  cash: "流动资金",
  fixed: "固定资产",
  investment: "投资理财",
  receivable: "应收款",
  liability: "负债",
  insurance: "保险项目"
};

export function majorCategoryLabel(key: string): string {
  return MAJOR_CATEGORY_LABELS[key] ?? key;
}

/** 交易类型标签（buy/sell/dividend/deposit/withdraw） */
export const TXN_TYPE_LABELS: Record<string, string> = {
  buy: "买入",
  sell: "卖出",
  dividend: "分红",
  deposit: "存入",
  withdraw: "取出"
};

export function txnTypeLabel(type: string): string {
  return TXN_TYPE_LABELS[type] ?? type;
}

// 建议放在 src/constants/index.ts 末尾
export const ALLOCATION_COLORS: Record<string, string> = {
  liquid: "#7A9AA8",
  stable: "#9D81A9",
  longterm: "#7A7FA8",
  speculative: "#C83E66",
  security: "#B88A8A"
};

/** 工具函数 */
export function getLedgerTypeLabel(type: string): string {
  return LEDGER_TYPE_LABELS[type] ?? type;
}

export function getAllocationLabel(alloc: string): string {
  return ALLOCATION_LABELS[alloc] ?? (alloc || "未配置");
}

export type AllocationType =
  "liquid" | "stable" | "longterm" | "speculative" | "security";
