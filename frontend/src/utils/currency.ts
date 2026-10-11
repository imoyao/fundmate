// src/utils/currency.ts
import {
  EXCHANGE_RATES,
  CURRENCY_SYMBOLS,
  BASE_CURRENCY,
  type CurrencyCode
} from "@/constants/exchangeRates";

/** 未知币种按基准币种（CNY）处理，汇率 1 */
function resolveRate(currency: string): number {
  return EXCHANGE_RATES[currency as CurrencyCode] ?? 1;
}

/** 金额按币种折算为基准币种（CNY） */
export function toBaseCurrency(
  amount: number,
  currency: string = BASE_CURRENCY
): number {
  return amount * resolveRate(currency);
}

/** 从基准币种（CNY）折算为目标币种 */
export function fromBaseCurrency(
  amount: number,
  currency: string = BASE_CURRENCY
): number {
  const rate = resolveRate(currency);
  return rate === 0 ? 0 : amount / rate;
}

/** 取币种展示符号，未知返回 ¥ */
export function getCurrencySymbol(currency: string = BASE_CURRENCY): string {
  return CURRENCY_SYMBOLS[currency as CurrencyCode] ?? "¥";
}

/**
 * 分 → 元（后端金额字段的唯一单位约定是**整数分**，见各 services 的 `*_cents`）。
 *
 * 展示层一律经此换算，禁止各处散写 `/ 100`：`/ 100` 与「万元」「份额最小单位」
 * 混在一起读不出单位，也无法在漏乘时被 grep 出来。空值（null / undefined）按 0，
 * 与后端「分母非正返回 null」的口径配合由 `MoneyDisplay` 的 `emptyText` 展示。
 */
export function centsToYuan(cents: number | null | undefined): number {
  return (cents ?? 0) / 100;
}

/**
 * 格式化金额（千分位 + 可控小数位），不附带涨跌着色（着色请用 MoneyDisplay）。
 * 用于图表 label / tooltip 等非 DOM 字符串场景。
 * @param value 数值
 * @param precision 小数位，默认 2
 */
export function formatAmount(value: number, precision = 2): string {
  if (!Number.isFinite(value)) return (0).toFixed(precision);
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision
  });
}

/**
 * 金额收口到「分」（CNY 基准币种精度），消除浮点乘加漂移。
 * 与 utils/valuationEngine.ts 汇总层口径一致（Math.round(x*100)/100）。
 * 用于**计算层**（非展示层）；展示层仍走 MoneyDisplay。
 * 非有限值（NaN/Infinity）按 0 处理，避免污染求和。
 */
export function roundToCents(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.round(value * 100) / 100;
}
