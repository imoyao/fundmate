import { CHANNEL_CATEGORY_SHORT, LEDGER_TYPE_SHORT } from "@/constants";

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
    // ledger_type（内部资产类键，仅兜底用）
    bank: "var(--asset-cat-saving)",
    stock: "var(--asset-cat-stock)",
    fund: "var(--asset-cat-fund)",
    property: "var(--asset-cat-property)",
    // channel_category（用户可见渠道类别，展示优先走这套）
    securities: "var(--asset-cat-stock)",
    fund_platform: "var(--asset-cat-fund)",
    insurance: "var(--asset-cat-property)",
    futures: "var(--asset-cat-stock)",
    other: "var(--color-neutral)"
  };
  return map[type] || "var(--color-neutral)";
}

/**
 * 账户徽标的取值（字 + 色）——**渠道类别优先，ledger_type 兜底**。
 *
 * 为何要有这个函数：后端模型注释与设计文档 §2.3 的硬性约定是「账户列表分组、类型标签、
 * 排序、筛选一律只读 channel_category，绝不读 ledger_type 当展示」。此前三处调用方
 * （账户卡 / 买入账户下拉 / 卖出账户下拉）都传的是 `ledger_type`，踩了两个坑：
 *
 * 1. **显示错**：微众银行被 E账户导入建成 `ledger_type='fund'`，于是「银行」分组里的账户
 *    挂着「基」徽标；
 * 2. **改不了**：`ledger_type` 是内部计算口径键、编辑时不可变（409），用户把渠道类别改成
 *    银行也无济于事——徽标依然读旧字段。
 *
 * 抽成纯函数是为了让「优先级」本身可测：组件里只做 CSS，判断逻辑留在这里。
 */
export function resolveLedgerBadge(input: {
  channelCategory?: string | null;
  type?: string | null;
  label?: string | null;
}): { label: string; color: string } {
  const { channelCategory, type, label } = input;
  if (label) {
    return { label, color: getLedgerColor(channelCategory || type || "") };
  }
  if (channelCategory) {
    return {
      label: CHANNEL_CATEGORY_SHORT[channelCategory] || channelCategory,
      color: getLedgerColor(channelCategory)
    };
  }
  const t = type || "";
  return { label: LEDGER_TYPE_SHORT[t] || t, color: getLedgerColor(t) };
}
