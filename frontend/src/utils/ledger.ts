/**
 * 账户类型 → 品种色（#1602）
 *
 * 唯一真相源是 colors.css 的 `--asset-cat-*`（资产品种色）。本表只做「账户类型 → 品种」的语义翻译。
 *
 * 历史债（已清）：曾借语义色表达品种 —— `stock` 用 `--color-danger`（玫瑰红）、
 * `fund` 用 `--color-warning`（与当时的「债券」色同值）、`property` 用 `--color-accent`，
 * 导致「同一个股票」在自选列表 / 买卖表单是玫瑰红、在桑基图是蓝灰（#1602）。
 */
export function getLedgerColor(type: string): string {
  const map: Record<string, string> = {
    bank: "var(--asset-cat-saving)",
    stock: "var(--asset-cat-stock)",
    fund: "var(--asset-cat-fund)",
    property: "var(--asset-cat-property)"
  };
  return map[type] || "var(--color-neutral)";
}
