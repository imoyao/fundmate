/**
 * 账户颜色工具
 * 全局统一，严禁在组件内硬编码色值。
 */
export function getLedgerColor(type: string): string {
  const map: Record<string, string> = {
    bank: "var(--tag-mint-green)",
    stock: "var(--color-danger)",
    fund: "var(--color-warning)",
    property: "var(--color-accent)",
  };
  return map[type] || "var(--color-neutral)";
}

/** 传入颜色 CSS 变量，返回带透明度的背景色变量 */
export function bgFromColor(cssVar: string): string {
  // --tag-mint-green → --tag-mint-green-20 （或者直接拼接 -20）
  return cssVar.replace(")", "-20)");
}
