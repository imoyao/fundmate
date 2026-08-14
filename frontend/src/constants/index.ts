// src/constants/index.ts
// 全局业务常量，与后端 app/core/constants.py 保持一致

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
