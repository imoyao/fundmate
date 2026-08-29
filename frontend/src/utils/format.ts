// src/utils/format.ts
/**
 * 份额/数量格式化：保留 2 位 + 千分位。
 * design.md「份额/数量保留 2 位」；与金额格式化（utils/currency.ts formatAmount）区分，
 * 份额不是货币，不参与币种/涨跌语义。
 */
export function formatQuantity(qty: number): string {
  return (qty || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

/**
 * 百分比格式化：输入小数（如 0.0852），输出百分比字符串（如 "8.52%"）。
 * 用于持仓占比等场景。
 */
export function formatPercent(ratio: number): string {
  const pct = (ratio || 0) * 100;
  return `${pct.toFixed(2)}%`;
}
