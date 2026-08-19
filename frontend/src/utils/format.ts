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
