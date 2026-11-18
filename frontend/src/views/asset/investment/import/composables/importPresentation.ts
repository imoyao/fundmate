/**
 * 导入向导展示/格式化 helper（#2876 增量 2）。
 * 从 useImportWizard.ts 逐字搬运的纯常量与纯函数：不依赖 Vue、不读写 ref / computed /
 * reactive、不发 API、不碰写命令与资金正确性逻辑；口径与旧实现逐字一致，本次只搬家不修行为，
 * 组件与既有 spec 经 useImportWizard 返回值继续消费同名绑定，零感知。
 */

import type { LedgerItem } from "@/api/ledger";
import { isMissingAmount } from "./cellEditLogic";
import { isFeeExplained, isRowBlocked } from "./previewPredicates";

export const fundTypeColorMap: Record<string, string> = {
  股票型: "var(--asset-cat-stock)",
  混合型: "var(--asset-cat-fund)",
  债券型: "var(--asset-cat-bond)",
  货币型: "var(--asset-cat-money-fund)",
  指数型: "var(--asset-cat-etf)",
  QDII: "var(--asset-cat-fund)",
  FOF: "var(--asset-cat-portfolio)"
};

// 类型中文标签统一走后端唯一来源 frontend/src/constants/assetType（getTypeLabel），不再在此私藏副本（#1171 枚举一致性）。

// 品种 → 颜色：真相源是 `--asset-cat-*`（#1602）。此处曾用 `--palette-*` 装饰色表达品种
// （stock 用 muted-blue、fund 用 rose-taupe……），与 getLedgerColor 的 `--asset-cat-*` 并存，
// 导致「同一个股票」在导入向导是蓝灰、在自选 / 买卖表单是紫 —— 这正是 colors.css 里
// 「业务代码禁止再借用 --palette-* 装饰色表达品种」要拦的情形，本处属 #1604 漏改。
// cash / static 在 12 槽位里无同名槽位：现金取货币基金（同属现金管理工具）、static 回退中性色。
export const typeColorMap: Record<string, string> = {
  stock: "var(--asset-cat-stock)",
  fund: "var(--asset-cat-fund)",
  bond: "var(--asset-cat-bond)",
  etf: "var(--asset-cat-etf)",
  crypto: "var(--asset-cat-crypto)",
  saving: "var(--asset-cat-saving)",
  cash: "var(--asset-cat-money-fund)",
  static: "var(--color-neutral)"
};

export const ledgerTypeMap: Record<string, string> = {
  stock: "股票账户",
  fund: "基金账户",
  cash: "现金账户",
  general: "综合账户",
  family: "家庭账户"
};

export function getTemplateKeyForLedger(ledger: LedgerItem | null): string {
  if (!ledger) return "";
  switch (ledger.ledger_type) {
    case "stock":
      return "standard_stock";
    case "fund":
    case "cash":
      return "standard_fund";
    default:
      return "";
  }
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(2) + " MB";
}

export function getFundTypeColor(typeName: string): string {
  return fundTypeColorMap[typeName] || "var(--palette-stone-gray)";
}

export function getTypeColor(type: string): string {
  return typeColorMap[type] || "var(--palette-stone-gray)";
}

export function addRowKeys<T extends object>(data: T[]) {
  return data.map((item, idx) => ({ ...item, _rowKey: `row_${idx}` }));
}

export function getRowClassName({ row }: { row: unknown }) {
  // el-table 的 DefaultRow 与本仓 PreviewRow 无交集，只在这个边界断言一次。
  const r = row as import("./previewRow").PreviewRow;
  if (r.is_duplicate) return "row-duplicate";
  if (r.error || isRowBlocked(r)) return "row-blocked";
  return "";
}

export function getCellClassName({
  row,
  column
}: {
  row: unknown;
  column: { property?: string };
}) {
  const r = row as import("./previewRow").PreviewRow;
  const prop = column.property;
  if (prop === "quantity" && isRowBlocked(r) && !r.is_duplicate && !r.error)
    return "cell-blocked";
  if (prop === "price" && isRowBlocked(r) && !r.is_duplicate && !r.error)
    return "cell-blocked";
  // cell-missing 随手续费列退场改挂金额列（#1790 列收敛，理由见 #1790 取舍说明）
  if (prop === "amount" && isMissingAmount(r)) return "cell-missing";
  // 差额被手续费解释：金额列给淡黄底提示。列收敛（#1790）下不新增手续费列，
  // 解释线索改由金额列底色 + 该格 tooltip 承载（见 PreviewTable 的 amount slot）。
  if (prop === "amount" && isFeeExplained(r)) return "cell-fee";
  return "";
}

export function getCategoryDesc(key: string): string {
  const map: Record<string, string> = {
    error: "解析错误，无法在面板内修正",
    missingCode: "系统无法识别以下证券代码",
    missingQtyPrice: "数量或价格缺失",
    mismatch: "金额与数量×价格不符，且差额超过手续费"
  };
  return map[key] || "";
}

/**
 * 分区条数 tag 的颜色档：按**问题性质**定档，不比条数。
 *
 * 旧实现按条数分档（>200 danger / >50 warning / >10 info / 其余 success），于是
 * 「代码未匹配 5 条」被染成 success 绿——把「有问题、需处理」显示成「通过」。
 * 条数只说明规模，不说明性质；5 条匹配失败和 500 条一样不可导入。
 *
 * 现口径与状态列三态同源：阻断（不可导入）= danger，可导入但需留意 = warning。
 */
export function getCategoryTagType(
  key: string
): "danger" | "warning" | "success" | "info" {
  if (key === "error" || key === "missingQtyPrice") return "danger";
  if (key === "missingCode" || key === "mismatch") return "warning";
  return "info";
}
