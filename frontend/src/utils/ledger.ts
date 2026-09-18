/**
 * 账户颜色工具
 * 全局统一，严禁在组件内硬编码色值。
 *
 * ⚠️ 已知问题（#1602，待卡 2/3 处理）：本表映射与 `--asset-*` 资产类别色板不一致 ——
 * `stock` 在这里是 `--color-danger`（玫瑰红 #c83e66），而探市页 / 桑基图用的是
 * `--asset-stock`（蓝灰 #7a9aa8）；`fund` 这里是 `--color-warning`，与 `--asset-bond`
 * 同值。属「同一概念多套色板」技术债，本 PR 不改行为，仅登记。
 */
export function getLedgerColor(type: string): string {
  const map: Record<string, string> = {
    bank: "var(--tag-mint-green)",
    stock: "var(--color-danger)",
    fund: "var(--color-warning)",
    property: "var(--color-accent)"
  };
  return map[type] || "var(--color-neutral)";
}
