// src/constants/exchangeRates.ts
/**
 * 汇率单一来源（Single Source of Truth）。
 *
 * 生产环境的实时汇率由后端 enrich 计算并以 CNY 形式下发
 * （如 distributions.total_assets_cny / positions_total_mv），前端一般无需自行换算。
 * 本文件仅作为「前端需要按币种展示/换算时的唯一参考」，避免各页内联魔法数字。
 * 如接入实时汇率，替换 EXCHANGE_RATES 即可，调用方无需改动。
 */

/** 支持的币种 */
export type CurrencyCode = "CNY" | "USD" | "HKD" | "JPY";

/** 基准币种 */
export const BASE_CURRENCY: CurrencyCode = "CNY";

/**
 * 参考汇率：1 单位外币 = 多少 CNY（静态参考值，非实时）。
 * 仅用于前端展示兜底，真实金额以后端 CNY 为准。
 */
export const EXCHANGE_RATES: Record<CurrencyCode, number> = {
  CNY: 1,
  USD: 7.2,
  HKD: 0.92,
  JPY: 0.048
};

/** 币种展示符号 */
export const CURRENCY_SYMBOLS: Record<CurrencyCode, string> = {
  CNY: "¥",
  USD: "$",
  HKD: "HK$",
  JPY: "¥"
};
