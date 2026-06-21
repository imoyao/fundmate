/**
 * 交易规则工具
 * 包含最小交易单位、碎股判断、快捷比例常量等。
 */

/**
 * 计算最小交易单位（一手股数）
 * 纯函数，便于买入/卖出复用
 */
export function getStep(params: {
  type: string;
  market: string;
  symbol: string;
}): number {
  // 场外基金永远按 1 份交易
  if (params.type === "fund") return 1;

  const { market, type, symbol } = params;
  if (market === "US" || market === "CRYPTO") return 1;
  if (market === "CN_HK") return 100;
  if (type === "bond") return 10; // 可转债 10 张

  if (type === "stock" || type === "etf") {
    if (symbol.startsWith("688")) return 200; // 科创板
    if (symbol.startsWith("8")) return 100;   // 北交所
    return 100; // 主板、创业板
  }
  return 1;
}

/** 是否支持 1 股递增 */
export function supportsOneShare(params: {
  type: string;
  market: string;
  symbol: string;
}): boolean {
  if (params.type === "fund") return true;
  if (params.market === "US" || params.market === "CRYPTO") return true;
  if (params.market === "CN_HK") return false;
  if (params.type === "bond") return false;
  const { symbol } = params;
  return symbol.startsWith("688") || symbol.startsWith("8");
}

/** 小数精度 */
export function getPrecision(type: string): number {
  return type === "fund" ? 4 : 0;
}

/** 卖出快捷比例（公用的常量） */
export const SELL_QUICK_RATIOS = [
  { label: "全部", value: 1 },
  { label: "1/4", value: 1 / 4 },
  { label: "1/3", value: 1 / 3 },
  { label: "1/2", value: 1 / 2 },
  { label: "3/4", value: 3 / 4 },
];

/** 基金默认申购费率 */
export const DEFAULT_SUB_RATE = 0.015;
