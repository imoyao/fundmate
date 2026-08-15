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
