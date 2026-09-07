// src/constants/index.ts
// 全局业务常量，与后端 app/core/constants.py 保持一致

/** 持仓数据来源枚举值（与后端 app.core.constants.PositionSource 对齐）。
 * 注意：中文 label 不在此处手抄，统一从 GET /api/utils/enums 的 position_source 下发，
 * 前端用 useEnumLabels 获取，避免前后端各维护一套导致漂移。 */
export const POSITION_SOURCE = {
  MANUAL: "manual",
  E_ACCOUNT: "e_account_holding",
  BROKER_TIANTIAN: "tiantian_fund",
  BROKER_THS: "ths_stock",
  BROKER_STD_FUND: "standard_fund",
  BROKER_STD_STOCK: "standard_stock",
  BROKER_ALIPAY: "alipay_fund",
  BROKER_ALIPAY_PDF: "alipay_pdf",
  BROKER_STD_TEMPLATE: "standard_template",
  AI_TXN: "ai_txn",
  AI_HOLDING: "ai_holding",
  EXPLORE: "explore"
} as const;

/**
 * 账户类型（渠道分组）选项：创建账户时选择「渠道分组」，
 * 后端按 channel_category 派生 ledger_type。value 与 CHANNEL_CATEGORY_LABELS 对齐。
 */
export const LEDGER_TYPE_OPTIONS = [
  { value: "bank", label: "银行" },
  { value: "securities", label: "证券" },
  { value: "fund_platform", label: "基金" },
  { value: "insurance", label: "保险" },
  { value: "futures", label: "期货" },
  { value: "other", label: "其他" }
] as const;

export const LEDGER_TYPE_LABELS: Record<string, string> = {
  bank: "银行账户",
  stock: "证券账户",
  fund: "基金",
  property: "实物资产"
};

/** 渠道分组中文标签（用户可见分组，对应后端 Ledger.channel_category） */
export const CHANNEL_CATEGORY_LABELS: Record<string, string> = {
  bank: "银行",
  securities: "证券",
  fund_platform: "基金",
  insurance: "保险",
  futures: "期货",
  other: "其他"
};

/** 渠道分组标签：命中单一真相源则返回，否则原样返回（兼容未知分组） */
export function getChannelCategoryLabel(key: string): string {
  return CHANNEL_CATEGORY_LABELS[key] ?? key;
}

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

/** 资产大类标签（与后端 app/core/asset_types.py ASSET_CATEGORY_LABELS 对齐）。
 * 注意：bank_wealth / advisory / trust / private_fund / wealth_insurance 五个键
 * 仅用于「存量明细标签回退」，不再是大类选项（#1354 已收敛到投资理财），
 * 新建记录禁止再写入这五个 major_category，细分走 minor_category。 */
export const MAJOR_CATEGORY_LABELS: Record<string, string> = {
  cash: "流动资金",
  fixed: "固定资产",
  investment: "投资理财",
  receivable: "应收款",
  liability: "负债",
  insurance: "保险项目",
  bank_wealth: "银行理财",
  advisory: "投顾",
  trust: "信托",
  private_fund: "私募",
  wealth_insurance: "理财型保险"
};

/** 可选的大类（6 个主类）。盘点页标签栏与录入表单的下拉都以它为准。
 * label 从 MAJOR_CATEGORY_LABELS 派生，避免两处重复维护导致漂移（#1355 AI review）。 */
const MAJOR_CATEGORY_ORDER = [
  "investment",
  "cash",
  "fixed",
  "liability",
  "receivable",
  "insurance"
] as const;

export const MAJOR_CATEGORY_OPTIONS = MAJOR_CATEGORY_ORDER.map(value => ({
  value,
  label: MAJOR_CATEGORY_LABELS[value]
}));

/** 投资理财下的细分子类（写 minor_category；与后端 INVESTMENT_MINOR_CATEGORIES 对齐） */
export const INVESTMENT_MINOR_CATEGORIES = [
  { value: "bank_wealth", label: "银行理财" },
  { value: "advisory", label: "投顾" },
  { value: "trust", label: "信托" },
  { value: "private_fund", label: "私募" },
  { value: "wealth_insurance", label: "理财型保险" }
] as const;

/** 历史细分大类（曾作为平级 major_category，#1354 收敛后为存量兼容的查询键）。
 * 与 INVESTMENT_MINOR_CATEGORIES 的值当前相同但语义不同：此处是「查询口径的
 * major_category 取值」，后者是「写入口径的 minor_category 取值」，故单独维护，
 * 避免 minor 维度新增非历史 major 的细分类时两维耦合出错（#1355 AI review）。 */
export const INVESTMENT_LEGACY_MAJOR_KEYS = [
  "bank_wealth",
  "advisory",
  "trust",
  "private_fund",
  "wealth_insurance"
] as const;

/** 「投资理财」在查询口径下包含的全部 major_category（含历史细分类），
 * 逗号分隔直接传给后端 major_category 多值过滤（#1354）。 */
export const INVESTMENT_MAJOR_KEYS = [
  "investment",
  ...INVESTMENT_LEGACY_MAJOR_KEYS
].join(",");

export function majorCategoryLabel(key: string): string {
  return MAJOR_CATEGORY_LABELS[key] ?? key;
}

/** 交易类型标签（buy/sell/dividend/deposit/withdraw/split/dividend_reinvest） */
export const TXN_TYPE_LABELS: Record<string, string> = {
  buy: "买入",
  sell: "卖出",
  dividend: "分红",
  deposit: "存入",
  withdraw: "取出",
  split: "送股/拆分",
  dividend_reinvest: "红利再投资"
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

/** 温度指标数据来源 -> 中文显示名（单一真相源，避免页面手抄拼音/英文）。
 * 与后端温度计数据来源的 source 取值对齐（韭圈儿/且慢/东财等）。 */
export const TEMP_SOURCE_LABELS: Record<string, string> = {
  jiucaishuo_fear: "韭圈儿",
  jiucaishuo_medium: "韭圈儿",
  qieman: "且慢",
  youzhiyouxing: "有知有行",
  jisilu_cb: "集思录",
  jisilu_indicator: "集思录",
  eastmoney_volume: "东财",
  eastmoney: "东财",
  self_calc: "自算",
  fulai: "富来智投",
  default: ""
};

/** 温度来源中文标签：命中单一真相源则返回，否则原样返回（兼容未知来源） */
export function tempSourceLabel(source?: string): string {
  if (!source) return "";
  return TEMP_SOURCE_LABELS[source] ?? source;
}
