// frontend/src/utils/trading.ts

/**
 * 计算最小交易单位（一手股数/张数）
 * 用于前端 UI 的步长控制和最小起购限制
 */
export function getStep(params: {
  type: string;
  market: string;
  symbol: string;
}): number {
  if (params.type === "fund") return 1;

  const { market, type, symbol } = params;
  if (market === "US" || market === "CRYPTO") return 1;
  if (market === "CN_HK") return 100;
  if (type === "bond") return 10;

  if (type === "stock" || type === "etf") {
    if (symbol.startsWith("688")) return 200;
    if (symbol.startsWith("8")) return 100;
    return 100;
  }
  return 1;
}

/** 是否支持 1 股递增（用于碎股卖出场景） */
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

/** 小数精度（用于 UI 输入框的控制） */
export function getPrecision(type: string): number {
  return type === "fund" ? 4 : 0;
}

/** 卖出快捷比例（公用的常量） */
export const SELL_QUICK_RATIOS = [
  { label: "全部", value: 1 },
  { label: "1/4", value: 1 / 4 },
  { label: "1/3", value: 1 / 3 },
  { label: "1/2", value: 1 / 2 },
  { label: "3/4", value: 3 / 4 }
];

/** 基金默认申购费率 */
export const DEFAULT_SUB_RATE = 0.015;
